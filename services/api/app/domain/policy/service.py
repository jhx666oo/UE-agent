from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...crawlers.runner import CrawlError, crawl_source, extract_readable_text
from ...repository import ProjectRepository, new_id, utc_now


ALLOWED_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".pdf"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class CrawlServiceError(Exception):
    """一键抓取失败；code 对应稳定 API 错误码。"""

    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# PRD 11.10：可解析的政策字段 -> 关联的 Excel 参数编号。
# 模式按可读文本匹配；百分比统一换算为 0-1 存储（PRD 10.5）。
SUGGESTION_PATTERNS: tuple[tuple[str, str, re.Pattern[str], bool], ...] = (
    # (field_id, 参数名称, 匹配模式, 是否百分比)
    ("P1", "单小时服务单价", re.compile(r"单小时服务单价[^0-9]{0,12}([0-9]+(?:\.[0-9]+)?)"), False),
    ("P2", "基金支付比例", re.compile(r"基金支付比例[^0-9]{0,8}([0-9]+(?:\.[0-9]+)?)\s*%"), True),
    ("P8", "单次服务时长", re.compile(r"单次服务[^0-9]{0,6}([0-9]+(?:\.[0-9]+)?)\s*小时"), False),
)


def parse_suggestions(text: str | None) -> list[dict[str, Any]]:
    """从抓取的可读文本中解析参数建议值（不自动写入城市参数）。"""
    if not text:
        return []
    suggestions: list[dict[str, Any]] = []
    for field_id, name, pattern, is_percent in SUGGESTION_PATTERNS:
        match = pattern.search(text)
        if match is None:
            continue
        value: float | int = float(match.group(1))
        if value.is_integer():
            value = int(value)
        if is_percent:
            value = value / 100
        suggestions.append({"fieldId": field_id, "name": name, "value": value, "quote": match.group(0).strip()})
    return suggestions


class PolicyService:
    """Local policy workflow; candidate values never become approved implicitly."""

    def __init__(self, repository: ProjectRepository):
        self.repository = repository
        # 生产保持 False：拒绝本机/私有地址。测试注入 True 以便用本地 HTTP 服务验证行为。
        self.crawl_allow_private = False

    def crawl_source_now(self, source_id: str, *, raw_dir: Path) -> dict[str, Any]:
        """一键抓取：保存原文、记录变更比对，并把解析出的建议值写给该城市场景。

        抓取失败也保留失败记录，且不删除上一次成功结果（PRD 11.6）。
        """
        try:
            source = self.repository.update_data_source(source_id, {})
        except KeyError:
            raise CrawlServiceError("NOT_FOUND", f"Data source not found: {source_id}", 404) from None
        if source.get("status") == "paused":
            raise CrawlServiceError("POLICY_SOURCE_DISABLED", "该官网来源已停用，请先启用", 409)
        url = source.get("url")
        if not url or not str(url).strip():
            raise CrawlServiceError("POLICY_SOURCE_URL_REQUIRED", "该来源没有配置官网链接", 400)

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
                str(url).strip(),
                raw_dir,
                timeout_seconds=int(source.get("timeoutSeconds") or 0) or None,
                max_bytes=int(source.get("maxBytes") or 0) or None,
                allow_private=self.crawl_allow_private,
            )
        except CrawlError as error:
            self.repository.create_crawl_artifact(
                {
                    "sourceId": source_id,
                    "cityId": source["cityId"],
                    "requestedUrl": str(url).strip(),
                    "finalUrl": None,
                    "httpStatus": None,
                    "contentType": None,
                    "contentLength": None,
                    "sha256": None,
                    "storedPath": None,
                    "title": None,
                    "changeStatus": None,
                    "status": "failed",
                    "errorMessage": str(error),
                }
            )
            self.repository.update_data_source(source_id, {"status": "error"})
            raise CrawlServiceError("POLICY_SOURCE_FETCH_FAILED", str(error), 502) from error

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
            }
        )
        self.repository.update_data_source(
            source_id,
            {
                "status": "active",
                "lastFetchedAt": artifact["fetchedAt"],
                "lastHttpStatus": result.http_status,
                "lastChangeStatus": change_status,
            },
        )

        # 解析建议值并写入该城市各场景的自动爬虫字段（PRD 11.10 / 15.3）
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
            for project in self.repository.list_projects():
                if str(project.get("cityId") or project.get("city")) != str(source["cityId"]):
                    continue
                for scenario in project.get("scenarios", []):
                    for suggestion in suggestions:
                        row = dict(suggested_source)
                        row["quote"] = suggestion["quote"]
                        self.repository.save_field_suggestion(
                            scenario["id"], suggestion["fieldId"], suggestion["value"], row
                        )
        artifact["suggestions"] = suggestions
        return artifact

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
        all_city_ids = {
            str(item.get("cityId") or item.get("city") or "unknown-city") for item in projects
        } | {str(item.get("cityId")) for item in documents + sources if item.get("cityId")}
        selected = set(city_ids or all_city_ids)
        cities = [self._city_summary(city_id, projects, documents, sources, facts) for city_id in sorted(selected)]
        pending = sum(int(city["pendingReviewCount"]) for city in cities)
        approved = sum(int(city["approvedFactCount"]) for city in cities)
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
        return {
            "cities": cities,
            "pendingReviewCount": pending,
            "approvedFactCount": approved,
            "alerts": alerts,
        }

    def city_detail(self, city_id: str) -> dict[str, Any]:
        projects = [
            project
            for project in self.repository.list_projects()
            if str(project.get("cityId") or project.get("city")) == city_id
        ]
        documents = self.repository.list_policy_documents(city_id=city_id)
        sources = self.repository.list_data_sources(city_id=city_id)
        facts = self.repository.list_policy_facts(city_id=city_id)
        return {
            "cityId": city_id,
            "cityName": str(projects[0].get("city") if projects else city_id),
            "documents": documents,
            "dataSources": sources,
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
    ) -> dict[str, Any]:
        city_documents = [item for item in documents if item.get("cityId") == city_id]
        city_sources = [item for item in sources if item.get("cityId") == city_id]
        city_facts = [item for item in facts if item.get("cityId") == city_id]
        city_projects = [project for project in projects if str(project.get("cityId") or project.get("city")) == city_id]
        approved_facts = [fact for fact in city_facts if fact.get("status") == "approved"]
        pending = [fact for fact in city_facts if fact.get("status") == "candidate"]
        latest_values = [
            str(item.get("updatedAt") or item.get("uploadedAt") or "")
            for item in city_documents + city_sources + city_facts
            if item.get("updatedAt") or item.get("uploadedAt")
        ]
        return {
            "cityId": city_id,
            "cityName": str(city_projects[0].get("city") if city_projects else city_id),
            "documentCount": len(city_documents),
            "latestUpdatedAt": max(latest_values, default=None),
            "pendingReviewCount": len(pending),
            "approvedFactCount": len(approved_facts),
            "completeness": None,
            "sourceStatus": "active" if any(item.get("status") == "active" for item in city_sources) else "missing",
            "affectedProjectCount": len(city_projects),
            "approvedFacts": approved_facts,
        }
