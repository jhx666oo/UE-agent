"""城市政策与数据来源发现。

发现器只负责把城市名和字段族转换成候选 URL，不负责把 URL 当成事实。
正式来源的信任分流集中在 :func:`classify_source`，这样替换搜索引擎或 AI
提供商时不会影响入场任务和政策抓取链路。
"""

from __future__ import annotations

import html
import os
import re
from collections.abc import Mapping, Sequence
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import parse_qs, quote_plus, unquote, urlsplit

import httpx


class DiscoveryError(Exception):
    """来源发现不可用或返回内容无法解析。"""


class SourceDiscoveryProvider(Protocol):
    def discover(
        self, city_name: str, field_families: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]: ...


class UnconfiguredDiscoveryProvider:
    """测试/离线仓储使用的显式空适配器，不访问外部网络。"""

    def discover(
        self, city_name: str, field_families: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        raise DiscoveryError("未配置城市来源发现器，暂时无法自动发现官网来源")


def city_id_from_name(city_name: str) -> str:
    """把用户输入的城市名变成稳定、可读的城市标识。"""
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", city_name.strip().lower())
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    return normalized[:80] or "unknown-city"


def classify_source(url: str, title: str | None = None) -> str:
    """把发现结果分成 official / candidate / rejected。

    `.gov.cn` 是最强的官方信号；其他域名只有在域名或标题明确包含政府部门
    关键词时才会进入正式来源。普通文章不丢失，而是进入候选区供业务确认。
    """
    raw_url = str(url or "").strip()
    try:
        parsed = urlsplit(raw_url)
    except ValueError:
        return "rejected"
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "rejected"
    hostname = parsed.hostname.lower().rstrip(".")
    title_text = str(title or "").lower()
    official_host_tokens = (
        "gov", "ybj", "tjj", "mzj", "rsj", "nhsa", "med", "statistics",
        "government", "医保", "统计", "民政", "人社",
    )
    official_title_tokens = ("政府", "医保局", "统计局", "民政局", "人社局", "政务")
    if os.getenv("UE_AGENT_E2E_ALLOW_PRIVATE") == "1" and hostname in {"127.0.0.1", "localhost"} and any(
        token in title_text for token in official_title_tokens
    ):
        return "official"
    if hostname.endswith(".gov.cn"):
        return "official"
    if any(token in hostname for token in official_host_tokens) and any(
        token in title_text for token in official_title_tokens
    ):
        return "official"
    return "candidate"


class _SearchResultParser(HTMLParser):
    """兼容常见搜索页的最小链接提取器，不依赖 BeautifulSoup。"""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.results: list[dict[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attributes = dict(attrs)
        href = attributes.get("href")
        if href:
            self._href = href
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        title = re.sub(r"\s+", " ", " ".join(self._text)).strip()
        self.results.append({"url": html.unescape(self._href), "title": title})
        self._href = None
        self._text = []


def _unwrap_result_url(raw_url: str) -> str | None:
    value = unquote(html.unescape(raw_url.strip()))
    if value.startswith("//"):
        value = "https:" + value
    if value.startswith("/"):
        query = parse_qs(urlsplit(value).query)
        value = (query.get("uddg") or query.get("url") or [""])[0]
    try:
        parsed = urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return value


class WebSearchDiscoveryProvider:
    """通过配置的搜索页发现公开 URL。

    `UE_AGENT_DISCOVERY_SEARCH_URL` 是包含 `{query}` 的 URL 模板，例如：
    `https://www.baidu.com/s?wd={query}`。真实 API 未配置时默认使用百度公开搜索页；
    测试仓储会显式注入空适配器，避免测试和离线单元测试访问外部网络。
    """

    def __init__(self, search_url: str | None = None, *, timeout_seconds: float = 8, max_results: int = 5):
        self.search_url = (search_url if search_url is not None else os.getenv(
            "UE_AGENT_DISCOVERY_SEARCH_URL", "https://www.baidu.com/s?wd={query}"
        )).strip()
        self.timeout_seconds = timeout_seconds
        self.max_results = max(1, min(max_results, 20))

    def discover(
        self, city_name: str, field_families: Sequence[Mapping[str, Any]]
    ) -> list[dict[str, Any]]:
        if not self.search_url:
            raise DiscoveryError("未配置 UE_AGENT_DISCOVERY_SEARCH_URL，暂时无法自动发现官网来源")
        all_results: list[dict[str, Any]] = []
        seen: set[str] = set()
        headers = {"User-Agent": "UE-Agent-Demo/0.1 (+local-policy-discovery)"}
        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True, headers=headers) as client:
            for family in field_families:
                template = str(family.get("queryTemplate") or "{城市} 长期护理保险 政策")
                query = template.replace("{城市}", city_name).replace("{city}", city_name)
                target = self.search_url.replace("{query}", quote_plus(query))
                try:
                    response = client.get(target)
                    response.raise_for_status()
                except httpx.HTTPError as error:
                    raise DiscoveryError(f"搜索请求失败：{error}") from error
                parser = _SearchResultParser()
                parser.feed(response.text)
                accepted = 0
                for item in parser.results:
                    url = _unwrap_result_url(item["url"])
                    if not url or url in seen:
                        continue
                    seen.add(url)
                    all_results.append(
                        {
                            "url": url,
                            "title": item["title"] or url,
                            "summary": None,
                            "query": query,
                            "family": family.get("family"),
                            "targetFields": list(family.get("fields") or []),
                            "origin": "web_search",
                            "relevance": 0.9 if classify_source(url, item["title"]) == "official" else 0.55,
                        }
                    )
                    accepted += 1
                    if accepted >= self.max_results:
                        break
        return all_results
