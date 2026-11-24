from __future__ import annotations

import json
import re
from typing import List, Optional
from bs4 import BeautifulSoup, Tag

from classifier.ml_compliance import normalize_condition, normalize_seller_reputation
from config import settings
from database.logger import get_logger
from scrapers.base import BaseScraper, ScrapedOffer, parse_brl_price

logger = get_logger("scrapers.ml_offers")

ML_OFFERS_URLS = [
    "https://www.mercadolivre.com.br/ofertas",
    "https://www.mercadolivre.com.br/ofertas?promotion_type=LIGHTNING_DEAL",
    "https://www.mercadolivre.com.br/supermercado/market/higiene-e-cuidados-pessoais",
    "https://www.mercadolivre.com.br/supermercado/market/bebes-e-criancas",
    "https://www.mercadolivre.com.br/supermercado/market/utilidades",
    "https://www.mercadolivre.com.br/ofertas/supermercado",
]


def _extract_andes_amount(container: Optional[Tag]) -> Optional[float]:
    if container is None:
        return None

    aria = container.get("aria-label") or ""
    if aria:
        m = re.search(
            r"(\d[\d.]*)\s*reais(?:\s*com\s*(\d{1,2})\s*centavos)?",
            str(aria),
            re.I,
        )
        if m:
            reais = m.group(1).replace(".", "")
            cents = m.group(2) or "00"
            try:
                return float(f"{reais}.{cents.zfill(2)}")
            except ValueError:
                pass

    frac_el = container.select_one(".andes-money-amount__fraction, .price-tag-fraction")
    if not frac_el:
        return parse_brl_price(container.get_text(" ", strip=True))

    frac_text = frac_el.get_text(strip=True).replace(".", "").replace(",", "")
    cents_el = container.select_one(".andes-money-amount__cents, .price-tag-cents")
    cents_text = cents_el.get_text(strip=True) if cents_el else "00"
    cents_text = re.sub(r"\D", "", cents_text)[:2].zfill(2)

    try:
        val = float(f"{frac_text}.{cents_text}")
        return val if val > 0 else None
    except ValueError:
        return None


def _extract_high_res_image(card: Tag) -> Optional[str]:
    img = card.select_one("img")
    if not img:
        return None
    for attr in ("data-src", "src", "srcset"):
        raw = img.get(attr)
        if raw and isinstance(raw, str):
            url = raw.split()[0].strip()
            if url.startswith("http") and "data:image" not in url:
                url = re.sub(r"-[IWSV]\.(webp|jpg|png)$", r"-O.\1", url)
                return url
    return None


def _extract_rating_and_reviews(card: Tag) -> tuple[Optional[float], Optional[int]]:
    rating: Optional[float] = None
    reviews_count: Optional[int] = None

    rating_el = card.select_one(
        ".poly-reviews__rating, .ui-search-reviews__rating-number, "
        ".ui-pdp-review__rating"
    )
    if rating_el:
        m_rat = re.search(r"(\d[.,]\d)", rating_el.get_text(" ", strip=True))
        if m_rat:
            try:
                val = float(m_rat.group(1).replace(",", "."))
                if 1.0 <= val <= 5.0:
                    rating = val
            except ValueError:
                pass

    rev_el = card.select_one(
        ".poly-reviews__total, .ui-search-reviews__amount, "
        ".ui-pdp-review__amount"
    )
    if rev_el:
        rev_text = rev_el.get_text(" ", strip=True).lower()
        m_mil = re.search(r"(\d+(?:[.,]\d+)?)\s*mil", rev_text)
        if m_mil:
            try:
                reviews_count = int(float(m_mil.group(1).replace(",", ".")) * 1000)
            except ValueError:
                pass
        else:
            digits = re.sub(r"\D", "", rev_text)
            if digits:
                try:
                    reviews_count = int(digits)
                except ValueError:
                    pass

    return rating, reviews_count


def _extract_condition_from_node(node: Tag, title: str = "", raw_html: str = "") -> str:
    sub_el = node.select_one(
        ".ui-pdp-subtitle, .poly-component__condition, .ui-search-item__condition"
    )
    if sub_el:
        sub_text = sub_el.get_text(" ", strip=True)
        cond = normalize_condition(sub_text, title=title)
        if cond != "new":
            return cond

    if raw_html:
        m_ld = re.search(r"schema\.org/(UsedCondition|RefurbishedCondition|NewCondition)", raw_html, re.I)
        if m_ld:
            tok = m_ld.group(1).lower()
            if "used" in tok:
                return "used"
            if "refurbished" in tok:
                return "refurbished"
            return "new"

    card_text = node.get_text(" ", strip=True)
    if re.search(r"\brecondicionado\b", card_text, re.I):
        return "refurbished"
    if re.search(r"\busado\b", card_text, re.I):
        return "used"
    return normalize_condition(None, title=title)


def _extract_seller_reputation(soup: Tag, raw_html: str = "") -> Optional[str]:
    thermo = soup.select_one("ul.ui-thermometer[value], .ui-thermometer[value]")
    if thermo and thermo.get("value"):
        val = str(thermo.get("value")).strip()
        if val in ("5", "4"):
            return "green"
        if val == "3":
            return "yellow"
        if val == "2":
            return "orange"
        if val == "1":
            return "red"

    if raw_html:
        m_lvl = re.search(
            r'"(?:level_id|thermometer_level|reputation_level)"\s*:\s*"(5_green|4_light_green|3_yellow|2_orange|1_red)"',
            raw_html,
            re.I,
        )
        if m_lvl:
            return normalize_seller_reputation(m_lvl.group(1))

    seller_el = soup.select_one(
        ".ui-pdp-seller__header__title, .ui-seller-info__status-info, "
        ".poly-component__seller, .ui-pdp-seller__status-info"
    )
    if seller_el:
        txt = seller_el.get_text(" ", strip=True)
        rep = normalize_seller_reputation(txt)
        if rep:
            return rep
        if re.search(r"loja\s+oficial|mercadol[ií]der|por\s+mercado\s+livre", txt, re.I):
            return "green"

    return None


def parse_ml_cards(
    html_content: str,
    source_name: str = "ml_offers",
    require_previous_price: bool = True,
    min_discount_pct: int = 20,
    min_rating: Optional[float] = None,
    category_hint: Optional[str] = None,
) -> List[ScrapedOffer]:
    soup = BeautifulSoup(html_content, "lxml")
    cards = soup.select(
        "div.poly-card, li.ui-search-layout__item, div.promotion-item, div.andes-card.poly-card"
    )

    offers: List[ScrapedOffer] = []
    seen_urls: set[str] = set()

    for card in cards:
        title_link = card.select_one(
            "a.poly-component__title, a.ui-search-link__title-card, "
            "a.ui-search-item__group__element, a.promotion-item__link-container"
        )
        title_el = (
            card.select_one(
                ".poly-component__title, .ui-search-item__title, .promotion-item__title"
            )
            or title_link
        )
        if not title_el:
            continue

        title = title_el.get_text(" ", strip=True)
        link = ""
        if title_link and title_link.get("href"):
            link = str(title_link.get("href")).strip()
        else:
            any_a = card.select_one("a[href*='mercadolivre.com.br'], a[href*='MLB']")
            if any_a and any_a.get("href"):
                link = str(any_a.get("href")).strip()

        if not title or not link or not link.startswith("http"):
            continue

        base_link = link.split("#")[0].split("?")[0]
        if base_link in seen_urls:
            continue

        condition = _extract_condition_from_node(card, title=title)
        if condition == "used":
            continue

        seller_rep = _extract_seller_reputation(card)
        if seller_rep in ("red", "orange"):
            continue

        prev_el = card.select_one(
            "s.andes-money-amount--previous, .poly-price__current s, "
            ".ui-search-price__original-value, .promotion-item__oldprice"
        )
        original_price = _extract_andes_amount(prev_el)

        current_container = card.select_one(
            ".poly-price__current .andes-money-amount:not(.andes-money-amount--previous), "
            ".ui-search-price__second-line .andes-money-amount, "
            ".promotion-item__price"
        )
        if not current_container:
            for cand in card.select(".andes-money-amount"):
                classes = cand.get("class") or []
                if "andes-money-amount--previous" not in classes and cand.name != "s":
                    current_container = cand
                    break

        price = _extract_andes_amount(current_container)
        if not price or price <= 0:
            continue

        discount_pct = 0
        disc_el = card.select_one(
            ".andes-money-amount__discount, .ui-search-price__discount, .promotion-item__discount-text"
        )
        if disc_el:
            m = re.search(r"(\d{1,2})\s*%", disc_el.get_text(" ", strip=True))
            if m:
                discount_pct = int(m.group(1))

        if discount_pct <= 0 and original_price and original_price > price:
            discount_pct = round(((original_price - price) / original_price) * 100)

        if not original_price and discount_pct > 0 and discount_pct < 95:
            original_price = round(price / (1.0 - (discount_pct / 100.0)), 2)

        if require_previous_price and not original_price:
            continue
        if discount_pct < min_discount_pct:
            continue

        is_full = bool(
            card.select_one(
                ".poly-component__shipped-from [aria-label*='FULL' i], "
                "svg.ui-pdp-icon--full, .ui-search-item__fulfillment, "
                "[class*='full' i]"
            )
            or re.search(r"\bfull\b", card.get_text(" ", strip=True), re.I)
        )

        coupon = None
        coupon_el = card.select_one(".poly-component__coupons, .ui-search-Highlight")
        if coupon_el:
            c_text = coupon_el.get_text(" ", strip=True)
            if "off" in c_text.lower() or "cupom" in c_text.lower():
                coupon = c_text

        installments = None
        inst_el = card.select_one(
            ".poly-price__installments, .ui-search-installments, .promotion-item__installments"
        )
        if inst_el:
            inst_text = re.sub(r"\s+", " ", inst_el.get_text(" ", strip=True)).strip()
            if "sem juros" in inst_text.lower() or re.search(r"\b\d{1,2}x\b", inst_text, re.I):
                installments = inst_text

        image_url = _extract_high_res_image(card)
        rating, reviews_count = _extract_rating_and_reviews(card)
        effective_min_rating = min_rating if min_rating is not None else settings.min_rating
        if rating is not None and 0 < rating < effective_min_rating:
            continue

        seen_urls.add(base_link)

        offers.append(
            ScrapedOffer(
                title=title,
                price=price,
                original_price=original_price,
                discount_pct=discount_pct,
                coupon=coupon,
                installments=installments,
                url=link,
                image_url=image_url,
                store="Mercado Livre",
                is_full=is_full,
                rating=rating,
                reviews_count=reviews_count,
                condition=condition,
                seller_reputation=seller_rep,
                category_hint=category_hint,
                source=source_name,
            )
        )

    return offers


async def scrape_single_product_url(
    raw_url: str,
    coupon: Optional[str] = None,
) -> Optional[ScrapedOffer]:
    from affiliate.url_cleaner import detect_store, unshorten_and_clean_url

    clean_url = await unshorten_and_clean_url(raw_url)
    target_url = clean_url or raw_url

    scraper = BaseScraper(timeout=15.0, max_retries=2)
    html_text = await scraper.fetch_text(target_url)
    if not html_text:
        return None

    soup = BeautifulSoup(html_text, "lxml")
    store_name = detect_store(target_url)

    title = ""
    for sel in (
        "h1.ui-pdp-title",
        "h1[data-testid='heading-product-title']",
    ):
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            title = el.get_text(" ", strip=True)
            break
    if not title:
        og_title = soup.select_one("meta[property='og:title'], meta[name='twitter:title']")
        if og_title and og_title.get("content"):
            title = str(og_title.get("content")).strip()
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)

    title = re.sub(r"\s*\|\s*Mercado\s*Livre.*$", "", title, flags=re.I).strip()
    title = re.sub(r"\s*-\s*R\$\s*[\d.,]+.*$", "", title, flags=re.I).strip()
    if not title:
        return None

    price: Optional[float] = None
    original_price: Optional[float] = None

    ml_price_el = soup.select_one(
        ".ui-pdp-price__second-line .andes-money-amount:not(.andes-money-amount--previous), "
        "div.ui-pdp-price__main-container .andes-money-amount:not(.andes-money-amount--previous)"
    )
    if ml_price_el:
        price = _extract_andes_amount(ml_price_el)

    ml_prev_el = soup.select_one(
        "s.andes-money-amount--previous, .ui-pdp-price__original-value"
    )
    if ml_prev_el:
        original_price = _extract_andes_amount(ml_prev_el)

    if not price:
        meta_price = soup.select_one(
            "meta[property='product:price:amount'], meta[property='og:price:amount'], meta[itemprop='price']"
        )
        if meta_price and meta_price.get("content"):
            price = parse_brl_price(meta_price.get("content"))

    if not price:
        for ld_script in soup.select("script[type='application/ld+json']"):
            try:
                data = json.loads(ld_script.string or "")
                items = data if isinstance(data, list) else [data]
                for obj in items:
                    if not isinstance(obj, dict):
                        continue
                    offers_node = obj.get("offers")
                    if isinstance(offers_node, dict):
                        price = parse_brl_price(offers_node.get("price") or offers_node.get("lowPrice"))
                    elif isinstance(offers_node, list) and offers_node:
                        price = parse_brl_price(offers_node[0].get("price"))
                    if price:
                        break
            except Exception:
                continue

    if not price or price <= 0:
        return None

    image_url = None
    og_img = soup.select_one("meta[property='og:image'], img.ui-pdp-image")
    if og_img:
        raw_img = og_img.get("content") or og_img.get("data-zoom") or og_img.get("src")
        if raw_img and str(raw_img).startswith("http"):
            image_url = re.sub(r"-[IWSV]\.(webp|jpg|png)$", r"-O.\1", str(raw_img).strip())

    installments = None
    inst_el = soup.select_one("#pricing_price_subtitle, .ui-pdp-price__subtitles, .poly-price__installments")
    if inst_el:
        inst_text = re.sub(r"\s+", " ", inst_el.get_text(" ", strip=True)).strip()
        if "sem juros" in inst_text.lower() or re.search(r"\b\d{1,2}x\b", inst_text, re.I):
            installments = inst_text

    is_full = bool(
        soup.select_one("svg.ui-pdp-icon--full, [aria-label*='FULL' i]")
    )
    rating, reviews_count = _extract_rating_and_reviews(soup)
    condition = _extract_condition_from_node(soup, title=title, raw_html=html_text)
    seller_rep = _extract_seller_reputation(soup, raw_html=html_text)

    return ScrapedOffer(
        title=title,
        price=price,
        original_price=original_price,
        coupon=coupon,
        installments=installments,
        url=target_url,
        image_url=image_url,
        store=store_name,
        is_full=is_full,
        rating=rating,
        reviews_count=reviews_count,
        condition=condition,
        seller_reputation=seller_rep,
        source="manual_admin",
    )


async def enrich_offer_from_product_page(
    offer: ScrapedOffer,
    clean_url: str,
) -> ScrapedOffer:
    if not clean_url or "mercadolivre.com" not in clean_url.lower():
        return offer

    if (
        offer.original_price
        and offer.installments
        and offer.image_url
        and offer.seller_reputation
    ):
        return offer

    try:
        scraped = await scrape_single_product_url(clean_url, coupon=offer.coupon)
        if not scraped:
            return offer

        if not offer.original_price:
            if scraped.original_price and scraped.original_price > offer.price:
                offer.original_price = scraped.original_price
            elif scraped.price and scraped.price > offer.price * 1.05:
                offer.original_price = scraped.price

        if offer.original_price and offer.original_price > offer.price > 0:
            offer.discount_pct = round(
                ((offer.original_price - offer.price) / offer.original_price) * 100
            )

        if not offer.installments and scraped.installments:
            offer.installments = scraped.installments
        if not offer.image_url and scraped.image_url:
            offer.image_url = scraped.image_url
        if not offer.rating and scraped.rating:
            offer.rating = scraped.rating
        if not offer.reviews_count and scraped.reviews_count:
            offer.reviews_count = scraped.reviews_count
        if scraped.condition:
            offer.condition = scraped.condition
        if scraped.seller_reputation:
            offer.seller_reputation = scraped.seller_reputation
        if scraped.is_full:
            offer.is_full = True
    except Exception as exc:
        logger.debug(f"Falha silenciosa ao enriquecer oferta {clean_url}: {exc}")

    return offer


_PAUSED_OR_OOS_PATTERNS = (
    "anúncio pausado",
    "anuncio pausado",
    "anúncio finalizado",
    "anuncio finalizado",
    "este produto está indisponível",
    "este produto esta indisponivel",
    "não está disponível",
    "nao esta disponivel",
    "produto esgotado",
    "estoque esgotado",
)


async def validate_live_offer_status(
    url: str,
    expected_price: float,
    has_coupon: bool = False,
    max_price_jump_pct: float = 18.0,
) -> tuple[bool, Optional[float], Optional[float], str]:
    if not url or not url.startswith("http"):
        return True, None, None, "skip"

    lower_url = url.lower()
    if "mercadolivre.com" not in lower_url:
        return False, None, None, "URL fora do Mercado Livre"

    scraper = BaseScraper(timeout=10.0, max_retries=1)
    html_text = await scraper.fetch_text(url)
    if not html_text:
        return True, None, None, "skip_network"

    lower_html = html_text.lower()
    if (
        "suspicious-traffic" in lower_html
        or "account-verification" in lower_html
        or "validatecaptcha" in lower_html
    ):
        return True, None, None, "skip_antibot"

    soup = BeautifulSoup(html_text, "lxml")
    visible_status_text = " ".join(
        el.get_text(" ", strip=True).lower()
        for el in soup.select(
            ".ui-pdp-StatusMessage, .ui-pdp-color--RED, h1, h2"
        )
    )
    for marker in _PAUSED_OR_OOS_PATTERNS:
        if marker in visible_status_text:
            return False, None, None, f"Anúncio indisponível/pausado ('{marker}')"

    live_cond = _extract_condition_from_node(soup, raw_html=html_text)
    if live_cond == "used":
        return False, None, None, "Produto usado bloqueado pelas regras de afiliados ML"

    live_rep = _extract_seller_reputation(soup, raw_html=html_text)
    if live_rep in ("red", "orange"):
        return False, None, None, f"Vendedor com reputação '{live_rep}' bloqueado"

    live_price: Optional[float] = None
    live_orig: Optional[float] = None

    ml_price_el = soup.select_one(
        ".ui-pdp-price__second-line .andes-money-amount:not(.andes-money-amount--previous), "
        "div.ui-pdp-price__main-container .andes-money-amount:not(.andes-money-amount--previous)"
    )
    if ml_price_el:
        live_price = _extract_andes_amount(ml_price_el)
    ml_prev_el = soup.select_one(
        "s.andes-money-amount--previous, .ui-pdp-price__original-value"
    )
    if ml_prev_el:
        live_orig = _extract_andes_amount(ml_prev_el)

    if live_price and live_price > 0 and expected_price > 0 and not has_coupon:
        max_allowed = expected_price * (1.0 + (max_price_jump_pct / 100.0))
        if live_price > max_allowed:
            return (
                False,
                live_price,
                live_orig,
                f"Preço subiu de R$ {expected_price:.2f} para R$ {live_price:.2f}",
            )

    return True, live_price, live_orig, "ok"


class MercadoLivreOffersScraper(BaseScraper):
    async def fetch_offers(
        self, min_discount_pct: Optional[int] = None
    ) -> List[ScrapedOffer]:
        min_disc = (
            min_discount_pct
            if min_discount_pct is not None
            else settings.min_discount_pct
        )
        all_offers: List[ScrapedOffer] = []
        seen_links: set[str] = set()

        for url in ML_OFFERS_URLS:
            html_text = await self.fetch_text(url)
            if not html_text:
                continue
            parsed = parse_ml_cards(
                html_text,
                source_name="ml_offers",
                require_previous_price=True,
                min_discount_pct=min_disc,
            )
            for item in parsed:
                clean_key = item.url.split("?")[0].split("#")[0]
                if clean_key not in seen_links:
                    seen_links.add(clean_key)
                    all_offers.append(item)

        logger.info(
            f"[Frente A - Ofertas ML] {len(all_offers)} ofertas coletadas (desconto >= {min_disc}%)."
        )
        return all_offers
