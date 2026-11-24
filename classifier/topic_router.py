from __future__ import annotations

import re
import unicodedata
from typing import Dict, List, Optional

from classifier.catalogs import (
    BLOCKED_JUNK_KEYWORDS,
    CATEGORY_KEYWORDS,
    OFFICIAL_TOPICS,
)
from classifier.ml_compliance import evaluate_ml_compliance
from config import settings
from database.logger import get_logger

logger = get_logger("classifier.topic_router")

LOW_APPEAL_HOME_TERMS: List[str] = [
    "esponja", "pano de prato", "pano multiuso", "saco de lixo", "detergente",
    "sabao em po", "amaciante", "agua sanitaria", "desinfetante", "lustrador",
    "lampada comum", "prendedor de roupa", "cabide", "pote plastico",
    "pilha alcalina", "pilhas", "palito de dente", "guardanapo", "papel toalha",
    "papel aluminio", "filme pvc",
]


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.lower())
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", clean).strip()


def _match_word(norm_text: str, kw: str) -> bool:
    norm_kw = _normalize(kw)
    if not norm_kw:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(norm_kw)}(?![a-z0-9])", norm_text))


def _score_category(norm_title: str, keywords: List[str]) -> int:
    score = 0
    for kw in keywords:
        if _match_word(norm_title, kw):
            score += 2 if " " in kw else 1
    return score


def classify_offer_topic(
    title: str,
    discount_pct: int = 0,
    coupon: Optional[str] = None,
    forced_food_check: bool = False,
    price: Optional[float] = None,
    url: Optional[str] = None,
    condition: Optional[str] = None,
    seller_reputation: Optional[str] = None,
    category_hint: Optional[str] = None,
) -> Optional[str]:
    if not title or not title.strip():
        return None

    compliance = evaluate_ml_compliance(
        title=title,
        url=url,
        condition=condition,
        seller_reputation=seller_reputation,
    )
    if not compliance.approved:
        logger.debug(f"Oferta bloqueada pelo Compliance ML: '{title}' ({compliance.reason})")
        return None

    norm_title = _normalize(title)

    for junk in BLOCKED_JUNK_KEYWORDS:
        if _match_word(norm_title, junk):
            logger.debug(f"Oferta bloqueada (item sem apelo/restrito): '{title}'")
            return None

    scores: Dict[str, int] = {}
    for cat_key, kw_list in CATEGORY_KEYWORDS.items():
        sc = _score_category(norm_title, kw_list)
        if sc > 0:
            scores[cat_key] = sc

    best_category: Optional[str] = None
    if scores:
        best_category = max(scores.items(), key=lambda kv: kv[1])[0]
    elif category_hint and category_hint in OFFICIAL_TOPICS and category_hint != "ofertas_bugs":
        best_category = category_hint

    is_low_appeal_home = any(_match_word(norm_title, t) for t in LOW_APPEAL_HOME_TERMS)
    price_val = float(price) if price is not None else 0.0
    meets_bug_price = price_val <= 0 or price_val >= settings.bug_min_price

    if discount_pct >= settings.bug_discount_pct and meets_bug_price and not is_low_appeal_home:
        return "ofertas_bugs"

    if best_category:
        return best_category

    if coupon and discount_pct >= settings.min_discount_pct and meets_bug_price and not is_low_appeal_home:
        return "ofertas_bugs"

    return None
