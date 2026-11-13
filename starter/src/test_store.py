"""Real pgvector integration tests on a disposable, uniquely named table."""
import sys
import unittest
import uuid
import tempfile
import json
from pathlib import Path
from unittest.mock import patch

import psycopg
from psycopg import sql
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models import Chunk
from src.store import PgVectorStore


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.url = dotenv_values(Path(__file__).resolve().parents[1] / '.env').get('DATABASE_URL')
        if not self.url:
            self.skipTest('starter/.env DATABASE_URL is required for integration tests')
        self.table = 'test_day6_' + uuid.uuid4().hex
        # Register cleanup before schema creation, including partially failed setup.
        self.addCleanup(self.drop_test_table)
        self.store = PgVectorStore(self.url, 3, table_name=self.table)
        self.store.create_schema()

    def drop_test_table(self):
        assert self.table.startswith('test_day6_') and len(self.table) == 42
        with psycopg.connect(self.url, connect_timeout=5) as connection:
            connection.execute(sql.SQL('DROP TABLE IF EXISTS {}').format(sql.Identifier(self.table)))

    def test_cosine_ranking_filters_and_strategy_isolation(self):
        chunks = [Chunk('a', 'doc', 'a.pdf', 1, 'alpha', {'chapter': 1}),
                  Chunk('b', 'doc', 'a.pdf', 2, 'beta', {'chapter': 2}),
                  Chunk('c', 'doc', 'a.pdf', 3, 'gamma', {'chapter': 2})]
        self.store.upsert('A', chunks, [[1,0,0], [0,1,0], [0.5,0.5,0]])
        self.store.upsert('B', [chunks[0]], [[0,0,1]])
        hits = self.store.search('A', [1,0,0])
        self.assertEqual([hit['chunk_id'] for hit in hits], ['a','c','b'])
        self.assertAlmostEqual(hits[0]['score'], 1)
        self.assertEqual(hits[0]['metadata']['document_id'], 'doc')
        filtered = self.store.search('A', [1,0,0], filters={'chapter': 2})
        self.assertEqual([hit['chunk_id'] for hit in filtered], ['c','b'])
        self.assertEqual(self.store.search('A', [1,0,0], filters={'source': "x' OR TRUE --"}), [])
        self.assertEqual(len(self.store.search('B', [1,0,0])), 1)
        with self.assertRaises(ValueError):
            self.store.search('A', [1,0,0], filters={'unapproved_key': 1})

    def test_reingestion_replaces_stale_chunks_but_preserves_other_documents(self):
        old = Chunk('old', 'doc1', 'a', 1, 'old')
        other = Chunk('other', 'doc2', 'b', 1, 'other')
        new = Chunk('new', 'doc1', 'a', 1, 'new')
        self.store.upsert('A', [old,other], [[1,0,0],[0,1,0]])
        self.store.upsert('A', [new], [[1,0,0]])
        self.store.upsert('A', [new], [[1,0,0]])
        self.assertEqual(self.store.count('A'), 2)
        self.assertEqual({hit['chunk_id'] for hit in self.store.search('A',[1,0,0])}, {'new','other'})
        self.store.upsert('A', [], [], document_ids=['doc1'])
        self.assertEqual(self.store.count('A'), 1)
        self.assertEqual(self.store.count('A', 'doc1'), 0)

    def test_invalid_vectors_are_rejected_and_failed_write_rolls_back(self):
        chunk = Chunk('old', 'doc', 'a', 1, 'old')
        self.store.upsert('A', [chunk], [[1,0,0]])
        for vectors in ([], [[1,0]], [[0,0,0]], [[float('nan'),0,0]]):
            with self.subTest(vectors=vectors), self.assertRaises(ValueError):
                self.store.upsert('A', [chunk], vectors)
        self.assertEqual(self.store.count('A'), 1)
        # Finite float64 accepted at the Python boundary, but outside vector float32 range.
        with self.assertRaises(psycopg.Error):
            self.store.upsert('A', [Chunk('new', 'doc', 'a', 1, 'new')], [[1e100,0,0]])
        self.assertEqual(self.store.search('A',[1,0,0])[0]['chunk_id'], 'old')
        with self.assertRaises(ValueError):
            PgVectorStore(self.url, 2, table_name=self.table).create_schema()
        for vector in ([1,0], [0,0,0], [float('inf'),0,0]):
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                self.store.search('A', vector)

    def test_synthetic_orchestration_ingest_then_dev_then_test(self):
        from src import run

        class FixtureEmbedder:
            total_tokens = 0
            document_batches = 0
            query_calls = 0

            def embed_documents(self, texts):
                self.document_batches += 1
                self.total_tokens += len(texts)
                return [[1,0,0] if text == 'alpha evidence' else [0,1,0] for text in texts]

            def embed_query(self, text):
                self.query_calls += 1
                return [1,0,0]

        chunks = [Chunk('alpha', 'doc', 'fixture.pdf', 1, 'alpha evidence', {'chapter': 1}),
                  Chunk('beta', 'doc', 'fixture.pdf', 2, 'beta evidence', {'chapter': 2})]
        questions = [{'id': 'unit-' + split, 'split': split, 'question': 'synthetic query',
                      'expected_answer': 'alpha', 'gold_source_id': 'doc', 'gold_page': 1,
                      'evidence_quote': 'alpha evidence', 'filter': {'chapter': 1}} for split in ['dev', 'test']]
        prepared = {'manifest': {'source_id': 'doc', 'license_or_permission': {'external_ai_upload_ready': True}},
                    'questions': questions, 'chunks': {'A': chunks, 'B': chunks, 'C': chunks}}
        config = {'model': 'synthetic-unit-fixture', 'dimensions': 3}
        embedder = FixtureEmbedder()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            with patch.object(run, 'MyEmbedder', return_value=embedder), patch.object(run, 'PgVectorStore', return_value=self.store):
                ingested = run.ingest(prepared, config, output, self.url)
            self.assertEqual(embedder.document_batches, 2)  # C reuses B's actual stored vectors.
            self.assertEqual(ingested['strategies']['C']['stored_chunks'], 2)
            with self.assertRaisesRegex(ValueError, 'prior run record'):
                run.evaluate_benchmark(prepared, config, output, self.store, embedder, 'test')
            self.assertEqual(embedder.query_calls, 0)
            dev = run.evaluate_benchmark(prepared, config, output, self.store, embedder, 'dev')
            self.assertTrue(all(row['hit_at_3']['rate'] == 1 for row in dev['by_strategy_split']))
            test = run.evaluate_benchmark(prepared, config, output, self.store, embedder, 'test')
            self.assertEqual(len(test['by_strategy_split']), 3)
            self.assertEqual(embedder.query_calls, 2)
            rows = [json.loads(line) for line in (output / 'traces.test.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual([row['applied_filter'] for row in rows], [{}, {}, {'chapter': 1}])
            self.assertTrue(all(row['manual_grounding_score'] is None for row in rows))
            audit_path = output/'manual_audit.test.json'
            audit = json.loads(audit_path.read_text(encoding='utf-8'))
            self.assertEqual([row['filter_compliance'] for row in audit], [None, None, None])
            audit[0]['grounding_score'] = 2
            audit_path.write_text(json.dumps(audit), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                run.evaluate_benchmark(prepared, config, output, self.store, embedder, 'test')
            self.assertEqual(json.loads(audit_path.read_text(encoding='utf-8'))[0]['grounding_score'], 2)


if __name__ == '__main__':
    unittest.main()
