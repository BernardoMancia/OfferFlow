from __future__ import annotations

import io
from typing import Any, Dict, Sequence

from PIL import Image, ImageDraw, ImageFont

from telegram_bot.formatter import format_brl


def generate_price_history_card(
    title: str,
    points: Sequence[Dict[str, Any]],
) -> bytes:
\
\
\

    width, height = 800, 420
    bg_color = (15, 23, 42)
    card_bg = (30, 41, 59)
    accent_green = (16, 185, 129)
    accent_blue = (56, 189, 248)
    text_white = (248, 250, 252)
    text_muted = (148, 163, 184)
    grid_color = (51, 65, 85)

    img = Image.new("RGB", (width, height), color=bg_color)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()


    draw.rounded_rectangle([16, 16, width - 16, height - 16], radius=14, fill=card_bg, outline=grid_color, width=2)

    clean_title = (title or "Produto Monitorado").strip()
    if len(clean_title) > 72:
        clean_title = clean_title[:69] + "..."

    draw.text((36, 32), "TERMOMETRO & HISTORICO DE PRECOS", fill=accent_blue, font=font)
    draw.text((36, 54), clean_title, fill=text_white, font=font)

    prices = [float(p.get("price") or 0.0) for p in points if float(p.get("price") or 0.0) > 0]
    if not prices:
        prices = [0.0]

    min_p = min(prices)
    max_p = max(prices)
    avg_p = sum(prices) / len(prices)
    cur_p = prices[-1]


    metrics = [
        ("ATUAL", format_brl(cur_p), accent_green if cur_p <= min_p else text_white),
        ("MENOR HISTORICO", format_brl(min_p), accent_green),
        ("MEDIA", format_brl(avg_p), accent_blue),
        ("MAIOR", format_brl(max_p), text_muted),
    ]
    box_w = 170
    for idx, (label, val_str, col) in enumerate(metrics):
        bx = 36 + idx * (box_w + 14)
        by = 86
        draw.rounded_rectangle([bx, by, bx + box_w, by + 56], radius=8, fill=bg_color, outline=grid_color, width=1)
        draw.text((bx + 12, by + 10), label, fill=text_muted, font=font)
        draw.text((bx + 12, by + 30), val_str, fill=col, font=font)


    chart_left, chart_top, chart_right, chart_bottom = 60, 168, width - 48, height - 52
    chart_w = chart_right - chart_left
    chart_h = chart_bottom - chart_top


    for i in range(4):
        gy = chart_top + int((chart_h / 3) * i)
        draw.line([(chart_left, gy), (chart_right, gy)], fill=grid_color, width=1)

    if len(prices) == 1:
        prices = [prices[0], prices[0]]

    spread = max_p - min_p
    if spread <= 0.01:
        spread = max(max_p * 0.15, 1.0)
        plot_min = max(0.0, min_p - spread / 2)
    else:
        plot_min = max(0.0, min_p - spread * 0.1)
        spread = (max_p + spread * 0.1) - plot_min

    coords: list[tuple[int, int]] = []
    for idx, p_val in enumerate(prices):
        px = chart_left + int((idx / max(len(prices) - 1, 1)) * chart_w)
        norm_y = (p_val - plot_min) / spread
        py = chart_bottom - int(norm_y * chart_h)
        py = max(chart_top + 6, min(chart_bottom - 6, py))
        coords.append((px, py))


    if len(coords) >= 2:
        draw.line(coords, fill=accent_blue, width=3)


    for idx, (px, py) in enumerate(coords):
        p_val = prices[idx]
        pt_color = accent_green if p_val <= min_p else accent_blue
        r = 5 if p_val <= min_p else 4
        draw.ellipse([px - r, py - r, px + r, py + r], fill=pt_color)


    footer_msg = (
        f"Pontos monitorados: {len(points)} | Economia vs topo: {format_brl(max(0.0, max_p - cur_p))}"
    )
    draw.text((36, height - 36), footer_msg, fill=text_muted, font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
