from __future__ import annotations

import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable, Iterable
from xml.etree import ElementTree

from .storage import Storage

SUPPORTED_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".csv",
    ".log",
    ".html",
    ".htm",
    ".xml",
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
}
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "appdata",
    "windows",
    "program files",
    "program files (x86)",
    "$recycle.bin",
    "system volume information",
}
MAX_FILE_BYTES = 8_000_000
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120


class KnowledgeError(RuntimeError):
    pass


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"} and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            stripped = data.strip()
            if stripped:
                self.parts.append(stripped)


def _html_text(text: str) -> str:
    parser = _TextExtractor()
    parser.feed(text)
    return " ".join(parser.parts)


def _pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise KnowledgeError(
            "PDF indexing needs pypdf: pip install pypdf"
        ) from exc
    reader = PdfReader(str(path))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n".join(pages)


def _docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            payload = archive.read("word/document.xml")
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise KnowledgeError(f"could not read {path}: {exc}") from exc
    root = ElementTree.fromstring(payload)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        text = "".join(node.text or "" for node in paragraph.iter(f"{namespace}t"))
        if text.strip():
            paragraphs.append(text.strip())
    return "\n".join(paragraphs)


def _xlsx_text(path: Path) -> str:
    main = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    try:
        with zipfile.ZipFile(path) as archive:
            shared: list[str] = []
            if "xl/sharedStrings.xml" in archive.namelist():
                root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
                for item in root.iter(f"{main}si"):
                    shared.append(
                        "".join(node.text or "" for node in item.iter(f"{main}t"))
                    )
            sheets = sorted(
                name for name in archive.namelist()
                if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", name)
            )
            parts: list[str] = []
            for number, name in enumerate(sheets, 1):
                root = ElementTree.fromstring(archive.read(name))
                rows: list[str] = []
                for row in root.iter(f"{main}row"):
                    values: list[str] = []
                    for cell in row.iter(f"{main}c"):
                        kind = cell.get("t")
                        node = cell.find(f"{main}v")
                        if kind == "inlineStr":
                            inline = cell.find(f"{main}is")
                            value = "".join(
                                text.text or "" for text in inline.iter(f"{main}t")
                            ) if inline is not None else ""
                        elif kind == "s" and node is not None and node.text:
                            index = int(node.text)
                            value = shared[index] if 0 <= index < len(shared) else ""
                        else:
                            value = node.text if node is not None and node.text else ""
                        if value:
                            values.append(value)
                    if values:
                        rows.append("\t".join(values))
                if rows:
                    parts.append(f"[Sheet {number}]\n" + "\n".join(rows))
    except (KeyError, OSError, ValueError, zipfile.BadZipFile) as exc:
        raise KnowledgeError(f"could not read {path}: {exc}") from exc
    return "\n\n".join(parts)


def _pptx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            slides = sorted(
                name for name in archive.namelist()
                if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
            )
            if not slides:
                raise KnowledgeError(f"no slides found in {path}")
            parts: list[str] = []
            for name in slides:
                root = ElementTree.fromstring(archive.read(name))
                text = " ".join(
                    node.text or "" for node in root.iter()
                    if node.tag.endswith("}t")
                )
                if text.strip():
                    parts.append(" ".join(text.split()))
    except (KeyError, OSError, zipfile.BadZipFile) as exc:
        raise KnowledgeError(f"could not read {path}: {exc}") from exc
    return "\n".join(parts)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_text(path)
    if suffix == ".docx":
        return _docx_text(path)
    if suffix == ".pptx":
        return _pptx_text(path)
    if suffix == ".xlsx":
        return _xlsx_text(path)
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore")
    except OSError as exc:
        raise KnowledgeError(f"could not read {path}: {exc}") from exc
    if path.suffix.lower() in {".html", ".htm", ".xml"}:
        return _html_text(raw)
    return raw


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    normalized = " ".join(text.split())
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + size)
        if end < len(normalized):
            boundary = normalized.rfind(". ", start + size // 2, end)
            if boundary > 0:
                end = boundary + 1
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(normalized):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _existing(storage: Storage, path: Path) -> tuple[int, float, int] | None:
    row = storage.db.execute(
        "SELECT id, mtime, size FROM documents WHERE path = ?", (str(path),)
    ).fetchone()
    if row is None:
        return None
    return int(row["id"]), float(row["mtime"]), int(row["size"])


def _drop_document(storage: Storage, doc_id: int, path: str) -> None:
    storage.db.execute("DELETE FROM doc_chunks WHERE doc_id = ?", (doc_id,))
    storage.db.execute("DELETE FROM doc_chunks_fts WHERE path = ?", (path,))
    storage.db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))


def index_file(storage: Storage, path: Path, *, force: bool = False) -> bool:
    path = path.expanduser().resolve()
    if path.suffix.lower() not in SUPPORTED_SUFFIXES or not path.is_file():
        return False
    stat = path.stat()
    if stat.st_size > MAX_FILE_BYTES:
        return False
    existing = _existing(storage, path)
    if (
        existing is not None
        and not force
        and existing[1] == stat.st_mtime
        and existing[2] == stat.st_size
    ):
        return False
    text = extract_text(path)
    chunks = chunk_text(text)
    if not chunks:
        return False
    with storage.db:
        if existing is not None:
            _drop_document(storage, existing[0], str(path))
        cursor = storage.db.execute(
            "INSERT INTO documents(path, title, mtime, size, indexed_at) "
            "VALUES (?, ?, ?, ?, strftime('%s','now'))",
            (str(path), path.stem, stat.st_mtime, stat.st_size),
        )
        doc_id = int(cursor.lastrowid)
        for ordinal, piece in enumerate(chunks):
            inserted = storage.db.execute(
                "INSERT INTO doc_chunks(doc_id, ordinal, text) VALUES (?, ?, ?)",
                (doc_id, ordinal, piece),
            )
            storage.db.execute(
                "INSERT INTO doc_chunks_fts(rowid, text, path, chunk_id) "
                "VALUES (?, ?, ?, ?)",
                (int(inserted.lastrowid), piece, str(path), int(inserted.lastrowid)),
            )
    return True


def index_path(
    storage: Storage,
    target: Path | str,
    *,
    progress: Callable[[int, str], None] | None = None,
    max_files: int = 1000,
) -> tuple[int, int]:
    root = Path(target).expanduser()
    if not root.exists():
        raise KnowledgeError(f"path does not exist: {root}")
    if root.is_file():
        files: Iterable[Path] = [root]
    else:
        found: list[Path] = []
        for path in root.rglob("*"):
            if len(found) >= max_files:
                break
            if any(part.lower() in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() in SUPPORTED_SUFFIXES and path.is_file():
                found.append(path)
        files = found
    indexed = 0
    skipped = 0
    for number, path in enumerate(files, 1):
        if progress is not None:
            progress(number, str(path))
        try:
            if index_file(storage, path):
                indexed += 1
            else:
                skipped += 1
        except (KnowledgeError, OSError, ValueError):
            skipped += 1
    return indexed, skipped


def _query_expression(query: str) -> str:
    tokens = re.findall(r"[\w'-]{2,}", query, flags=re.UNICODE)[:12]
    return " OR ".join(f'"{token}"' for token in tokens)


def search(storage: Storage, query: str, limit: int = 6) -> list[dict[str, object]]:
    expression = _query_expression(query)
    if not expression:
        return []
    try:
        rows = storage.db.execute(
            "SELECT path, chunk_id, text, bm25(doc_chunks_fts) AS rank "
            "FROM doc_chunks_fts WHERE doc_chunks_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (expression, limit),
        ).fetchall()
    except Exception:
        rows = []
    if not rows:
        like = f"%{query.strip()}%"
        rows = storage.db.execute(
            "SELECT d.path AS path, c.id AS chunk_id, c.text AS text, 0 AS rank "
            "FROM doc_chunks c JOIN documents d ON d.id = c.doc_id "
            "WHERE c.text LIKE ? LIMIT ?",
            (like, limit),
        ).fetchall()
    return [
        {
            "path": str(row["path"]),
            "chunk_id": int(row["chunk_id"]),
            "text": str(row["text"]),
        }
        for row in rows
    ]


def document_context(storage: Storage, query: str, *, max_chars: int = 3000) -> str:
    hits = search(storage, query, 5)
    if not hits:
        return ""
    parts: list[str] = []
    used = 0
    for hit in hits:
        text = str(hit["text"]).strip()
        block = f"[{hit['path']}]\n{text}"
        if used + len(block) > max_chars:
            block = block[: max(0, max_chars - used)]
        if not block:
            break
        parts.append(block)
        used += len(block)
        if used >= max_chars:
            break
    return "\n\n".join(parts)


def list_documents(storage: Storage) -> list[dict[str, object]]:
    rows = storage.db.execute(
        "SELECT d.id, d.path, d.title, d.size, d.indexed_at, "
        "(SELECT COUNT(*) FROM doc_chunks c WHERE c.doc_id = d.id) AS chunks "
        "FROM documents d ORDER BY d.path"
    ).fetchall()
    return [
        {
            "id": int(row["id"]),
            "path": str(row["path"]),
            "title": str(row["title"]),
            "size": int(row["size"]),
            "chunks": int(row["chunks"]),
        }
        for row in rows
    ]


def remove_document(storage: Storage, value: str) -> int:
    row = None
    if value.isdigit():
        row = storage.db.execute(
            "SELECT id, path FROM documents WHERE id = ?", (int(value),)
        ).fetchone()
    if row is None:
        row = storage.db.execute(
            "SELECT id, path FROM documents WHERE path = ?", (value,)
        ).fetchone()
    if row is None:
        return 0
    with storage.db:
        _drop_document(storage, int(row["id"]), str(row["path"]))
    return 1


def clear_documents(storage: Storage) -> int:
    count = storage.db.execute("SELECT COUNT(*) AS n FROM documents").fetchone()["n"]
    with storage.db:
        storage.db.execute("DELETE FROM doc_chunks_fts")
        storage.db.execute("DELETE FROM doc_chunks")
        storage.db.execute("DELETE FROM documents")
    return int(count)
