from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

from abu_alia.arabic.normalize import collapse_whitespace

PALETTES = [
    ((27, 42, 74), (246, 241, 232), (176, 137, 62)),
    ((31, 78, 74), (246, 241, 232), (196, 162, 92)),
    ((74, 42, 36), (246, 241, 232), (176, 137, 62)),
    ((45, 36, 64), (246, 241, 232), (176, 137, 62)),
]


def _font(path: Optional[Path], size: int) -> ImageFont.ImageFont:
    if path and path.exists():
        try:
            return ImageFont.truetype(str(path), size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int, max_lines: int) -> str:
    words = collapse_whitespace(text).split(" ")
    lines = []
    current = ""
    for w in words:
        trial = (w + " " + current).strip() if True else w
        # RTL visual: we still wrap by logical words
        trial = (current + " " + w).strip()
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = w
        if len(lines) >= max_lines:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) >= max_lines and (len(words) > 4):
        lines[-1] = lines[-1][: max(4, len(lines[-1]) - 1)] + "…"
    return "\n".join(lines)


def generate_cover(
    dest: Path,
    title: str,
    author: str,
    category: str = "",
    *,
    font_path: Optional[Path] = None,
    size: Tuple[int, int] = (480, 720),
    seed: int = 0,
) -> Path:
    w, h = size
    ink, parchment, gold = PALETTES[seed % len(PALETTES)]
    img = Image.new("RGB", (w, h), parchment)
    draw = ImageDraw.Draw(img)
    margin = 36
    draw.rectangle([18, 18, w - 19, h - 19], outline=ink, width=3)
    draw.rectangle([28, 28, w - 29, h - 29], outline=gold, width=1)
    draw.rectangle([0, 0, w, 14], fill=ink)
    draw.rectangle([0, h - 14, w, h], fill=ink)
    title_font = _font(font_path, 36)
    author_font = _font(font_path, 22)
    meta_font = _font(font_path, 16)
    brand = "مكتبة أبو علياء الرقمية"
    # Try arabic reshape if available
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        def vis(s: str) -> str:
            return get_display(arabic_reshaper.reshape(s))

    except Exception:

        def vis(s: str) -> str:
            return s

    title_v = vis(_wrap(draw, title, title_font, w - margin * 2, 6))
    author_v = vis(_wrap(draw, author, author_font, w - margin * 2, 3))
    cat_v = vis(category) if category else ""
    brand_v = vis(brand)
    # title block
    bbox = draw.multiline_textbbox((0, 0), title_v, font=title_font, align="center", spacing=8)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.multiline_text(
        ((w - tw) / 2, h * 0.28),
        title_v,
        font=title_font,
        fill=ink,
        align="center",
        spacing=8,
    )
    draw.line([(margin + 20, h * 0.28 + th + 28), (w - margin - 20, h * 0.28 + th + 28)], fill=gold, width=2)
    draw.multiline_text(
        (margin, h * 0.28 + th + 48),
        author_v,
        font=author_font,
        fill=ink,
        align="center",
        anchor="ma",
    )
    # center author better
    ab = draw.multiline_textbbox((0, 0), author_v, font=author_font, align="center")
    aw = ab[2] - ab[0]
    draw.rectangle([margin, int(h * 0.28 + th + 40), w - margin, int(h * 0.28 + th + 120)], fill=parchment)
    draw.multiline_text(
        ((w - aw) / 2, h * 0.28 + th + 48),
        author_v,
        font=author_font,
        fill=ink,
        align="center",
        spacing=6,
    )
    if cat_v:
        draw.text((w / 2, h - 90), cat_v, font=meta_font, fill=gold, anchor="mm")
    draw.text((w / 2, h - 48), brand_v, font=meta_font, fill=ink, anchor="mm")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="JPEG", quality=88)
    return dest
