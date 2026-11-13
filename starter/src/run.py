"""Explicit prepare/ingest/eval commands; preparation never calls an API or eval."""
import argparse
import hashlib
import json
import logging
import math
import os
import statistics
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAIError

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import canonical_text, load_pdf
from .store import FILTER_KEYS, PgVectorStore

ROOT = Path(__file__).resolve().parents[2]


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_id(config: dict) -> str:
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode('utf-8')).hexdigest()


def chunk_fingerprints(strategies: dict) -> dict:
    """Bind index and dev selection to actual chunk content, offsets and metadata."""
    return {name: hashlib.sha256(json.dumps([asdict(c) for c in chunks], sort_keys=True,
                ensure_ascii=False).encode('utf-8')).hexdigest() for name, chunks in strategies.items()}


def validate_frozen_inputs(root: Path, manifest_path: Path, questions_path: Path, freeze_path: Path):
    """Validate exact snapshot bytes and the split before any processing or API call."""
    manifest, questions, freeze = read_json(manifest_path), read_json(questions_path), read_json(freeze_path)
    source_path = (root / manifest['source_path_or_url']).resolve()
    for path in (manifest_path, questions_path, source_path):
        name = path.resolve().relative_to(root.resolve()).as_posix()
        if freeze['files'].get(name) != file_hash(path):
            raise ValueError(f'Frozen input changed or path is missing from freeze: {name}')
    if manifest['snapshot']['sha256'] != file_hash(source_path):
        raise ValueError('PDF differs from the manifest snapshot')
    ids = [q['id'] for q in questions]
    if len(ids) < 20 or len(set(ids)) != len(ids):
        raise ValueError('Require at least 20 unique benchmark question IDs')
    if any(q['split'] not in {'dev', 'test'} for q in questions):
        raise ValueError('Only dev/test splits are permitted')
    for split, minimum in [('dev', 15), ('test', 5)]:
        actual = [q['id'] for q in questions if q['split'] == split]
        if len(actual) < minimum or actual != freeze['splits'][split]:
            raise ValueError(f'Frozen {split} split changed')
    if sum(bool(q.get('filter')) for q in questions) < 3 or not any(q['split'] == 'test' and q.get('filter') for q in questions):
        raise ValueError('Require at least 3 filter questions, including a test question')
    return manifest, questions, freeze


def prepare_corpus(root: Path, manifest: dict, questions: list, *, size: int, overlap: int, paragraph_size: int) -> dict:
    all_pages = load_pdf(root / manifest['source_path_or_url'], manifest['source_id'],
                         manifest['source_path_or_url'],
                         manifest['normalization'].get('font_specific_ligature_replacements'))
    rows = {row['page']: row for row in manifest['pages']}
    if len(all_pages) != manifest['physical_page_count'] or len(rows) != len(all_pages):
        raise ValueError('Physical PDF page count differs from manifest')
    pages = []
    for page in all_pages:
        row = rows[page.page]
        if page.metadata['normalized_char_count'] != row['normalized_char_count']:
            raise ValueError(f'Normalization differs from manifest on page {page.page}')
        if row['included']:
            if page.metadata['extraction_status'] != 'ok':
                raise ValueError(f'Included PDF page {page.page} is empty or unreadable')
            page.metadata.update(chapter=row['chapter'], language=manifest['language'], printed_page=row['printed_page'])
            pages.append(page)
    if len(pages) < 30 or len(pages) != manifest['included_content_page_count']:
        raise ValueError('Require at least 30 valid content pages matching the manifest')
    page_map = {p.page: p for p in pages}
    for question in questions:
        if not question['question'].strip() or not question['expected_answer'].strip():
            raise ValueError('Question text and expected answer are required')
        if set(question.get('filter', {})) - (FILTER_KEYS - {'run_fingerprint'}):
            raise ValueError('Unsupported question filter')
        for gold in [question] + question.get('alternative_gold', []):
            page = page_map.get(gold['gold_page'])
            if (page is None or gold['gold_source_id'] != manifest['source_id']
                    or not canonical_text(gold['evidence_quote'])
                    or canonical_text(gold['evidence_quote']) not in canonical_text(page.text)):
                raise ValueError(f"Gold evidence does not match source: {question['id']}")
        for key, value in question.get('filter', {}).items():
            page = page_map[question['gold_page']]
            actual = {'document_id': page.document_id, 'source': page.source, 'page': page.page,
                      **page.metadata}.get(key)
            if value != actual:
                raise ValueError(f"Filter contradicts source metadata: {question['id']}")
    a = [chunk for page in pages for chunk in fixed_size(page, size, overlap)]
    b = [chunk for page in pages for chunk in by_paragraph(page, paragraph_size)]
    return {'manifest': manifest, 'questions': questions, 'pages': pages,
            'chunks': {'A': a, 'B': b, 'C': b},
            'extraction_issues': [{'page': p.page, **p.metadata} for p in all_pages
                                  if p.metadata['extraction_status'] != 'ok']}


def write_preparation(prepared: dict, output: Path, config: dict) -> dict:
    if (output / 'prepared.json').exists():
        require_matching_config(output / 'prepared.json', config)
    stats = {}
    for strategy, chunks in prepared['chunks'].items():
        lengths = [len(c.text) for c in chunks]
        stats[strategy] = {'chunks': len(chunks), 'total_chars': sum(lengths),
                           'min_chars': min(lengths), 'max_chars': max(lengths),
                           'mean_chars': statistics.mean(lengths), 'median_chars': statistics.median(lengths)}
        with (output / f'chunks.{strategy}.jsonl').open('w', encoding='utf-8') as stream:
            for chunk in chunks:
                stream.write(json.dumps(asdict(chunk), ensure_ascii=False) + '\n')
    samples = []
    # Fix positions from source order before seeing retrieval results.
    for page in prepared['pages'][:10]:
        position = len(page.text) // 2
        while position < len(page.text) and page.text[position].isspace():
            position += 1
        if position == len(page.text):
            position = len(page.text.rstrip()) - 1
        for strategy, chunks in prepared['chunks'].items():
            chunk = next(c for c in chunks if c.page == page.page
                         and c.metadata['start_char'] <= position < c.metadata['end_char'])
            samples.append({'strategy': strategy, 'document_id': page.document_id,
                            'page': page.page, 'source_position': position,
                            'chunk_id': chunk.chunk_id, 'text': chunk.text, 'score': None, 'reason': ''})
    audit_path = output / 'coherence_samples.json'
    if audit_path.exists():
        existing = read_json(audit_path)
        identities = lambda rows: [(r['strategy'], r['page'], r['source_position'], r['chunk_id']) for r in rows]
        if identities(existing) != identities(samples):
            raise ValueError('Existing coherence samples differ; use a new output directory')
    else:
        write_json(audit_path, samples)
    report = {'content_pages': len(prepared['pages']), 'strategies': stats,
              'extraction_issues': prepared['extraction_issues'], 'config': config}
    write_json(output / 'prepared.json', report)
    return report


def ingest(prepared: dict, config: dict, output: Path, database_url: str,
           *, batch_size: int = 64, price_per_million: float | None = None) -> dict:
    if prepared['manifest']['license_or_permission'].get('external_ai_upload_ready') is not True:
        raise ValueError('Corpus API-use permission is not documented in the manifest')
    embedder = MyEmbedder(config['model'], config['dimensions'])
    store = PgVectorStore(database_url, config['dimensions'])
    store.create_schema()
    stats, cached_b = {}, None
    for strategy, chunks in prepared['chunks'].items():
        started = time.perf_counter()
        before_tokens = embedder.total_tokens
        if strategy == 'C':
            vectors = cached_b
        else:
            vectors = []
            for start in range(0, len(chunks), batch_size):
                vectors.extend(embedder.embed_documents([c.text for c in chunks[start:start + batch_size]]))
            if strategy == 'B':
                cached_b = vectors
        tagged = []
        for chunk in chunks:
            tagged.append(type(chunk)(chunk.chunk_id, chunk.document_id, chunk.source, chunk.page,
                          chunk.text, {**chunk.metadata, 'run_fingerprint': config_id(config)}))
        document_id = prepared['manifest']['source_id']
        store.upsert(strategy, tagged, vectors, document_ids=[document_id])
        count = store.count(strategy, document_id, run_fingerprint=config_id(config))
        if count != len(chunks):
            raise ValueError('Stored chunk count differs from prepared snapshot')
        tokens = embedder.total_tokens - before_tokens
        stats[strategy] = {'stored_chunks': count, 'seconds': time.perf_counter() - started,
                           'embedding_tokens': tokens,
                           'estimated_cost_usd': tokens * price_per_million / 1_000_000 if price_per_million is not None else None,
                           'embedding_reused_from': 'B' if strategy == 'C' else None}
    result = {'config': config, 'created_at': datetime.now(timezone.utc).isoformat(),
              'strategies': stats, 'cost_note': 'Cost is an estimate only when a provider rate was supplied; otherwise consult provider usage.'}
    write_json(output / 'ingest.json', result)
    return result


def require_matching_config(path: Path, config: dict) -> dict:
    if not path.exists():
        raise ValueError(f'Required prior run record is missing: {path.name}')
    record = read_json(path)
    if record['config'] != config:
        raise ValueError(f'Run configuration differs from {path.name}; ingest/select on dev again')
    return record


def evaluate_benchmark(prepared: dict, config: dict, output: Path, store: PgVectorStore,
                       embedder: MyEmbedder, split: str) -> dict:
    require_matching_config(output / 'ingest.json', config)
    if split == 'test':
        require_matching_config(output / 'selection.dev.json', config)
    protected = [output / f'{prefix}.{split}.{suffix}' for prefix, suffix in
                 [('summary', 'json'), ('traces', 'jsonl'), ('manual_audit', 'json')]]
    if split == 'dev':
        protected.append(output / 'summary.test.json')
    if any(path.exists() for path in protected):
        raise ValueError('Evaluation already exists; use a new experiment output directory')
    document_id = prepared['manifest']['source_id']
    for strategy, chunks in prepared['chunks'].items():
        if store.count(strategy, document_id, run_fingerprint=config_id(config)) != len(chunks):
            raise ValueError('Index is incomplete or was built with a different model/configuration')
    traces, manual_rows = [], []
    for question in prepared['questions']:
        if question['split'] != split:
            continue
        # Embed only the query; gold/answers are used after retrieval for scoring.
        query = embedder.embed_query(question['question'])
        for strategy in ('A', 'B', 'C'):
            applied = question.get('filter', {}) if strategy == 'C' else {}
            hits = store.search(strategy, query, top_k=3,
                                filters={**applied, 'document_id': document_id, 'run_fingerprint': config_id(config)})
            trace = evaluate_query(question, hits, strategy=strategy)
            trace['applied_filter'] = applied
            trace['corpus_filter'] = {'document_id': document_id, 'run_fingerprint': config_id(config)}
            traces.append(trace)
            manual_rows.append({'strategy': strategy, 'question_id': question['id'],
                'question': question['question'], 'grounding_score': None, 'grounding_reason': '',
                'requested_filter': question.get('filter', {}), 'applied_filter': applied,
                'filter_compliance': None if question.get('filter') else 'N/A',
                'hits': [{**hit, 'metadata_correct': None, 'metadata_reason': ''} for hit in hits]})
    summary = summarize(traces)
    with (output / f'traces.{split}.jsonl').open('w', encoding='utf-8') as stream:
        for trace in traces:
            stream.write(json.dumps(trace, ensure_ascii=False, allow_nan=False) + '\n')
    write_json(output / f'summary.{split}.json', summary)
    write_json(output / f'manual_audit.{split}.json', manual_rows)
    if split == 'dev':
        best = min(summary['by_strategy_split'], key=lambda row: (
            -row['hit_at_3']['rate'], -row['hit_at_1']['rate'],
            len(prepared['chunks'][row['strategy']]), row['strategy']))
        write_json(output / 'selection.dev.json', {'config': config, 'selected_strategy': best['strategy'],
                   'selected_at': datetime.now(timezone.utc).isoformat(),
                   'rule': 'dev Evidence Hit@3, then Hit@1, then fewer chunks; alphabetical tie-break'})
    return summary


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['prepare', 'ingest', 'eval'], default='prepare')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'data/manifest.json')
    parser.add_argument('--questions', type=Path, default=ROOT / 'benchmark/questions.json')
    parser.add_argument('--freeze', type=Path, default=ROOT / 'benchmark/freeze.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'starter/results')
    parser.add_argument('--split', choices=['dev', 'test'], default='dev')
    parser.add_argument('--size', type=int, default=500)
    parser.add_argument('--overlap', type=int, default=50)
    parser.add_argument('--paragraph-size', type=int, default=500)
    parser.add_argument('--dimensions', type=int, default=1536)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--price-per-million', type=float)
    args = parser.parse_args(argv)
    if not 1 <= args.batch_size <= 2048 or args.dimensions <= 0:
        parser.error('batch-size must be 1..2048 and dimensions must be positive')
    if args.price_per_million is not None and (not math.isfinite(args.price_per_million) or args.price_per_million < 0):
        parser.error('price-per-million must be finite and nonnegative')
    load_dotenv(ROOT / 'starter/.env')
    manifest, questions, freeze = validate_frozen_inputs(ROOT, args.manifest, args.questions, args.freeze)
    config = {'inputs': freeze['files'], 'model': os.getenv('EMBEDDING_MODEL') or 'text-embedding-3-small',
              'dimensions': args.dimensions, 'fixed_size': args.size, 'overlap': args.overlap,
              'paragraph_size': args.paragraph_size, 'metric': 'cosine', 'search': 'exact', 'top_k': 3}
    prepared = prepare_corpus(ROOT, manifest, questions, size=args.size, overlap=args.overlap,
                              paragraph_size=args.paragraph_size)
    config['chunk_snapshots'] = chunk_fingerprints(prepared['chunks'])
    args.output.mkdir(parents=True, exist_ok=True)
    if args.mode == 'prepare':
        result = write_preparation(prepared, args.output, config)
    else:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError('DATABASE_URL missing from starter/.env')
        if args.mode == 'ingest':
            write_preparation(prepared, args.output, config)
            result = ingest(prepared, config, args.output, database_url,
                            batch_size=args.batch_size, price_per_million=args.price_per_million)
        else:
            result = evaluate_benchmark(prepared, config, args.output,
                       PgVectorStore(database_url, args.dimensions),
                       MyEmbedder(config['model'], args.dimensions), args.split)
    print(json.dumps(result, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s: %(message)s')
    try:
        main()
    except OpenAIError as exc:
        sys.exit(f'OpenAI operation failed: {type(exc).__name__}; HTTP={getattr(exc, "status_code", None)}; code={getattr(exc, "code", None)}')
    except psycopg.Error as exc:
        sys.exit(f'Database operation failed: {type(exc).__name__}; check database setup and schema')
    except (ValueError, OSError, KeyError) as exc:
        sys.exit(f'Pipeline failed: {exc}')
