"""
Hybrid Search — BM25 + Vector for profile field retrieval.

PROBLEM THIS SOLVES:
  External sites ask questions like:
    "How many years of experience do you have with React?"
    "What is your current CTC?"
    "Are you open to relocation?"

  The agent must retrieve the answer from the user's profile.
  If the answer is NOT in the profile → do NOT assume → fail gracefully.

STRATEGY:
  1. BM25 (rank_bm25)  → exact keyword match (fast, high precision)
  2. Vector (cosine)   → semantic match (handles paraphrasing)
  3. Score fusion      → weighted combination
  4. Threshold gate    → if top score < MIN_CONFIDENCE → return None (unanswered)

PROFILE SCHEMA (what the user stores):
  {
    "skills":           ["React", "Python", "Docker"],
    "experience_years": 5,
    "current_ctc":      "12 LPA",
    "expected_ctc":     "18 LPA",
    "notice_period":    "30 days",
    "location":         "Bangalore",
    "open_to_relocation": True,
    "education": [
      {"degree": "B.Tech", "field": "CS", "year": 2019}
    ],
    "certifications":   ["AWS SAA", "GCP ACE"],
    "summary":          "5 years full-stack engineer...",
    ...
  }

USAGE:
  searcher = HybridSearcher(profile)
  result = searcher.answer_question("How many years of React experience?")
  if result is None:
      # Add to unanswered_questions — do NOT guess
  else:
      # Fill the form field with result.answer
"""

import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# ─── Thresholds ────────────────────────────────────────────────────────────────
BM25_WEIGHT     = 0.55   # higher = prefer exact keyword match
VECTOR_WEIGHT   = 0.45   # higher = prefer semantic similarity
MIN_CONFIDENCE  = 0.35   # below this → unanswered (do NOT guess)
MAX_ANSWER_CHARS = 500   # trim overly long answers


@dataclass
class SearchResult:
    answer:       str
    confidence:   float
    matched_key:  str     # which profile field matched
    method:       str     # "bm25" | "vector" | "hybrid"


class HybridSearcher:
    """
    Initialized once per session with the user's profile.
    Call answer_question() for each form field.
    """

    def __init__(self, profile: dict, embedder=None):
        """
        profile   : User's full profile dict
        embedder  : Optional sentence-transformer model (SentenceTransformer instance)
                    If None, falls back to BM25-only mode.
        """
        self.profile  = profile
        self.embedder = embedder

        # Flatten profile into searchable (key, text) pairs
        self.corpus: list[tuple[str, str]] = self._flatten_profile(profile)
        self.keys   = [c[0] for c in self.corpus]
        self.texts  = [c[1] for c in self.corpus]

        # Build BM25 index
        tokenized = [self._tokenize(t) for t in self.texts]
        self.bm25 = BM25Okapi(tokenized)

        # Pre-compute vector embeddings if embedder provided
        self.embeddings: Optional[np.ndarray] = None
        if self.embedder:
            try:
                self.embeddings = self.embedder.encode(self.texts, normalize_embeddings=True)
            except Exception as e:
                logger.warning(f"Embedding failed, BM25-only mode: {e}")
                self.embedder = None

        logger.info(f"HybridSearcher ready | corpus={len(self.corpus)} fields | "
                    f"mode={'hybrid' if self.embedder else 'bm25-only'}")

    # ─── Public API ──────────────────────────────────────────────────────────

    def answer_question(self, question: str) -> Optional[SearchResult]:
        """
        Given a form question, return the best answer from the profile.
        Returns None if confidence < MIN_CONFIDENCE.
        Caller MUST treat None as "unanswered" and add to failed_questions.
        """
        if not question or not self.corpus:
            return None

        bm25_scores  = self._bm25_score(question)
        vector_scores = self._vector_score(question) if self.embedder else np.zeros(len(self.corpus))

        # Normalize scores to [0, 1]
        bm25_norm   = self._normalize(bm25_scores)
        vector_norm = self._normalize(vector_scores)

        # Weighted fusion
        fused = BM25_WEIGHT * bm25_norm + VECTOR_WEIGHT * vector_norm
        best_idx   = int(np.argmax(fused))
        confidence = float(fused[best_idx])

        if confidence < MIN_CONFIDENCE:
            logger.info(
                f"[HybridSearch] No confident match for: '{question}' "
                f"(best={confidence:.3f} < {MIN_CONFIDENCE})"
            )
            return None

        method = "hybrid" if self.embedder else "bm25"
        if bm25_norm[best_idx] > vector_norm[best_idx]:
            method = "bm25"
        elif vector_norm[best_idx] > bm25_norm[best_idx]:
            method = "vector"

        raw_answer = self.texts[best_idx]
        answer     = raw_answer[:MAX_ANSWER_CHARS]

        logger.info(
            f"[HybridSearch] '{question}' → '{self.keys[best_idx]}' "
            f"| conf={confidence:.3f} | method={method}"
        )
        return SearchResult(
            answer      = answer,
            confidence  = confidence,
            matched_key = self.keys[best_idx],
            method      = method,
        )

    def batch_answer(self, questions: list[str]) -> dict[str, Optional[SearchResult]]:
        """
        Answer multiple questions at once.
        Returns dict: {question → SearchResult | None}
        None values MUST go to unanswered_questions list on the job record.
        """
        return {q: self.answer_question(q) for q in questions}

    # ─── Private ─────────────────────────────────────────────────────────────

    def _bm25_score(self, question: str) -> np.ndarray:
        tokens = self._tokenize(question)
        scores = self.bm25.get_scores(tokens)
        return np.array(scores, dtype=float)

    def _vector_score(self, question: str) -> np.ndarray:
        if self.embeddings is None:
            return np.zeros(len(self.corpus))
        q_emb   = self.embedder.encode([question], normalize_embeddings=True)
        cosine  = (self.embeddings @ q_emb.T).flatten()
        return np.clip(cosine, 0, 1)

    @staticmethod
    def _normalize(arr: np.ndarray) -> np.ndarray:
        mn, mx = arr.min(), arr.max()
        if mx - mn < 1e-9:
            return np.zeros_like(arr)
        return (arr - mn) / (mx - mn)

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return text.lower().split()

    @staticmethod
    def _flatten_profile(profile: dict) -> list[tuple[str, str]]:
        """
        Convert nested profile dict into flat (key, human_readable_text) pairs.
        Each pair is one searchable document in BM25/vector index.
        """
        corpus = []

        def add(key: str, value):
            if value is None:
                return
            if isinstance(value, list):
                text = ", ".join(str(v) for v in value)
            elif isinstance(value, dict):
                text = " ".join(f"{k}: {v}" for k, v in value.items())
            elif isinstance(value, bool):
                text = "yes" if value else "no"
            else:
                text = str(value).strip()
            if text:
                corpus.append((key, text))

        # Direct fields
        simple_keys = [
            "skills", "experience_years", "current_ctc", "expected_ctc",
            "notice_period", "location", "open_to_relocation", "summary",
            "languages", "certifications", "availability", "preferred_role",
            "work_mode", "current_company", "current_designation",
        ]
        for k in simple_keys:
            if k in profile:
                add(k, profile[k])

        # Education (array → expand)
        for edu in profile.get("education", []):
            text = f"{edu.get('degree','')} in {edu.get('field','')} from {edu.get('institute','')} ({edu.get('year','')})"
            corpus.append(("education", text.strip()))

        # Experience (array → expand)
        for exp in profile.get("experience", []):
            text = (f"{exp.get('designation','')} at {exp.get('company','')} "
                    f"for {exp.get('duration','')} years. {exp.get('description','')}")
            corpus.append(("experience", text.strip()))

        # Projects
        for proj in profile.get("projects", []):
            text = f"{proj.get('name','')} - {proj.get('description','')}"
            corpus.append(("project", text.strip()))

        return corpus
