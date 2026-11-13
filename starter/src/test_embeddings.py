"""Offline adapter checks: python -m unittest test_embeddings -v."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from embeddings import MyEmbedder


class EmbeddingTests(unittest.TestCase):
    def setUp(self):
        # Replace only the external API boundary; exercise the real adapter.
        client_patch = patch("embeddings.OpenAI", create=True)
        self.client = client_patch.start().return_value
        self.addCleanup(client_patch.stop)

    def test_vectors_keep_document_order_and_query_compatibility(self):
        embedder = MyEmbedder("text-embedding-3-small", dimensions=3)
        self.client.embeddings.create.return_value = SimpleNamespace(data=[
            SimpleNamespace(index=1, embedding=[0.0, 1.0, 0.0]),
            SimpleNamespace(index=0, embedding=[1.0, 0.0, 0.0]),
        ])
        self.assertEqual(embedder.embed_documents(["first", "second"]),
                         [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
        self.client.embeddings.create.assert_called_with(
            model="text-embedding-3-small", input=["first", "second"],
            dimensions=3, encoding_format="float")
        self.client.embeddings.create.return_value = SimpleNamespace(data=[
            SimpleNamespace(index=0, embedding=[1.0, 0.0, 0.0]),
        ])
        self.assertEqual(embedder.embed_query("first"), [1.0, 0.0, 0.0])

    def test_empty_batch_and_blank_text_do_not_call_api(self):
        embedder = MyEmbedder("text-embedding-3-small", dimensions=3)
        self.assertEqual(embedder.embed_documents([]), [])
        for texts in ([""], ["   "], ["valid", ""]):
            with self.subTest(texts=texts), self.assertRaises(ValueError):
                embedder.embed_documents(texts)
        self.client.embeddings.create.assert_not_called()

    def test_rejects_wrong_dimensions_and_missing_vectors(self):
        embedder = MyEmbedder("text-embedding-3-small", dimensions=3)
        for data in ([], [SimpleNamespace(index=0, embedding=[1.0])],
                     [SimpleNamespace(index=1, embedding=[1.0, 0.0, 0.0])]):
            self.client.embeddings.create.return_value = SimpleNamespace(data=data)
            with self.subTest(data=data), self.assertRaises(ValueError):
                embedder.embed_documents(["text"])

    def test_provider_failure_is_not_replaced_with_fake_vectors(self):
        embedder = MyEmbedder("text-embedding-3-small", dimensions=3)
        self.client.embeddings.create.side_effect = RuntimeError("provider unavailable")
        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            embedder.embed_query("text")


if __name__ == "__main__":
    unittest.main()
