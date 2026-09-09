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
)


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
