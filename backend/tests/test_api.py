"""
HctrConvert — Tests
───────────────────
Tests for the conversion API endpoints, services, and utilities.

SOFTWARE ENGINEERING PRINCIPLE: "Test pyramid"
- Unit tests:        Test individual services & helpers in isolation
- Integration tests: Test the full API endpoint flow & static UI serving
"""
from __future__ import annotations

import io
import pytest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.main import app


client = TestClient(app)


# ── Static Frontend & Middleware Headers ─────────────────────────
class TestFrontendAndMiddleware:
    def test_root_serves_index_html_and_security_headers(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "HctrConvert" in response.text
        assert 'type="module"' in response.text
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert response.headers.get("X-Request-ID")
        assert response.headers.get("X-Process-Time-Ms")

    def test_frontend_es_modules_served(self):
        for mod in ("config.js", "state.js", "api.js", "ui.js", "app.js"):
            resp = client.get(f"/js/{mod}")
            assert resp.status_code == 200, f"Missing JS module: {mod}"

    def test_custom_request_id_echoed_on_errors(self):
        resp = client.post(
            "/convert",
            headers={"X-Request-ID": "trace-abc123"},
            files={"file": ("bad.xyz", io.BytesIO(b"data"), "application/octet-stream")},
            data={"target_format": "png"},
        )
        assert resp.status_code == 415
        assert resp.headers.get("X-Request-ID") == "trace-abc123"
        assert resp.json().get("request_id") == "trace-abc123"


# ── Health Endpoint ───────────────────────────────────────────────
class TestHealth:
    def test_health_returns_ok(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "dependencies" in data

    def test_health_includes_dependency_status(self):
        response = client.get("/health")
        deps = response.json()["dependencies"]
        assert "ffmpeg" in deps
        assert "libreoffice" in deps
        assert "builtin_documents" in deps
        assert deps["ffmpeg"] is True
        assert deps["builtin_documents"] is True
        assert isinstance(deps["libreoffice"], bool)


# ── Formats Endpoint ─────────────────────────────────────────────
class TestFormats:
    def test_list_formats(self):
        response = client.get("/formats")
        assert response.status_code == 200
        data = response.json()
        assert list(data.keys()) == ["document", "image", "audio", "video"]
        assert "png" in data["image"]
        assert "heic" in data["image"]
        assert "jxl" in data["image"]
        assert "mp3" in data["audio"]

    def test_format_matrix(self):
        response = client.get("/formats/matrix")
        assert response.status_code == 200
        matrix = response.json()
        assert list(matrix.keys()) == ["document", "image", "audio", "video"]
        assert "pdf" in matrix["document"]["inputs"]
        assert "odt" in matrix["document"]["outputs"]


# ── Convert Endpoint — Validation ─────────────────────────────────
class TestConvertValidation:
    def test_no_file_returns_422(self):
        """Missing required 'file' field."""
        response = client.post("/convert", data={"target_format": "png"})
        assert response.status_code == 422

    def test_empty_file_returns_415(self):
        """Zero-byte file should be rejected cleanly."""
        empty = io.BytesIO(b"")
        response = client.post(
            "/convert",
            files={"file": ("empty.png", empty, "image/png")},
            data={"target_format": "jpg"},
        )
        assert response.status_code == 415

    def test_unsupported_extension_returns_415(self):
        """A .xyz file is not in any known category."""
        fake = io.BytesIO(b"fake data")
        response = client.post(
            "/convert",
            files={"file": ("test.xyz", fake, "application/octet-stream")},
            data={"target_format": "png"},
        )
        assert response.status_code == 415

    def test_invalid_target_format_returns_422(self):
        """Trying to convert an image to 'mp3' should fail."""
        fake = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        response = client.post(
            "/convert",
            files={"file": ("test.png", fake, "image/png")},
            data={"target_format": "mp3"},
        )
        assert response.status_code == 422

    def test_out_of_bounds_quality_or_page_size_returns_422(self):
        fake = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
        q_resp = client.post(
            "/convert",
            files={"file": ("test.png", fake, "image/png")},
            data={"target_format": "jpg", "quality": "250"},
        )
        assert q_resp.status_code == 422

        p_resp = client.post(
            "/convert",
            files={"file": ("doc.txt", io.BytesIO(b"hi"), "text/plain")},
            data={"target_format": "pdf", "page_size": "A99"},
        )
        assert p_resp.status_code == 422

    def test_mismatched_tab_category_still_validates_by_extension(self):
        """Dropping an MP3 while on the Image tab shouldn't run Pillow on an MP3."""
        fake = io.BytesIO(b"ID3" + b"\x00" * 50)
        response = client.post(
            "/convert",
            files={"file": ("song.mp3", fake, "audio/mpeg")},
            data={"target_format": "png", "category": "image"},
        )
        assert response.status_code == 422
        assert "audio" in response.json()["detail"].lower()

    def test_file_too_large_returns_413(self):
        """Files over the size limit should be rejected."""
        with patch("app.api.routes.get_settings") as mock_settings:
            settings = mock_settings.return_value
            settings.max_file_size_bytes = 10
            settings.MAX_FILE_SIZE_MB = 0
            settings.UPLOAD_DIR = Path("tmp/uploads")
            settings.OUTPUT_DIR = Path("tmp/outputs")
            settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

            fake = io.BytesIO(b"x" * 100)
            response = client.post(
                "/convert",
                files={"file": ("test.png", fake, "image/png")},
                data={"target_format": "jpg"},
            )
            assert response.status_code == 413


# ── Image Conversion ──────────────────────────────────────────────
class TestImageConversion:
    def _create_test_png(self, mode: str = "RGB", size: tuple[int, int] = (20, 10)) -> io.BytesIO:
        """Create a minimal valid PNG for testing."""
        from PIL import Image

        color = (255, 0, 0, 128) if mode == "RGBA" else "red"
        img = Image.new(mode, size, color=color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return buf

    def test_png_to_jpg_and_rgba_conversion(self):
        """RGBA PNG → JPEG should flatten alpha to RGB cleanly."""
        png_data = self._create_test_png(mode="RGBA")
        response = client.post(
            "/convert",
            files={"file": ("test.png", png_data, "image/png")},
            data={"target_format": "jpg", "quality": "85"},
        )
        assert response.status_code == 200
        assert len(response.content) > 0
        assert "test.jpg" in response.headers.get("content-disposition", "")

    def test_png_resize_preserves_aspect_ratio(self):
        """Specifying only width should scale height proportionally."""
        from PIL import Image

        png_data = self._create_test_png(size=(40, 20))
        response = client.post(
            "/convert",
            files={"file": ("wide.png", png_data, "image/png")},
            data={"target_format": "png", "width": "10", "height": "0"},
        )
        assert response.status_code == 200
        out_img = Image.open(io.BytesIO(response.content))
        assert out_img.size == (10, 5)

    def test_png_to_webp(self):
        png_data = self._create_test_png()
        response = client.post(
            "/convert",
            files={"file": ("photo.png", png_data, "image/png")},
            data={"target_format": "webp", "quality": "90"},
        )
        assert response.status_code == 200

    def test_png_to_gif(self):
        png_data = self._create_test_png()
        response = client.post(
            "/convert",
            files={"file": ("image.png", png_data, "image/png")},
            data={"target_format": "gif"},
        )
        assert response.status_code == 200

    def test_png_to_heic(self):
        png_data = self._create_test_png()
        response = client.post(
            "/convert",
            files={"file": ("photo.png", png_data, "image/png")},
            data={"target_format": "heic", "quality": "80"},
        )
        assert response.status_code == 200
        assert "photo.heic" in response.headers.get("content-disposition", "")

    def test_svg_to_png_and_jxl_roundtrip(self):
        from PIL import Image

        svg_bytes = (
            b'<svg xmlns="http://www.w3.org/2000/svg" width="80" height="40">'
            b'<rect width="80" height="40" fill="#f97316"/></svg>'
        )
        png_resp = client.post(
            "/convert",
            files={"file": ("logo.svg", io.BytesIO(svg_bytes), "image/svg+xml")},
            data={"target_format": "png", "width": "120"},
        )
        assert png_resp.status_code == 200
        im = Image.open(io.BytesIO(png_resp.content))
        assert im.size == (120, 60)

        jxl_resp = client.post(
            "/convert",
            files={"file": ("logo.png", io.BytesIO(png_resp.content), "image/png")},
            data={"target_format": "jxl", "quality": "90"},
        )
        assert jxl_resp.status_code == 200
        assert len(jxl_resp.content) > 0

    def test_animated_gif_to_webp_preserves_all_frames(self):
        from PIL import Image

        frames = [Image.new("RGB", (24, 24), c) for c in ("red", "green", "blue")]
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=120, loop=0)
        buf.seek(0)

        resp = client.post(
            "/convert",
            files={"file": ("anim.gif", buf, "image/gif")},
            data={"target_format": "webp"},
        )
        assert resp.status_code == 200
        out = Image.open(io.BytesIO(resp.content))
        assert getattr(out, "is_animated", False) is True
        assert getattr(out, "n_frames", 1) == 3

    def test_exif_orientation_transposed_and_metadata_preserved(self):
        from PIL import Image

        img = Image.new("RGB", (40, 20), "orange")
        exif = Image.Exif()
        exif[0x0112] = 6  # Rotate 90 CW
        exif[0x010E] = "HctrConvert EXIF"
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif.tobytes())
        buf.seek(0)

        resp = client.post(
            "/convert",
            files={"file": ("rotated.jpg", buf, "image/jpeg")},
            data={"target_format": "png"},
        )
        assert resp.status_code == 200
        out = Image.open(io.BytesIO(resp.content))
        assert out.size == (20, 40)
        assert out.getexif().get(0x010E) == "HctrConvert EXIF"


# ── Audio / Video / Document Dispatch & Validation ────────────────
class TestMediaAndDocumentDispatch:
    def test_audio_invalid_bitrate_returns_422(self):
        fake = io.BytesIO(b"RIFF" + b"\x00" * 40)
        response = client.post(
            "/convert",
            files={"file": ("clip.wav", fake, "audio/wav")},
            data={"target_format": "mp3", "bitrate": "bad"},
        )
        assert response.status_code == 422

    def test_video_invalid_resolution_returns_422(self):
        fake = io.BytesIO(b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 40)
        response = client.post(
            "/convert",
            files={"file": ("clip.mp4", fake, "video/mp4")},
            data={"target_format": "webm", "resolution": "not_a_res"},
        )
        assert response.status_code == 422

    def test_audio_dispatch_writes_output(self):
        async def fake_run(cmd, tool_name):
            Path(cmd[-1]).write_bytes(b"ID3fake_mp3")
            return b""

        with (
            patch("app.services.audio_service.get_ffmpeg_path", return_value="ffmpeg"),
            patch("app.services.audio_service.run_cli_command", side_effect=fake_run),
        ):
            fake = io.BytesIO(b"RIFF" + b"\x00" * 40)
            response = client.post(
                "/convert",
                files={"file": ("sound.wav", fake, "audio/wav")},
                data={"target_format": "mp3", "bitrate": "192", "sample_rate": "44100"},
            )
            assert response.status_code == 200
            assert response.content == b"ID3fake_mp3"

    def test_video_dispatch_writes_output(self):
        async def fake_run(cmd, tool_name):
            Path(cmd[-1]).write_bytes(b"fake_webm")
            return b""

        with (
            patch("app.services.video_service.get_ffmpeg_path", return_value="ffmpeg"),
            patch("app.services.video_service.run_cli_command", side_effect=fake_run),
        ):
            fake = io.BytesIO(b"fake_mp4")
            response = client.post(
                "/convert",
                files={"file": ("clip.mp4", fake, "video/mp4")},
                data={"target_format": "webm", "resolution": "1280x720", "fps": "30"},
            )
            assert response.status_code == 200
            assert response.content == b"fake_webm"

    def test_document_dispatch_writes_output_with_isolated_profile(self):
        seen_cmds = []

        async def fake_run(cmd, tool_name):
            seen_cmds.append(cmd)
            out_dir = Path(cmd[cmd.index("--outdir") + 1])
            src = Path(cmd[-1])
            (out_dir / f"{src.stem}.pdf").write_bytes(b"%PDF-1.4 fake")
            return b""

        with (
            patch("app.services.document_service.find_libreoffice", return_value="soffice"),
            patch("app.services.document_service.run_cli_command", side_effect=fake_run),
        ):
            fake = io.BytesIO(b"PKfake_docx")
            response = client.post(
                "/convert",
                files={"file": ("report.docx", fake, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"target_format": "pdf"},
            )
            assert response.status_code == 200
            assert response.headers.get("content-type") == "application/pdf"
            assert response.content.startswith(b"%PDF-1.4")
            assert any(arg.startswith("-env:UserInstallation=file:///") for arg in seen_cmds[0])

    def test_real_ffmpeg_wav_to_mp3(self):
        """Real audio conversion via bundled imageio-ffmpeg (no mock)."""
        import struct
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(22050)
            wf.writeframes(struct.pack("<" + "h" * 2205, *([0] * 2205)))
        buf.seek(0)

        response = client.post(
            "/convert",
            files={"file": ("tone.wav", buf, "audio/wav")},
            data={"target_format": "mp3", "bitrate": "128", "sample_rate": "22050"},
        )
        assert response.status_code == 200
        assert len(response.content) > 100

    def test_real_ffmpeg_mp3_with_cover_art_to_m4a_and_ogg(self):
        """Audio with attached cover art converts cleanly to M4A/OGG without crashing."""
        import subprocess
        import tempfile
        from PIL import Image
        from app.utils.dependencies import get_ffmpeg_path

        ffmpeg = get_ffmpeg_path()
        with tempfile.TemporaryDirectory() as td:
            td_path = Path(td)
            cover = td_path / "cover.jpg"
            Image.new("RGB", (32, 32), "orange").save(cover, "JPEG")
            mp3_art = td_path / "art.mp3"
            subprocess.run(
                [
                    ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-i", str(cover), "-map", "0:a", "-map", "1:v", "-c:v", "mjpeg",
                    "-disposition:v", "attached_pic", "-metadata", "title=TrackOne", str(mp3_art),
                ],
                check=True, capture_output=True,
            )
            mp3_bytes = mp3_art.read_bytes()

        for fmt in ("m4a", "ogg", "opus"):
            resp = client.post(
                "/convert",
                files={"file": ("song.mp3", io.BytesIO(mp3_bytes), "audio/mpeg")},
                data={"target_format": fmt, "bitrate": "128"},
            )
            assert resp.status_code == 200, f"Failed converting MP3 w/ cover to {fmt}: {resp.text}"
            assert len(resp.content) > 100

    def test_real_ffmpeg_gif_to_mp4(self):
        """Real video conversion from animated GIF → MP4 via bundled FFmpeg."""
        from PIL import Image

        frames = [Image.new("RGB", (32, 32), c) for c in ("red", "blue")]
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
        buf.seek(0)

        response = client.post(
            "/convert",
            files={"file": ("anim.gif", buf, "image/gif")},
            data={"target_format": "mp4", "category": "video"},
        )
        assert response.status_code == 200
        assert len(response.content) > 100

    def test_real_ffmpeg_odd_video_to_avi_wmv_ogv_webm(self):
        """Odd dimensions and non-CRF codecs (AVI/WMV/OGV/WEBM) convert cleanly."""
        import subprocess
        import tempfile
        from app.utils.dependencies import get_ffmpeg_path

        ffmpeg = get_ffmpeg_path()
        with tempfile.TemporaryDirectory() as td:
            odd_in = Path(td) / "odd.webm"
            subprocess.run(
                [
                    ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=duration=1:size=321x241:rate=24",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "libvpx-vp9", "-c:a", "libopus", str(odd_in),
                ],
                check=True, capture_output=True,
            )
            vid_bytes = odd_in.read_bytes()

        for fmt in ("mp4", "avi", "wmv", "ogv"):
            resp = client.post(
                "/convert",
                files={"file": ("clip.webm", io.BytesIO(vid_bytes), "video/webm")},
                data={"target_format": fmt, "crf": "24"},
            )
            assert resp.status_code == 200, f"Failed converting odd video to {fmt}: {resp.text}"
            assert len(resp.content) > 100

    def test_python_engine_preserves_document_formatting(self):
        """Styled DOCX & PDF preserve headings, tables, colors, and convert to ODT/RTF/HTML/PDF."""
        import pymupdf
        from docx import Document
        from docx.shared import RGBColor
        from app.core.exceptions import DependencyMissingError

        # Create styled DOCX with heading, colored bold run, and table
        doc = Document()
        doc.add_heading("Formatted Heading", level=1)
        p = doc.add_paragraph()
        run = p.add_run("Orange Bold")
        run.bold = True
        run.font.color.rgb = RGBColor(0xF9, 0x73, 0x16)
        tbl = doc.add_table(rows=2, cols=2)
        tbl.cell(0, 0).text = "Key"
        tbl.cell(0, 1).text = "Value"
        tbl.cell(1, 0).text = "Theme"
        tbl.cell(1, 1).text = "DarkBlue"
        docx_buf = io.BytesIO()
        doc.save(docx_buf)
        docx_bytes = docx_buf.getvalue()

        with patch("app.services.document_service.find_libreoffice", side_effect=DependencyMissingError()):
            # DOCX → HTML preserves heading, strong/bold, and table
            html_resp = client.post(
                "/convert",
                files={"file": ("styled.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"target_format": "html"},
            )
            assert html_resp.status_code == 200
            assert "<h1" in html_resp.text and "Formatted Heading" in html_resp.text
            assert "<table>" in html_resp.text and "DarkBlue" in html_resp.text

            # DOCX → ODT & RTF
            odt_resp = client.post(
                "/convert",
                files={"file": ("styled.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"target_format": "odt"},
            )
            assert odt_resp.status_code == 200
            assert odt_resp.content[:2] == b"PK"

            rtf_resp = client.post(
                "/convert",
                files={"file": ("styled.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"target_format": "rtf"},
            )
            assert rtf_resp.status_code == 200
            assert rtf_resp.content.startswith(b"{\\rtf")

            # DOCX → PDF via Pandoc HTML + PyMuPDF Story
            pdf_resp = client.post(
                "/convert",
                files={"file": ("styled.docx", io.BytesIO(docx_bytes), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"target_format": "pdf", "page_size": "A4"},
            )
            assert pdf_resp.status_code == 200
            assert pdf_resp.content.startswith(b"%PDF-")

            # PDF → DOCX & PDF → ODT (screenshot case!) & PDF → HTML
            pdf_to_docx = client.post(
                "/convert",
                files={"file": ("cheatsheet.pdf", io.BytesIO(pdf_resp.content), "application/pdf")},
                data={"target_format": "docx"},
            )
            assert pdf_to_docx.status_code == 200
            assert pdf_to_docx.content[:2] == b"PK"

            pdf_to_odt = client.post(
                "/convert",
                files={"file": ("cheatsheet.pdf", io.BytesIO(pdf_resp.content), "application/pdf")},
                data={"target_format": "odt"},
            )
            assert pdf_to_odt.status_code == 200
            assert pdf_to_odt.content[:2] == b"PK"

            pdf_to_html = client.post(
                "/convert",
                files={"file": ("cheatsheet.pdf", io.BytesIO(pdf_resp.content), "application/pdf")},
                data={"target_format": "html"},
            )
            assert pdf_to_html.status_code == 200
            assert "style=" in pdf_to_html.text

            # Verify PDF text extraction
            pdoc = pymupdf.open(stream=pdf_resp.content, filetype="pdf")
            extracted = "".join(pg.get_text() for pg in pdoc)
            pdoc.close()
            assert "Formatted Heading" in extracted

    def test_python_engine_xlsx_html_pdf_csv_preserving_table(self):
        from app.core.exceptions import DependencyMissingError

        with patch("app.services.document_service.find_libreoffice", side_effect=DependencyMissingError()):
            xlsx_resp = client.post(
                "/convert",
                files={"file": ("data.csv", io.BytesIO(b"name,score\nalice,95\n"), "text/csv")},
                data={"target_format": "xlsx"},
            )
            assert xlsx_resp.status_code == 200
            assert xlsx_resp.content[:2] == b"PK"

            html_resp = client.post(
                "/convert",
                files={"file": ("data.xlsx", io.BytesIO(xlsx_resp.content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"target_format": "html"},
            )
            assert html_resp.status_code == 200
            assert "<table>" in html_resp.text and "<th>name</th>" in html_resp.text

            pdf_resp = client.post(
                "/convert",
                files={"file": ("data.xlsx", io.BytesIO(xlsx_resp.content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"target_format": "pdf"},
            )
            assert pdf_resp.status_code == 200
            assert pdf_resp.content.startswith(b"%PDF-")

            csv_resp = client.post(
                "/convert",
                files={"file": ("data.xlsx", io.BytesIO(xlsx_resp.content), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                data={"target_format": "csv"},
            )
            assert csv_resp.status_code == 200
            assert "alice,95" in csv_resp.text

    def test_legacy_ppt_without_libreoffice_returns_501(self):
        from app.core.exceptions import DependencyMissingError

        with patch("app.services.document_service.find_libreoffice", side_effect=DependencyMissingError()):
            resp = client.post(
                "/convert",
                files={"file": ("slides.pptx", io.BytesIO(b"PKfake"), "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
                data={"target_format": "pdf"},
            )
            assert resp.status_code == 501
            assert "LibreOffice" in resp.json()["detail"]


# ── Unit Tests — Utilities ────────────────────────────────────────
class TestUtilities:
    def test_sanitize_filename_removes_path_traversal(self):
        from app.utils.file_utils import sanitize_filename
        assert sanitize_filename("../../etc/passwd") == "passwd"
        assert sanitize_filename("../secret.txt") == "secret.txt"

    def test_sanitize_filename_removes_special_chars(self):
        from app.utils.file_utils import sanitize_filename
        result = sanitize_filename("hello world (1).jpg")
        assert " " not in result or "_" in result
        assert "/" not in result
        assert "\\" not in result

    def test_generate_job_id_is_unique(self):
        from app.utils.file_utils import generate_job_id
        ids = {generate_job_id() for _ in range(100)}
        assert len(ids) == 100

    def test_detect_category(self):
        from app.models.schemas import detect_category, FileCategory
        assert detect_category(".png") == FileCategory.IMAGE
        assert detect_category(".mp3") == FileCategory.AUDIO
        assert detect_category(".mp4") == FileCategory.VIDEO
        assert detect_category(".pdf") == FileCategory.DOCUMENT
        assert detect_category(".xyz") is None

    def test_sweep_stale_temp_files(self):
        import os
        import time
        from app.core.config import get_settings
        from app.utils.file_utils import sweep_stale_temp_files

        settings = get_settings()
        stale_file = settings.UPLOAD_DIR / "stale_orphan_test.tmp"
        fresh_file = settings.UPLOAD_DIR / "fresh_active_test.tmp"
        stale_file.write_bytes(b"old")
        fresh_file.write_bytes(b"new")
        old_ts = time.time() - 7200
        os.utime(stale_file, (old_ts, old_ts))

        try:
            removed = sweep_stale_temp_files(max_age_seconds=3600)
            assert removed >= 1
            assert not stale_file.exists()
            assert fresh_file.exists()
        finally:
            fresh_file.unlink(missing_ok=True)
            stale_file.unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_run_cli_command_enforces_timeout(self):
        import sys
        from app.core.exceptions import ConversionError
        from app.utils.dependencies import run_cli_command

        with pytest.raises(ConversionError, match="timed out"):
            await run_cli_command(
                [sys.executable, "-c", "import time; time.sleep(5)"],
                "SlowTool",
                timeout_seconds=1,
            )
