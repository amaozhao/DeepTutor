"""Parser engine registry.

Maps an engine name to its adapter class, mirroring the RAG pipeline factory
(``services/rag/factory.py``). Engine modules import their third-party deps
lazily, so importing this registry is cheap and never fails on a missing
optional dependency.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List

from deeptutor.services.config.runtime_settings import (
    DOCUMENT_PARSING_ENGINE_DOCLING,
    DOCUMENT_PARSING_ENGINE_LITEPARSE,
    DOCUMENT_PARSING_ENGINE_MARKITDOWN,
    DOCUMENT_PARSING_ENGINE_MINERU,
    DOCUMENT_PARSING_ENGINE_PYMUPDF4LLM,
    DOCUMENT_PARSING_ENGINE_TEXT_ONLY,
    DOCUMENT_PARSING_ENGINE_TIKA,
)

from ..base import Parser
from ..types import ParserError

try:
    from .mineru.engine import MinerUParser
except ModuleNotFoundError:  # pragma: no cover - optional engine deps
    MinerUParser = None

try:
    from .text_only.engine import TextOnlyParser
except ModuleNotFoundError:  # pragma: no cover - optional engine deps
    TextOnlyParser = None

try:
    from .docling.engine import DoclingParser
except ModuleNotFoundError:  # pragma: no cover - optional engine deps
    DoclingParser = None

try:
    from .markitdown.engine import MarkItDownParser
except ModuleNotFoundError:  # pragma: no cover - optional engine deps
    MarkItDownParser = None

try:
    from .pymupdf4llm.engine import PyMuPDF4LLMParser
except ModuleNotFoundError:  # pragma: no cover - optional engine deps
    PyMuPDF4LLMParser = None


def _mineru_class():
    if MinerUParser is None:
        raise ModuleNotFoundError("MinerU parser engine is unavailable")
    return MinerUParser


def _text_only_class():
    if TextOnlyParser is None:
        raise ModuleNotFoundError("TextOnly parser engine is unavailable")
    return TextOnlyParser


def _docling_class():
    if DoclingParser is None:
        raise ModuleNotFoundError("Docling parser engine is unavailable")
    return DoclingParser


def _markitdown_class():
    if MarkItDownParser is None:
        raise ModuleNotFoundError("MarkItDown parser engine is unavailable")
    return MarkItDownParser


def _liteparse_class():
    from .liteparse.engine import LiteParseParser

    return LiteParseParser


def _pymupdf4llm_class():
    if PyMuPDF4LLMParser is None:
        raise ModuleNotFoundError("PyMuPDF4LLM parser engine is unavailable")
    return PyMuPDF4LLMParser


def _tika_class():
    from .tika.engine import TikaParser

    return TikaParser


# name -> zero-arg loader returning the engine class.
_ENGINE_LOADERS: Dict[str, Callable[[], Any]] = {
    DOCUMENT_PARSING_ENGINE_TEXT_ONLY: _text_only_class,
    DOCUMENT_PARSING_ENGINE_MINERU: _mineru_class,
    DOCUMENT_PARSING_ENGINE_DOCLING: _docling_class,
    DOCUMENT_PARSING_ENGINE_MARKITDOWN: _markitdown_class,
    DOCUMENT_PARSING_ENGINE_PYMUPDF4LLM: _pymupdf4llm_class,
    DOCUMENT_PARSING_ENGINE_LITEPARSE: _liteparse_class,
    DOCUMENT_PARSING_ENGINE_TIKA: _tika_class,
}

KNOWN_ENGINES = frozenset(_ENGINE_LOADERS)

# Static UI metadata (kept here so list_engines never imports engine deps).
_ENGINE_META: Dict[str, Dict[str, Any]] = {
    DOCUMENT_PARSING_ENGINE_TEXT_ONLY: {
        "name": "Text-only",
        "description": (
            "Built-in plain text extraction for PDF/Office/text files. No "
            "optional parser package, no model download, no layout structure."
        ),
        "needs_local_models": False,
    },
    DOCUMENT_PARSING_ENGINE_MINERU: {
        "name": "MinerU",
        "description": (
            "Highest-fidelity multimodal parsing (layout, tables, formulas). "
            "Local CLI downloads models, or use the hosted cloud API. Supports "
            "PDF, common images, DOCX, PPTX, and XLSX."
        ),
        "needs_local_models": True,
    },
    DOCUMENT_PARSING_ENGINE_DOCLING: {
        "name": "Docling",
        "description": (
            "Structured conversion across Docling's current document, image, e-book, "
            "email, audio/video, and data formats. Runs locally or against Docling "
            "Serve; some formats require system tools."
        ),
        "needs_local_models": True,
    },
    DOCUMENT_PARSING_ENGINE_MARKITDOWN: {
        "name": "markitdown",
        "description": (
            "Microsoft MarkItDown with every built-in format extra: PDF, modern "
            "Office, legacy XLS, e-books, mail, audio, images, notebooks, feeds, "
            "archives, and text. Markdown output; no local models."
        ),
        "needs_local_models": False,
    },
    DOCUMENT_PARSING_ENGINE_PYMUPDF4LLM: {
        "name": "PyMuPDF4LLM",
        "description": (
            "Current CPU-only PyMuPDF layout/OCR conversion with image extraction. "
            "Supports PDF, XPS, e-books, SVG, text/Markdown, and PyMuPDF image "
            "formats; no CUDA or first-run model download."
        ),
        "needs_local_models": False,
    },
    DOCUMENT_PARSING_ENGINE_LITEPARSE: {
        "name": "LiteParse",
        "description": (
            "Fast Rust-backed parser from LlamaIndex for PDF, Office, OpenDocument, "
            "iWork, and images. Markdown output and optional image extraction; "
            "Office-family inputs require LibreOffice."
        ),
        "needs_local_models": False,
    },
    DOCUMENT_PARSING_ENGINE_TIKA: {
        "name": "Tika",
        "description": (
            "Remote Apache Tika 4 server with content-based detection for more than "
            "a thousand types, including custom server parsers. No local Python "
            "package; use the current full server image for OCR/system backends."
        ),
        "needs_local_models": False,
    },
}


def _normalize_name(name: str) -> str:
    return (name or "").strip().lower().replace("-", "_").replace(" ", "_")


def get_parser(name: str) -> Parser:
    """Return an engine instance for ``name`` (raises if unknown)."""
    loader = _ENGINE_LOADERS.get(_normalize_name(name))
    if loader is None:
        raise ParserError(f"Unknown document-parsing engine: {name!r}")
    return loader()()


def is_engine_available(name: str) -> bool:
    loader = _ENGINE_LOADERS.get(_normalize_name(name))
    if loader is None:
        return False
    try:
        return bool(loader().is_available())
    except Exception:
        return False


def list_engines() -> List[Dict[str, Any]]:
    """Describe engines for the settings UI picker (no engine deps imported)."""
    out: List[Dict[str, Any]] = []
    for engine_id, meta in _ENGINE_META.items():
        out.append(
            {
                "id": engine_id,
                "name": meta["name"],
                "description": meta["description"],
                "needs_local_models": meta["needs_local_models"],
                "available": is_engine_available(engine_id),
            }
        )
    return out


__all__ = ["KNOWN_ENGINES", "get_parser", "is_engine_available", "list_engines"]
