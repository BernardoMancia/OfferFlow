from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional

from config import (
    BLACKLIST_NACIONAIS,
    WHITELIST_MARCAS_COMIDAS,
    WHITELIST_MARCAS_DOCES,
    WHITELIST_ORIGENS,
)
from database.logger import get_logger

logger = get_logger("classifier.imported_filter")


def normalize_text(text: str) -> str:

    if not text:
        return ""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _contains_any_term(normalized_text: str, terms: Iterable[str]) -> Optional[str]:
\
\
\

    for raw_term in terms:
        norm_term = normalize_text(raw_term).strip()
        if not norm_term:
            continue
        pattern = rf"(?<![a-z0-9]){re.escape(norm_term)}(?![a-z0-9])"
        if re.search(pattern, normalized_text):
            return raw_term
    return None


NON_FOOD_APPLIANCE_TERMS = (
    "cafeteira",
    "panela eletrica",
    "panela de arroz",
    "liquidificador",
    "batedeira",
    "airfryer",
    "air fryer",
    "fritadeira",
    "chaleira",
    "torradeira",
    "pipoqueira",
    "perfume",
    "eau de parfum",
    "eau de toilette",
    "colonia",
    "hidratante",
    "shampoo",
    "condicionador",
    "mascara capilar",
    "sabonete",
    "esfoliante",
    "batom",
    "gloss",
    "camiseta",
    "camisa",
    "moletom",
    "tenis",
    "chinelo",
    "caneca",
    "copo termico",
    "garrafa termica",
    "pote hermetico",
    "organizador",
    "brinquedo",
    "funko",
    "difusor",
    "aromatizador",
    "odorizador",
    "home spray",
    "vela aromatica",
    "incenso",
    "coala",
    "jaqueta",
    "fantasia",
)


SWEET_KEYWORDS = (
    "chocolate",
    "chocolates",
    "bombom",
    "bombons",
    "tablete",
    "barra de chocolate",
    "trufa",
    "trufas",
    "alfajor",
    "alfajores",
    "biscoito",
    "biscoitos",
    "bolacha",
    "bolachas",
    "cookie",
    "cookies",
    "wafer",
    "wafers",
    "stroopwafel",
    "bala",
    "balas",
    "goma",
    "fini",
    "gelatina",
    "marshmallow",
    "chiclete",
    "chicletes",
    "trident",
    "pirulito",
    "pirulitos",
    "doce de leite",
    "dulce de leche",
    "nutella",
    "creme de avela",
    "mochi",
    "pocky",
    "pepero",
    "torrone",
    "caramelo",
    "fudge",
    "brownie",
    "panettone",
    "panetone",
    "confeito",
    "confeitos",
    "granulado",
    "cobertura",
    "chantilly",
    "geleia",
    "drageado",
    "paçoca",
    "pacoca",
    "goiabada",
    "chocotone",
    "chocottone",
    "bolinho",
    "recheio",
    "ganache",
    "bananinha",
    "mel puro",
    "sache de mel",
    "barra de cereal",
    "barra de cereais",
    "confeite",
)


SAVORY_DRINK_KEYWORDS = (
    "lamen",
    "ramen",
    "ramyun",
    "miojo",
    "macarrao",
    "spaghetti",
    "espaguete",
    "penne",
    "fusilli",
    "fettuccine",
    "lasanha",
    "nhoque",
    "gnocchi",
    "molho de tomate",
    "molho tomate",
    "passata",
    "tomate pelado",
    "pesto",
    "azeite",
    "vinagre",
    "aceto balsamico",
    "mostarda",
    "ketchup",
    "maionese",
    "sriracha",
    "molho de pimenta",
    "gochujang",
    "shoyu",
    "pasta de amendoim",
    "manteiga de amendoim",
    "peanut butter",
    "maple syrup",
    "xarope de bordo",
    "salgadinho",
    "snacks",
    "snack",
    "chips",
    "batata frita",
    "pringles",
    "takis",
    "doritos",
    "cheetos",
    "topokki",
    "tteokbokki",
    "cafe em graos",
    "cafe em grao",
    "cafe graos",
    "cafe torrado",
    "cafe moido",
    "capsula de cafe",
    "capsulas de cafe",
    "cafe l'or",
    "cafe soluv",
    "cha importado",
    "cha ingles",
    "cha verde",
    "cha branco",
    "matcha",
    "refrigerante",
    "sprite",
    "coca cola",
    "coca-cola",
    "guarana",
    "suco",
    "nectar",
    "agua mineral",
    "agua com gas",
    "agua de coco",
    "gatorade",
    "isotônico",
    "isotonico",
    "eletrolitos",
    "energetico",
    "monster energy",
    "red bull",
    "soju",
    "saque",
    "vinho",
    "whisky",
    "whiskey",
    "vodka",
    "gin ",
    "espumante",
    "aperitivo",
    "campari",
    "licor",
    "cerveja",
    "arroz",
    "feijao",
    "tapioca",
    "aveia",
    "farinha",
    "torrada",
    "bauducco",
    "leite uht",
    "leite integral",
    "leite de aveia",
    "leite infantil",
    "bebida lactea",
    "yopro",
    "whey",
    "cereja em calda",
    "oleo de soja",
    "acucar",
    "adocante",
    "leite condensado",
    "creme de leite",
    "achocolatado",
    "nescau",
    "toddy",
    "cesta basica",
    "cesta de natal",
    "pao de forma",
    "pao de queijo",
    "croissant",
    "sopa",
    "missoshiru",
    "risoto",
    "pure de batata",
    "creme de cebola",
    "atum",
    "sardinha",
    "anchova",
    "palmito",
    "azeitona",
    "pepino",
    "milho verde",
    "ervilha",
    "conserva",
    "pipoca",
    "quinoa",
    "lentilha",
    "semente de abobora",
    "granola",
    "cereal",
    "cereais",
    "sucrilhos",
    "barra de proteina",
    "creatina",
    "pre-treino",
    "suplemento",
    "tempero",
    "chimichurri",
    "paprica",
    "sal marinho",
    "sal integral",
    "fermento",
    "amido",
    "desmoldante",
    "unta forma",
    "lecitina",
    "batata palha",
    "molho barbecue",
    "molho tare",
    "oleo de coco",
    "erva mate",
    "erva-mate",
    "chimarrao",
    "terere",
    "cappuccino",
    "champagne",
    "champanhe",
    "champan",
    "prosecco",
    "cava",
    "ades",
    "castanha",
)


@dataclass
class ImportedFilterResult:
    is_food_universe: bool
    approved: bool
    topic_key: Optional[str]
    reason: str


def is_food_or_drink_item(title: str) -> bool:
\
\

    norm = normalize_text(title)
    if not norm:
        return False


    if _contains_any_term(norm, WHITELIST_MARCAS_DOCES) or _contains_any_term(
        norm, WHITELIST_MARCAS_COMIDAS
    ):

        if _contains_any_term(norm, NON_FOOD_APPLIANCE_TERMS):
            return False
        return True

    if _contains_any_term(norm, BLACKLIST_NACIONAIS):
        return True

    if _contains_any_term(norm, NON_FOOD_APPLIANCE_TERMS):
        return False

    if _contains_any_term(norm, SWEET_KEYWORDS) or _contains_any_term(
        norm, SAVORY_DRINK_KEYWORDS
    ):
        return True

    return False


GENERIC_CULINARY_ORIGIN_PHRASES = (
    "soda italiana",
    "palha italiana",
    "pao italiano",
    "pao frances",
    "pao australiano",
    "pao sirio",
    "torrada inglesa",
    "molho ingles",
    "batata inglesa",
    "queijo suico",
    "queijo reino",
    "gin ingles",
    "london dry",
    "amendoim japones",
    "corte americano",
    "copo americano",
    "jogo americano",
    "limao siciliano",
    "torta holandesa",
    "torta alema",
    "creme belga",
    "waffle belga",
)


def _strip_generic_culinary_phrases(norm_text: str) -> str:

    cleaned = norm_text
    for phrase in GENERIC_CULINARY_ORIGIN_PHRASES:
        cleaned = re.sub(
            rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])",
            " ",
            cleaned,
        )
    return cleaned


def evaluate_imported_food(title: str) -> ImportedFilterResult:
\
\
\
\
\
\
\
\
\

    norm = normalize_text(title)

    if not is_food_or_drink_item(title):
        return ImportedFilterResult(
            is_food_universe=False,
            approved=False,
            topic_key=None,
            reason="Produto não pertence ao universo de alimentos/doces/bebidas.",
        )


    blacklisted = _contains_any_term(norm, BLACKLIST_NACIONAIS)
    if blacklisted:
        logger.debug(f"Bloqueado pela Blacklist Nacional ('{blacklisted}'): {title}")
        return ImportedFilterResult(
            is_food_universe=True,
            approved=False,
            topic_key=None,
            reason=f"Bloqueado pela Lista Negra de nacionais comuns ('{blacklisted}').",
        )


    matched_sweet_brand = _contains_any_term(norm, WHITELIST_MARCAS_DOCES)
    matched_food_brand = _contains_any_term(norm, WHITELIST_MARCAS_COMIDAS)
    norm_without_generic_phrases = _strip_generic_culinary_phrases(norm)
    matched_origin = _contains_any_term(norm_without_generic_phrases, WHITELIST_ORIGENS)

    has_sweet_kw = _contains_any_term(norm, SWEET_KEYWORDS) is not None
    has_savory_kw = _contains_any_term(norm, SAVORY_DRINK_KEYWORDS) is not None

    if matched_sweet_brand:
        return ImportedFilterResult(
            is_food_universe=True,
            approved=True,
            topic_key="doces_importados",
            reason=f"Aprovado por marca global de doce importado ('{matched_sweet_brand}').",
        )

    if matched_food_brand:
        if matched_food_brand.lower() == "chupa chups" and has_sweet_kw and not has_savory_kw:
            return ImportedFilterResult(
                is_food_universe=True,
                approved=True,
                topic_key="doces_importados",
                reason=f"Aprovado por marca global ('{matched_food_brand}').",
            )
        return ImportedFilterResult(
            is_food_universe=True,
            approved=True,
            topic_key="comidas_importadas",
            reason=f"Aprovado por marca global de comida/bebida importada ('{matched_food_brand}').",
        )


    if matched_origin:
        if has_sweet_kw and not has_savory_kw:
            target_topic = "doces_importados"
        elif has_savory_kw and not has_sweet_kw:
            target_topic = "comidas_importadas"
        elif has_sweet_kw:
            target_topic = "doces_importados"
        else:
            target_topic = "comidas_importadas"

        return ImportedFilterResult(
            is_food_universe=True,
            approved=True,
            topic_key=target_topic,
            reason=f"Aprovado por origem importada ('{matched_origin}').",
        )


    logger.debug(f"Alimento/doce bloqueado por não ser importado/marca global: {title}")
    return ImportedFilterResult(
        is_food_universe=True,
        approved=False,
        topic_key=None,
        reason="Alimento ou doce nacional/comum sem marca global ou origem importada.",
    )
