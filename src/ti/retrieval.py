"""Hybrid RAG retrieval using sparse lexical and latent semantic signals."""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import asdict
from typing import Any

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import Normalizer

from .corpus import EvidenceChunk
from .governance import AccessContext, Authorizer


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+")


class BM25Index:
    def __init__(self, documents: list[str], k1: float = 1.5, b: float = 0.75):
        self.docs = [[token.lower() for token in TOKEN_RE.findall(doc)] for doc in documents]
        self.k1 = k1
        self.b = b
        self.lengths = [len(doc) for doc in self.docs]
        self.avgdl = sum(self.lengths) / max(len(self.lengths), 1)
        self.term_freqs = [Counter(doc) for doc in self.docs]
        document_frequency = Counter()
        for doc in self.docs:
            document_frequency.update(set(doc))
        n = max(len(self.docs), 1)
        self.idf = {term: math.log(1 + (n - freq + 0.5) / (freq + 0.5)) for term, freq in document_frequency.items()}

    def scores(self, query: str) -> np.ndarray:
        terms = [token.lower() for token in TOKEN_RE.findall(query)]
        scores = np.zeros(len(self.docs), dtype=float)
        for index, frequencies in enumerate(self.term_freqs):
            dl = self.lengths[index]
            for term in terms:
                tf = frequencies.get(term, 0)
                if not tf:
                    continue
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / max(self.avgdl, 1))
                scores[index] += self.idf.get(term, 0.0) * tf * (self.k1 + 1) / denominator
        maximum = scores.max(initial=0.0)
        return scores / maximum if maximum > 0 else scores


class HybridRetriever:
    """BM25 + TF-IDF + LSA retrieval with account-level authorization filtering."""

    def __init__(self, chunks: list[EvidenceChunk], latent_dimensions: int = 64):
        if not chunks:
            raise ValueError("At least one evidence chunk is required")
        self.chunks = chunks
        documents = [f"{chunk.title} {chunk.text}" for chunk in chunks]
        self.vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words="english",
            ngram_range=(1, 2),
            min_df=1,
            max_df=0.98,
            max_features=12000,
            sublinear_tf=True,
        )
        self.sparse = self.vectorizer.fit_transform(documents)
        dimensions = min(latent_dimensions, max(2, min(self.sparse.shape) - 1))
        self.svd = TruncatedSVD(n_components=dimensions, random_state=42)
        self.normalizer = Normalizer(copy=False)
        self.semantic = self.normalizer.fit_transform(self.svd.fit_transform(self.sparse))
        self.bm25 = BM25Index(documents)
        self.authorizer = Authorizer()

    def search(self, query: str, context: AccessContext, top_k: int = 5, account_domain: str = "") -> list[dict[str, Any]]:
        self.authorizer.require(context, "search", account_domain)
        query_sparse = self.vectorizer.transform([query])
        lexical = cosine_similarity(query_sparse, self.sparse).ravel()
        semantic_query = self.normalizer.transform(self.svd.transform(query_sparse))
        semantic = cosine_similarity(semantic_query, self.semantic).ravel()
        bm25 = self.bm25.scores(query)
        # Give exact-word matches a little more weight while keeping related language useful.
        combined = 0.40 * bm25 + 0.30 * lexical + 0.30 * semantic
        ranked = np.argsort(-combined)
        results = []
        for index in ranked:
            chunk = self.chunks[int(index)]
            if account_domain and account_domain not in chunk.customer_domain.split(";"):
                continue
            # Skip evidence outside the caller's account scope before returning results.
            if context.account_scopes and chunk.customer_domain:
                domains = set(filter(None, chunk.customer_domain.split(";")))
                if domains and not domains.intersection(context.account_scopes):
                    continue
            results.append({
                **asdict(chunk),
                "score": round(float(combined[index]), 6),
                "score_breakdown": {
                    "bm25": round(float(bm25[index]), 6),
                    "tfidf": round(float(lexical[index]), 6),
                    "lsa": round(float(semantic[index]), 6),
                },
            })
            if len(results) >= top_k:
                break
        return results
