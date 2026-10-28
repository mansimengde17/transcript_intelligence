import unittest
from pathlib import Path

from ti.corpus import EvidenceChunk, load_corpus
from ti.governance import AccessContext
from ti.retrieval import HybridRetriever


class RetrievalTests(unittest.TestCase):
    def test_hybrid_retrieval_returns_grounded_chunk(self):
        chunks = [
            EvidenceChunk("m1:000", "m1", "SAML certificate rotation", "2026-01-01", "coastal.example", "Support", 0, 30, "Customer cannot authenticate after certificate rotation", "h1"),
            EvidenceChunk("m2:000", "m2", "Backup planning", "2026-01-02", "vanta.example", "External", 0, 30, "Nightly backup and restore objectives", "h2"),
            EvidenceChunk("m3:000", "m3", "Engineering planning", "2026-01-03", "", "Internal", 0, 30, "Sprint backlog and delivery plan", "h3"),
        ]
        retriever = HybridRetriever(chunks, latent_dimensions=2)
        results = retriever.search("authentication certificate problem", AccessContext("test", "admin"), top_k=1)
        self.assertEqual(results[0]["meeting_id"], "m1")
        self.assertIn("score_breakdown", results[0])


if __name__ == "__main__":
    unittest.main()
