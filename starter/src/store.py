"""Persistent pgvector storage with exact cosine ranking and transactional updates."""
import math
from typing import Any

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from .models import Chunk

FILTER_KEYS = {'document_id', 'source', 'page', 'chapter', 'section', 'year', 'language',
               'category', 'version', 'audience', 'effective_date', 'document_type', 'run_fingerprint'}


class PgVectorStore:
    def __init__(self, database_url: str, dimensions: int, *, table_name: str = 'day6_chunks') -> None:
        if type(dimensions) is not int or dimensions <= 0:
            raise ValueError('Vector dimensions must be a positive integer')
        if not database_url or not table_name:
            raise ValueError('Database URL and table name are required')
        self.database_url = database_url
        self.dimensions = dimensions
        self.table_name = table_name
        self.table = sql.Identifier(table_name)

    def _vector(self, vector: list[float]) -> str:
        if len(vector) != self.dimensions:
            raise ValueError(f'Expected {self.dimensions} vector dimensions')
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in vector) or not any(vector):
            raise ValueError('Cosine vectors must be finite, numeric and nonzero')
        return '[' + ','.join(str(float(value)) for value in vector) + ']'

    def create_schema(self) -> None:
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            connection.execute(sql.SQL('''CREATE TABLE IF NOT EXISTS {} (
                strategy text NOT NULL, chunk_id text NOT NULL,
                document_id text NOT NULL, source text NOT NULL, page integer NOT NULL CHECK (page > 0),
                text text NOT NULL, metadata jsonb NOT NULL, embedding vector({}) NOT NULL,
                PRIMARY KEY (strategy, chunk_id)
            )''').format(self.table, sql.Literal(self.dimensions)))
            row = connection.execute('''SELECT format_type(atttypid, atttypmod)
                FROM pg_attribute WHERE attrelid = to_regclass(%s) AND attname = 'embedding' ''',
                (self.table.as_string(connection),)).fetchone()
            if not row or row[0] != f'vector({self.dimensions})':
                raise ValueError('Existing vector table has different dimensions; use a separate table')

    def upsert(self, strategy: str, chunks: list[Chunk], vectors: list[list[float]],
               *, document_ids: list[str] | None = None) -> None:
        """Atomically replace snapshots of the supplied documents, retaining other documents.

        document_ids also identifies documents whose new snapshot contains zero chunks.
        Supply complete chunk sets for each affected document, not partial batches.
        """
        if not strategy or len(chunks) != len(vectors):
            raise ValueError('Strategy and one vector per chunk are required')
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError('Duplicate chunk IDs in the input snapshot')
        affected = set(document_ids if document_ids is not None else [c.document_id for c in chunks])
        rows = []
        for chunk, vector in zip(chunks, vectors):
            if (not chunk.chunk_id or not chunk.document_id or not chunk.source or not chunk.text.strip()
                    or type(chunk.page) is not int or chunk.page <= 0 or chunk.document_id not in affected):
                raise ValueError('Chunk identity, source, page, text or document snapshot is invalid')
            rows.append((strategy, chunk.chunk_id, chunk.document_id, chunk.source, chunk.page,
                         chunk.text, Jsonb(chunk.metadata), self._vector(vector)))
        if not affected:
            return
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            connection.execute(sql.SQL('DELETE FROM {} WHERE strategy = %s AND document_id = ANY(%s)').format(self.table),
                               (strategy, sorted(affected)))
            with connection.cursor() as cursor:
                cursor.executemany(sql.SQL('''INSERT INTO {} (strategy, chunk_id, document_id,
                    source, page, text, metadata, embedding) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::vector)''').format(self.table), rows)

    def search(self, strategy: str, query_vector: list[float], top_k: int = 3,
               filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Apply allowlisted equality filters and rank by exact cosine similarity."""
        vector = self._vector(query_vector)
        if type(top_k) is not int or top_k <= 0:
            raise ValueError('top_k must be a positive integer')
        filters = filters or {}
        if set(filters) - FILTER_KEYS:
            raise ValueError('Unsupported metadata filter key')
        clauses = [sql.SQL('strategy = %s')]
        parameters = [vector, strategy]
        for key, value in filters.items():
            if not isinstance(value, (str, int, float, bool)) or (isinstance(value, float) and not math.isfinite(value)):
                raise ValueError('Filter values must be finite scalar values')
            if key in {'document_id', 'source', 'page'}:
                clauses.append(sql.SQL('{} = %s').format(sql.Identifier(key)))
                parameters.append(value)
            else:
                clauses.append(sql.SQL('metadata @> %s'))
                parameters.append(Jsonb({key: value}))
        query = sql.SQL('''SELECT chunk_id, document_id, source, page, text, metadata,
            1 - (embedding <=> %s::vector) AS score FROM {}
            WHERE {} ORDER BY embedding <=> %s::vector, chunk_id LIMIT %s''').format(
                self.table, sql.SQL(' AND ').join(clauses))
        with psycopg.connect(self.database_url, connect_timeout=5, row_factory=dict_row) as connection:
            rows = connection.execute(query, [*parameters, vector, top_k]).fetchall()
        for row in rows:
            row['metadata'] = {**row['metadata'], 'document_id': row['document_id'],
                               'source': row['source'], 'page': row['page']}
        return rows

    def count(self, strategy: str, document_id: str | None = None,
              *, run_fingerprint: str | None = None) -> int:
        query = sql.SQL('SELECT count(*) FROM {} WHERE strategy = %s').format(self.table)
        parameters = [strategy]
        if document_id is not None:
            query += sql.SQL(' AND document_id = %s')
            parameters.append(document_id)
        if run_fingerprint is not None:
            query += sql.SQL(' AND metadata @> %s')
            parameters.append(Jsonb({'run_fingerprint': run_fingerprint}))
        with psycopg.connect(self.database_url, connect_timeout=5) as connection:
            return connection.execute(query, parameters).fetchone()[0]
