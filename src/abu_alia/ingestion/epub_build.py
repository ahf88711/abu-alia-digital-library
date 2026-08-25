from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Iterable, List, Tuple

from ebooklib import epub

META_RE = re.compile(r"^#META#.*$", re.M)
PAGE_RE = re.compile(r"PageV\d+P\d+", re.I)
HEADER_RE = re.compile(r"^###\s*(\|{1,4})\s*(.*)$")


def mARkdown_to_chapters(text: str) -> Tuple[str, List[Tuple[str, str]]]:
    text = META_RE.sub("", text)
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
        chapters = [("المتن", [text[:4000]])]
    # first non-empty as possible title
    for ct, paras in chapters:
        for p in paras:
            if p and len(p) < 80:
                title = p
                break
        break
    html_chapters = []
    for i, (ct, paras) in enumerate(chapters):
        body = "".join(f"<p>{html.escape(p)}</p>" if p else "<p></p>" for p in paras[:4000])
        html_chapters.append((ct or f"فصل {i+1}", body))
    return title, html_chapters


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
    for i, (ch_title, body) in enumerate(chapters):
        chapter = epub.EpubHtml(
            title=ch_title,
            file_name=f"chap_{i+1}.xhtml",
            lang=language,
        )
        html_body = (preface if i == 0 else "") + body
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
    return dest
