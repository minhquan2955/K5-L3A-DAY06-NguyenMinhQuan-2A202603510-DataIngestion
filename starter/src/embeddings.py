"""OpenAI embeddings; run this file to check the configured API connection."""
import os
from pathlib import Path
from typing import Protocol

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError


class Embedder(Protocol):
    model_name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text, in the same order."""
        ...

    def embed_query(self, question: str) -> list[float]:
        """Return a query vector compatible with the stored document vectors."""
        ...


class MyEmbedder:
    """Use the same model and dimensions for document and query vectors."""

    def __init__(self, model_name: str | None = None, dimensions: int = 1536) -> None:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        self.model_name = model_name or os.getenv("EMBEDDING_MODEL") or "text-embedding-3-small"
        if dimensions <= 0:
            raise ValueError("Embedding dimensions must be positive")
        self.dimensions = dimensions
        self.total_tokens = 0
        self._client = OpenAI(timeout=30.0, max_retries=1)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if any(not isinstance(text, str) or not text.strip() for text in texts):
            raise ValueError("Each embedding input must be non-empty text")
        response = self._client.embeddings.create(
            model=self.model_name, input=texts, dimensions=self.dimensions,
            encoding_format="float",
        )
        items = sorted(response.data, key=lambda item: item.index)
        if [item.index for item in items] != list(range(len(texts))):
            raise ValueError("Embedding response does not match the input documents")
        vectors = [item.embedding for item in items]
        if any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError("Embedding response has unexpected dimensions")
        if getattr(response, 'usage', None) is not None:
            self.total_tokens += response.usage.total_tokens
        return vectors

    def embed_query(self, question: str) -> list[float]:
        return self.embed_documents([question])[0]


if __name__ == "__main__":
    import sys

    try:
        embedder = MyEmbedder()
        documents = embedder.embed_documents([
            "Data ingestion prepares documents for retrieval.",
            "Metadata links each chunk to its source page.",
        ])
        query = embedder.embed_query("How does metadata help retrieval?")
    except OpenAIError as exc:
        # Provider messages can include credential fragments; report only error codes.
        sys.exit(f"Embedding check failed: {type(exc).__name__}; "
                 f"HTTP={getattr(exc, 'status_code', None)}; "
                 f"code={getattr(exc, 'code', None)}")
    print(f"Embedding OK | model={embedder.model_name} | documents={len(documents)} "
          f"| dimensions={embedder.dimensions} | query_dimensions={len(query)}")
