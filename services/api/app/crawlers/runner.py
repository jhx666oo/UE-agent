"""官网来源抓取器入口：实现统一放在包的 __init__.py，此模块再导出一次，
保证 `from app.crawlers.runner import crawl_source` 与
`from app.crawlers import crawl_source` 两种用法等价。"""

from . import (
    CrawlError,
    CrawlResult,
    USER_AGENT,
    crawl_source,
    extract_readable_text,
    extract_title,
)

__all__ = [
    "CrawlError",
    "CrawlResult",
    "USER_AGENT",
    "crawl_source",
    "extract_readable_text",
    "extract_title",
]

