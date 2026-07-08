from __future__ import annotations

import zipfile

import pytest

from deeptutor.services.parsing.engines import factory
from deeptutor.services.parsing.types import ParserError


def test_known_engines() -> None:
    assert factory.KNOWN_ENGINES == {
        "text_only",
        "mineru",
        "docling",
        "markitdown",
        "pymupdf4llm",
    }


def test_list_engines_reports_metadata_and_availability() -> None:
    engines = {entry["id"]: entry for entry in factory.list_engines()}
    assert set(engines) == {
        "text_only",
        "mineru",
        "docling",
        "markitdown",
        "pymupdf4llm",
    }
    assert engines["text_only"]["available"] is True
    assert engines["text_only"]["needs_local_models"] is False
    # MinerU is an external CLI / hosted API — the adapter is always available;
    # readiness (not availability) gates actual use.
    assert engines["mineru"]["available"] is True
    assert engines["mineru"]["needs_local_models"] is True
    assert engines["markitdown"]["needs_local_models"] is False
    assert engines["pymupdf4llm"]["needs_local_models"] is False


def test_get_parser_unknown_raises() -> None:
    with pytest.raises(ParserError):
        factory.get_parser("nope")


def test_text_only_parser_extracts_docx_text(tmp_path) -> None:
    parser = factory.get_parser("text_only")
    assert type(factory.get_parser("text-only")) is type(parser)
    docx = tmp_path / "lesson.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr(
            "word/document.xml",
            """
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>Hello DeepTutor</w:t></w:r></w:p>
              </w:body>
            </w:document>
            """.strip(),
        )

    workdir = tmp_path / "parsed"
    workdir.mkdir()
    parser.parse(docx, workdir, config={})

    assert (workdir / "lesson.md").read_text(encoding="utf-8") == "Hello DeepTutor"


def test_mineru_signature_distinguishes_local_and_cloud() -> None:
    parser = factory.get_parser("mineru")
    MinerUConfig = __import__(
        "deeptutor.services.parsing.engines.mineru.config", fromlist=["MinerUConfig"]
    ).MinerUConfig

    local = parser.signature(MinerUConfig(mode="local")).hash()
    cloud = parser.signature(MinerUConfig(mode="cloud")).hash()
    assert local != cloud


def test_mineru_cloud_readiness_needs_token() -> None:
    MinerUConfig = __import__(
        "deeptutor.services.parsing.engines.mineru.config", fromlist=["MinerUConfig"]
    ).MinerUConfig
    mineru_readiness = __import__(
        "deeptutor.services.parsing.engines.mineru.readiness", fromlist=["mineru_readiness"]
    ).mineru_readiness

    assert mineru_readiness(MinerUConfig(mode="cloud", api_token="")).reason == "not_configured"
    assert mineru_readiness(MinerUConfig(mode="cloud", api_token="tok")).ready is True


def test_mineru_local_model_download_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    backend = __import__("deeptutor.services.parsing.engines.mineru", fromlist=["backend"]).backend
    rd = __import__("deeptutor.services.parsing.engines.mineru", fromlist=["readiness"]).readiness
    MinerUConfig = __import__(
        "deeptutor.services.parsing.engines.mineru.config", fromlist=["MinerUConfig"]
    ).MinerUConfig

    monkeypatch.setattr(
        backend,
        "local_cli_probe",
        lambda p="": {"found": True, "command": "mineru", "path": "", "source": "path"},
    )
    monkeypatch.setattr(rd, "mineru_models_ready", lambda source="huggingface": False)

    # Models missing + auto-download off → gated.
    blocked = rd.mineru_readiness(MinerUConfig(mode="local", allow_local_model_download=False))
    assert blocked.ready is False
    assert blocked.reason == "models_missing"

    # Explicit opt-in → allowed.
    allowed = rd.mineru_readiness(MinerUConfig(mode="local", allow_local_model_download=True))
    assert allowed.ready is True

    # CLI missing → distinct gate.
    monkeypatch.setattr(
        backend,
        "local_cli_probe",
        lambda p="": {"found": False, "command": "", "path": "", "source": "path"},
    )
    no_cli = rd.mineru_readiness(MinerUConfig(mode="local"))
    assert no_cli.reason == "cli_missing"


def test_pymupdf4llm_signature_tracks_image_knobs() -> None:
    parser = factory.get_parser("pymupdf4llm")
    PyMuPDF4LLMConfig = __import__(
        "deeptutor.services.parsing.engines.pymupdf4llm.config", fromlist=["PyMuPDF4LLMConfig"]
    ).PyMuPDF4LLMConfig

    base = parser.signature(
        PyMuPDF4LLMConfig(write_images=True, image_format="png", image_dpi=150)
    ).hash()
    other_dpi = parser.signature(
        PyMuPDF4LLMConfig(write_images=True, image_format="png", image_dpi=300)
    ).hash()
    no_images = parser.signature(PyMuPDF4LLMConfig(write_images=False)).hash()
    assert base != other_dpi
    assert base != no_images


def test_pymupdf4llm_readiness_reflects_install() -> None:
    parser = factory.get_parser("pymupdf4llm")
    # Name lookup is case-insensitive (the metadata label is mixed-case).
    assert type(factory.get_parser("PyMuPDF4LLM")) is type(parser)
    report = parser.is_ready(parser.resolve_config())
    if parser.is_available():
        assert report.ready is True
    else:
        # Absent optional package → gated with a pip-install hint, not a crash.
        assert report.reason == "not_configured"
        assert "pymupdf4llm" in report.message


def test_pymupdf4llm_parses_pdf_and_extracts_images(tmp_path) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    pytest.importorskip("pymupdf4llm")
    PyMuPDF4LLMConfig = __import__(
        "deeptutor.services.parsing.engines.pymupdf4llm.config", fromlist=["PyMuPDF4LLMConfig"]
    ).PyMuPDF4LLMConfig

    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello DeepTutor via PyMuPDF4LLM")
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 120, 120))
    pix.clear_with(128)
    page.insert_image(pymupdf.Rect(100, 200, 320, 420), pixmap=pix)
    doc.save(pdf)
    doc.close()

    parser = factory.get_parser("pymupdf4llm")
    workdir = tmp_path / "parsed"
    workdir.mkdir()
    parser.parse(
        pdf,
        workdir,
        config=PyMuPDF4LLMConfig(write_images=True, image_format="png", image_dpi=96),
    )

    md = (workdir / "doc.md").read_text(encoding="utf-8")
    assert "DeepTutor" in md
    images = workdir / "images"
    assert images.is_dir()
    extracted = list(images.glob("*.png"))
    assert extracted, "expected at least one extracted image"
    # Links are rewritten to the portable images/<name> form, not an abs path.
    assert any(f"images/{p.name}" in md for p in extracted)
    assert str(images) not in md


def test_pymupdf4llm_no_images_leaves_no_asset_dir(tmp_path) -> None:
    pymupdf = pytest.importorskip("pymupdf")
    pytest.importorskip("pymupdf4llm")
    PyMuPDF4LLMConfig = __import__(
        "deeptutor.services.parsing.engines.pymupdf4llm.config", fromlist=["PyMuPDF4LLMConfig"]
    ).PyMuPDF4LLMConfig

    pdf = tmp_path / "text.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Text only, no figures here.")
    doc.save(pdf)
    doc.close()

    parser = factory.get_parser("pymupdf4llm")
    workdir = tmp_path / "parsed"
    workdir.mkdir()
    parser.parse(pdf, workdir, config=PyMuPDF4LLMConfig(write_images=True))

    assert (workdir / "text.md").exists()
    # An empty images/ dir is cleaned up so the cache loader sees no asset_dir.
    assert not (workdir / "images").exists()


def test_install_manager_spec_allowlist() -> None:
    ENGINE_PIP_SPECS = __import__(
        "deeptutor.services.parsing.engines._install", fromlist=["ENGINE_PIP_SPECS"]
    ).ENGINE_PIP_SPECS
    installable_engines = __import__(
        "deeptutor.services.parsing.engines._install", fromlist=["installable_engines"]
    ).installable_engines

    # Only optional pip-backed engines are installable; built-in / external are not.
    assert installable_engines() == {"pymupdf4llm", "markitdown", "docling"}
    assert ENGINE_PIP_SPECS["pymupdf4llm"] == ["pymupdf4llm>=0.0.17,<1.0"]
    assert "text_only" not in ENGINE_PIP_SPECS
    assert "mineru" not in ENGINE_PIP_SPECS


def test_model_download_allowlist() -> None:
    ENGINE_MODEL_DOWNLOADERS = __import__(
        "deeptutor.services.parsing.engines._install", fromlist=["ENGINE_MODEL_DOWNLOADERS"]
    ).ENGINE_MODEL_DOWNLOADERS
    model_downloadable_engines = __import__(
        "deeptutor.services.parsing.engines._install", fromlist=["model_downloadable_engines"]
    ).model_downloadable_engines

    # Only Docling fetches model weights; the others need no models.
    assert model_downloadable_engines() == {"docling"}
    assert ENGINE_MODEL_DOWNLOADERS["docling"][0] == "docling-tools"
    assert "pymupdf4llm" not in ENGINE_MODEL_DOWNLOADERS


def test_resolve_model_downloader_unknown_engine() -> None:
    resolve_model_downloader = __import__(
        "deeptutor.services.parsing.engines._install", fromlist=["resolve_model_downloader"]
    ).resolve_model_downloader

    assert resolve_model_downloader("pymupdf4llm") is None
    assert resolve_model_downloader("nope") is None


def test_background_job_manager_idle_status() -> None:
    get_background_job_manager = __import__(
        "deeptutor.services.parsing.engines._install", fromlist=["get_background_job_manager"]
    ).get_background_job_manager

    status = get_background_job_manager().status(0)
    assert status["state"] in {"idle", "running", "done", "failed", "cancelled"}
    assert status["kind"] in {"", "install", "models"}
    assert "engine" in status
    assert isinstance(status["lines"], list)


def test_docling_models_dir_honors_cache_env(monkeypatch, tmp_path) -> None:
    docling_engine = __import__(
        "deeptutor.services.parsing.engines.docling", fromlist=["engine"]
    ).engine

    monkeypatch.setenv("DOCLING_CACHE_DIR", str(tmp_path))
    assert docling_engine.docling_models_dir() == tmp_path / "models"
    # Empty cache → not ready; a populated models dir → detected as ready.
    monkeypatch.delenv("DOCLING_ARTIFACTS_PATH", raising=False)
    monkeypatch.setenv("HF_HOME", str(tmp_path / "nohub"))
    assert docling_engine._docling_models_ready() is False
    models = tmp_path / "models" / "layout"
    models.mkdir(parents=True)
    (models / "model.bin").write_bytes(b"x")
    assert docling_engine._docling_models_ready() is True
