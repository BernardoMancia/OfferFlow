from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

from classifier.catalogs import (
    ML_BLOCKED_FOOD_BEVERAGE,
    ML_BLOCKED_LIVE_ANIMALS,
    ML_BLOCKED_MEDICAL_PHARMA,
    ML_BLOCKED_PROHIBITED_CATEGORIES,
    ML_BLOCKED_USED_TERMS,
    ML_GENERIC_URL_PATTERNS,
    NON_FOOD_SAFE_EQUIPMENT,
)


@dataclass
class MLComplianceResult:
    approved: bool
    reason: str
    normalized_condition: str = "new"
    normalized_reputation: Optional[str] = None


def _normalize_text(text: str) -> str:
    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    clean = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", clean).strip()


def _contains_term(norm_text: str, term: str) -> bool:
    norm_term = _normalize_text(term)
    if not norm_term:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(norm_term)}(?![a-z0-9])"
    return bool(re.search(pattern, norm_text))


def _is_ml_domain(url: str) -> bool:
    if not url:
        return False
    host = (urlparse(url).netloc or "").lower()
    return (
        "mercadolivre.com" in host
        or "mercadolibre.com" in host
        or "meli.la" in host
        or "mlstatic.com" in host
    )


def is_valid_ml_product_or_list_url(url: str) -> bool:
    if not url or not _is_ml_domain(url):
        return False
    low = url.strip().lower()
    for pat in ML_GENERIC_URL_PATTERNS:
        if re.search(pat, low):
            return False
    if any(
        marker in low
        for marker in (
            "/p/mlb",
            "mlb-",
            "mlb_",
            "/up/mlbu",
            "/sec/",
            "meli.la/",
            "/ofertas",
            "/mais-vendidos/",
            "lista.mercadolivre.com.br/",
        )
    ):
        return True
    return False


def normalize_seller_reputation(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    low = _normalize_text(raw)
    if any(k in low for k in ("5_green", "4_light_green", "green", "verde", "mercadolider", "platinum", "gold", "loja oficial", "official")):
        return "green"
    if any(k in low for k in ("3_yellow", "yellow", "amarelo", "amarela")):
        return "yellow"
    if any(k in low for k in ("2_orange", "orange", "laranja")):
        return "orange"
    if any(k in low for k in ("1_red", "red", "vermelho", "vermelha", "sem reputacao", "baixa")):
        return "red"
    return None


def normalize_condition(raw: Optional[str], title: str = "") -> str:
    low_raw = _normalize_text(raw or "")
    low_title = _normalize_text(title)
    if any(k in low_raw for k in ("recondicionado", "refurbished", "reembalado")):
        return "refurbished"
    if any(k in low_raw for k in ("usado", "used", "seminovo")):
        return "used"
    for term in ML_BLOCKED_USED_TERMS:
        if _contains_term(low_title, term):
            return "used"
    if any(_contains_term(low_title, t) for t in ("recondicionado", "refurbished")):
        return "refurbished"
    return "new"


def evaluate_ml_compliance(
    title: str,
    url: Optional[str] = None,
    condition: Optional[str] = None,
    seller_reputation: Optional[str] = None,
    category_key: Optional[str] = None,
) -> MLComplianceResult:
    if url is not None and not is_valid_ml_product_or_list_url(url):
        return MLComplianceResult(
            approved=False,
            reason="URL fora do Mercado Livre ou página genérica/proibida pelo Programa de Afiliados.",
        )

    norm_title = _normalize_text(title)
    if not norm_title:
        return MLComplianceResult(approved=False, reason="Título vazio.")

    norm_cond = normalize_condition(condition, title=title)
    if norm_cond == "used":
        return MLComplianceResult(
            approved=False,
            reason="Produto usado não é permitido no Programa de Afiliados do Mercado Livre.",
            normalized_condition="used",
        )

    norm_rep = normalize_seller_reputation(seller_reputation)
    if norm_rep in ("red", "orange"):
        return MLComplianceResult(
            approved=False,
            reason=f"Reputação de vendedor '{norm_rep}' bloqueada (exigido Amarelo ou Verde).",
            normalized_condition=norm_cond,
            normalized_reputation=norm_rep,
        )

    for term in ML_BLOCKED_MEDICAL_PHARMA:
        if _contains_term(norm_title, term):
            return MLComplianceResult(
                approved=False,
                reason=f"Produto médico/farmacêutico bloqueado ('{term}').",
                normalized_condition=norm_cond,
                normalized_reputation=norm_rep,
            )

    for term in ML_BLOCKED_LIVE_ANIMALS:
        if _contains_term(norm_title, term):
            return MLComplianceResult(
                approved=False,
                reason=f"Comercialização de animais vivos proibida ('{term}').",
                normalized_condition=norm_cond,
                normalized_reputation=norm_rep,
            )

    for term in ML_BLOCKED_PROHIBITED_CATEGORIES:
        if _contains_term(norm_title, term):
            return MLComplianceResult(
                approved=False,
                reason=f"Categoria não elegível no Programa de Afiliados ML ('{term}').",
                normalized_condition=norm_cond,
                normalized_reputation=norm_rep,
            )

    is_safe_equipment = any(_contains_term(norm_title, eq) for eq in NON_FOOD_SAFE_EQUIPMENT)
    if not is_safe_equipment:
        for term in ML_BLOCKED_FOOD_BEVERAGE:
            if _contains_term(norm_title, term):
                return MLComplianceResult(
                    approved=False,
                    reason=f"Alimentos e bebidas não geram ganhos de afiliado no ML ('{term}').",
                    normalized_condition=norm_cond,
                    normalized_reputation=norm_rep,
                )

    is_book = any(
        _contains_term(norm_title, kw)
        for kw in ("livro", "box livros", "hq", "quadrinho", "manga", "revista", "gibi")
    )
    if is_book and norm_cond != "new":
        return MLComplianceResult(
            approved=False,
            reason="Livros, revistas e quadrinhos são válidos apenas para produtos novos.",
            normalized_condition=norm_cond,
            normalized_reputation=norm_rep,
        )

    return MLComplianceResult(
        approved=True,
        reason="Aprovado no padrão oficial do Programa de Afiliados do Mercado Livre.",
        normalized_condition=norm_cond,
        normalized_reputation=norm_rep,
    )
