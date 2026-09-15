from __future__ import annotations

import http.server
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from app.crawlers.runner import (
    CrawlError,
    CrawlResult,
    crawl_source,
    extract_readable_text,
    extract_title,
)
from app.domain.policy.service import parse_suggestions


class _QuietHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass

    def do_GET(self):  # noqa: N802 - stdlib naming
        if self.path == "/policy":
            body = "<html><head><title>长沙市长期护理保险实施办法</title></head><body><p>基金支付比例为 80%。</p></body></html>"
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/policy")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif self.path == "/large":
            data = b"x" * (2 * 1024 * 1024)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/slow":
            import time

            time.sleep(3)
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def do_POST(self):  # noqa: N802 - stdlib naming
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.end_headers()


def _serve() -> tuple[str, int, http.server.ThreadingHTTPServer]:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[:2]
    return str(host), int(port), server


class HtmlDecodingTests(unittest.TestCase):
    """国内政务站大量用 GBK，且常在响应头谎报 charset=utf-8。"""

    _HTML = (
        "<html><head><title>岳阳市医疗保障局</title></head>"
        "<body><p>截至2023年底，我市常住人口499.14万人，占比20.58%。</p></body></html>"
    )

    def test_gbk_body_survives_even_when_header_claims_utf8(self):
        """旧实现固定按 UTF-8 + errors='ignore' 解，会把 GBK 中文整段静默删掉。"""
        content = self._HTML.encode("gb18030")

        text = extract_readable_text(content, "text/html; charset=utf-8")

        self.assertIsNotNone(text)
        self.assertIn("常住人口", text)
        self.assertIn("499.14", text)

    def test_title_decoded_from_gbk_page(self):
        content = self._HTML.encode("gb18030")

        self.assertEqual(extract_title(content, "text/html; charset=utf-8"), "岳阳市医疗保障局")

    def test_utf8_page_still_works(self):
        content = self._HTML.encode("utf-8")

        text = extract_readable_text(content, "text/html; charset=utf-8")

        self.assertIsNotNone(text)
        self.assertIn("常住人口", text)

    def test_declared_gb2312_is_treated_as_gb18030(self):
        content = self._HTML.encode("gb18030")

        text = extract_readable_text(content, "text/html; charset=gb2312")

        self.assertIsNotNone(text)
        self.assertIn("常住人口", text)


class PolicySuggestionParserTests(unittest.TestCase):
    def test_parser_extracts_supported_policy_and_city_fields(self):
        text = (
            "长沙市为新一线城市；常住人口 499.14 万人；60岁以上人口占比 20.58%；"
            "80岁以上人口占比 3.2%；职工医保参保人数 210 万人；医保基金净结余 12.6 亿元；"
            "区域总面积 11819 平方公里；单小时服务单价 66 元；基金支付比例 80%；"
            "最低护理员纳保数 20 人；最低护士配置数 2 人；失能状态持续时长要求 6 个月；"
            "评估通过率门槛 70%；单次服务时长 2 小时；每月必选服务项数 3 项；"
            "辅具政策纳入试点，支持亲情照护模式。"
        )

        result = {item["fieldId"]: item["value"] for item in parse_suggestions(text)}

        self.assertEqual(result["C2"], "新一线")
        self.assertEqual(result["C3"], 499.14)
        self.assertEqual(result["C4"], 0.2058)
        self.assertEqual(result["C5"], 0.032)
        self.assertEqual(result["C10"], 210)
        self.assertEqual(result["C11"], 12.6)
        self.assertEqual(result["C13"], 11819)
        self.assertEqual(result["P1"], 66)
        self.assertEqual(result["P2"], 0.8)
        self.assertEqual(result["P4"], 20)
        self.assertEqual(result["P5"], 2)
        self.assertEqual(result["P6"], 6)
        self.assertEqual(result["P7"], 0.7)
        self.assertEqual(result["P8"], 2)
        self.assertEqual(result["P9"], 3)
        self.assertEqual(result["P10"], "是")
        self.assertEqual(result["P11"], "是")

    def test_parser_does_not_estimate_disability_rate_fields(self):
        result = parse_suggestions(
            "失能率_60-69岁约 12%，失能率_70-79岁约 18%，失能率_80岁以上约 25%。"
        )
        field_ids = {item["fieldId"] for item in result}

        self.assertNotIn("C6", field_ids)
        self.assertNotIn("C7", field_ids)
        self.assertNotIn("C8", field_ids)

    def test_parser_converts_percent_to_decimal_and_keeps_quotes(self):
        result = parse_suggestions("基金支付比例为 80%，评估通过率门槛为 70%。")
        by_id = {item["fieldId"]: item for item in result}

        self.assertEqual(by_id["P2"]["value"], 0.8)
        self.assertEqual(by_id["P7"]["value"], 0.7)
        self.assertIn("80%", by_id["P2"]["quote"])

    def test_parser_preserves_negative_boolean_policy_statements(self):
        result = parse_suggestions("辅具政策未纳入试点，暂不支持亲情照护模式。")
        by_id = {item["fieldId"]: item["value"] for item in result}

        self.assertEqual(by_id["P10"], "否")
        self.assertEqual(by_id["P11"], "否")


class CrawlerSecurityTests(unittest.TestCase):
    """只允许公开 HTTP(S)，私有网段与本机地址一律拒绝（PRD 11.7）。"""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.raw_dir = Path(self.temp_dir.name) / "raw_sources"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_rejects_non_http_schemes(self):
        for url in ("ftp://example.gov.cn/file", "file:///etc/passwd", "javascript:alert(1)"):
            with self.assertRaises(CrawlError) as context:
                crawl_source(url, self.raw_dir)
            self.assertIn("协议", str(context.exception))

    def test_rejects_private_and_loopback_targets(self):
        for url in (
            "http://127.0.0.1/policy",
            "http://localhost/policy",
            "http://192.168.1.1/policy",
            "http://10.0.0.1/policy",
            "http://172.16.0.1/policy",
            "http://169.254.169.254/latest/meta-data",
            "http://[::1]/policy",
        ):
            with self.assertRaises(CrawlError) as context:
                crawl_source(url, self.raw_dir)
            self.assertIn("私有网络", str(context.exception), url)

    def test_rejects_urls_with_credentials(self):
        with self.assertRaises(CrawlError):
            crawl_source("http://user:secret@example.gov.cn/policy", self.raw_dir)


class CrawlerFetchTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.raw_dir = Path(self.temp_dir.name) / "raw_sources"
        self.host, self.port, self.server = _serve()
        self.base = f"http://{self.host}:{self.port}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.temp_dir.cleanup()

    def _public(self, path: str) -> str:
        # 测试服务器监听 127.0.0.1，抓取器默认拦截本机地址；
        # 通过 override 参数在测试里放行，同时验证拦截逻辑可以被显式控制。
        return f"{self.base}{path}"

    def test_fetches_html_saves_raw_file_and_extracts_title(self):
        result = crawl_source(self._public("/policy"), self.raw_dir, allow_private=True)

        self.assertIsInstance(result, CrawlResult)
        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.final_url, self._public("/policy"))
        self.assertEqual(result.content_type, "text/html; charset=utf-8")
        self.assertGreater(result.content_length, 0)
        self.assertEqual(result.title, "长沙市长期护理保险实施办法")
        self.assertIsNotNone(result.sha256)
        self.assertTrue(result.stored_path.startswith("raw_sources/"))
        raw = self.raw_dir.parent / result.stored_path
        self.assertTrue(raw.is_file())
        self.assertEqual(raw.read_bytes(), result.raw_content)
        # 内容指纹与文件内容一致
        import hashlib

        self.assertEqual(result.sha256, hashlib.sha256(result.raw_content).hexdigest())

    def test_follows_redirects_and_records_final_url(self):
        result = crawl_source(self._public("/redirect"), self.raw_dir, allow_private=True)

        self.assertEqual(result.http_status, 200)
        self.assertEqual(result.final_url, self._public("/policy"))

    def test_enforces_response_size_limit(self):
        with self.assertRaises(CrawlError) as context:
            crawl_source(self._public("/large"), self.raw_dir, allow_private=True, max_bytes=1024 * 1024)

        self.assertIn("大小", str(context.exception))

    def test_enforces_timeout(self):
        with self.assertRaises(CrawlError) as context:
            crawl_source(self._public("/slow"), self.raw_dir, allow_private=True, timeout_seconds=1)

        self.assertIn("超时", str(context.exception))

    def test_http_error_status_raises(self):
        with self.assertRaises(CrawlError) as context:
            crawl_source(self._public("/missing"), self.raw_dir, allow_private=True)

        self.assertIn("404", str(context.exception))

    def test_user_agent_is_identifiable(self):
        from app.crawlers.runner import USER_AGENT

        self.assertIn("UE-Agent", USER_AGENT)


if __name__ == "__main__":
    unittest.main()
