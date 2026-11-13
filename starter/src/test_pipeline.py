"""Behavior checks; these do not run retrieval evaluation on the lab benchmark."""
import json
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pypdf import PdfWriter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.chunking import by_paragraph, fixed_size
from src.ingestion import load_pdf, normalize_text
from src.models import DocumentPage
from src.evaluation import evaluate_query, summarize

ROOT = Path(__file__).resolve().parents[2]


class IngestionChunkTests(unittest.TestCase):
    def test_normalization_preserves_paragraphs_and_removes_footers(self):
        raw = '  Cafe\u0301\t  notes\r\nsecond line\r\n\r\n Next paragraph \n8     1 • Chapter\nAccess for free at openstax.org\n'
        self.assertEqual(normalize_text(raw), 'Café notes\nsecond line\n\nNext paragraph')

    def test_blank_pdf_page_is_recorded(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'blank.pdf'
            writer = PdfWriter()
            writer.add_blank_page(width=100, height=100)
            writer.write(path)
            with self.assertLogs('src.ingestion', level='WARNING'):
                pages = load_pdf(path, 'doc', 'blank.pdf')
        self.assertEqual(len(pages), 1)
        self.assertEqual((pages[0].document_id, pages[0].page, pages[0].text), ('doc', 1, ''))
        self.assertEqual(pages[0].metadata['extraction_status'], 'empty')

    def test_real_pdf_matches_frozen_page_counts_and_all_evidence(self):
        manifest = json.loads((ROOT / 'data/manifest.json').read_text(encoding='utf-8'))
        with self.assertLogs('src.ingestion', level='WARNING'):
            pages = load_pdf(ROOT / manifest['source_path_or_url'], manifest['source_id'],
                             manifest['source_path_or_url'],
                             manifest['normalization']['font_specific_ligature_replacements'])
        self.assertEqual(len(pages), 83)
        texts = {p.page: re.sub(r'\s+', ' ', p.text).strip() for p in pages}
        for row in manifest['pages']:
            self.assertEqual(len(texts[row['page']]), row['normalized_char_count'])
        questions = json.loads((ROOT / 'benchmark/questions.json').read_text(encoding='utf-8'))
        for question in questions:
            for gold in [question] + question['alternative_gold']:
                start, end = gold['evidence_normalized_char_start'], gold['evidence_normalized_char_end']
                self.assertEqual(texts[gold['gold_page']][start:end], gold['evidence_quote'])

    def test_fixed_windows_cover_text_and_have_stable_ids_and_metadata(self):
        page = DocumentPage('doc', 'a.pdf', 2, 'abcdefghijkl', {'chapter': 2})
        chunks = fixed_size(page, 5, 2)
        self.assertEqual([c.text for c in chunks], ['abcde', 'defgh', 'ghijk', 'jkl'])
        self.assertEqual([c.chunk_id for c in chunks], [c.chunk_id for c in fixed_size(page, 5, 2)])
        self.assertTrue(all(c.metadata['chapter'] == 2 and c.page == 2 for c in chunks))
        self.assertEqual([c.metadata['start_char'] for c in chunks], [0, 3, 6, 9])
        self.assertNotEqual(chunks[0].chunk_id, fixed_size(DocumentPage('other', 'a.pdf', 2, page.text), 5, 2)[0].chunk_id)
        for size, overlap in [(0, 0), (5, 5), (5, -1)]:
            with self.subTest(size=size, overlap=overlap), self.assertRaises(ValueError):
                fixed_size(page, size, overlap)
        self.assertEqual(fixed_size(DocumentPage('d', 'a', 1, '   '), 5, 0), [])

    def test_paragraph_chunks_preserve_boundaries_and_split_long_words_safely(self):
        page = DocumentPage('doc', 'a.pdf', 1, 'alpha beta\n\ngamma delta\n\none two three four', {'chapter': 1})
        chunks = by_paragraph(page, 12)
        self.assertEqual([c.text for c in chunks], ['alpha beta', 'gamma delta', 'one two', 'three four'])
        for chunk in chunks:
            start, end = chunk.metadata['start_char'], chunk.metadata['end_char']
            self.assertEqual(page.text[start:end], chunk.text)
            self.assertLessEqual(len(chunk.text), 12)
        self.assertEqual(''.join(c.text.replace(' ', '').replace('\n', '') for c in chunks),
                         re.sub(r'\s+', '', page.text))
        self.assertEqual([c.text for c in by_paragraph(DocumentPage('d', 'a', 1, 'abcdefghijkl'), 5)], ['abcde', 'fghij', 'kl'])
        self.assertEqual(by_paragraph(DocumentPage('d', 'a', 1, ''), 10), [])
        with self.assertRaises(ValueError):
            by_paragraph(page, 0)

    def test_paragraphs_infer_source_headings_and_bullets_without_blank_lines(self):
        text = 'Overview\nThis is a paragraph\nthat finishes here.\n• First item\n  with continuation.\n• Second item'
        page = DocumentPage('doc', 'a.pdf', 1, text)
        chunks = by_paragraph(page, 40)
        self.assertEqual([c.text for c in chunks], ['Overview', 'This is a paragraph\nthat finishes here.',
                                                   '• First item\n  with continuation.', '• Second item'])


class EvaluationTests(unittest.TestCase):
    def test_source_page_and_complete_evidence_are_all_required(self):
        question = {'id': 'synthetic-q', 'split': 'dev', 'question': 'Where?',
                    'gold_source_id': 'doc', 'gold_page': 2, 'evidence_quote': 'complete evidence'}
        hits = [
            {'document_id': 'wrong', 'page': 2, 'text': 'complete evidence'},
            {'document_id': 'doc', 'page': 9, 'text': 'complete evidence'},
            {'document_id': 'doc', 'page': 2, 'text': 'complete'},
            {'document_id': 'doc', 'page': 2, 'text': 'complete evidence'},
        ]
        trace = evaluate_query(question, hits, strategy='A')
        self.assertEqual((trace['hit_at_1'], trace['hit_at_3']), (0, 0))
        self.assertEqual(len(trace['hits']), 3)
        question['alternative_gold'] = [{'gold_source_id': 'doc', 'gold_page': 9,
                                          'evidence_quote': 'complete evidence'}]
        trace = evaluate_query(question, hits, strategy='B')
        self.assertEqual((trace['hit_at_1'], trace['hit_at_3']), (0, 1))
        self.assertIsNone(trace['manual_grounding_score'])
        hit = {'metadata': {'document_id': 'doc', 'page': 2}, 'text': 'complete\n  evidence'}
        self.assertEqual(evaluate_query(question, [hit], strategy='C')['hit_at_1'], 1)
        self.assertEqual(evaluate_query(question, [], strategy='C')['hit_at_3'], 0)

    def test_summary_keeps_strategy_split_denominators_and_rejects_duplicates(self):
        traces = [
            {'strategy': 'A', 'split': 'dev', 'question_id': 'q1', 'hit_at_1': 1, 'hit_at_3': 1},
            {'strategy': 'A', 'split': 'dev', 'question_id': 'q2', 'hit_at_1': 0, 'hit_at_3': 1},
            {'strategy': 'A', 'split': 'test', 'question_id': 'q3', 'hit_at_1': 0, 'hit_at_3': 0},
            {'strategy': 'B', 'split': 'dev', 'question_id': 'q1', 'hit_at_1': 1, 'hit_at_3': 1},
        ]
        groups = summarize(traces)['by_strategy_split']
        a_dev = next(g for g in groups if g['strategy'] == 'A' and g['split'] == 'dev')
        self.assertEqual(a_dev['hit_at_1'], {'hits': 1, 'total': 2, 'rate': 0.5})
        self.assertEqual(a_dev['hit_at_3'], {'hits': 2, 'total': 2, 'rate': 1.0})
        self.assertEqual(summarize([]), {'by_strategy_split': []})
        with self.assertRaises(ValueError):
            summarize(traces + [traces[0]])


class OrchestrationTests(unittest.TestCase):
    def test_coherence_position_skips_whitespace_trimmed_by_chunkers(self):
        from src import run
        page = DocumentPage('doc', 'fixture.pdf', 1, 'abc def')
        b = by_paragraph(page, 3)
        prepared = {'pages': [page], 'chunks': {'A': fixed_size(page, 3, 0), 'B': b, 'C': b},
                    'extraction_issues': []}
        with tempfile.TemporaryDirectory() as folder:
            run.write_preparation(prepared, Path(folder), {})
            rows = json.loads((Path(folder)/'coherence_samples.json').read_text(encoding='utf-8'))
        self.assertEqual([row['source_position'] for row in rows], [4,4,4])
        self.assertEqual([row['text'] for row in rows], ['de','def','def'])

    def test_preparation_preserves_manual_labels_and_rejects_changed_chunk_config(self):
        from src import run
        page = DocumentPage('doc', 'fixture.pdf', 1, 'abc def')
        b = by_paragraph(page, 3)
        prepared = {'pages': [page], 'chunks': {'A': fixed_size(page, 3, 0), 'B': b, 'C': b},
                    'extraction_issues': []}
        first_digest = run.chunk_fingerprints(prepared['chunks'])
        changed_page = DocumentPage('doc', 'fixture.pdf', 1, 'xyz def')
        altered = {'A': fixed_size(changed_page, 3, 0), 'B': b, 'C': b}
        self.assertEqual(len(prepared['chunks']['A']), len(altered['A']))
        self.assertNotEqual(first_digest, run.chunk_fingerprints(altered))
        config = {'chunk_snapshots': first_digest}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            run.write_preparation(prepared, output, config)
            audit_path = output/'coherence_samples.json'
            audit = json.loads(audit_path.read_text(encoding='utf-8'))
            audit[0].update(score=1, reason='human label')
            audit_path.write_text(json.dumps(audit), encoding='utf-8')
            run.write_preparation(prepared, output, config)
            self.assertEqual(json.loads(audit_path.read_text(encoding='utf-8'))[0]['score'], 1)
            with self.assertRaisesRegex(ValueError, 'configuration'):
                run.write_preparation(prepared, output, {'chunk_snapshots': run.chunk_fingerprints(altered)})

    def test_prepare_writes_chunks_and_audit_samples_without_api_database_or_eval(self):
        from src import run
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(run, 'MyEmbedder', side_effect=AssertionError('unexpected API'), create=True), \
                 patch.object(run, 'PgVectorStore', side_effect=AssertionError('unexpected DB'), create=True), \
                 patch.object(run, 'evaluate_query', side_effect=AssertionError('unexpected eval'), create=True), \
                 patch('sys.stdout', new=io.StringIO()), self.assertLogs('src.ingestion', level='WARNING'):
                run.main(['--mode', 'prepare', '--output', folder])
            report = json.loads((Path(folder) / 'prepared.json').read_text(encoding='utf-8'))
            self.assertEqual(report['content_pages'], 58)
            self.assertEqual(set(report['strategies']), {'A','B','C'})
            self.assertEqual(report['strategies']['B'], report['strategies']['C'])
            self.assertTrue((Path(folder) / 'chunks.B.jsonl').exists())
            self.assertFalse(list(Path(folder).glob('summary.*.json')))
            audit = json.loads((Path(folder) / 'coherence_samples.json').read_text(encoding='utf-8'))
            self.assertEqual(len(audit), 30)
            self.assertTrue(all(row['score'] is None for row in audit))

    def test_changed_frozen_questions_are_rejected(self):
        from src import run
        freeze = json.loads((ROOT / 'benchmark/freeze.json').read_text(encoding='utf-8'))
        freeze['files']['benchmark/questions.json'] = '0' * 64
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'freeze.json'
            path.write_text(json.dumps(freeze), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Frozen input changed'):
                run.validate_frozen_inputs(ROOT, ROOT/'data/manifest.json', ROOT/'benchmark/questions.json', path)

    def test_ingest_requires_documented_permission_and_config_changes_are_rejected(self):
        from src import run
        prepared = {'manifest': {'license_or_permission': {'external_ai_upload_ready': False}}}
        with self.assertRaisesRegex(ValueError, 'permission'):
            run.ingest(prepared, {}, Path('.'), 'unused')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'ingest.json'
            path.write_text(json.dumps({'config': {'model': 'model-a'}}), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'configuration'):
                run.require_matching_config(path, {'model': 'model-b'})


if __name__ == '__main__':
    unittest.main()
