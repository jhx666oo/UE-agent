from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Mapping, Sequence

from ...repository import ProjectRepository, new_id, utc_now


ALLOWED_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".pdf"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


class PolicyService:
    """Local policy workflow; candidate values never become approved implicitly."""

    def __init__(self, repository: ProjectRepository):
        self.repository = repository

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
