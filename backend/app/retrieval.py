from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

@dataclass
class Chunk:
    chunk_id: str
    document_title: str
    text: str
    source_type: str
    applicable_scenarios: str

class PolicyRetriever:
    def __init__(self, policy_dir: Path):
        self.policy_dir = policy_dir
        self.chunks = self._load()
        corpus = [c.text for c in self.chunks] or [""]
        self.vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1)
        self.matrix = self.vectorizer.fit_transform(corpus)

    def _load(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for path in sorted(self.policy_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            meta = {k.strip(): v.strip() for k, v in re.findall(r"^([a-z_]+):\s*(.+)$", raw, re.M)}
            body = raw.split("---", 2)[-1]
            parts = [p.strip() for p in re.split(r"\n(?=## )", body) if len(p.strip()) > 30]
            for idx, part in enumerate(parts):
                chunks.append(Chunk(f"{path.stem}-{idx:02d}", meta.get("title", path.stem), part[:1200], meta.get("source_type", "synthetic_demo"), meta.get("applicable_scenarios", "all")))
        return chunks

    def search(self, query: str, top_k: int = 4, scenario: str | None = None) -> list[dict]:
        candidates = [(i, c) for i, c in enumerate(self.chunks) if not scenario or scenario in c.applicable_scenarios or "all" in c.applicable_scenarios]
        if not candidates or not query.strip(): return []
        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix).ravel()
        ranked = sorted(candidates, key=lambda pair: (-scores[pair[0]], pair[1].chunk_id))[:top_k]
        return [{"citation_id": f"C{rank+1}", "chunk_id": c.chunk_id, "document_title": c.document_title, "snippet": c.text[:360], "score": round(float(scores[i]), 4), "source_type": c.source_type} for rank, (i, c) in enumerate(ranked) if scores[i] > 0]

