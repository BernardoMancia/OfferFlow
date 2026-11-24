from __future__ import annotations

from scrapers.base import BaseScraper, ScrapedOffer, parse_brl_price
from scrapers.gatry import GatryScraper
from scrapers.ml_category_hunter import MercadoLivreCategoryHunter
from scrapers.ml_offers import MercadoLivreOffersScraper
from scrapers.pelando import PelandoScraper
from scrapers.promobit import PromobitScraper

__all__ = [
    "BaseScraper",
    "GatryScraper",
    "MercadoLivreCategoryHunter",
    "MercadoLivreOffersScraper",
    "PelandoScraper",
    "PromobitScraper",
    "ScrapedOffer",
    "parse_brl_price",
]
