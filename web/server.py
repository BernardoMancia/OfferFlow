from __future__ import annotations

import asyncio
import json
from typing import Any, Optional
from urllib.parse import parse_qs, urlparse

from config import OFFICIAL_TOPICS, settings
from database.db import DatabaseManager, db
from database.logger import get_logger

logger = get_logger("web.server")

SHOWCASE_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>OfferFlow — Vitrine Ao Vivo • 100% Mercado Livre</title>
  <script src="https://telegram.org/js/telegram-web-app.js"></script>
  <style>
    :root {
      --bg: #0f172a;
      --card: #1e293b;
      --border: #334155;
      --text: #f8fafc;
      --muted: #94a3b8;
      --accent: #10b981;
      --accent-hover: #059669;
      --badge: #ef4444;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: var(--bg);
      color: var(--text);
      padding: 16px;
      max-width: 1180px;
      margin: 0 auto;
    }
    header {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-bottom: 18px;
      border-bottom: 1px solid var(--border);
      padding-bottom: 16px;
    }
    .title-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px;
    }
    h1 { font-size: 1.35rem; font-weight: 700; }
    .stats-pill {
      background: var(--card);
      border: 1px solid var(--border);
      padding: 6px 12px;
      border-radius: 999px;
      font-size: 0.82rem;
      color: var(--muted);
    }
    .search-box {
      width: 100%;
      padding: 11px 14px;
      border-radius: 10px;
      border: 1px solid var(--border);
      background: var(--card);
      color: var(--text);
      font-size: 0.95rem;
      outline: none;
    }
    .topics-bar {
      display: flex;
      gap: 8px;
      overflow-x: auto;
      padding-bottom: 4px;
    }
    .chip {
      white-space: nowrap;
      padding: 7px 13px;
      border-radius: 999px;
      border: 1px solid var(--border);
      background: var(--card);
      color: var(--text);
      cursor: pointer;
      font-size: 0.85rem;
    }
    .chip.active {
      background: var(--accent);
      border-color: var(--accent);
      color: #052e16;
      font-weight: 600;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: 14px;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 14px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      gap: 10px;
    }
    .img-wrap {
      width: 100%;
      height: 160px;
      background: #ffffff;
      border-radius: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      position: relative;
    }
    .img-wrap img {
      max-width: 92%;
      max-height: 92%;
      object-fit: contain;
    }
    .disc-badge {
      position: absolute;
      top: 8px;
      left: 8px;
      background: var(--badge);
      color: #fff;
      font-weight: 700;
      font-size: 0.78rem;
      padding: 3px 8px;
      border-radius: 6px;
    }
    .store-line {
      font-size: 0.78rem;
      color: var(--muted);
      display: flex;
      justify-content: space-between;
    }
    .prod-title {
      font-size: 0.93rem;
      font-weight: 600;
      line-height: 1.35;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }
    .old-price {
      font-size: 0.8rem;
      color: var(--muted);
      text-decoration: line-through;
    }
    .cur-price {
      font-size: 1.22rem;
      font-weight: 800;
      color: var(--accent);
    }
    .coupon-box {
      font-size: 0.78rem;
      background: #0f172a;
      border: 1px dashed var(--accent);
      padding: 5px 8px;
      border-radius: 6px;
      color: #a7f3d0;
    }
    .btn {
      display: block;
      text-align: center;
      text-decoration: none;
      background: var(--accent);
      color: #052e16;
      font-weight: 700;
      padding: 10px;
      border-radius: 8px;
      font-size: 0.9rem;
    }
    .btn:hover { background: var(--accent-hover); color: #fff; }
  </style>
</head>
<body>
  <header>
    <div class="title-row">
      <h1>⚡ OfferFlow — Vitrine 100% Mercado Livre</h1>
      <span class="stats-pill" id="stats-pill">Carregando ofertas...</span>
    </div>
    <input type="search" id="search" class="search-box" placeholder="🔍 Buscar produto no Mercado Livre..." />
    <div class="topics-bar" id="topics">
      <button class="chip active" data-topic="">Todas</button>
      <button class="chip" data-topic="ofertas_bugs">🔥 Ofertas & Bugs</button>
      <button class="chip" data-topic="tech_celulares">💻 Tech & Celulares</button>
      <button class="chip" data-topic="games_geek">🎮 Games & Livros</button>
      <button class="chip" data-topic="casa_eletro">🏠 Casa & Eletro</button>
      <button class="chip" data-topic="ferramentas_construcao">🛠️ Ferramentas</button>
      <button class="chip" data-topic="moda_relogios">👟 Moda & Relógios</button>
      <button class="chip" data-topic="beleza_esportes">💄 Beleza & Esportes</button>
      <button class="chip" data-topic="pet_bebes_papelaria">🐾 Pet, Bebês & Papelaria</button>
    </div>
  </header>
  <main class="grid" id="grid"></main>
  <script>
    if (window.Telegram && window.Telegram.WebApp) {
      window.Telegram.WebApp.ready();
      window.Telegram.WebApp.expand();
    }
    let currentTopic = "";
    const grid = document.getElementById("grid");
    const searchInput = document.getElementById("search");
    const statsPill = document.getElementById("stats-pill");

    function fmtBRL(v) {
      return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
    }

    async function loadOffers() {
      const q = encodeURIComponent(searchInput.value.trim());
      const res = await fetch(`/api/offers?topic=${currentTopic}&q=${q}`);
      const data = await res.json();
      const items = data.offers || [];
      statsPill.textContent = `${items.length} ofertas exibidas`;
      grid.innerHTML = items.map(it => `
        <article class="card">
          <div>
            <div class="img-wrap">
              ${it.discount_pct > 0 ? `<span class="disc-badge">-${it.discount_pct}%</span>` : ""}
              ${it.image_url ? `<img src="${it.image_url}" alt="" loading="lazy" />` : `<span>🛍️</span>`}
            </div>
            <div class="store-line" style="margin-top:8px;">
              <span>🏪 ${it.store}${it.is_full ? " ⚡ Full" : ""}</span>
              <span>${it.rating ? `⭐ ${Number(it.rating).toFixed(1)}` : ""}</span>
            </div>
            <div class="prod-title" style="margin-top:4px;">${it.title}</div>
          </div>
          <div>
            ${it.original_price && it.original_price > it.price ? `<div class="old-price">De: ${fmtBRL(it.original_price)}</div>` : ""}
            <div class="cur-price">${fmtBRL(it.price)}</div>
            ${it.coupon ? `<div class="coupon-box" style="margin-top:6px;">🎟️ ${it.coupon}</div>` : ""}
            <a class="btn" style="margin-top:10px;" href="${it.affiliate_url}" target="_blank" rel="noopener">🛒 Pegar Promoção</a>
          </div>
        </article>
      `).join("");
    }

    document.getElementById("topics").addEventListener("click", e => {
      const btn = e.target.closest(".chip");
      if (!btn) return;
      document.querySelectorAll(".chip").forEach(c => c.classList.remove("active"));
      btn.classList.add("active");
      currentTopic = btn.dataset.topic || "";
      loadOffers();
    });
    searchInput.addEventListener("input", () => loadOffers());
    loadOffers();
  </script>
</body>
</html>
"""


def build_showcase_api_payload(
    topic_key: Optional[str] = None,
    search_query: Optional[str] = None,
    limit: int = 60,
    database: DatabaseManager = db,
) -> dict[str, Any]:
    offers = database.get_showcase_offers(
        topic_key=topic_key,
        search_query=search_query,
        limit=limit,
    )
    return {
        "ok": True,
        "count": len(offers),
        "topics": OFFICIAL_TOPICS,
        "offers": offers,
    }


async def _handle_http_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    database: DatabaseManager = db,
) -> None:
    try:
        request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
        if not request_line:
            return
        parts = request_line.decode("utf-8", errors="ignore").strip().split()
        if len(parts) < 2:
            return
        path_raw = parts[1]


        while True:
            line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not line or line in (b"\r\n", b"\n"):
                break

        parsed = urlparse(path_raw)
        qs = parse_qs(parsed.query)

        if parsed.path == "/health":
            from core.telemetry import get_health_payload

            payload = get_health_payload()
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        elif parsed.path == "/api/offers":
            topic = (qs.get("topic") or [""])[0].strip() or None
            q = (qs.get("q") or [""])[0].strip() or None
            payload = build_showcase_api_payload(topic_key=topic, search_query=q, database=database)
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        elif parsed.path == "/api/stats":
            rep = database.get_24h_operational_report()
            body = json.dumps(rep, ensure_ascii=False).encode("utf-8")
            content_type = "application/json; charset=utf-8"
        else:
            body = SHOWCASE_HTML.encode("utf-8")
            content_type = "text/html; charset=utf-8"

        headers = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Connection: close\r\n\r\n"
        ).encode("utf-8")
        writer.write(headers + body)
        await writer.drain()
    except Exception:
        pass
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass


async def start_showcase_web_server(
    port: Optional[int] = None,
    database: DatabaseManager = db,
) -> Optional[asyncio.AbstractServer]:
    target_port = port if port is not None else settings.web_port
    if target_port <= 0:
        return None
    try:
        server = await asyncio.start_server(
            lambda r, w: _handle_http_client(r, w, database=database),
            host=settings.web_host,
            port=target_port,
        )
        logger.info(
            f"Vitrine Web Pública / Healthcheck iniciada em http://{settings.web_host}:{target_port} (Health: /health | API: /api/offers)"
        )
        return server
    except Exception as exc:
        logger.warning(f"Não foi possível iniciar a Vitrine Web na porta {target_port}: {exc}")
        return None
