from __future__ import annotations

import asyncio
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from database.logger import get_logger

logger = get_logger("scrapers.base")

USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
]


@dataclass
class ScrapedOffer:
    title: str
    price: float
    url: str
    original_price: Optional[float] = None
    discount_pct: int = 0
    coupon: Optional[str] = None
    installments: Optional[str] = None
    image_url: Optional[str] = None
    store: str = "Mercado Livre"
    is_full: bool = False
    rating: Optional[float] = None
    reviews_count: Optional[int] = None
    condition: str = "new"
    seller_reputation: Optional[str] = None
    category_hint: Optional[str] = None
    source: str = "scraper"

    def __post_init__(self) -> None:
        if (
            self.discount_pct <= 0
            and self.original_price
            and self.original_price > self.price > 0
        ):
            self.discount_pct = round(
                ((self.original_price - self.price) / self.original_price) * 100
            )


def parse_brl_price(raw: Any) -> Optional[float]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if val > 0 else None

    text = str(raw).strip()
    if not text:
        return None

    match = re.search(
        r"(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?)", text
    )
    if not match:
        return None

    num_str = match.group(1)
    if "," in num_str and "." in num_str:
        num_str = num_str.replace(".", "").replace(",", ".")
    elif re.search(r"\.\d{3}(?!\d)", num_str):
        num_str = num_str.replace(".", "")
    elif "," in num_str:
        num_str = num_str.replace(",", ".")

    try:
        val = float(num_str)
        return val if val > 0 else None
    except ValueError:
        return None


class BaseScraper:
    def __init__(self, timeout: float = 18.0, max_retries: int = 3) -> None:
        self.timeout = timeout
        self.max_retries = max_retries

    def build_headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        }
        if extra:
            headers.update(extra)
        return headers

    async def fetch_text(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        client: Optional[httpx.AsyncClient] = None,
    ) -> Optional[str]:
        owns_client = client is None
        http_client = client or httpx.AsyncClient(
            follow_redirects=True,
            timeout=self.timeout,
        )
        try:
            for attempt in range(1, self.max_retries + 1):
                try:
                    req_headers = self.build_headers(headers)
                    resp = await http_client.get(url, headers=req_headers)
                    if resp.status_code == 200 and resp.text:
                        return resp.text
                    logger.warning(
                        f"[{attempt}/{self.max_retries}] HTTP {resp.status_code} ao buscar {url}"
                    )
                except Exception as exc:
                    logger.warning(
                        f"[{attempt}/{self.max_retries}] Erro de rede em {url}: {exc}"
                    )
                if attempt < self.max_retries:
                    await asyncio.sleep(1.2 * attempt)
            return None
        finally:
            if owns_client:
                await http_client.aclose()
