from __future__ import annotations
import math
import re
from collections import Counter
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
    source_url: str = ""
    publisher: str = ""
    version: str = ""
    checked_at: str = ""
    platform: str = "all"
    content_type: str = "authored_demo"
    section: str = ""

class PolicyRetriever:
    def __init__(self, policy_dir: Path):
        self.policy_dir = policy_dir
        self.chunks = self._load()
        corpus = [c.text for c in self.chunks] or [""]
        self.vectorizer = TfidfVectorizer(analyzer="char", ngram_range=(2, 4), min_df=1)
        self.matrix = self.vectorizer.fit_transform(corpus)
        self.analyze_tokens = self.vectorizer.build_analyzer()
        self.term_counts = [Counter(self.analyze_tokens(text)) for text in corpus]
        self.document_frequency = Counter(token for row in self.term_counts for token in row)
        self.mean_length = sum(sum(row.values()) for row in self.term_counts) / len(self.term_counts)

    def _load(self) -> list[Chunk]:
        chunks: list[Chunk] = []
        for path in sorted(self.policy_dir.glob("*.md")):
            raw = path.read_text(encoding="utf-8")
            meta = {k.strip(): v.strip() for k, v in re.findall(r"^([a-z_]+):\s*(.+)$", raw, re.M)}
            body = raw.split("---", 2)[-1]
            parts = [p.strip() for p in re.split(r"\n(?=## )", body) if len(p.strip()) > 30]
            for idx, part in enumerate(parts):
                chunks.append(Chunk(f"{path.stem}-{idx:02d}", meta.get("title", path.stem), part[:1200], meta.get("source_type", "synthetic_demo"), meta.get("applicable_scenarios", "all"), source_url=meta.get("source_url", ""), publisher=meta.get("publisher", ""), version=meta.get("version", ""), checked_at=meta.get("checked_at", ""), platform=meta.get("platform", "all"), content_type=meta.get("content_type", "authored_demo"), section=part.splitlines()[0].lstrip("# ")))
        return chunks

    def search(self, query: str, top_k: int = 4, scenario: str | None = None, platform: str = "generic", method: str = "tfidf") -> list[dict]:
        candidates = [(i, c) for i, c in enumerate(self.chunks) if c.platform in {"all", platform} and (not scenario or scenario in c.applicable_scenarios or "all" in c.applicable_scenarios)]
        if not candidates or not query.strip(): return []
        if method == "tfidf":
            q = self.vectorizer.transform([query])
            scores = cosine_similarity(q, self.matrix).ravel()
        elif method == "bm25":
            scores = []
            count = len(self.term_counts)
            for terms in self.term_counts:
                score = 0.0
                norm = 1.5 * (1 - .75 + .75 * sum(terms.values()) / max(1, self.mean_length))
                for term in set(self.analyze_tokens(query)):
                    frequency = terms.get(term, 0)
                    if frequency:
                        df = self.document_frequency[term]
                        score += math.log(1 + (count - df + .5) / (df + .5)) * frequency * 2.5 / (frequency + norm)
                scores.append(score)
        else:
            raise ValueError("检索方法仅支持tfidf或bm25；Embedding需要另行配置并评测")
        ranked = sorted(candidates, key=lambda pair: (-scores[pair[0]], pair[1].chunk_id))[:top_k]
        return [{"citation_id": f"C{rank+1}", "chunk_id": c.chunk_id, "document_title": c.document_title, "snippet": c.text[:360], "score": round(float(scores[i]), 4), "source_type": c.source_type, "source_url":c.source_url or None, "publisher":c.publisher or None, "section":c.section, "version":c.version or None, "checked_at":c.checked_at or None, "platform":c.platform, "content_type":c.content_type} for rank, (i, c) in enumerate(ranked) if scores[i] > 0]

