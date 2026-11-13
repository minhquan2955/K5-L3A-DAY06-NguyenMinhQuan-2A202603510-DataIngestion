"""Read physical PDF pages while preserving source and extraction status."""
import logging
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

from .models import DocumentPage

logger = logging.getLogger(__name__)


def load_pdf(path: Path, document_id: str, source: str,
             font_replacements: dict[str, dict[str, str]] | None = None) -> list[DocumentPage]:
    """Return every physical page, including empty/error pages for auditability."""
    maps = {font: {int(code.removeprefix('U+'), 16): value for code, value in mapping.items()}
            for font, mapping in (font_replacements or {}).items()}
    result = []
    for number, page in enumerate(PdfReader(path).pages, 1):
        pieces = []

        def visitor(text, cm, tm, font, size):
            name = str(font.get('/BaseFont')) if font else ''
            pieces.append(text.translate(maps.get(name, {})))

        try:
            page.extract_text(visitor_text=visitor)
            text = normalize_text(''.join(pieces))
            metadata = {'extraction_status': 'ok' if text else 'empty'}
        except Exception as exc:
            text = ''
            metadata = {'extraction_status': 'error', 'extraction_error': type(exc).__name__}
            logger.warning('PDF page %s extraction failed (%s): %s', number, type(exc).__name__, path)
        if not text and metadata['extraction_status'] == 'empty':
            logger.warning('PDF page %s has no body text: %s', number, path)
        metadata['normalized_char_count'] = len(canonical_text(text))
        result.append(DocumentPage(document_id, source, number, text, metadata))
    return result


def normalize_text(text: str) -> str:
    """Normalize NFC/line endings, retaining paragraphs and removing page furniture."""
    lines = []
    for line in unicodedata.normalize('NFC', text).replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        line = re.sub(r'[^\S\n]+', ' ', line).strip()
        if line == 'Access for free at openstax.org':
            continue
        if re.match(r'^(?:\d+\s+)?\d+(?:\.\d+)?\s+•\s', line):
            continue
        if re.fullmatch(r'(?:Preface\s+\d+|\d+\s+Preface)', line):
            continue
        lines.append(line)
    return re.sub(r'\n{3,}', '\n\n', '\n'.join(lines)).strip()


def canonical_text(text: str) -> str:
    """Whitespace-insensitive representation used for manifest counts and evidence."""
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', text)).strip()
