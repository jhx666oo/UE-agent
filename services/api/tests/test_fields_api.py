from __future__ import annotations

import tempfile
import unittest
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient` is deprecated")

from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import JsonProjectRepository


class FieldApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        repository = JsonProjectRepository(Path(self.temp_dir.name) / "projects.json")
        self.client = TestClient(create_app(repository))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_list_fields_returns_all_75_in_excel_order_with_blocks(self):
        response = self.client.get("/api/fields")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["modelVersion"], "u1-excel-v2.1-parity")
        self.assertEqual(len(body["fields"]), 75)
        self.assertEqual(body["fields"][0]["fieldId"], "C1")
        self.assertEqual(body["fields"][-1]["fieldId"], "Z5")
        # 字段顺序必须与 Excel 控制台一致，不得按名称或分组重排
        self.assertEqual([f["fieldId"] for f in body["fields"]][13], "P1")
        self.assertEqual(body["fields"][13]["block"], "政策准入")

    def test_field_payload_contains_control_contract(self):
        response = self.client.get("/api/fields")
        fields = response.json()["fields"]

        by_id = {field["fieldId"]: field for field in fields}
        # 自动爬虫字段
        self.assertEqual(by_id["C3"]["sourceType"], "自动爬虫")
        self.assertTrue(by_id["C3"]["editable"])
        self.assertFalse(by_id["C3"]["readOnly"])
        # 公式自动字段必须只读
        for formula_id in ("C9", "P3", "S3", "S5", "B12", "B16"):
            self.assertEqual(by_id[formula_id]["sourceType"], "公式自动", formula_id)
            self.assertTrue(by_id[formula_id]["readOnly"], formula_id)
            self.assertFalse(by_id[formula_id]["editable"], formula_id)
        # 枚举参数带 options
        self.assertEqual(by_id["C2"]["options"], ["一线", "新一线", "二线", "三线"])
        self.assertEqual(by_id["B3"]["options"], ["挂证", "全职", "兼任"])
        self.assertIsNone(by_id["C1"]["options"])
        # 其他来源字段可留空
        self.assertEqual(by_id["S1"]["sourceType"], "暗访实地")
        self.assertTrue(by_id["S1"]["editable"])
        # 通用字段
        for field in fields:
            for key in ("fieldId", "name", "unit", "excelCell", "sourceType", "block", "blockOrder", "stage", "valueType", "required", "editable", "readOnly"):
                self.assertIn(key, field, field["fieldId"])

    def test_filter_by_block_returns_only_that_block(self):
        response = self.client.get("/api/fields", params={"block": "政策准入"})

        self.assertEqual(response.status_code, 200)
        fields = response.json()["fields"]
        self.assertEqual(len(fields), 11)
        self.assertEqual({field["block"] for field in fields}, {"政策准入"})
        self.assertEqual(fields[0]["fieldId"], "P1")

    def test_unknown_block_returns_invalid_query(self):
        response = self.client.get("/api/fields", params={"block": "不存在的分组"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_QUERY")

    def test_scenario_update_rejects_formula_fields(self):
        project = self.client.post("/api/projects", json={"name": "公式字段测试", "city": "长沙"}).json()
        scenario = self.client.post(
            f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}
        ).json()

        response = self.client.put(
            f"/api/projects/{project['id']}/scenarios/{scenario['id']}",
            json={"inputs": {"C9": 9999}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "FORMULA_FIELD_READ_ONLY")
        self.assertIn("C9", response.json()["error"]["message"])
        # 公式字段没有写入，场景输入保持不变
        reloaded = self.client.get(
            f"/api/projects/{project['id']}/scenarios/{scenario['id']}"
        ).json()
        self.assertNotIn("C9", reloaded["inputs"])

    def test_scenario_update_rejects_unknown_field_ids(self):
        project = self.client.post("/api/projects", json={"name": "未知字段测试", "city": "长沙"}).json()
        scenario = self.client.post(
            f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}
        ).json()

        response = self.client.put(
            f"/api/projects/{project['id']}/scenarios/{scenario['id']}",
            json={"inputs": {"X99": 1}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "UNKNOWN_FIELD")

    def test_scenario_update_rejects_out_of_enum_options(self):
        project = self.client.post("/api/projects", json={"name": "枚举测试", "city": "长沙"}).json()
        scenario = self.client.post(
            f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}
        ).json()

        response = self.client.put(
            f"/api/projects/{project['id']}/scenarios/{scenario['id']}",
            json={"inputs": {"B3": "外包"}},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "INVALID_FIELD_VALUE")

    def test_scenario_update_accepts_valid_enum_option(self):
        project = self.client.post("/api/projects", json={"name": "枚举合法值", "city": "长沙"}).json()
        scenario = self.client.post(
            f"/api/projects/{project['id']}/scenarios", json={"name": "基准"}
        ).json()

        response = self.client.put(
            f"/api/projects/{project['id']}/scenarios/{scenario['id']}",
            json={"inputs": {"B3": "兼任"}},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["inputs"]["B3"], "兼任")


if __name__ == "__main__":
    unittest.main()
