from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit

from ...crawlers.runner import CrawlError, crawl_source, extract_readable_text
from ...repository import LocalPolicyFileStore, ProjectRepository, new_id, utc_now


ALLOWED_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".pdf"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
FALLBACK_TASK_ACTIVE_STATUSES = {"queued", "in_progress"}


class CrawlServiceError(Exception):
    """一键抓取失败；code 对应稳定 API 错误码。"""

    def __init__(self, code: str, message: str, status_code: int, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = dict(details or {})


def crawl_error_details(error: CrawlError) -> dict[str, Any]:
    """把底层抓取错误转成 Agent 和前端都能理解的稳定字段。"""
    return {
        "httpStatus": error.http_status,
        "errorCode": error.error_code or "POLICY_SOURCE_FETCH_FAILED",
        "fallbackAction": error.fallback_action,
        "fallbackReason": error.fallback_reason,
    }


# PRD 11.10：可解析的政策字段 -> 关联的 Excel 参数编号。
#
# 这里只接受「字段标签 + 数值/明确结论」的正文，不根据上下文猜测。
# 百分比统一换算为 0-1 存储（PRD 10.5）；C6/C7/C8 刻意不配置规则，
# 因为官方通常不公开按年龄段拆分的失能率，不能让兜底脚本产生伪数据。
# pattern 的 value 组是命名组，quote 仍保留完整匹配文本供页面回溯。
SUGGESTION_PATTERNS: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    # (field_id, 参数名称, 匹配模式, 解析类型: number / percent / enum / boolean)
    (
        "C2",
        "城市行政等级",
        re.compile(r"(?:为|是|属于)\s*(?P<value>一线|新一线|二线|三线)\s*城市"),
        "enum",
    ),
    (
        "C3",
        "常住总人口",
        re.compile(r"常住(?:总)?人口[^0-9]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*万(?:人)?"),
        "number",
    ),
    (
        "C4",
        "60岁以上人口占比",
        re.compile(r"60\s*岁(?:以上|及以上)[^0-9]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*%"),
        "percent",
    ),
    (
        "C5",
        "80岁以上人口占比",
        re.compile(r"80\s*岁(?:以上|及以上)[^0-9]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*%"),
        "percent",
    ),
    (
        "C10",
        "职工医保参保人数",
        re.compile(r"职工医保(?:参保)?人数[^0-9]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*万(?:人)?"),
        "number",
    ),
    (
        "C11",
        "医保基金净结余",
        re.compile(r"医保基金(?:净)?结余[^0-9-]{0,16}(?P<value>-?[0-9]+(?:\.[0-9]+)?)\s*亿(?:元)?"),
        "number",
    ),
    (
        "C13",
        "区域总面积",
        re.compile(
            r"(?:区域|行政区域|全市|全区)?总面积[^0-9]{0,16}"
            r"(?P<value>[0-9]+(?:\.[0-9]+)?)\s*(?:平方公里|km²|km2)"
        ),
        "number",
    ),
    (
        "P1",
        "单小时服务单价",
        re.compile(r"(?:单小时|每小时)服务单价[^0-9]{0,16}(?P<value>[0-9]+(?:\.[0-9]+)?)"),
        "number",
    ),
    (
        "P2",
        "基金支付比例",
        re.compile(r"基金支付比例[^0-9]{0,12}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*%"),
        "percent",
    ),
    (
        "P4",
        "最低护理员纳保数",
        re.compile(r"最低护理员纳保数[^0-9]{0,12}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*人"),
        "number",
    ),
    (
        "P5",
        "最低护士配置数",
        re.compile(r"最低护士配置数[^0-9]{0,12}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*人"),
        "number",
    ),
    (
        "P6",
        "失能状态持续时长要求",
        re.compile(r"失能状态持续时长要求[^0-9]{0,12}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*个?月"),
        "number",
    ),
    (
        "P7",
        "评估通过率门槛",
        re.compile(r"评估通过率门槛[^0-9]{0,12}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*%"),
        "percent",
    ),
    (
        "P8",
        "单次服务时长",
        re.compile(r"单次服务(?:时长|服务时长)?[^0-9]{0,12}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*小时"),
        "number",
    ),
    (
        "P9",
        "每月必选服务项数",
        re.compile(r"每月必选服务项数[^0-9]{0,12}(?P<value>[0-9]+(?:\.[0-9]+)?)\s*项"),
        "number",
    ),
    (
        "P10",
        "辅具政策是否试点",
        re.compile(r"(?:不|未)[^。；，,]{0,12}辅具[^。；，,]{0,24}(?:试点|纳入|开展)|辅具[^。；，,]{0,24}(?:试点|纳入|开展)"),
        "boolean",
    ),
    (
        "P11",
        "亲情照护模式",
        re.compile(r"(?:不|未)[^。；，,]{0,12}亲情照护[^。；，,]{0,24}(?:支持|开展|允许|模式|服务)|亲情照护[^。；，,]{0,24}(?:支持|开展|允许|模式|服务)"),
        "boolean",
    ),
)


def parse_suggestions(text: str | None) -> list[dict[str, Any]]:
    """从抓取的可读文本中解析参数建议值（不自动写入城市参数）。"""
    if not text:
        return []
    suggestions: list[dict[str, Any]] = []
    for field_id, name, pattern, value_type in SUGGESTION_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        if value_type == "boolean":
            value = "否" if re.search(r"不|未|无", match.group(0)) else "是"
        elif value_type == "enum":
            value = match.group("value")
        else:
            numeric_value = float(match.group("value"))
            if numeric_value.is_integer():
                numeric_value = int(numeric_value)
            value = round(numeric_value / 100, 10) if value_type == "percent" else numeric_value
        suggestions.append({"fieldId": field_id, "name": name, "value": value, "quote": match.group(0).strip()})
    return suggestions


class PolicyService:
    """Local policy workflow; candidate values never become approved implicitly."""

    def __init__(self, repository: ProjectRepository):
        self.repository = repository
        # 生产保持 False：拒绝本机/私有地址。测试注入 True 以便用本地 HTTP 服务验证行为。
        self.crawl_allow_private = False

    def _source(self, source_id: str) -> dict[str, Any]:
        try:
            return next(
                source
                for source in self.repository.list_data_sources()
                if str(source.get("id")) == str(source_id)
            )
        except StopIteration:
            raise CrawlServiceError("NOT_FOUND", f"Data source not found: {source_id}", 404) from None

    @staticmethod
    def _fallback_task_prompt(
        source: Mapping[str, Any], requested_url: str, details: Mapping[str, Any]
    ) -> str:
        reason = str(details.get("fallbackReason") or "官网 HTTP 通道不可用")
        error_code = str(details.get("errorCode") or "POLICY_SOURCE_FETCH_FAILED")
        return (
            "请使用 WorkBuddy 浏览器处理 UE-Agent 政策兜底任务："
            f"城市={source.get('cityId') or '未知'}；来源={source.get('name') or source.get('id')}; "
            f"原链接={requested_url}；原因={reason}；错误码={error_code}。"
            "先打开原链接；若被拦截或跳转失败，再检索同一城市的官方发布页/官方 PDF。"
            "确认正文来自官方来源后，将可复核正文、最终 URL、标题回传 /api/policies/browser-artifacts；"
            "回传后再按字段目录提交抽取结果。禁止凭空补数字，找不到官方正文时回写失败原因。"
        )

    def _ensure_browser_fallback_task(
        self,
        source: Mapping[str, Any],
        *,
        requested_url: str,
        details: Mapping[str, Any],
        research_run_id: str | None = None,
    ) -> dict[str, Any]:
        source_id = str(source.get("id") or "")
        existing = self.repository.get_active_policy_fallback_task(
            source_id=source_id,
            requested_url=requested_url,
        )
        task_data = {
            "cityId": source.get("cityId"),
            "sourceId": source_id,
            "researchRunId": research_run_id,
            "requestedUrl": requested_url,
            "sourceName": source.get("name"),
            "status": "queued",
            "httpStatus": details.get("httpStatus"),
            "errorCode": details.get("errorCode"),
            "fallbackAction": details.get("fallbackAction") or "browser_search",
            "fallbackReason": details.get("fallbackReason"),
            "lastError": details.get("message"),
        }
        if existing is not None:
            return self.repository.update_policy_fallback_task(
                existing["id"],
                {
                    **task_data,
                    "status": existing.get("status") or "queued",
                    "attempts": existing.get("attempts") or 0,
                },
            )
        return self.repository.create_policy_fallback_task(task_data)

    def _pending_browser_fallback_task(
        self, source: Mapping[str, Any], requested_url: str
    ) -> dict[str, Any] | None:
        source_id = str(source.get("id") or "")
        active = self.repository.get_active_policy_fallback_task(
            source_id=source_id,
            requested_url=requested_url,
        )
        if active is not None:
            return active

        # 009 迁移前的失败记录没有任务表。第一次重试时从兼容元数据补建任务，
        # 同时确保 URL 被改过后不会把旧链接的失败状态误套到新链接上。
        artifacts = self.repository.list_crawl_artifacts(source_id=source_id)
        latest_failed = next(reversed(artifacts), None) if artifacts else None
        if not (
            latest_failed
            and latest_failed.get("status") == "failed"
            and latest_failed.get("requestedUrl") == requested_url
            and latest_failed.get("fallbackAction") == "browser_search"
        ):
            latest_failed = None
        if latest_failed is None:
            return None
        details = {
            "httpStatus": latest_failed.get("httpStatus"),
            "errorCode": latest_failed.get("errorCode"),
            "fallbackAction": latest_failed.get("fallbackAction"),
            "fallbackReason": latest_failed.get("fallbackReason"),
            "message": latest_failed.get("errorMessage"),
        }
        return self._ensure_browser_fallback_task(
            source,
            requested_url=requested_url,
            details=details,
        )

    @staticmethod
    def _browser_required_error(task: Mapping[str, Any]) -> CrawlServiceError:
        details = {
            "httpStatus": task.get("httpStatus"),
            "errorCode": task.get("errorCode") or "POLICY_SOURCE_BROWSER_REQUIRED",
            "fallbackAction": task.get("fallbackAction") or "browser_search",
            "fallbackReason": task.get("fallbackReason"),
            "fallbackTaskId": task.get("id"),
        }
        return CrawlServiceError(
            "POLICY_SOURCE_BROWSER_REQUIRED",
            "该来源已进入 WorkBuddy 浏览器兜底队列，系统不会重复 HTTP 抓取",
            409,
            details,
        )

    def list_browser_fallback_tasks(
        self, *, city_id: str | None = None, status: str | None = None
    ) -> list[dict[str, Any]]:
        self._backfill_legacy_fallback_tasks(city_id=city_id)
        projects = {str(project.get("cityId")): project for project in self.repository.list_projects()}
        sources = {str(source.get("id")): source for source in self.repository.list_data_sources()}
        result: list[dict[str, Any]] = []
        for task in self.repository.list_policy_fallback_tasks(city_id=city_id, status=status):
            source = sources.get(str(task.get("sourceId")), {})
            item = dict(task)
            item["cityName"] = projects.get(str(task.get("cityId")), {}).get("city") or task.get("cityId")
            item["sourceName"] = task.get("sourceName") or source.get("name")
            item["taskPrompt"] = self._fallback_task_prompt(
                {**source, **item}, str(task.get("requestedUrl") or ""), task
            )
            result.append(item)
        return result

    def _backfill_legacy_fallback_tasks(self, *, city_id: str | None = None) -> None:
        """把 010 迁移前已经存在的失败 artifact 转成一次性队列任务。"""
        known_keys = {
            (str(task.get("sourceId")), str(task.get("requestedUrl")))
            for task in self.repository.list_policy_fallback_tasks(city_id=city_id)
        }
        for source in self.repository.list_data_sources(city_id=city_id):
            source_id = str(source.get("id") or "")
            requested_url = str(source.get("url") or "").strip()
            if not source_id or not requested_url or (source_id, requested_url) in known_keys:
                continue
            artifacts = self.repository.list_crawl_artifacts(source_id=source_id)
            latest_failed = next(reversed(artifacts), None) if artifacts else None
            if not (
                latest_failed
                and latest_failed.get("status") == "failed"
                and latest_failed.get("requestedUrl") == requested_url
                and latest_failed.get("fallbackAction") == "browser_search"
            ):
                latest_failed = None
            if latest_failed is None:
                continue
            self._ensure_browser_fallback_task(
                source,
                requested_url=requested_url,
                details={
                    "httpStatus": latest_failed.get("httpStatus"),
                    "errorCode": latest_failed.get("errorCode"),
                    "fallbackAction": latest_failed.get("fallbackAction"),
                    "fallbackReason": latest_failed.get("fallbackReason"),
                    "message": latest_failed.get("errorMessage"),
                },
            )
            known_keys.add((source_id, requested_url))

    def claim_browser_fallback_task(self, task_id: str) -> dict[str, Any]:
        try:
            task = self.repository.get_policy_fallback_task(task_id)
        except KeyError:
            raise CrawlServiceError("NOT_FOUND", f"Fallback task not found: {task_id}", 404) from None
        status = str(task.get("status") or "queued")
        if status == "in_progress":
            return task
        if status in {"archived", "completed"}:
            return task
        if status not in {"queued", "failed"}:
            raise CrawlServiceError("FALLBACK_TASK_INVALID_STATUS", "该兜底任务当前不可领取", 409)
        return self.repository.update_policy_fallback_task(
            task_id,
            {"status": "in_progress", "attempts": int(task.get("attempts") or 0) + 1},
        )

    def fail_browser_fallback_task(self, task_id: str, reason: str) -> dict[str, Any]:
        try:
            task = self.repository.get_policy_fallback_task(task_id)
        except KeyError:
            raise CrawlServiceError("NOT_FOUND", f"Fallback task not found: {task_id}", 404) from None
        if task.get("status") in {"archived", "completed"}:
            return task
        return self.repository.update_policy_fallback_task(
            task_id,
            {"status": "failed", "lastError": reason.strip()},
        )

    def _archive_browser_fallback_tasks(
        self, *, source_id: str, requested_url: str, artifact_id: str
    ) -> str | None:
        archived_id: str | None = None
        for task in self.repository.list_policy_fallback_tasks():
            if (
                task.get("sourceId") == source_id
                and task.get("requestedUrl") == requested_url
                and task.get("status") in FALLBACK_TASK_ACTIVE_STATUSES
            ):
                self.repository.update_policy_fallback_task(
                    task["id"], {"status": "archived", "artifactId": artifact_id, "lastError": None}
                )
                archived_id = str(task["id"])
        return archived_id

    def crawl_source_now(self, source_id: str, *, raw_dir: Path) -> dict[str, Any]:
        """一键抓取：保存原文、记录变更比对，并把解析出的建议值写给该城市场景。

        抓取失败也保留失败记录，且不删除上一次成功结果（PRD 11.6）。
        """
        source = self._source(source_id)
        if source.get("status") == "paused":
            raise CrawlServiceError("POLICY_SOURCE_DISABLED", "该官网来源已停用，请先启用", 409)
        url = source.get("url")
        if not url or not str(url).strip():
            raise CrawlServiceError("POLICY_SOURCE_URL_REQUIRED", "该来源没有配置官网链接", 400)
        requested_url = str(url).strip()
        pending_task = self._pending_browser_fallback_task(source, requested_url)
        if pending_task is not None:
            raise self._browser_required_error(pending_task)

        previous_success = next(
            (
                artifact
                for artifact in reversed(self.repository.list_crawl_artifacts(source_id=source_id))
                if artifact.get("status") == "success"
            ),
            None,
        )

        try:
            result = crawl_source(
                requested_url,
                raw_dir,
                timeout_seconds=int(source.get("timeoutSeconds") or 0) or None,
                max_bytes=int(source.get("maxBytes") or 0) or None,
                allow_private=self.crawl_allow_private,
            )
        except CrawlError as error:
            details = crawl_error_details(error)
            if details.get("fallbackAction") == "browser_search":
                task = self._ensure_browser_fallback_task(
                    source,
                    requested_url=requested_url,
                    details={**details, "message": str(error)},
                )
                details["fallbackTaskId"] = task["id"]
            self.repository.create_crawl_artifact(
                {
                    "sourceId": source_id,
                    "cityId": source["cityId"],
                    "requestedUrl": requested_url,
                    "finalUrl": None,
                    "httpStatus": details["httpStatus"],
                    "contentType": None,
                    "contentLength": None,
                    "sha256": None,
                    "storedPath": None,
                    "title": None,
                    "changeStatus": None,
                    "status": "failed",
                    "errorMessage": str(error),
                    "fetchMode": "http",
                    "errorCode": details["errorCode"],
                    "fallbackAction": details["fallbackAction"],
                    "fallbackReason": details["fallbackReason"],
                }
            )
            self.repository.update_data_source(
                source_id,
                {
                    "status": "error",
                    "lastHttpStatus": details["httpStatus"],
                    "lastFetchMode": "http",
                    "lastErrorCode": details["errorCode"],
                    "lastFallbackAction": details["fallbackAction"],
                    "lastFallbackReason": details["fallbackReason"],
                },
            )
            raise CrawlServiceError("POLICY_SOURCE_FETCH_FAILED", str(error), 502, details) from error

        if previous_success is None:
            change_status = "first_fetch"
        elif previous_success.get("sha256") == result.sha256:
            change_status = "unchanged"
        else:
            change_status = "new_version"

        artifact = self.repository.create_crawl_artifact(
            {
                "sourceId": source_id,
                "cityId": source["cityId"],
                "requestedUrl": result.requested_url,
                "finalUrl": result.final_url,
                "httpStatus": result.http_status,
                "contentType": result.content_type,
                "contentLength": result.content_length,
                "sha256": result.sha256,
                "storedPath": result.stored_path,
                "title": result.title,
                "changeStatus": change_status,
                "status": "success",
                "errorMessage": None,
                "fetchMode": "http",
                "errorCode": None,
                "fallbackAction": None,
                "fallbackReason": None,
            }
        )
        self.repository.update_data_source(
            source_id,
            {
                "status": "active",
                "lastFetchedAt": artifact["fetchedAt"],
                "lastHttpStatus": result.http_status,
                "lastChangeStatus": change_status,
                "lastFetchMode": "http",
                "lastErrorCode": None,
                "lastFallbackAction": None,
                "lastFallbackReason": None,
            },
        )

        # 解析建议值并写入该城市各场景的自动爬虫字段（PRD 11.10 / 15.3）
        #
        # 这是**正则兜底路径**，与 WorkBuddy 的 AI 抽取（agent_service）并存。
        # 正则只取第一处匹配且不看上下文，准确度远低于 AI —— 实测它曾把统计公报里的
        # 「目录范围内基金支付比例 80.23%」（住院报销比例）当成 P2 基金支付比例写进去，
        # 又曾把「未就业城乡居民…50% 左右」写成 P2，覆盖掉 AI 正确抽出的 0.7。
        # 因此这里**只在字段还没有建议值时才写**，绝不覆盖已有结果（AI 优先）。
        readable = extract_readable_text(result.raw_content, result.content_type)
        suggestions = parse_suggestions(readable)
        if suggestions:
            suggested_source = {
                "sourceId": source_id,
                "sourceName": source.get("name") or source_id,
                "url": result.final_url,
                "artifactId": artifact["artifactId"],
                "documentId": None,
                "quote": None,
            }
            written: list[dict[str, Any]] = []
            skipped: list[dict[str, Any]] = []
            for project in self.repository.list_projects():
                if str(project.get("cityId") or project.get("city")) != str(source["cityId"]):
                    continue
                for scenario in project.get("scenarios", []):
                    existing = {
                        str(row["fieldId"]): row
                        for row in self.repository.list_field_values(str(scenario["id"]))
                    }
                    for suggestion in suggestions:
                        field_id = str(suggestion["fieldId"])
                        current = existing.get(field_id) or {}
                        if current.get("suggestedValue") is not None:
                            skipped.append(
                                {
                                    "scenarioId": scenario["id"],
                                    "fieldId": field_id,
                                    "reason": "该字段已有建议值，正则兜底不覆盖",
                                }
                            )
                            continue
                        row = dict(suggested_source)
                        row["quote"] = suggestion["quote"]
                        self.repository.save_field_suggestion(
                            scenario["id"], field_id, suggestion["value"], row
                        )
                        written.append(
                            {
                                "fieldId": field_id,
                                "value": suggestion["value"],
                                "unit": None,
                                "confidence": None,
                                "quote": suggestion["quote"],
                                "effectiveDate": None,
                            }
                        )
            # 补审计：正则路径过去直接写库、不留痕，排查建议值来源时会断链。
            # 只在实际写入时留记录，避免每次抓取都产生空记录。
            if written:
                self.repository.create_extraction_submission(
                    {
                        "cityId": source.get("cityId"),
                        "sourceId": source_id,
                        "artifactId": artifact["artifactId"],
                        "agentRunId": "regex-fallback",
                        "agentVersion": "regex-fallback@1",
                        "payload": {
                            "submissions": [],
                            "accepted": written,
                            "skipped": skipped,
                            "notDisclosed": [],
                            "origin": "regex_fallback",
                        },
                        "resultStatus": "accepted",
                        "acceptedCount": len(written),
                        "rejectedCount": 0,
                        "rejections": [],
                    }
                )
        artifact["suggestions"] = suggestions
        return artifact

    def fetch_for_agent(
        self,
        *,
        requests: Sequence[Mapping[str, Any]],
        raw_dir: Path,
        max_chars: int = 40000,
        research_run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """为 WorkBuddy 抓取正文（WorkBuddy 驱动架构，见设计文档 8.4）。

        与 `crawl_source_now` 共用同一条抓取链路（SSRF 防护、原文存档、SHA256 变更检测），
        区别在于：本方法**不做正则解析、不写建议值** —— 解析交给 WorkBuddy，
        只把正文文本与变更状态回传，让上游决定是否值得调用模型。

        `changeStatus == "unchanged"` 时 `text` 仍会返回，但上游据此跳过抽取即可省下 AI 成本。
        """
        results: list[dict[str, Any]] = []
        for request in requests:
            url = str(request.get("url") or "").strip()
            city_id = str(request.get("cityId") or "").strip()
            source_id = request.get("sourceId")
            name = request.get("name")
            if not url:
                results.append({"url": None, "status": "failed", "errorMessage": "缺少 url"})
                continue

            # 若给了 sourceId，沿用其超时/大小配置与状态校验。
            source: dict[str, Any] | None = None
            if source_id:
                try:
                    source = self._source(str(source_id))
                except CrawlServiceError as error:
                    if error.status_code == 404:
                        source = None
                    else:
                        raise

            if source is not None and source.get("status") == "paused":
                results.append(
                    {
                        "url": url,
                        "sourceId": source_id,
                        "status": "skipped",
                        "errorMessage": "该官网来源已停用，请先启用",
                    }
                )
                continue

            if source is not None:
                pending_task = self._pending_browser_fallback_task(source, url)
                if pending_task is not None:
                    results.append(
                        {
                            "url": url,
                            "sourceId": source_id,
                            "status": "browser_required",
                            "errorMessage": "该来源已进入 WorkBuddy 浏览器兜底队列，系统不会重复 HTTP 抓取",
                            "httpStatus": pending_task.get("httpStatus"),
                            "errorCode": pending_task.get("errorCode") or "POLICY_SOURCE_BROWSER_REQUIRED",
                            "fallbackAction": pending_task.get("fallbackAction") or "browser_search",
                            "fallbackReason": pending_task.get("fallbackReason"),
                            "fallbackTaskId": pending_task.get("id"),
                        }
                    )
                    continue

            previous_success: dict[str, Any] | None = None
            if source_id:
                previous_success = next(
                    (
                        artifact
                        for artifact in reversed(
                            self.repository.list_crawl_artifacts(source_id=str(source_id))
                        )
                        if artifact.get("status") == "success"
                    ),
                    None,
                )

            timeout = int((source or {}).get("timeoutSeconds") or 0) or None
            max_bytes = int((source or {}).get("maxBytes") or 0) or None
            try:
                result = crawl_source(
                    url,
                    raw_dir,
                    timeout_seconds=timeout,
                    max_bytes=max_bytes,
                    allow_private=self.crawl_allow_private,
                )
            except CrawlError as error:
                details = crawl_error_details(error)
                if source is not None and details.get("fallbackAction") == "browser_search":
                    task = self._ensure_browser_fallback_task(
                        source,
                        requested_url=url,
                        details={**details, "message": str(error)},
                        research_run_id=research_run_id,
                    )
                    details["fallbackTaskId"] = task["id"]
                if source_id and city_id:
                    self.repository.create_crawl_artifact(
                        {
                            "sourceId": str(source_id),
                            "cityId": city_id,
                            "requestedUrl": url,
                            "finalUrl": None,
                            "httpStatus": details["httpStatus"],
                            "contentType": None,
                            "contentLength": None,
                            "sha256": None,
                            "storedPath": None,
                            "title": None,
                            "changeStatus": None,
                            "status": "failed",
                            "errorMessage": str(error),
                            "fetchMode": "http",
                            "errorCode": details["errorCode"],
                            "fallbackAction": details["fallbackAction"],
                            "fallbackReason": details["fallbackReason"],
                            **({"researchRunId": research_run_id} if research_run_id else {}),
                        }
                    )
                    self.repository.update_data_source(
                        str(source_id),
                        {
                            "status": "error",
                            "lastHttpStatus": details["httpStatus"],
                            "lastFetchMode": "http",
                            "lastErrorCode": details["errorCode"],
                            "lastFallbackAction": details["fallbackAction"],
                            "lastFallbackReason": details["fallbackReason"],
                        },
                    )
                results.append({"url": url, "sourceId": source_id, "status": "failed", "errorMessage": str(error), **details})
                continue

            if previous_success is None:
                change_status = "first_fetch"
            elif previous_success.get("sha256") == result.sha256:
                change_status = "unchanged"
            else:
                change_status = "new_version"

            artifact: dict[str, Any] = {
                "artifactId": new_id("artifact"),
                "requestedUrl": result.requested_url,
                "finalUrl": result.final_url,
                "httpStatus": result.http_status,
                "contentType": result.content_type,
                "contentLength": result.content_length,
                "sha256": result.sha256,
                "storedPath": result.stored_path,
                "title": result.title,
                "changeStatus": change_status,
                "status": "success",
                "errorMessage": None,
                "fetchMode": "http",
                "errorCode": None,
                "fallbackAction": None,
                "fallbackReason": None,
            }
            if source_id and city_id:
                artifact_data = {"sourceId": str(source_id), "cityId": city_id, **artifact}
                if research_run_id:
                    artifact_data["researchRunId"] = research_run_id
                artifact = self.repository.create_crawl_artifact(artifact_data)
                self.repository.update_data_source(
                    str(source_id),
                    {
                        "status": "active",
                        "lastFetchedAt": artifact["fetchedAt"],
                        "lastHttpStatus": result.http_status,
                        "lastChangeStatus": change_status,
                        "lastFetchMode": "http",
                        "lastErrorCode": None,
                        "lastFallbackAction": None,
                        "lastFallbackReason": None,
                    },
                )

            readable = extract_readable_text(result.raw_content, result.content_type)
            text = (readable or "")[:max_chars] or None
            results.append(
                {
                    "url": result.final_url,
                    "requestedUrl": result.requested_url,
                    "sourceId": source_id,
                    "sourceName": name,
                    "artifactId": artifact.get("artifactId"),
                    "title": result.title,
                    "sha256": result.sha256,
                    "httpStatus": result.http_status,
                    "contentType": result.content_type,
                    "changeStatus": change_status,
                    "text": text,
                    "textTruncated": bool(readable and len(readable) > max_chars),
                    "textLength": len(readable) if readable else 0,
                    "status": "success",
                    "errorMessage": None,
                }
            )
        return results

    def archive_browser_artifact(
        self,
        *,
        city_id: str,
        source_id: str,
        research_run_id: str | None,
        requested_url: str,
        final_url: str | None,
        title: str | None,
        content: str,
        content_type: str,
        raw_dir: Path,
    ) -> dict[str, Any]:
        """归档 WorkBuddy 浏览器看到的官方正文，并恢复该来源的可用状态。

        浏览器访问发生在 WorkBuddy 侧；API 只接收用户可复核的正文和 URL，做
        URL 形态校验、哈希去重、原文落盘和来源状态更新，不信任浏览器回传的
        任意 HTML/脚本或未经引用的字段值。
        """
        city = str(city_id or "").strip()
        source_key = str(source_id or "").strip()
        requested = str(requested_url or "").strip()
        final = str(final_url or requested).strip()
        body = str(content or "")
        if not city or not source_key:
            raise CrawlServiceError("INVALID_BROWSER_ARTIFACT", "cityId 和 sourceId 不能为空", 422)
        if not body.strip():
            raise CrawlServiceError("INVALID_BROWSER_ARTIFACT", "浏览器回传正文不能为空", 422)
        if len(body) > 200000:
            raise CrawlServiceError("INVALID_BROWSER_ARTIFACT", "浏览器回传正文不能超过 200000 个字符", 422)

        def validate_url(value: str, field: str) -> None:
            parsed = urlsplit(value)
            if len(value) > 2000 or parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise CrawlServiceError("INVALID_BROWSER_ARTIFACT", f"{field} 必须是公开的 http/https 链接", 422)
            if parsed.username or parsed.password:
                raise CrawlServiceError("INVALID_BROWSER_ARTIFACT", f"{field} 不能包含账号或密码", 422)

        validate_url(requested, "requestedUrl")
        validate_url(final, "finalUrl")

        try:
            source = next(
                source for source in self.repository.list_data_sources(city_id=city)
                if str(source.get("id")) == source_key
            )
        except StopIteration:
            raise CrawlServiceError("NOT_FOUND", f"Data source not found: {source_key}", 404) from None

        payload = body.encode("utf-8")
        digest = hashlib.sha256(payload).hexdigest()
        previous_success = next(
            (
                artifact
                for artifact in reversed(self.repository.list_crawl_artifacts(source_id=source_key))
                if artifact.get("status") == "success"
            ),
            None,
        )
        if previous_success and previous_success.get("sha256") == digest:
            task_id = self._archive_browser_fallback_tasks(
                source_id=source_key,
                requested_url=requested,
                artifact_id=str(previous_success["artifactId"]),
            )
            return {
                "artifact": previous_success,
                "idempotent": True,
                **({"fallbackTaskId": task_id} if task_id else {}),
            }

        change_status = (
            "first_fetch"
            if previous_success is None
            else "new_version"
        )
        stored = LocalPolicyFileStore(raw_dir.parent).put(
            f"raw_sources/{digest}.bin",
            payload,
            content_type=content_type or "text/plain; charset=utf-8",
        )
        artifact = self.repository.create_crawl_artifact(
            {
                "sourceId": source_key,
                "cityId": city,
                "requestedUrl": requested,
                "finalUrl": final,
                "httpStatus": None,
                "contentType": content_type or "text/plain; charset=utf-8",
                "contentLength": len(payload),
                "sha256": digest,
                "storedPath": stored["pathname"],
                "title": str(title).strip() if title and str(title).strip() else None,
                "changeStatus": change_status,
                "status": "success",
                "errorMessage": None,
                "fetchMode": "workbuddy_browser",
                "errorCode": None,
                "fallbackAction": None,
                "fallbackReason": None,
                **({"researchRunId": research_run_id} if research_run_id else {}),
            }
        )
        self.repository.update_data_source(
            source_key,
            {
                "status": "active",
                "lastFetchedAt": artifact["fetchedAt"],
                "lastHttpStatus": None,
                "lastChangeStatus": change_status,
                "lastFetchMode": "workbuddy_browser",
                "lastErrorCode": None,
                "lastFallbackAction": None,
                "lastFallbackReason": None,
            },
        )
        task_id = self._archive_browser_fallback_tasks(
            source_id=source_key,
            requested_url=requested,
            artifact_id=str(artifact["artifactId"]),
        )
        return {
            "artifact": artifact,
            "idempotent": False,
            **({"fallbackTaskId": task_id} if task_id else {}),
        }

    def upload_document(
        self,
        *,
        city_id: str,
        source: str,
        original_name: str,
        mime_type: str,
        content: bytes,
    ) -> dict[str, Any]:
        suffix = Path(original_name).suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError("仅支持 Word、Excel 或 PDF 文件")
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("文件大小不能超过 20 MB")
        if not city_id.strip() or not source.strip():
            raise ValueError("cityId 和 source 不能为空")
        return self.repository.create_policy_document(
            {
                "cityId": city_id.strip(),
                "originalName": original_name,
                "mimeType": mime_type or "application/octet-stream",
                "size": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "source": source.strip(),
                "status": "uploaded",
            },
            content,
            suffix,
        )

    def parse_document(self, document_id: str, candidates: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        document = self.repository.get_policy_document(document_id)
        if document.get("status") in {"approved", "rejected"}:
            raise ValueError("已审核文件不能重新解析，请上传新版本")
        self.repository.update_policy_document(document_id, {"status": "parsing"})
        fact_ids: list[str] = []
        for candidate in candidates:
            field_id = str(candidate.get("fieldId") or "").strip()
            if not field_id:
                raise ValueError("候选字段缺少 fieldId")
            confidence = candidate.get("confidence")
            if confidence is not None and (not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1):
                raise ValueError("confidence 必须在 0 到 1 之间")
            fact = self.repository.create_policy_fact(
                {
                    "documentId": document_id,
                    "cityId": document["cityId"],
                    "fieldId": field_id,
                    "value": candidate.get("value"),
                    "unit": candidate.get("unit"),
                    "confidence": confidence,
                    "source": candidate.get("source") or document.get("source"),
                    "status": "candidate",
                    "reviewer": None,
                    "reviewedAt": None,
                    "effectiveDate": None,
                }
            )
            fact_ids.append(str(fact["id"]))
        updated = self.repository.update_policy_document(document_id, {"status": "review_pending"})
        return {
            **updated,
            "factIds": fact_ids,
            "pendingFactCount": len(fact_ids),
        }

    def review_fact(
        self,
        document_id: str,
        fact_id: str,
        *,
        decision: str,
        reviewer: str,
        source: str | None,
        effective_date: str | None,
    ) -> dict[str, Any]:
        if decision not in {"approve", "reject"}:
            raise ValueError("decision 必须是 approve 或 reject")
        if not reviewer.strip():
            raise ValueError("reviewer 不能为空")
        document = self.repository.get_policy_document(document_id)
        fact = self.repository.get_policy_fact(fact_id)
        if fact.get("documentId") != document_id:
            raise ValueError("政策事实不属于该文件")
        if fact.get("status") != "candidate":
            raise ValueError("该政策事实已审核")
        reviewed = self.repository.update_policy_fact(
            fact_id,
            {
                "status": "approved" if decision == "approve" else "rejected",
                "reviewer": reviewer.strip(),
                "reviewedAt": utc_now(),
                "source": source.strip() if source and source.strip() else fact.get("source") or document.get("source"),
                "effectiveDate": effective_date,
            },
        )
        facts = self.repository.list_policy_facts(document_id=document_id)
        if any(item.get("status") == "candidate" for item in facts):
            status = "review_pending"
        elif any(item.get("status") == "approved" for item in facts):
            status = "approved"
        else:
            status = "rejected"
        self.repository.update_policy_document(document_id, {"status": status})
        return reviewed

    def overview(self, city_ids: Sequence[str] | None = None) -> dict[str, Any]:
        projects = self.repository.list_projects()
        documents = self.repository.list_policy_documents()
        sources = self.repository.list_data_sources()
        facts = self.repository.list_policy_facts()
        artifacts = self.repository.list_crawl_artifacts()
        suggestion_counts = self._suggestion_counts(projects)
        all_city_ids = {
            str(item.get("cityId") or item.get("city") or "unknown-city") for item in projects
        } | {str(item.get("cityId")) for item in documents + sources if item.get("cityId")}
        selected = set(city_ids or all_city_ids)
        cities = [
            self._city_summary(
                city_id,
                projects,
                documents,
                sources,
                facts,
                artifacts,
                suggestion_counts.get(city_id, 0),
            )
            for city_id in sorted(selected)
        ]
        pending = sum(int(city["pendingReviewCount"]) for city in cities)
        approved = sum(int(city["approvedFactCount"]) for city in cities)
        source_count = sum(int(city["sourceCount"]) for city in cities)
        active_source_count = sum(int(city["activeSourceCount"]) for city in cities)
        crawl_count = sum(int(city["crawlCount"]) for city in cities)
        suggestion_count = sum(int(city["suggestionCount"]) for city in cities)
        fallback_required_count = sum(int(city["fallbackRequiredCount"]) for city in cities)
        alerts = [
            {
                "type": "policy",
                "severity": "warning",
                "cityId": city["cityId"],
                "cityName": city["cityName"],
                "message": f"有 {city['pendingReviewCount']} 个政策候选字段待审核",
                "href": f"/policies/{city['cityId']}",
            }
            for city in cities
            if city["pendingReviewCount"]
        ]
        alerts.extend(
            {
                "type": "policy-source",
                "severity": "danger",
                "cityId": city["cityId"],
                "cityName": city["cityName"],
                "message": f"有 {city['errorSourceCount']} 个政策来源最近抓取失败",
                "href": f"/policies/{city['cityId']}",
            }
            for city in cities
            if city["errorSourceCount"]
        )
        alerts.extend(
            {
                "type": "policy-browser-fallback",
                "severity": "warning",
                "cityId": city["cityId"],
                "cityName": city["cityName"],
                "message": f"有 {city['fallbackRequiredCount']} 个政策来源需要 WorkBuddy 浏览器兜底",
                "href": f"/policies/{city['cityId']}",
            }
            for city in cities
            if city["fallbackRequiredCount"]
        )
        alerts.extend(
            {
                "type": "policy-suggestion",
                "severity": "info",
                "cityId": city["cityId"],
                "cityName": city["cityName"],
                "message": f"有 {city['suggestionCount']} 个政策建议值待采用",
                "href": f"/projects/{city['projectId']}" if city.get("projectId") else f"/policies/{city['cityId']}",
            }
            for city in cities
            if city["suggestionCount"]
        )
        return {
            "cities": cities,
            "pendingReviewCount": pending,
            "approvedFactCount": approved,
            "sourceCount": source_count,
            "activeSourceCount": active_source_count,
            "crawlCount": crawl_count,
            "suggestionCount": suggestion_count,
            "fallbackRequiredCount": fallback_required_count,
            "alerts": alerts,
        }

    def _suggestion_counts(self, projects: Sequence[Mapping[str, Any]]) -> dict[str, int]:
        """按城市统计去重后的待采用建议值，不把多个场景重复算成多条。"""
        fields_by_city: dict[str, set[str]] = defaultdict(set)
        for project in projects:
            city_id = str(project.get("cityId") or project.get("city") or "")
            if not city_id:
                continue
            for scenario in project.get("scenarios") or []:
                scenario_id = str(scenario.get("id") or "")
                if not scenario_id:
                    continue
                for row in self.repository.list_field_values(scenario_id):
                    if row.get("valueState") == "suggestion_ready" and row.get("suggestedValue") is not None:
                        fields_by_city[city_id].add(str(row.get("fieldId")))
        return {city_id: len(field_ids) for city_id, field_ids in fields_by_city.items()}

    def city_detail(self, city_id: str) -> dict[str, Any]:
        projects = [
            project
            for project in self.repository.list_projects()
            if str(project.get("cityId") or project.get("city")) == city_id
        ]
        documents = self.repository.list_policy_documents(city_id=city_id)
        sources = self.repository.list_data_sources(city_id=city_id)
        facts = self.repository.list_policy_facts(city_id=city_id)
        artifacts = self.repository.list_crawl_artifacts(city_id=city_id)
        summary = self._city_summary(
            city_id,
            projects,
            documents,
            sources,
            facts,
            artifacts,
            self._suggestion_counts(projects).get(city_id, 0),
        )
        return {
            "cityId": city_id,
            "cityName": str(projects[0].get("city") if projects else city_id),
            "documents": documents,
            "dataSources": sources,
            "sourceCount": summary["sourceCount"],
            "activeSourceCount": summary["activeSourceCount"],
            "errorSourceCount": summary["errorSourceCount"],
            "fallbackRequiredCount": summary["fallbackRequiredCount"],
            "crawlCount": summary["crawlCount"],
            "lastFetchedAt": summary["lastFetchedAt"],
            "suggestionCount": summary["suggestionCount"],
            "facts": facts,
            "approvedFacts": [fact for fact in facts if fact.get("status") == "approved"],
            "pendingReviewCount": sum(fact.get("status") == "candidate" for fact in facts),
            "projects": [{"id": project.get("id"), "name": project.get("name")} for project in projects],
        }

    @staticmethod
    def _city_summary(
        city_id: str,
        projects: Sequence[Mapping[str, Any]],
        documents: Sequence[Mapping[str, Any]],
        sources: Sequence[Mapping[str, Any]],
        facts: Sequence[Mapping[str, Any]],
        artifacts: Sequence[Mapping[str, Any]],
        suggestion_count: int,
    ) -> dict[str, Any]:
        city_documents = [item for item in documents if item.get("cityId") == city_id]
        city_sources = [item for item in sources if item.get("cityId") == city_id]
        city_facts = [item for item in facts if item.get("cityId") == city_id]
        city_artifacts = [item for item in artifacts if item.get("cityId") == city_id]
        city_projects = [project for project in projects if str(project.get("cityId") or project.get("city")) == city_id]
        approved_facts = [fact for fact in city_facts if fact.get("status") == "approved"]
        pending = [fact for fact in city_facts if fact.get("status") == "candidate"]
        active_source_count = sum(item.get("status") == "active" for item in city_sources)
        error_source_count = sum(item.get("status") == "error" for item in city_sources)
        fallback_required_count = sum(
            (item.get("fallbackAction") or item.get("lastFallbackAction")) == "browser_search"
            for item in city_sources
        )
        source_status = (
            "partial_failed"
            if error_source_count and active_source_count
            else "fallback_required"
            if fallback_required_count
            else "error"
            if error_source_count
            else "active"
            if active_source_count
            else "paused"
            if city_sources
            else "missing"
        )
        latest_values = [
            str(item.get("updatedAt") or item.get("uploadedAt") or item.get("fetchedAt") or "")
            for item in city_documents + city_sources + city_facts + city_artifacts
            if item.get("updatedAt") or item.get("uploadedAt") or item.get("fetchedAt")
        ]
        return {
            "cityId": city_id,
            "cityName": str(city_projects[0].get("city") if city_projects else city_id),
            "documentCount": len(city_documents),
            "latestUpdatedAt": max(latest_values, default=None),
            "sourceCount": len(city_sources),
            "activeSourceCount": active_source_count,
            "errorSourceCount": error_source_count,
            "fallbackRequiredCount": fallback_required_count,
            "crawlCount": len(city_artifacts),
            "lastFetchedAt": max(
                (str(item.get("fetchedAt")) for item in city_artifacts if item.get("fetchedAt")),
                default=None,
            ),
            "suggestionCount": suggestion_count,
            "pendingReviewCount": len(pending),
            "approvedFactCount": len(approved_facts),
            "completeness": None,
            "sourceStatus": source_status,
            "affectedProjectCount": len(city_projects),
            "projectId": city_projects[0].get("id") if city_projects else None,
            "approvedFacts": approved_facts,
        }
