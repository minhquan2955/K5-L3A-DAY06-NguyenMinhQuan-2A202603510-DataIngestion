"""Implement fixed-size and structure-aware chunking."""
import hashlib
import json
import re

from .models import Chunk, DocumentPage


def _chunk(page: DocumentPage, start: int, end: int, method: str) -> Chunk | None:
    while start < end and page.text[start].isspace():
        start += 1
    while end > start and page.text[end - 1].isspace():
        end -= 1
    if start == end:
        return None
    text = page.text[start:end]
    identity = [page.document_id, page.source, page.page, method, start, end, text]
    chunk_id = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode('utf-8')).hexdigest()
    metadata = {**page.metadata, 'chunking': method, 'start_char': start,
                'end_char': end, 'char_count': len(text)}
    return Chunk(chunk_id, page.document_id, page.source, page.page, text, metadata)


def fixed_size(page: DocumentPage, size: int, overlap: int) -> list[Chunk]:
    """Split into character windows without crossing source-page boundaries."""
    if type(size) is not int or size <= 0 or type(overlap) is not int or not 0 <= overlap < size:
        raise ValueError('Require size > 0 and 0 <= overlap < size')
    chunks = []
    for start in range(0, len(page.text), size - overlap):
        end = min(start + size, len(page.text))
        chunk = _chunk(page, start, end, f'fixed:{size}:{overlap}')
        if chunk:
            chunks.append(chunk)
        if end == len(page.text):
            break
    return chunks


def by_paragraph(page: DocumentPage, max_size: int) -> list[Chunk]:
    """Pack source blocks; infer headings/bullets when PDF extraction loses blank lines."""
    if type(max_size) is not int or max_size <= 0:
        raise ValueError('max_size must be a positive integer')
    boundaries = {0, len(page.text)}
    for separator in re.finditer(r'\n\s*\n', page.text):
        boundaries.update(separator.span())
    title_words = {'a', 'an', 'and', 'as', 'at', 'by', 'for', 'from', 'in', 'of',
                   'on', 'or', 'the', 'to', 'with', 'within', 'between'}
    # ponytail: PDF source-line heuristic; use layout-aware parsing if audits show bad boundaries.
    for line in re.finditer(r'[^\n]+', page.text):
        value = line.group().strip()
        words = value.split()
        heading = (bool(words) and len(value) <= 80 and len(words) <= 12
                   and not value.endswith(('.', '!', '?', ':', ';', ','))
                   and all(word[0].isupper() or word.lower() in title_words for word in words))
        if re.match(r'(?:•\s|\d+\.\s)', value) or heading:
            boundaries.add(line.start())
        if heading or (len(value) < 80 and value.endswith(('.', '!', '?'))):
            boundaries.add(line.end())
    points = sorted(boundaries)
    spans = []
    for start, end in zip(points, points[1:]):
        while start < end and page.text[start].isspace():
            start += 1
        while end > start and page.text[end - 1].isspace():
            end -= 1
        while start < end:
            cut = min(start + max_size, end)
            if cut < end and not page.text[cut].isspace():
                boundary = max(page.text.rfind(' ', start, cut + 1), page.text.rfind('\n', start, cut + 1))
                if boundary > start:
                    cut = boundary
            spans.append((start, cut))
            start = cut
            while start < end and page.text[start].isspace():
                start += 1
    groups = []
    for start, end in spans:
        if groups and end - groups[-1][0] <= max_size:
            groups[-1] = (groups[-1][0], end)
        else:
            groups.append((start, end))
    return [chunk for start, end in groups
            if (chunk := _chunk(page, start, end, f'paragraph-v2:{max_size}')) is not None]
