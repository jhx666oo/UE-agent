"""AI 回传链路的领域服务（WorkBuddy 驱动架构）。

背景见 docs/superpowers/specs/2026-09-10-policy-ai-crawl-design.md 第 8 节：
AI 检索与字段抽取由 WorkBuddy 执行，本模块负责服务端的确定性部分 ——
派活清单、抓取落档、回传校验、候选来源入池。

设计原则：
- 不信任回传数据。所有候选值必须通过 7 项校验才可能进入建议值。
- 校验失败不回滚整批：单条拒绝并记录原因，其余照常接收（回传是增量、易重试的）。
- 空引用的抽取值一律拒绝：这是防幻觉最有效的一道闸。
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from ...repository import ProjectRepository, new_id, utc_now

# 数值字段的合理区间（PRD 参数语义约束）。超出即标警告，仍接收，交由人工判断。
NUMERIC_BOUNDS: dict[str, tuple[float, float]] = {
    "C3": (1.0, 5000.0),  # 常住总人口（万人）
    "C4": (0.0, 100.0),  # 60 岁以上人口占比（%）
    "C5": (0.0, 100.0),  # 80 岁以上人口占比（%）
    "C6": (0.0, 100.0),  # 失能率 60-69（%）
    "C7": (0.0, 100.0),  # 失能率 70-79（%）
    "C8": (0.0, 100.0),  # 失能率 80+（%）
    "C10": (1.0, 5000.0),  # 职工医保参保人数（万人）
    "C11": (-1000.0, 10000.0),  # 医保基金净结余（亿元，允许为负）
    "C13": (10.0, 200000.0),  # 区域总面积（km²）
    "P1": (1.0, 1000.0),  # 单小时服务单价（元/小时）
    "P2": (0.0, 1.0),  # 基金支付比例（存储为 0-1）
    "P4": (0.0, 10000.0),  # 最低护理员纳保数（人）
    "P5": (0.0, 10000.0),  # 最低护士配置数（人）
    "P6": (0.0, 120.0),  # 失能状态持续时长要求（月）
    "P7": (0.0, 100.0),  # 评估通过率门槛（%）
    "P8": (0.1, 24.0),  # 单次服务时长（小时）
    "P9": (0.0, 100.0),  # 每月必选服务项数（项）
}

# 字段族 -> 检索关键词模板。供派活接口下发给 WorkBuddy 作为检索提示。
FIELD_FAMILIES: tuple[tuple[str, str, tuple[str, ...], str], ...] = (
    (
        "政策准入",
        "{城市} 长期护理保险 实施办法 待遇标准",
        ("P1", "P2", "P4", "P5", "P6", "P7", "P8", "P9", "P10", "P11"),
        "医保局政策文件",
    ),
    (
        "城市人口",
        "{城市} 统计年鉴 常住人口 老龄化率 site:gov.cn",
        ("C3", "C4", "C5", "C10", "C11"),
        "统计局/人社局统计公报",
    ),
    (
        "空间面积",
        "{城市} 行政区域面积 官方",
        ("C13",),
        "政府门户网站",
    ),
)

# 抽取难度分档：告知 WorkBuddy 每档的预期与禁忌。
DIFFICULTY_LEVELS: dict[str, str] = {
    "A": "政策文本可直接读到数值，准确率最高",
    "B": "政策有表述但需归一化到枚举值",
    "C": "属统计公报数据，通常不在医保局政策页，需换源检索",
    "D": "官方无公开数据，抽取时必须返回 null，禁止估算",
}

# D 档：官方无按年龄段公布的失能率，严禁 AI 编造。
# 注意 C2（城市行政等级）不在此列 —— 它属 B 档，应由 AI 按城市名录归一化到枚举值。
NEVER_ESTIMATE_FIELDS: frozenset[str] = frozenset({"C6", "C7", "C8"})

_FIELD_DIFFICULTY: dict[str, str] = {
    "P1": "A", "P2": "A", "P4": "A", "P5": "A", "P6": "A",
    "P7": "A", "P8": "A", "P9": "A", "P10": "A", "P11": "A",
    "C2": "B",
    "C3": "C", "C4": "C", "C5": "C", "C10": "C", "C11": "C", "C13": "C",
    "C6": "D", "C7": "D", "C8": "D",
}


class SubmissionError(Exception):
    """回传/入池失败；code 对应稳定 API 错误码。"""

    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def serialize_catalog_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """下发给 WorkBuddy 的字段定义（只含抽取所需信息）。"""
    field_id = str(entry.get("id"))
    return {
        "id": field_id,
        "name": entry.get("name"),
        "unit": entry.get("unit"),
        "valueType": entry.get("valueType"),
        "options": entry.get("options"),
        "block": entry.get("block"),
        "difficulty": _FIELD_DIFFICULTY.get(field_id, "A"),
        "neverEstimate": field_id in NEVER_ESTIMATE_FIELDS,
    }


class AgentSubmissionService:
    """服务端确定性逻辑：不调用任何模型，只做校验、落库与写回。"""

    def __init__(self, repository: ProjectRepository):
        self.repository = repository

    # ---------- 派活 ----------

    def build_field_catalog(self, catalog: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
        """只下发自动爬虫字段 —— WorkBuddy 无权写内部填写或公式自动字段。"""
        return [
            serialize_catalog_entry(entry)
            for entry in catalog.values()
            if entry.get("sourceType") == "自动爬虫"
        ]

    def crawl_targets(self, catalog: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        """给 WorkBuddy 的待办清单：每个城市有哪些来源、上次是否变更、缺哪些字段。"""
        sources = self.repository.list_data_sources()
        projects = self.repository.list_projects()
        auto_fields = [
            str(entry["id"])
            for entry in catalog.values()
            if entry.get("sourceType") == "自动爬虫"
        ]
        city_names: dict[str, str] = {}
        for project in projects:
            city_id = str(project.get("cityId") or project.get("city") or "")
            if city_id:
                city_names.setdefault(city_id, str(project.get("city") or city_id))

        by_city: dict[str, list[dict[str, Any]]] = {}
        for source in sources:
            city_id = str(source.get("cityId") or "")
            if not city_id:
                continue
            last_artifact = self._latest_success_artifact(str(source.get("id")))
            filled = self._filled_fields_for_city(city_id)
            by_city.setdefault(city_id, []).append(
                {
                    "sourceId": source.get("id"),
                    "name": source.get("name"),
                    "url": source.get("url"),
                    "status": source.get("status"),
                    "lastFetchedAt": source.get("lastFetchedAt"),
                    "lastChangeStatus": source.get("lastChangeStatus"),
                    "lastArtifactId": last_artifact.get("artifactId") if last_artifact else None,
                    "lastArtifactSha256": last_artifact.get("sha256") if last_artifact else None,
                    # 增量感知：该来源上次抓取时尚未填写的字段。
                    "fieldsToFill": [fid for fid in auto_fields if fid not in filled],
                    # alreadyFilled 让 WorkBuddy 知道哪些字段已有值，避免重复抽。
                    "alreadyFilled": sorted(filled & set(auto_fields)),
                }
            )

        return {
            "generatedAt": utc_now(),
            "readScope": "configured_sources_plus_ai_discovery",
            "fieldCatalog": self.build_field_catalog(catalog),
            "fieldFamilies": [
                {"family": name, "queryTemplate": template, "fields": list(fields), "sourceHint": hint}
                for name, template, fields, hint in FIELD_FAMILIES
            ],
            "difficultyLevels": DIFFICULTY_LEVELS,
            "neverEstimateFields": sorted(NEVER_ESTIMATE_FIELDS),
            "cities": [
                {
                    "cityId": city_id,
                    "cityName": city_names.get(city_id, city_id),
                    "sources": items,
                }
                for city_id, items in sorted(by_city.items())
            ],
        }

    def _latest_success_artifact(self, source_id: str) -> dict[str, Any] | None:
        artifacts = self.repository.list_crawl_artifacts(source_id=source_id)
        for artifact in reversed(artifacts):
            if artifact.get("status") == "success":
                return artifact
        return None

    def _filled_fields_for_city(self, city_id: str) -> set[str]:
        """城市中「已有可信来源」的自动爬虫字段集合。

        注意不能简单地用 `inputs` 是否非空来判断：场景创建时会被 U1 基准输入
        （fixtures/u1-baseline.json）整表填充，所有字段天生就"有值"，
        那样 `fieldsToFill` 永远为空，增量感知形同虚设。

        真正的判据是 `scenario_field_values` 的行状态：
        - `accepted`：已采用过爬虫建议值 → 该字段已有来源，暂不必重抽；
        - `overridden`：人工覆盖过 → 人工判断优先，不应被爬虫反复打扰。
        `empty` / `suggestion_ready` 表示尚无可信来源，应继续纳入待填清单。
        """
        filled: set[str] = set()
        for project in self.repository.list_projects():
            if str(project.get("cityId") or project.get("city")) != city_id:
                continue
            for scenario in project.get("scenarios") or []:
                scenario_id = str(scenario["id"])
                for row in self.repository.list_field_values(scenario_id):
                    if row.get("valueState") in {"accepted", "overridden"}:
                        filled.add(str(row.get("fieldId")))
        return filled

    # ---------- 回传校验 ----------

    def submit_extraction(
        self,
        *,
        city_id: str,
        catalog: Mapping[str, Mapping[str, Any]],
        submissions: Sequence[Mapping[str, Any]],
        agent_run_id: str | None = None,
        agent_version: str | None = None,
    ) -> dict[str, Any]:
        """接收 WorkBuddy 的抽取结果，逐条校验后写入灰色建议值。"""
        if not city_id.strip():
            raise SubmissionError("INVALID_INPUT", "cityId 不能为空", 400)
        if not submissions:
            raise SubmissionError("INVALID_INPUT", "submissions 不能为空", 400)

        accepted: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        conflicts: list[dict[str, Any]] = []
        scenario_ids = self._scenarios_for_city(city_id)
        # 同一批次内同一字段可能被回传多次（例如模型给出多个候选）。
        # 必须去重后再写库，否则后一条会静默覆盖前一条 —— 曾因此让未换算的
        # P2=80 覆盖掉正确的 P2=0.8。择优规则：先比是否落在合理区间，
        # 再比置信度，最后比引用长度（引用更长通常证据更充分）。
        best: dict[str, dict[str, Any]] = {}

        for submission in submissions:
            source_id = str(submission.get("sourceId") or "")
            artifact_id = submission.get("artifactId")
            source_meta = self._suggestion_source(source_id, artifact_id)
            for fact in submission.get("facts") or []:
                outcome = self._validate_fact(fact, catalog)
                if not outcome["ok"]:
                    rejected.append(
                        {
                            "fieldId": fact.get("fieldId"),
                            "reason": outcome["reason"],
                            "quote": fact.get("quote"),
                        }
                    )
                    continue
                field_id = outcome["fieldId"]
                previous = best.get(field_id)
                if previous is None:
                    best[field_id] = {**outcome, "_sourceMeta": source_meta}
                    continue
                winner, loser = _pick_better(previous, outcome)
                if winner is previous:
                    conflicts.append(
                        {
                            "fieldId": field_id,
                            "kept": previous["value"],
                            "dropped": outcome["value"],
                            "reason": "同批次重复回传，保留质量更高的一条",
                        }
                    )
                else:
                    best[field_id] = {**outcome, "_sourceMeta": source_meta}
                    conflicts.append(
                        {
                            "fieldId": field_id,
                            "kept": outcome["value"],
                            "dropped": previous["value"],
                            "reason": "同批次重复回传，保留质量更高的一条",
                        }
                    )

        for field_id, outcome in best.items():
            source_meta = outcome.pop("_sourceMeta", {})
            if outcome.get("warning"):
                warnings.append({"fieldId": field_id, "warning": outcome["warning"]})
            for scenario_id in scenario_ids:
                self.repository.save_field_suggestion(
                    scenario_id,
                    field_id,
                    outcome["value"],
                    {**source_meta, **self._source_extras(outcome)},
                )
            accepted.append(
                {
                    "fieldId": field_id,
                    "value": outcome["value"],
                    "unit": outcome.get("unit"),
                    "confidence": outcome.get("confidence"),
                    "quote": outcome.get("quote"),
                    "effectiveDate": outcome.get("effectiveDate"),
                }
            )

        # 未披露字段单独记录：这是合规信号，不是失败。
        not_disclosed: list[str] = []
        for submission in submissions:
            for field_id in submission.get("notDisclosed") or []:
                if field_id in catalog and catalog[field_id].get("sourceType") == "自动爬虫":
                    not_disclosed.append(str(field_id))

        result_status = (
            "rejected" if not accepted and rejected
            else "partially_rejected" if rejected
            else "accepted"
        )
        record = self.repository.create_extraction_submission(
            {
                "cityId": city_id,
                "sourceId": submissions[0].get("sourceId"),
                "artifactId": submissions[0].get("artifactId"),
                "agentRunId": agent_run_id,
                "agentVersion": agent_version,
                "payload": {
                    "submissions": [dict(item) for item in submissions],
                    "accepted": accepted,
                    "notDisclosed": sorted(set(not_disclosed)),
                },
                "resultStatus": result_status,
                "acceptedCount": len(accepted),
                "rejectedCount": len(rejected),
                "rejections": rejected,
            }
        )
        return {
            "submissionId": record["id"],
            "cityId": city_id,
            "resultStatus": result_status,
            "acceptedCount": len(accepted),
            "rejectedCount": len(rejected),
            "accepted": accepted,
            "rejected": rejected,
            "warnings": warnings,
            "conflicts": conflicts,
            "notDisclosed": sorted(set(not_disclosed)),
            "affectedScenarioCount": len(scenario_ids),
        }

    def _validate_fact(
        self, fact: Mapping[str, Any], catalog: Mapping[str, Mapping[str, Any]]
    ) -> dict[str, Any]:
        """7 项校验。任何一项不通过即拒绝该条。"""
        field_id = str(fact.get("fieldId") or "").strip()
        if not field_id:
            return {"ok": False, "reason": "字段编号为空"}
        entry = catalog.get(field_id)
        if entry is None:
            return {"ok": False, "reason": f"字段 {field_id} 不在参数字典中"}
        if entry.get("sourceType") != "自动爬虫":
            return {
                "ok": False,
                "reason": f"字段 {field_id} 的数据源类型为 {entry.get('sourceType')}，AI 不可写入",
            }

        raw_value = fact.get("value")
        if raw_value is None:
            return {"ok": False, "reason": f"字段 {field_id} 的 value 为空"}

        # 校验 2：valueType 匹配
        value_type = entry.get("valueType")
        if value_type == "number":
            if isinstance(raw_value, bool) or not isinstance(raw_value, (int, float)):
                return {"ok": False, "reason": f"字段 {field_id} 要求数值，收到 {type(raw_value).__name__}"}
            value: Any = float(raw_value)
            if value.is_integer():
                value = int(value)
        else:
            if not isinstance(raw_value, str):
                return {"ok": False, "reason": f"字段 {field_id} 要求文本，收到 {type(raw_value).__name__}"}
            value = raw_value.strip()
            if not value:
                return {"ok": False, "reason": f"字段 {field_id} 的文本值为空"}

        # 校验 3：有 options 的字段必须在枚举内
        options = entry.get("options")
        if options:
            if str(value) not in {str(option) for option in options}:
                return {
                    "ok": False,
                    "reason": f"字段 {field_id} 的值 {value!r} 不在允许选项 {options} 内",
                }

        # 校验 4：confidence ∈ [0, 1]
        confidence = fact.get("confidence")
        if confidence is not None:
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
                return {"ok": False, "reason": f"字段 {field_id} 的 confidence 不是数值"}
            if not 0 <= float(confidence) <= 1:
                return {"ok": False, "reason": f"字段 {field_id} 的 confidence 超出 0-1 区间"}

        # 校验 5：quote 非空 —— 防幻觉核心闸门
        quote = fact.get("quote")
        if not isinstance(quote, str) or not quote.strip():
            return {"ok": False, "reason": f"字段 {field_id} 缺少原文引用（quote），不予采信"}

        # 校验 6：D 档字段禁止估算
        if field_id in NEVER_ESTIMATE_FIELDS:
            return {
                "ok": False,
                "reason": f"字段 {field_id} 属官方无公开数据字段，禁止估算（应在 notDisclosed 中声明）",
            }

        # 校验 7：数值合理区间，超界标警告但仍接收
        warning: str | None = None
        if value_type == "number":
            bounds = NUMERIC_BOUNDS.get(field_id)
            if bounds is not None:
                low, high = bounds
                if not (low <= float(value) <= high):
                    warning = f"数值 {value} 超出预期区间 [{low}, {high}]，请人工核对"

        return {
            "ok": True,
            "fieldId": field_id,
            "value": value,
            "unit": fact.get("unit") or entry.get("unit"),
            "confidence": confidence,
            "quote": quote.strip()[:500],
            "effectiveDate": fact.get("effectiveDate"),
            "warning": warning,
        }

    def _scenarios_for_city(self, city_id: str) -> list[str]:
        scenario_ids: list[str] = []
        for project in self.repository.list_projects():
            if str(project.get("cityId") or project.get("city")) != city_id:
                continue
            for scenario in project.get("scenarios") or []:
                scenario_ids.append(str(scenario["id"]))
        return scenario_ids

    def _suggestion_source(self, source_id: str, artifact_id: str | None) -> dict[str, Any]:
        name = source_id
        url: str | None = None
        try:
            sources = self.repository.list_data_sources()
        except Exception:  # noqa: BLE001 - 来源缺失不应中断回传
            sources = []
        for source in sources:
            if str(source.get("id")) == source_id:
                name = str(source.get("name") or source_id)
                url = source.get("url")
                break
        return {
            "sourceId": source_id or None,
            "sourceName": name,
            "url": url,
            "artifactId": artifact_id,
            "documentId": None,
            "origin": "workbuddy_ai_extraction",
        }

    @staticmethod
    def _source_extras(outcome: Mapping[str, Any]) -> dict[str, Any]:
        """把 confidence / quote 带进建议来源，供城市公式页展示可信度与原文。"""
        extras: dict[str, Any] = {"quote": outcome.get("quote")}
        if outcome.get("confidence") is not None:
            extras["confidence"] = outcome.get("confidence")
        if outcome.get("effectiveDate"):
            extras["effectiveDate"] = outcome.get("effectiveDate")
        return extras

    # ---------- 候选来源入池 ----------

    def submit_candidate_sources(
        self, *, city_id: str, candidates: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        if not city_id.strip():
            raise SubmissionError("INVALID_INPUT", "cityId 不能为空", 400)
        if not candidates:
            raise SubmissionError("INVALID_INPUT", "candidates 不能为空", 400)
        created: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []
        for candidate in candidates:
            url = str(candidate.get("url") or "").strip()
            if not url:
                skipped.append({"url": None, "reason": "缺少 url"})
                continue
            if not url.startswith(("http://", "https://")):
                skipped.append({"url": url, "reason": "仅接受 http/https 链接"})
                continue
            record = self.repository.create_candidate_source(
                {
                    "cityId": city_id,
                    "url": url,
                    "name": candidate.get("name") or candidate.get("title") or url,
                    "domain": candidate.get("domain") or _domain_of(url),
                    "title": candidate.get("title"),
                    "publishedAt": candidate.get("publishedAt"),
                    "summary": candidate.get("summary"),
                    "targetFields": list(candidate.get("targetFields") or []),
                    "relevance": candidate.get("relevance"),
                    "origin": candidate.get("origin") or "ai_search",
                }
            )
            created.append(record)
        return {
            "createdCount": len(created),
            "skippedCount": len(skipped),
            "created": created,
            "skipped": skipped,
        }

    def promote_candidate_source(self, candidate_id: str) -> dict[str, Any]:
        """把候选来源转成正式 DataSource 并标记已入池。"""
        try:
            candidate = self.repository.get_candidate_source(candidate_id)
        except KeyError:
            raise SubmissionError("NOT_FOUND", f"候选来源不存在：{candidate_id}", 404) from None
        if candidate.get("status") == "promoted" and candidate.get("promotedSourceId"):
            return candidate
        source = self.repository.create_data_source(
            {
                "cityId": candidate["cityId"],
                "name": candidate.get("name") or candidate["url"],
                "kind": "web",
                "url": candidate["url"],
                "status": "active",
                "note": f"由 AI 检索候选来源转入（相关度 {candidate.get('relevance')}）",
            }
        )
        return self.repository.update_candidate_source(
            candidate_id,
            {
                "status": "promoted",
                "promotedSourceId": source["id"],
                "reviewedBy": "operator",
                "reviewedAt": utc_now(),
            },
        )

    def reject_candidate_source(self, candidate_id: str, reason: str | None = None) -> dict[str, Any]:
        try:
            self.repository.get_candidate_source(candidate_id)
        except KeyError:
            raise SubmissionError("NOT_FOUND", f"候选来源不存在：{candidate_id}", 404) from None
        return self.repository.update_candidate_source(
            candidate_id,
            {
                "status": "rejected",
                "reviewedBy": "operator",
                "reviewedAt": utc_now(),
                "note": reason,
            },
        )


def _domain_of(url: str) -> str | None:
    from urllib.parse import urlsplit

    try:
        hostname = urlsplit(url).hostname
    except ValueError:
        return None
    return hostname


def _pick_better(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """同批次内同字段重复回传时择优，返回 (保留, 丢弃)。

    排序依据（依次比较）：
    1. 是否落在合理区间 —— 未换算的 80 会被换算正确的 0.8 击败；
    2. 置信度更高者优先；
    3. 引用更长者优先（证据通常更充分）。
    """
    in_range_first = not first.get("warning")
    in_range_second = not second.get("warning")
    if in_range_first != in_range_second:
        return (first, second) if in_range_first else (second, first)
    confidence_first = float(first.get("confidence") or 0)
    confidence_second = float(second.get("confidence") or 0)
    if confidence_first != confidence_second:
        return (first, second) if confidence_first > confidence_second else (second, first)
    quote_first = len(str(first.get("quote") or ""))
    quote_second = len(str(second.get("quote") or ""))
    return (first, second) if quote_first >= quote_second else (second, first)


def new_submission_id() -> str:
    return new_id("submission")
