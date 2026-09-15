from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


class DocumentationContractTests(unittest.TestCase):
    def test_readmes_describe_sqlite_and_crawler_demo(self):
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        api_readme = (REPO_ROOT / "services/api/README.md").read_text(encoding="utf-8")

        for document in (readme, api_readme):
            self.assertIn("SQLite", document)
            self.assertIn("pnpm bootstrap", document)
            self.assertIn("crawl-all", document)

        self.assertNotIn("当前版本支持全部城市总览、单城市/多城市对比、创建项目、编辑参数、保存场景、执行 24 个月测算、不可变结果快照，以及 Word/Excel/PDF 本地上传", readme)
        self.assertNotIn("默认读取 `/api/dashboard/overview`", readme)
        self.assertNotIn("默认写入 `services/api/data/projects.json`", api_readme)

    def test_product_docs_define_crawl_only_policy_ingestion(self):
        product_prd = (REPO_ROOT / "docs/product/UE-Agent-产品需求文档-v1.0.md").read_text(encoding="utf-8")

        self.assertIn("Demo 阶段不提供政策文件手动上传接口", product_prd)
        self.assertIn("灰色建议值", product_prd)
        self.assertIn("S3", product_prd)
        self.assertIn("S5", product_prd)


if __name__ == "__main__":
    unittest.main()
