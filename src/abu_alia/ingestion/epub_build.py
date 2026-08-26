from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from ebooklib import epub

META_RE = re.compile(r"^#META#.*$", re.M)
PAGE_RE = re.compile(r"PageV\d+P\d+", re.I)
HEADER_RE = re.compile(r"^###\s*(\|{1,4})\s*(.*)$")

# Split long chapters into XHTML parts so readers stay stable.
# This must never drop paragraphs — only pack them.
PARAS_PER_XHTML = 250
MAX_XHTML_FILES = 500


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    if size <= 0:
        yield items
        return
    for i in range(0, len(items), size):
        yield items[i : i + size]


def mARkdown_to_chapters(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    text = META_RE.sub("", text or "")
    lines = text.splitlines()
    title = "كتاب"
    chapters: List[Tuple[str, List[str]]] = []
    current_title = "المتن"
    buf: List[str] = []
    for raw in lines:
        line = PAGE_RE.sub("", raw).rstrip()
        if not line.strip():
            if buf and buf[-1] != "":
                buf.append("")
            continue
        m = HEADER_RE.match(line.strip())
        if m:
            if buf:
                chapters.append((current_title, buf))
                buf = []
            current_title = m.group(2).strip() or current_title
            continue
        if line.startswith("#META#"):
            continue
        cleaned = line.replace("~~", "").strip()
        if cleaned.startswith("OpenITI") or cleaned.startswith("######OpenITI"):
            continue
        buf.append(cleaned)
    if buf:
        chapters.append((current_title, buf))
    if not chapters:
        paras = [p for p in (text or "").splitlines() if p.strip()]
        chapters = [("المتن", paras or [text])]
    for ct, paras in chapters:
        for p in paras:
            if p and len(p) < 80:
                title = p
                break
        break
    html_chapters: List[Tuple[str, str]] = []
    for i, (ct, paras) in enumerate(chapters):
        parts = list(_chunks(paras, PARAS_PER_XHTML)) or [[]]
        for j, part in enumerate(parts):
            body = "".join(f"<p>{html.escape(p)}</p>" if p else "<p></p>" for p in part)
            label = ct or f"فصل {i+1}"
            if len(parts) > 1:
                label = f"{label} — {j+1}"
            html_chapters.append((label, body))
    return title, _pack_chapters(html_chapters)


def _pack_chapters(html_chapters: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Merge extra XHTML files without dropping any HTML body."""
    if len(html_chapters) <= MAX_XHTML_FILES:
        return html_chapters
    size = (len(html_chapters) + MAX_XHTML_FILES - 1) // MAX_XHTML_FILES
    packed: List[Tuple[str, str]] = []
    for i in range(0, len(html_chapters), size):
        group = html_chapters[i : i + size]
        title = group[0][0]
        body = "".join(f"<h2>{html.escape(t)}</h2>{b}" for t, b in group)
        packed.append((title, body))
    return packed


def build_epub(
    dest: Path,
    *,
    title: str,
    author: str,
    language: str = "ar",
    chapters: Iterable[Tuple[str, str]],
    identifier: str,
    attribution: str = "",
) -> Path:
    book = epub.EpubBook()
    book.set_identifier(identifier)
    book.set_title(title)
    book.set_language(language)
    book.add_author(author)
    book.set_direction("rtl")
    css = epub.EpubItem(
        uid="style",
        file_name="style/main.css",
        media_type="text/css",
        content=(
            "html,body{direction:rtl;text-align:right;font-family:serif;line-height:1.8;"
            "color:#1a2332;background:#f6f1e8;}"
            "p{margin:0 0 0.8em 0;} h1,h2{font-weight:700;}"
        ).encode("utf-8"),
    )
    book.add_item(css)
    spine = ["nav"]
    toc = []
    items = []
    preface = ""
    if attribution:
        preface = f"<p>{html.escape(attribution)}</p>"
    chapter_list = _pack_chapters(list(chapters))
    if not chapter_list:
        chapter_list = [("المتن", "<p>…</p>")]
    for i, (ch_title, body) in enumerate(chapter_list):
        chapter = epub.EpubHtml(
            title=ch_title,
            file_name=f"chap_{i+1}.xhtml",
            lang=language,
        )
        html_body = (preface if i == 0 else "") + (body or "")
        if not html_body.strip():
            html_body = "<p>…</p>"
        chapter.content = f"<h1>{html.escape(ch_title)}</h1>{html_body}"
        chapter.add_item(css)
        book.add_item(chapter)
        items.append(chapter)
        spine.append(chapter)
        toc.append(chapter)
        preface = ""
    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    dest.parent.mkdir(parents=True, exist_ok=True)
    epub.write_epub(str(dest), book, {})
    with zipfile.ZipFile(dest) as zf:
        broken = zf.testzip()
        if broken is not None:
            raise RuntimeError(f"epub archive corrupt after write: {broken}")
        if "mimetype" not in zf.namelist():
            raise RuntimeError("epub missing mimetype after write")
    return dest
