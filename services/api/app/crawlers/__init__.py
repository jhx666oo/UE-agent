"""官网来源抓取器（PRD 11.6 / 11.7）。

只抓取用户配置的单个 URL：先校验协议与目标地址（拒绝私有网络、回环和
链路本地地址，除非测试显式放行），再按超时与大小上限执行 GET，最多跟随
5 次重定向，原始内容原子落盘到 raw_sources/ 并计算 SHA-256 指纹。
本模块不解析政策含义、不生成建议值——那是解析器与政策域的职责。
"""

from __future__ import annotations

import hashlib
import ipaddress
import os
import re
import socket
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

USER_AGENT = "UE-Agent/0.1 (+local policy collector; contact: local operator)"
MAX_REDIRECTS = 5
DEFAULT_TIMEOUT_SECONDS = 15
MAX_TIMEOUT_SECONDS = 60
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
HARD_MAX_BYTES = 20 * 1024 * 1024
_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_SCRIPT_PATTERN = re.compile(r"<script\b.*?</script>|<style\b.*?</style>", re.IGNORECASE | re.DOTALL)
_TAG_PATTERN = re.compile(r"<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")
# 响应头 / <meta> 里的 charset 声明。
_CHARSET_PATTERN = re.compile(r"charset\s*=\s*[\"']?\s*([\w-]+)", re.IGNORECASE)
_META_CHARSET_PATTERN = re.compile(rb"charset\s*=\s*[\"']?\s*([\w-]+)", re.IGNORECASE)
# GB2312 / GBK 一律按 gb18030 解 —— 它是这两者的超集，能兜住绝大多数中文站。
_CHARSET_ALIASES = {"gb2312": "gb18030", "gbk": "gb18030"}


class CrawlError(Exception):
    """抓取失败；message 面向用户，不包含敏感信息。"""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_code: str | None = None,
        fallback_action: str | None = None,
        fallback_reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.error_code = error_code
        self.fallback_action = fallback_action
        self.fallback_reason = fallback_reason


@dataclass(frozen=True)
class CrawlResult:
    requested_url: str
    final_url: str
    http_status: int
    content_type: str
    content_length: int
    sha256: str
    stored_path: str
    title: str | None
    raw_content: bytes


def _reject_private(hostname: str) -> None:
    """拒绝本机、私有网段和链路本地地址（SSRF 防护）。"""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as error:
        raise CrawlError(
            "无法解析目标官网，请改用 WorkBuddy 浏览器检索官方页面",
            error_code="DNS_BROWSER_FALLBACK",
            fallback_action="browser_search",
            fallback_reason="network_or_tls",
        ) from error
    for info in infos:
        address = info[4][0]
        try:
            parsed = ipaddress.ip_address(address)
        except ValueError:
            continue
        if (
            parsed.is_private
            or parsed.is_loopback
            or parsed.is_link_local
            or parsed.is_reserved
            or parsed.is_multicast
            or parsed.is_unspecified
        ):
            raise CrawlError(f"目标地址属于私有网络或本机地址，已拒绝抓取：{address}")


def _validate_url(url: str, *, allow_private: bool) -> str:
    if not url or len(url) > 2000:
        raise CrawlError("官网链接不能为空且不能超过 2000 字符")
    parts = urlsplit(url.strip())
    if parts.scheme not in ("http", "https"):
        raise CrawlError(f"仅支持 HTTP 或 HTTPS 协议，收到 {parts.scheme!r}")
    if not parts.hostname:
        raise CrawlError("官网链接缺少主机地址")
    if parts.username or parts.password:
        raise CrawlError("官网链接不允许携带账号密码")
    if not allow_private:
        _reject_private(parts.hostname)
    return url.strip()


def _bounded_timeout(timeout_seconds: int | None) -> httpx.Timeout:
    timeout = DEFAULT_TIMEOUT_SECONDS if timeout_seconds is None else timeout_seconds
    if timeout <= 0 or timeout > MAX_TIMEOUT_SECONDS:
        raise CrawlError(f"超时必须是 1 至 {MAX_TIMEOUT_SECONDS} 秒")
    return httpx.Timeout(timeout)


def _bounded_max_bytes(max_bytes: int | None) -> int:
    limit = DEFAULT_MAX_BYTES if max_bytes is None else max_bytes
    if limit <= 0 or limit > HARD_MAX_BYTES:
        raise CrawlError(f"文件大小上限必须是 1 至 {HARD_MAX_BYTES} 字节")
    return limit


def decode_html(content: bytes, content_type: str) -> str:
    """把 HTML 字节解成文本 —— 绝不静默丢字节。

    原实现是固定的 `content.decode("utf-8", errors="ignore")`。国内政务站大量使用
    GBK/GB2312，而且**经常在响应头里谎报 `charset=utf-8`**；这种情况下中文会作为
    「非法 UTF-8 字节」被 `errors="ignore"` **整段删掉**，正文只剩 ASCII 骨架，
    于是 AI 一个值都抽不到（实测岳阳某答复页：原文 8324B 只提出 771 字导航，
    而原文里 499.14 / 20.58 / 59.78 / 19.9 全都在）。

    候选顺序：响应头声明 → `<meta>` 声明 → utf-8 → gb18030；都不成才用替换符兜底
    （宁可看到乱码，也不要静默丢掉整段正文）。
    """
    candidates: list[str] = []
    declared = _CHARSET_PATTERN.search(content_type or "")
    if declared:
        candidates.append(declared.group(1))
    meta = _META_CHARSET_PATTERN.search(content[:4096])
    if meta:
        candidates.append(meta.group(1).decode("ascii", "ignore"))
    candidates.extend(["utf-8", "gb18030"])

    tried: set[str] = set()
    for name in candidates:
        key = _CHARSET_ALIASES.get(name.strip().lower().replace("_", "-"), name.strip().lower())
        if not key or key in tried:
            continue
        tried.add(key)
        try:
            return content.decode(key)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", errors="replace")


def extract_title(content: bytes, content_type: str) -> str | None:
    if "html" not in content_type.lower():
        return None
    try:
        head = decode_html(content[:65536], content_type)
    except Exception:
        return None
    match = _TITLE_PATTERN.search(head)
    if match is None:
        return None
    return _WHITESPACE_PATTERN.sub(" ", match.group(1)).strip() or None


def extract_readable_text(content: bytes, content_type: str) -> str | None:
    """HTML 去除脚本样式与标签后的可读文本，供解析器使用。"""
    if "html" not in content_type.lower():
        return None
    text = decode_html(content, content_type)
    text = _SCRIPT_PATTERN.sub(" ", text)
    text = _TAG_PATTERN.sub(" ", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return _WHITESPACE_PATTERN.sub(" ", text).strip() or None


def _atomic_write(raw_dir: Path, relative: str, content: bytes) -> str:
    target = raw_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=target.parent, prefix=f".{target.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary_path = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, target)
        temporary_path = None
    finally:
        if temporary_path is not None:
            Path(temporary_path).unlink(missing_ok=True)
    return f"raw_sources/{relative}"


def crawl_source(
    url: str,
    raw_dir: Path | str,
    *,
    timeout_seconds: int | None = None,
    max_bytes: int | None = None,
    allow_private: bool = False,
) -> CrawlResult:
    """抓取单个公开 URL 并把原文原子保存到 raw_dir 下。

    allow_private 仅供本地测试使用；生产路径必须保持默认拒绝。
    """
    target_url = _validate_url(url, allow_private=allow_private)
    timeout = _bounded_timeout(timeout_seconds)
    limit = _bounded_max_bytes(max_bytes)
    raw_root = Path(raw_dir)

    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            trust_env=False,
        ) as client:
            response = client.get(target_url)
    except httpx.TimeoutException as error:
        raise CrawlError(
            "官网抓取超时，请稍后重试或调整超时设置",
            error_code="NETWORK_TIMEOUT_BROWSER_FALLBACK",
            fallback_action="browser_search",
            fallback_reason="timeout",
        ) from error
    except httpx.TooManyRedirects as error:
        raise CrawlError(f"重定向次数超过 {MAX_REDIRECTS} 次，已中止抓取") from error
    except httpx.InvalidURL as error:
        raise CrawlError("官网链接格式无效，请检查链接是否可公开访问") from error
    except (httpx.ConnectError, httpx.NetworkError) as error:
        raise CrawlError(
            "无法连接目标官网，请检查链接是否可公开访问",
            error_code="NETWORK_BROWSER_FALLBACK",
            fallback_action="browser_search",
            fallback_reason="network_or_tls",
        ) from error

    if response.status_code >= 400:
        status = response.status_code
        browser_fallback = status in {403, 412, 429} or status >= 500
        raise CrawlError(
            f"官网返回 HTTP {status}，未保存内容",
            http_status=status,
            error_code=f"HTTP_{status}_BROWSER_REQUIRED" if browser_fallback else f"HTTP_{status}",
            fallback_action="browser_search" if browser_fallback else None,
            fallback_reason="js_challenge" if status == 412 else "http_blocked" if browser_fallback else None,
        )

    final_url = str(response.url)
    # 重定向后重新校验目标地址，防止跳到内网。
    _validate_url(final_url, allow_private=allow_private)

    content = response.content
    if len(content) > limit:
        raise CrawlError(f"响应大小 {len(content)} 字节超过上限 {limit} 字节，已中止保存")

    content_type = response.headers.get("content-type", "application/octet-stream")
    digest = hashlib.sha256(content).hexdigest()
    stored_path = _atomic_write(raw_root, f"{digest}.bin", content)
    title = extract_title(content, content_type)
    return CrawlResult(
        requested_url=target_url,
        final_url=final_url,
        http_status=response.status_code,
        content_type=content_type,
        content_length=len(content),
        sha256=digest,
        stored_path=stored_path,
        title=title,
        raw_content=content,
    )


def fetch_client_kwargs() -> dict[str, Any]:
    """测试与文档参考：抓取器的网络客户端配置。"""
    return {
        "follow_redirects": True,
        "max_redirects": MAX_REDIRECTS,
        "timeout": DEFAULT_TIMEOUT_SECONDS,
        "headers": {"User-Agent": USER_AGENT},
    }
