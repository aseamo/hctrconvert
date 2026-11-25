"""
HctrConvert — Document Conversion Service
──────────────────────────────────────────
Preserves document formatting, layout, styles, tables, colors, and images.

SOFTWARE ENGINEERING PRINCIPLE: "Fidelity-First Adapter Pattern"
- Routes document jobs to the highest-fidelity adapter available (`pdf2docx`,
  `PyMuPDF`, `Pandoc`, `openpyxl`, or isolated `LibreOffice` profiles) while
  delegating low-level rendering primitives to `doc_renderers.py`.
"""
from __future__ import annotations

import asyncio
import csv
import html
import io
import shutil
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.exceptions import ConversionError, DependencyMissingError
from app.services.doc_renderers import (
    build_styled_spreadsheet_html,
    html_to_pdf,
    pandoc_convert,
    pdf_to_docx,
)
from app.utils.dependencies import find_libreoffice, run_cli_command

logger = get_logger(__name__)

PANDOC_RICH_INPUTS = {".docx", ".odt", ".rtf", ".html", ".md", ".epub"}
PANDOC_RICH_OUTPUTS = {"docx", "odt", "rtf", "html", "txt"}
SPREADSHEET_INPUTS = {".xlsx", ".csv"}
LIBREOFFICE_ONLY_EXTS = {".doc", ".xls", ".ods", ".ppt", ".pptx", ".odp"}
LIBREOFFICE_ONLY_TARGETS = {"ods", "pptx", "odp"}


async def convert_document(
    src: Path,
    dst: Path,
    target_format: str,
    job_id: str,
    page_size: str = "A4",
) -> Path:
    """Convert a document while preserving formatting and structure."""
    src_ext = src.suffix.lower()
    fmt = target_format.lower().lstrip(".")

    if src_ext.lstrip(".") == fmt:
        shutil.copyfile(src, dst)
        return dst

    try:
        lo_exe = find_libreoffice()
    except DependencyMissingError:
        lo_exe = None

    if src_ext == ".pdf":
        return await _convert_from_pdf(src, dst, fmt, job_id, lo_exe)

    if src_ext in SPREADSHEET_INPUTS and fmt in {"xlsx", "csv", "html", "pdf", "docx", "odt", "rtf", "txt"}:
        if lo_exe and src_ext == ".xlsx" and fmt in {"pdf", "ods", "html"}:
            return await _convert_with_libreoffice(lo_exe, src, dst, fmt, job_id)
        return await _convert_spreadsheet(src, dst, fmt, page_size)

    if lo_exe and (
        src_ext in LIBREOFFICE_ONLY_EXTS
        or fmt in LIBREOFFICE_ONLY_TARGETS
        or src_ext in {".docx", ".odt", ".rtf", ".html"}
    ):
        return await _convert_with_libreoffice(lo_exe, src, dst, fmt, job_id)

    if (
        (src_ext in PANDOC_RICH_INPUTS or src_ext == ".txt")
        and fmt not in LIBREOFFICE_ONLY_TARGETS
        and src_ext not in LIBREOFFICE_ONLY_EXTS
    ):
        return await _convert_via_python_engine(src, dst, fmt, job_id, page_size)

    raise DependencyMissingError(
        f"Converting {src_ext} → .{fmt} requires LibreOffice to preserve full formatting. "
        "Install LibreOffice from https://www.libreoffice.org/download/ "
        "(Windows: `winget install TheDocumentFoundation.LibreOffice`)."
    )


async def _convert_from_pdf(
    src: Path,
    dst: Path,
    fmt: str,
    job_id: str,
    lo_exe: str | None,
) -> Path:
    """Convert PDF to DOCX / ODT / RTF / HTML / TXT while preserving formatting."""
    settings = get_settings()

    def _run_pdf_pipeline():
        import pymupdf

        if fmt == "txt":
            doc = pymupdf.open(str(src))
            try:
                pages = [page.get_text("text") for page in doc]
                dst.write_text("\n\n".join(pages).strip(), encoding="utf-8")
            finally:
                doc.close()
            return None

        if fmt == "html":
            doc = pymupdf.open(str(src))
            try:
                page_divs = [
                    f'<section class="pdf-page">\n{page.get_text("html")}\n</section>'
                    for page in doc
                ]
            finally:
                doc.close()
            html_doc = (
                "<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n"
                f"<meta charset=\"UTF-8\"><title>{html.escape(src.stem)}</title>\n"
                "<style>body{background:#f1f5f9;margin:24px auto;max-width:920px;font-family:sans-serif}"
                ".pdf-page{background:#fff;padding:24px;margin-bottom:24px;box-shadow:0 2px 10px rgba(0,0,0,.08)}</style>\n"
                f"</head>\n<body>\n{''.join(page_divs)}\n</body>\n</html>\n"
            )
            dst.write_text(html_doc, encoding="utf-8")
            return None

        if fmt == "docx":
            pdf_to_docx(src, dst)
            return None

        if fmt in ("odt", "rtf"):
            temp_docx = settings.OUTPUT_DIR / f"{job_id}_intermediate.docx"
            try:
                pdf_to_docx(src, temp_docx)
                if lo_exe:
                    return temp_docx
                pandoc_convert(temp_docx, dst, fmt)
            except Exception:
                temp_docx.unlink(missing_ok=True)
                raise
            finally:
                if not lo_exe:
                    temp_docx.unlink(missing_ok=True)
            return None

        raise DependencyMissingError(
            f"Converting .pdf → .{fmt} requires LibreOffice. "
            "Install LibreOffice from https://www.libreoffice.org/download/ "
            "(Windows: `winget install TheDocumentFoundation.LibreOffice`)."
        )

    loop = asyncio.get_running_loop()
    try:
        handoff = await loop.run_in_executor(None, _run_pdf_pipeline)
        if handoff and isinstance(handoff, Path) and lo_exe:
            try:
                await _convert_with_libreoffice(lo_exe, handoff, dst, fmt, f"{job_id}_lo")
            finally:
                handoff.unlink(missing_ok=True)
    except (DependencyMissingError, ConversionError):
        raise
    except Exception as e:
        raise ConversionError(f"PDF conversion failed: {e}") from e

    logger.info(f"Document saved: {dst.name} ({dst.stat().st_size} bytes)")
    return dst


async def _convert_via_python_engine(
    src: Path,
    dst: Path,
    fmt: str,
    job_id: str,
    page_size: str,
) -> Path:
    """Convert DOCX/ODT/RTF/HTML/MD/EPUB/TXT preserving formatting via Pandoc & PyMuPDF."""
    settings = get_settings()
    src_ext = src.suffix.lower()

    def _run():
        if src_ext == ".epub" and fmt == "pdf":
            import pymupdf
            doc = pymupdf.open(str(src))
            try:
                dst.write_bytes(doc.convert_to_pdf())
            finally:
                doc.close()
            return

        if src_ext == ".html" and fmt == "pdf":
            html_content = src.read_text(encoding="utf-8", errors="replace")
            html_to_pdf(html_content, dst, page_size)
            return

        if src_ext == ".txt":
            raw = src.read_text(encoding="utf-8", errors="replace")
            if fmt == "html":
                escaped = html.escape(raw)
                dst.write_text(
                    "<!DOCTYPE html><html lang=\"en\"><head><meta charset=\"UTF-8\">"
                    f"<title>{html.escape(src.stem)}</title>"
                    "<style>body{font-family:system-ui,sans-serif;max-width:820px;margin:40px auto;padding:0 20px;line-height:1.6}"
                    "pre{white-space:pre-wrap;font-family:inherit}</style>"
                    f"</head><body><pre>{escaped}</pre></body></html>",
                    encoding="utf-8",
                )
                return
            if fmt == "pdf":
                escaped = html.escape(raw).replace("\n", "<br>\n")
                html_to_pdf(
                    f"<html><body style='font-family:sans-serif;font-size:11pt;line-height:1.5'>{escaped}</body></html>",
                    dst,
                    page_size,
                )
                return

        if fmt == "pdf":
            temp_html = settings.OUTPUT_DIR / f"{job_id}_story.html"
            try:
                pandoc_convert(src, temp_html, "html")
                html_content = temp_html.read_text(encoding="utf-8", errors="replace")
                html_to_pdf(html_content, dst, page_size)
            finally:
                temp_html.unlink(missing_ok=True)
            return

        if fmt in PANDOC_RICH_OUTPUTS:
            pandoc_convert(src, dst, fmt)
            return

        raise DependencyMissingError(
            f"Converting {src_ext} → .{fmt} requires LibreOffice. "
            "Install LibreOffice from https://www.libreoffice.org/download/."
        )

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _run)
    except (DependencyMissingError, ConversionError):
        raise
    except Exception as e:
        raise ConversionError(f"Document conversion failed: {e}") from e

    logger.info(f"Document saved: {dst.name} ({dst.stat().st_size} bytes)")
    return dst


async def _convert_spreadsheet(src: Path, dst: Path, fmt: str, page_size: str) -> Path:
    """Convert XLSX/CSV while preserving tabular grid formatting."""
    src_ext = src.suffix.lower()

    def _run():
        sheets: list[tuple[str, list[list[str]]]] = []
        if src_ext == ".csv":
            raw = src.read_text(encoding="utf-8", errors="replace")
            rows = list(csv.reader(io.StringIO(raw)))
            sheets.append((src.stem, rows))
        elif src_ext == ".xlsx":
            from openpyxl import load_workbook
            wb = load_workbook(filename=str(src), data_only=True, read_only=True)
            try:
                for ws in wb.worksheets:
                    rows = []
                    for row in ws.iter_rows(values_only=True):
                        str_row = ["" if v is None else str(v) for v in row]
                        if any(str_row):
                            rows.append(str_row)
                    sheets.append((ws.title, rows))
            finally:
                wb.close()

        if fmt == "csv":
            all_rows = sheets[0][1] if sheets else [[""]]
            with dst.open("w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerows(all_rows or [[""]])
            return

        if fmt == "txt":
            lines = []
            for title, rows in sheets:
                if len(sheets) > 1:
                    lines.append(f"=== {title} ===")
                lines.extend("\t".join(r) for r in rows)
            dst.write_text("\n".join(lines), encoding="utf-8")
            return

        if fmt == "xlsx":
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill
            wb = Workbook()
            ws = wb.active
            ws.title = (sheets[0][0] if sheets else "Sheet1")[:31]
            rows = sheets[0][1] if sheets else []
            for r_idx, row in enumerate(rows, start=1):
                ws.append(row)
                if r_idx == 1:
                    for c_idx in range(1, len(row) + 1):
                        cell = ws.cell(row=1, column=c_idx)
                        cell.font = Font(bold=True, color="FFFFFF")
                        cell.fill = PatternFill(start_color="0F1930", end_color="0F1930", fill_type="solid")
            wb.save(str(dst))
            return

        table_html = build_styled_spreadsheet_html(src.stem, sheets)
        if fmt == "html":
            dst.write_text(table_html, encoding="utf-8")
            return
        if fmt == "pdf":
            html_to_pdf(table_html, dst, page_size)
            return
        if fmt in ("docx", "odt", "rtf"):
            import pypandoc
            pypandoc.convert_text(table_html, fmt, format="html", outputfile=str(dst), extra_args=["--standalone"])
            return

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, _run)
    except (DependencyMissingError, ConversionError):
        raise
    except Exception as e:
        raise ConversionError(f"Spreadsheet conversion failed: {e}") from e

    logger.info(f"Document saved: {dst.name} ({dst.stat().st_size} bytes)")
    return dst


async def _convert_with_libreoffice(
    lo_exe: str,
    src: Path,
    dst: Path,
    target_format: str,
    job_id: str,
) -> Path:
    """
    Convert via LibreOffice headless mode with an isolated per-job user profile
    so concurrent conversions never deadlock on LibreOffice's default profile lock.
    """
    settings = get_settings()
    out_dir = settings.OUTPUT_DIR / job_id
    profile_dir = settings.OUTPUT_DIR / f"{job_id}_lo_profile"
    out_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    profile_uri = profile_dir.resolve().as_uri()
    cmd = [
        lo_exe,
        f"-env:UserInstallation={profile_uri}",
        "--headless",
    ]
    if src.suffix.lower() == ".pdf" and target_format in ("odt", "docx", "rtf", "html", "txt"):
        cmd.append("--infilter=writer_pdf_import")
    cmd += ["--convert-to", target_format, "--outdir", str(out_dir), str(src)]

    logger.info(f"Converting document via LibreOffice: {src.name} → {target_format}")

    try:
        await run_cli_command(cmd, "LibreOffice")

        expected_name = f"{src.stem}.{target_format}"
        out_file = out_dir / expected_name

        if not out_file.exists():
            candidates = list(out_dir.iterdir())
            if candidates:
                out_file = candidates[0]
            else:
                raise ConversionError("LibreOffice produced no output file.")

        shutil.move(str(out_file), str(dst))
        logger.info(f"Document saved: {dst.name} ({dst.stat().st_size} bytes)")
        return dst
    finally:
        shutil.rmtree(out_dir, ignore_errors=True)
        shutil.rmtree(profile_dir, ignore_errors=True)
