"""Embedding and reranking clients.

Providers:
  tei  - Hugging Face text-embeddings-inference (self-hosted, GPU in production)
  hash - deterministic feature-hashing embedder for tests and credential-free dev.
         It is NOT semantically meaningful beyond lexical overlap; swap for TEI in real use.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

import httpx
import numpy as np

from eb.config import get_settings

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.\-/][a-z0-9]+)*")


class Embedder(Protocol):
    model_name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Feature-hashed unigram+bigram embedding, L2-normalised. Deterministic, dependency-free."""

    def __init__(self, dim: int = 1024):
        self.dim = dim
        self.model_name = f"hash-{dim}"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(self.dim, dtype=np.float32)
        toks = _TOKEN_RE.findall(text.lower())
        grams = toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:], strict=False)]
        for g in grams:
            h = hashlib.blake2b(g.encode(), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            v[idx] += sign
        n = float(np.linalg.norm(v))
        if n > 0:
            v /= n
        return v

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t).tolist() for t in texts]


class TEIEmbedder:
    def __init__(self, url: str, model_name: str, dim: int, batch_size: int = 32):
        self.url = url.rstrip("/")
        self.model_name = model_name
        self.dim = dim
        self.batch_size = batch_size
        self._client = httpx.Client(timeout=120.0)

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            r = self._client.post(
                f"{self.url}/embed", json={"inputs": batch, "normalize": True, "truncate": True}
            )
            r.raise_for_status()
            out.extend(r.json())
        return out


class TEIReranker:
    def __init__(self, url: str):
        self.url = url.rstrip("/")
        self._client = httpx.Client(timeout=120.0)

    def rerank(self, query: str, texts: list[str]) -> list[float]:
        """Return a relevance score per text, in input order."""
        if not texts:
            return []
        r = self._client.post(
            f"{self.url}/rerank",
            json={"query": query, "texts": texts, "raw_scores": False, "truncate": True},
        )
        r.raise_for_status()
        scores = [0.0] * len(texts)
        for item in r.json():
            scores[item["index"]] = float(item["score"])
        return scores


_embedder: Embedder | None = None
_reranker: TEIReranker | None = None


def get_embedder() -> Embedder:
    global _embedder
    if _embedder is None:
        s = get_settings()
        if s.embedding_provider == "tei":
            _embedder = TEIEmbedder(s.tei_embed_url, s.embedding_model, s.embedding_dim)
        else:
            _embedder = HashEmbedder(s.embedding_dim)
    return _embedder


def get_reranker() -> TEIReranker | None:
    global _reranker
    s = get_settings()
    if s.tei_rerank_url and _reranker is None:
        _reranker = TEIReranker(s.tei_rerank_url)
    return _reranker


def approx_tokens(text: str) -> int:
    """Cheap token estimate (~4 chars per token for English technical text)."""
    return max(1, math.ceil(len(text) / 4))
