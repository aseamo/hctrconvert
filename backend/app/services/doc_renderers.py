"""
HctrConvert — Low-Level Document Rendering Toolkit
──────────────────────────────────────────────────
Encapsulates layout-preserving PDF, Pandoc, PyMuPDF Story, and styled
spreadsheet HTML table helpers used by `document_service.py`.

SOFTWARE ENGINEERING PRINCIPLE: "Single Responsibility"
- Keeps low-level library adapters (`pdf2docx`, `pypandoc`, `pymupdf.Story`,
  `openpyxl` table HTML) separate from high-level conversion routing.
"""
from __future__ import annotations

import gc
import html
from pathlib import Path

from app.core.exceptions import DependencyMissingError


def pdf_to_docx(src: Path, dst: Path) -> None:
    """Convert PDF to DOCX using pdf2docx while releasing Windows file handles."""
    try:
        from pdf2docx import Converter
    except ImportError:
        raise DependencyMissingError("pdf2docx is not installed. Run `pip install pdf2docx`.")

    cv = Converter(str(src))
    try:
        cv.convert(str(dst))
    finally:
        cv.close()
        del cv
        gc.collect()


def pandoc_convert(src: Path, dst: Path, fmt: str) -> None:
    """Convert rich documents via Pandoc preserving styles, links, tables, and media."""
    try:
        import pypandoc
    except ImportError:
        raise DependencyMissingError("pypandoc-binary is not installed. Run `pip install pypandoc-binary`.")

    src_ext = src.suffix.lower()
    in_fmt_map = {
        ".md": "markdown",
        ".html": "html",
        ".docx": "docx",
        ".odt": "odt",
        ".rtf": "rtf",
        ".epub": "epub",
        ".txt": "markdown",
    }
    in_fmt = in_fmt_map.get(src_ext)
    out_fmt = "plain" if fmt == "txt" else fmt

    extra_args: list[str] = []
    if fmt == "html":
        extra_args += ["--standalone", "--embed-resources"]
    elif fmt in ("rtf", "docx", "odt"):
        extra_args += ["--standalone"]

    pypandoc.convert_file(
        str(src),
        out_fmt,
        format=in_fmt,
        outputfile=str(dst),
        extra_args=extra_args,
    )


def html_to_pdf(html_content: str, dst: Path, page_size: str) -> None:
    """Render styled HTML/CSS to a multi-page PDF using PyMuPDF Story."""
    import pymupdf

    size_map = {
        "A4": "a4",
        "A3": "a3",
        "Letter": "letter",
        "Legal": "legal",
    }
    paper = size_map.get(page_size, "a4")
    mediabox = pymupdf.paper_rect(paper)
    where = mediabox + (36, 36, -36, -36)

    story = pymupdf.Story(html=html_content)
    writer = pymupdf.DocumentWriter(str(dst))
    try:
        more = True
        while more:
            dev = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(dev, None)
            writer.end_page()
    finally:
        writer.close()
        del writer
        del story
        gc.collect()


def build_styled_spreadsheet_html(title: str, sheets: list[tuple[str, list[list[str]]]]) -> str:
    """Render spreadsheet sheets into a clean, styled HTML table document."""
    sections = []
    for sheet_name, rows in sheets:
        if not rows:
            continue
        thead = "".join(f"<th>{html.escape(c)}</th>" for c in rows[0])
        tbody_rows = []
        for row in rows[1:]:
            tds = "".join(f"<td>{html.escape(c)}</td>" for c in row)
            tbody_rows.append(f"<tr>{tds}</tr>")
        sections.append(
            f"<h2>{html.escape(sheet_name)}</h2>"
            f"<table><thead><tr>{thead}</tr></thead><tbody>{''.join(tbody_rows)}</tbody></table>"
        )
    return (
        "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\">"
        f"<title>{html.escape(title)}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:28px;color:#0f172a}"
        "h2{margin:20px 0 10px;font-size:15pt;color:#0f1930}"
        "table{border-collapse:collapse;width:100%;margin-bottom:20px;font-size:10pt}"
        "th,td{border:1px solid #cbd5e1;padding:6px 10px;text-align:left}"
        "th{background:#0f1930;color:#fff;font-weight:600}"
        "tr:nth-child(even) td{background:#f8fafc}</style></head>"
        f"<body>{''.join(sections)}</body></html>"
    )
