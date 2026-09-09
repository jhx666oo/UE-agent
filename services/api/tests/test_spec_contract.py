import unittest

from app.domain.u1.spec import (
    BLOCK_ORDER,
    ENUM_PARAMETER_OPTIONS,
    load_parameter_catalog,
    validate_parameter_catalog,
)


class SpecContractTests(unittest.TestCase):
    def test_catalog_contains_all_excel_parameter_groups_and_no_duplicate_ids(self):
        catalog = load_parameter_catalog()
        errors = validate_parameter_catalog(catalog)

        self.assertEqual(errors, [])
        self.assertEqual(len(catalog), 75)
        self.assertEqual(catalog["C1"]["excelCell"], "控制台!E4")
        self.assertEqual(catalog["P1"]["excelCell"], "控制台!E17")
        self.assertEqual(catalog["Z5"]["excelCell"], "控制台!E78")
        self.assertEqual(catalog["P3"]["inputKind"], "formula")
        self.assertEqual(catalog["C8"]["excelCell"], "控制台!E11")
        self.assertEqual(catalog["C9"]["excelCell"], "控制台!E12")
        self.assertEqual(catalog["C13"]["excelCell"], "控制台!E16")

    def test_every_parameter_carries_block_and_block_order(self):
        catalog = load_parameter_catalog()

        for parameter_id, entry in catalog.items():
            self.assertIn(entry["block"], BLOCK_ORDER, parameter_id)
            self.assertEqual(entry["blockOrder"], BLOCK_ORDER.index(entry["block"]) + 1, parameter_id)

        # PRD 14.1 分组编号范围
        self.assertEqual(catalog["C1"]["block"], "城市与市场")
        self.assertEqual(catalog["P11"]["block"], "政策准入")
        self.assertEqual(catalog["S8"]["block"], "站点空间")
        self.assertEqual(catalog["B16"]["block"], "成本参数")
        self.assertEqual(catalog["D8"]["block"], "阶段参数")
        self.assertEqual(catalog["E8"]["block"], "效率与风险")
        self.assertEqual(catalog["A6"]["block"], "辅助收入")
        self.assertEqual(catalog["Z5"]["block"], "战略情景")

    def test_enum_parameters_expose_exact_options(self):
        catalog = load_parameter_catalog()

        self.assertEqual(
            sorted(ENUM_PARAMETER_OPTIONS), sorted(["C2", "C12", "P10", "P11", "B3", "D4", "Z1", "Z5"])
        )
        for parameter_id, expected in ENUM_PARAMETER_OPTIONS.items():
            self.assertEqual(catalog[parameter_id]["options"], list(expected), parameter_id)

    def test_validator_rejects_wrong_block_and_options(self):
        catalog = load_parameter_catalog()
        broken = {key: dict(value) for key, value in catalog.items()}
        broken["C1"]["block"] = "政策准入"
        broken["B3"]["options"] = ["挂证", "全职"]

        errors = validate_parameter_catalog(broken)

        messages = "\n".join(errors)
        self.assertIn("C1 block must be 城市与市场, got 政策准入", messages)
        self.assertIn("B3 options must be ['挂证', '全职', '兼任'], got ['挂证', '全职']", messages)


if __name__ == "__main__":
    unittest.main()
