from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Optional, Tuple
from urllib.parse import parse_qs, unquote, urlencode, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from database.logger import get_logger

logger = get_logger("affiliate.url_cleaner")


AGGREGATOR_DOMAINS = (
    "promobit.com.br",
    "pelando.com.br",
    "dpl.pelando.com.br",
    "gatry.com",
)


TRACKING_PARAMS = {
    "matt_tool",
    "matt_word",
    "matt_source",
    "matt_campaign",
    "matt_account",
    "matt_event_ts",
    "matt_d2id",
    "matt_tracing_id",
    "matt_tool_id",
    "tracking_id",
    "reco_item_pos",
    "reco_backend",
    "reco_backend_type",
    "reco_client",
    "reco_id",
    "c_id",
    "c_uid",
    "sid",
    "wid",
    " tag",
    "tag",
    "linkcode",
    "linkid",
    "ascsubtag",
    " creative",
    "creative",
    "creativeasin",
    "social_share",
    "btn_type",
    "btn_ref",
    "ref_",
    "ref",
    "psc",
    "qid",
    "sr",
    "dib",
    "dib_tag",
    "sprefix",
    "crid",
    "keywords",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "aff_id",
    "aff_platform",
    "aff_trace_key",
    "aff_fcid",
    "aff_fsk",
    "aff_short_key",
    "af_siteid",
    "pid",
    "subid",
    "sub_id",
    "partner_id",
    "mmp_pid",
    "uls_trackid",
    "gads_t_sig",
    "sp_atk",
    "xptdk",
    "__mobile__",
    "exp_group",
    "fbclid",
    "gclid",
    "msclkid",
    "pdp_filters",
    "position",
    "search_layout",
    "type",
    "is_advertising",
    "deal_print_id",
    "promotion_type",
}

EMBEDDED_URL_KEYS = (
    "url",
    "u",
    "redirect",
    "redirect_url",
    "dest",
    "destination",
    "target",
    "ued",
    "dl",
    "to",
)

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


def is_aggregator_url(url: str) -> bool:

    if not url:
        return True
    host = urlparse(url).netloc.lower()
    return any(host == d or host.endswith(f".{d}") for d in AGGREGATOR_DOMAINS)


def extract_pelando_jwt_url(url: str) -> Optional[str]:
\
\
\
\

    if "dpl.pelando.com.br/r/" not in url:
        return None
    try:
        jwt_part = url.split("/r/", 1)[1].split("?", 1)[0].split("#", 1)[0]
        parts = jwt_part.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1] + "=" * (-len(parts[1]) % 4)
            decoded = json.loads(
                base64.urlsafe_b64decode(payload_b64).decode("utf-8", errors="ignore")
            )
            if isinstance(decoded, dict):
                target = str(decoded.get("url") or "").strip()
                if target.startswith(("http://", "https://")):
                    return target
    except Exception as exc:
        logger.debug(f"Falha ao decodificar JWT do Pelando ({url}): {exc}")
    return None


def extract_embedded_destination(url: str) -> str:
\
\
\

    current = url.strip()
    for _ in range(4):
        jwt_target = extract_pelando_jwt_url(current)
        if jwt_target and jwt_target != current:
            current = jwt_target
            continue

        parsed = urlparse(current)
        qs = parse_qs(parsed.query)
        found = None
        for key in EMBEDDED_URL_KEYS:
            for q_key, values in qs.items():
                if q_key.lower() == key and values:
                    candidate = unquote(values[0]).strip()
                    if candidate.startswith(("http://", "https://")):
                        found = candidate
                        break
            if found:
                break
        if found and found != current:
            current = found
        else:
            break
    return current


def clean_store_url(url: str) -> str:
\
\
\

    if not url:
        return ""

    extracted = extract_embedded_destination(url)
    parsed = urlparse(extracted)
    host = parsed.netloc.lower()


    if "mercadolivre.com" in host or "mercadolibre.com" in host:
        clean_path = parsed.path
        return urlunparse((parsed.scheme or "https", parsed.netloc, clean_path, "", "", ""))


    if "shopee.com" in host:
        return urlunparse((parsed.scheme or "https", parsed.netloc, parsed.path, "", "", ""))


    netloc = parsed.netloc
    if host == "m.magazineluiza.com.br":
        netloc = "www.magazineluiza.com.br"


    qs = parse_qs(parsed.query, keep_blank_values=False)
    filtered_qs = {
        k: v
        for k, v in qs.items()
        if k.lower().strip() not in TRACKING_PARAMS
        and not k.lower().startswith(
            ("utm_", "aff_", "matt_", "reco_", "pf_rd_", "pd_rd_", "uls_", "gads_")
        )
    }
    new_query = urlencode(filtered_qs, doseq=True)
    return urlunparse((parsed.scheme or "https", netloc, parsed.path, "", new_query, ""))


def _needs_further_unshortening(url: str) -> bool:

    if not url:
        return False
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path
    if is_aggregator_url(url):
        return True
    if any(
        short_host in host
        for short_host in (
            "meli.la",
            "amzn.to",
            "a.co",
            "link.amazon",
            "shp.ee",
            "s.click.aliexpress",
            "bit.ly",
            "tidd.ly",
            "compre.vc",
            "divulgador.inteligente",
        )
    ):
        return True
    if ("mercadolivre.com" in host or "mercadolibre.com" in host) and (
        "/sec/" in path or "/social/" in path
    ):
        return True
    return False


async def unshorten_and_enrich_url(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 12.0,
) -> Tuple[str, Optional[str], Optional[str]]:
\
\
\
\

    if not url:
        return "", None, None

    initial = extract_embedded_destination(url)
    parsed = urlparse(initial)
    host = parsed.netloc.lower()


    if (
        ("mercadolivre.com.br" in host or "produto.mercadolivre.com.br" in host)
        and "/sec/" not in parsed.path
        and "/social/" not in parsed.path
        and ("MLB" in parsed.path.upper())
    ):
        return clean_store_url(initial), None, "Mercado Livre"


    if not _needs_further_unshortening(initial):
        cleaned = clean_store_url(initial)
        return cleaned, None, detect_store(cleaned)

    owns_client = client is None
    http_client = client or httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        follow_redirects=True,
        timeout=timeout,
    )

    discovered_coupon: Optional[str] = None
    discovered_store: Optional[str] = None

    try:
        response = await http_client.get(
            initial, headers=DEFAULT_HEADERS, follow_redirects=True
        )
        final_url = str(response.url)
        body = response.text or ""


        if "pelando.com.br/d/" in final_url and body:
            soup_pel = BeautifulSoup(body, "lxml")
            clickout_a = soup_pel.select_one(
                "a[data-clickout='true'][href], a[href*='dpl.pelando.com.br/r/']"
            )
            if clickout_a:
                raw_code = str(clickout_a.get("data-code") or "").strip()
                if raw_code and raw_code.lower() != "none":
                    discovered_coupon = raw_code
                raw_store = str(clickout_a.get("data-store-name") or "").strip()
                if raw_store:
                    discovered_store = raw_store

                clickout_href = str(clickout_a.get("href") or "").strip()
                decoded_url = extract_embedded_destination(clickout_href)
                if decoded_url and not is_aggregator_url(decoded_url):
                    final_url = decoded_url
                    if _needs_further_unshortening(final_url):
                        resp2 = await http_client.get(
                            final_url, headers=DEFAULT_HEADERS, follow_redirects=True
                        )
                        final_url = str(resp2.url)
                        body = resp2.text or ""


        if "promobit.com.br/Redirect/to" in final_url and body:
            m_js = re.search(r"l\s*=\s*['\"](https?://[^'\"]+)['\"]", body)
            if m_js:
                hop_url = extract_embedded_destination(m_js.group(1))
                response = await http_client.get(
                    hop_url, headers=DEFAULT_HEADERS, follow_redirects=True
                )
                final_url = str(response.url)
                body = response.text or ""


        if (
            "/sec/" in final_url
            or "/social/" in final_url
            or "meli.la" in final_url
        ) and body:
            soup = BeautifulSoup(body, "lxml")
            for a_el in soup.find_all("a", href=True):
                href = str(a_el.get("href") or "")
                if (
                    "/p/MLB" in href
                    or "/up/MLBU" in href
                    or "produto.mercadolivre.com.br/MLB" in href
                ):
                    final_url = href
                    break

        cleaned = clean_store_url(final_url)
        return cleaned, discovered_coupon, discovered_store
    except Exception as exc:
        logger.debug(f"Não foi possível seguir redirecionamento de {initial}: {exc}")
        return clean_store_url(initial), discovered_coupon, discovered_store
    finally:
        if owns_client:
            await http_client.aclose()


async def unshorten_and_clean_url(
    url: str,
    client: Optional[httpx.AsyncClient] = None,
    timeout: float = 12.0,
) -> str:
\
\

    cleaned, _, _ = await unshorten_and_enrich_url(
        url, client=client, timeout=timeout
    )
    return cleaned


def detect_store(url: str) -> str:

    host = urlparse(url).netloc.lower()
    if any(d in host for d in ("mercadolivre", "mercadolibre", "meli.la")):
        return "Mercado Livre"
    if any(d in host for d in ("amazon.", "amzn.to", "a.co", "link.amazon")):
        return "Amazon"
    if "shopee." in host or "shp.ee" in host:
        return "Shopee"
    if "magazineluiza." in host or "magalu." in host or "magazinevoce." in host:
        return "Magalu"
    if "kabum.com" in host:
        return "KaBuM!"
    if "aliexpress." in host or "s.click.aliexpress" in host:
        return "AliExpress"
    if "casasbahia." in host:
        return "Casas Bahia"
    if "fastshop." in host:
        return "Fast Shop"
    if "americanas." in host:
        return "Americanas"
    if "netshoes." in host:
        return "Netshoes"
    if "centauro." in host:
        return "Centauro"
    if "nike.com" in host:
        return "Nike"
    if "adidas.com" in host:
        return "Adidas"
    if "samsung.com" in host:
        return "Samsung"
    if "lg.com" in host:
        return "LG"
    if "steampowered.com" in host or "steamcommunity.com" in host:
        return "Steam"
    if "nuuvem.com" in host:
        return "Nuuvem"
    if "instant-gaming.com" in host:
        return "Instant Gaming"
    if "epicgames.com" in host:
        return "Epic Games"
    return "Loja Oficial"


def is_mercadolivre_url(url: str) -> bool:

    host = urlparse(url).netloc.lower()
    return any(d in host for d in ("mercadolivre.com", "mercadolibre.com", "meli.la"))


def extract_mlb_code(url: str) -> Optional[str]:

    match = re.search(r"\b(MLBU?)[-]?(\d{6,14})\b", url, flags=re.IGNORECASE)
    if match:
        prefix = match.group(1).upper()
        return f"{prefix}{match.group(2)}"
    return None


def extract_offer_key(url: str, title: str = "") -> str:
\
\
\
\
\

    clean = clean_store_url(url)

    mlb = extract_mlb_code(clean)
    if mlb:
        return f"ml:{mlb}"

    asin_match = re.search(
        r"(?:/dp/|/gp/product/)([A-Z0-9]{10})\b", clean, flags=re.IGNORECASE
    )
    if asin_match:
        return f"amz:{asin_match.group(1).upper()}"

    basis = clean if clean else title.strip().lower()
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:14]
    store_prefix = detect_store(clean).lower().replace(" ", "")[:6] or "item"
    return f"{store_prefix}:{digest}"
