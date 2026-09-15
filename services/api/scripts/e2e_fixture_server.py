"""端到端验证用的假政策页服务。

提供一个固定的长护险政策 HTML 页面，供 e2e-agent-flow.sh 抓取。
独立成文件（而非 heredoc）是为了避免 shell 管道缓冲导致脚本输出丢失。
"""

from __future__ import annotations

import http.server
import sys

HTML = """<!DOCTYPE html>
<html><head><title>长沙市长期护理保险实施办法</title></head><body>
<h1>长沙市长期护理保险实施办法</h1>
<p>长沙市为新一线城市；常住人口 499.14 万人；60岁以上人口占比 20.58%；80岁以上人口占比 3.2%。</p>
<p>职工医保参保人数 210 万人，医保基金净结余 12.6 亿元，区域总面积 11819 平方公里。</p>
<p>第七条 长期护理保险基金支付比例为 80%。</p>
<p>第八条 单小时服务单价调整为 66 元。</p>
<p>单次服务时长 2 小时，每月必选服务项数 3 项。</p>
<p>本市为长护险国家试点城市，辅具租赁纳入试点范围，支持亲情照护模式。</p>
<p>最低护理员纳保数 20 人，最低护士配置数 2 人。</p>
<p>失能状态持续时长要求 6 个月，评估通过率门槛 70%。</p>
</body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args) -> None:  # noqa: A002
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/search"):
            port = self.server.server_address[1]
            body = (
                "<html><body>"
                f'<a href="http://127.0.0.1:{port}/policy">长沙医保局长护险实施办法</a>'
                f'<a href="http://127.0.0.1:{port}/industry">养老政策整理</a>'
                "</body></html>"
            ).encode("utf-8")
        else:
            body = HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8124
    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"[fixture] 假政策页已启动：http://127.0.0.1:{port}/policy", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
