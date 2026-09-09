from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import JsonProjectRepository


class PolicyApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp_dir.name) / "data" / "projects.json"
        self.repository = JsonProjectRepository(self.store_path)
        self.client = TestClient(create_app(self.repository))

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def upload(self, filename: str = "policy.pdf", content: bytes = b"local policy") -> dict:
        response = self.client.post(
            "/api/policies/documents/upload",
            data={"cityId": "city-a", "source": "local-review"},
            files={"file": (filename, content, "application/pdf")},
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_policy_state_machine_keeps_candidates_out_of_summary_until_approved(self) -> None:
        document = self.upload()
        self.assertEqual(document["status"], "uploaded")
        self.assertEqual(document["sha256"], hashlib.sha256(b"local policy").hexdigest())
        self.assertTrue((self.store_path.parent / document["storedPath"]).exists())
        self.assertNotEqual(Path(document["storedPath"]).name, "policy.pdf")
        original = self.client.get(f"/api/policies/documents/{document['id']}/content")
        self.assertEqual(original.status_code, 200, original.text)
        self.assertEqual(original.content, b"local policy")

        parsed = self.client.post(
            f"/api/policies/documents/{document['id']}/parse",
            json={
                "candidates": [
                    {
                        "fieldId": "fundPaymentRatio",
                        "value": 0.8,
                        "unit": "比例",
                        "confidence": 0.92,
                        "source": "第3条",
                    }
                ]
            },
        )
        self.assertEqual(parsed.status_code, 200, parsed.text)
        self.assertEqual(parsed.json()["status"], "review_pending")
        self.assertEqual(parsed.json()["pendingFactCount"], 1)

        pending_summary = self.client.get("/api/dashboard/policy-summary?cityIds=city-a")
        self.assertEqual(pending_summary.status_code, 200, pending_summary.text)
        self.assertEqual(pending_summary.json()["cities"][0]["approvedFactCount"], 0)
        self.assertEqual(pending_summary.json()["cities"][0]["pendingReviewCount"], 1)
        self.assertEqual(pending_summary.json()["cities"][0]["approvedFacts"], [])

        rejected = self.client.post(
            f"/api/policies/documents/{document['id']}/facts/{parsed.json()['factIds'][0]}/review",
            json={"decision": "reject", "reviewer": "reviewer-a"},
        )
        self.assertEqual(rejected.status_code, 200, rejected.text)
        self.assertEqual(rejected.json()["status"], "rejected")

        rejected_summary = self.client.get("/api/dashboard/policy-summary?cityIds=city-a")
        self.assertEqual(rejected_summary.json()["cities"][0]["approvedFacts"], [])

        approved_document = self.upload("policy-v2.docx", b"approved policy")
        approved_parse = self.client.post(
            f"/api/policies/documents/{approved_document['id']}/parse",
            json={
                "candidates": [
                    {
                        "fieldId": "fundPaymentRatio",
                        "value": 0.85,
                        "unit": "比例",
                        "confidence": 0.96,
                        "source": "第4条",
                    }
                ]
            },
        )
        fact_id = approved_parse.json()["factIds"][0]
        approved = self.client.post(
            f"/api/policies/documents/{approved_document['id']}/facts/{fact_id}/review",
            json={
                "decision": "approve",
                "reviewer": "reviewer-a",
                "source": "民政局公告",
                "effectiveDate": "2026-01-01",
            },
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["status"], "approved")

        approved_summary = self.client.get("/api/dashboard/policy-summary?cityIds=city-a")
        city_summary = approved_summary.json()["cities"][0]
        self.assertEqual(city_summary["approvedFactCount"], 1)
        self.assertEqual(city_summary["approvedFacts"][0]["value"], 0.85)
        self.assertEqual(city_summary["pendingReviewCount"], 0)
        dashboard = self.client.get("/api/dashboard/overview")
        self.assertEqual(dashboard.status_code, 200, dashboard.text)
        self.assertEqual(dashboard.json()["policySummary"]["cities"][0]["approvedFactCount"], 1)

    def test_policy_overview_and_sources_are_local_and_explicit(self) -> None:
        project = self.repository.create_project({"name": "City A", "city": "城市A"})
        scenario = self.repository.create_scenario(project["id"], {"name": "基准", "inputs": {"fundPaymentRatio": 0.5}})
        document = self.upload("policy.xlsx", b"xlsx placeholder")

        source = self.client.post(
            "/api/policies/sources",
            json={"cityId": "city-a", "name": "官方来源", "kind": "web", "url": "https://example.test/policy"},
        )
        self.assertEqual(source.status_code, 201, source.text)
        self.assertEqual(self.client.get("/api/policies/sources?cityId=city-a").json()[0]["status"], "active")

        overview = self.client.get("/api/policies/overview")
        self.assertEqual(overview.status_code, 200, overview.text)
        self.assertEqual(overview.json()["cities"][0]["pendingReviewCount"], 0)
        detail = self.client.get("/api/policies/cities/city-a")
        self.assertEqual(detail.status_code, 200, detail.text)
        self.assertEqual(detail.json()["documents"][0]["id"], document["id"])

        unchanged = self.repository.get_scenario(project["id"], scenario["id"])
        self.assertEqual(unchanged["inputs"]["fundPaymentRatio"], 0.5)


if __name__ == "__main__":
    unittest.main()
