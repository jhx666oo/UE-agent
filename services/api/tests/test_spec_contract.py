import unittest

from app.domain.u1.spec import load_parameter_catalog, validate_parameter_catalog


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


if __name__ == "__main__":
    unittest.main()
