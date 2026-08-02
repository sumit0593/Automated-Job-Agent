"""
Resume Hybrid RAG Auto-Extractor Engine
─────────────────────────────────────────────────────────────────────────────
Extracts candidate Profile and Answer Bank data directly from an uploaded resume PDF.
Uses a zero-hallucination Hybrid RAG pipeline:
  1. Chunk resume into semantic paragraphs / sections
  2. Dense Vector Embedding + Lexical BM25 Search over resume chunks
  3. BGE Cross-Encoder Reranking to find top evidence chunks for each query
  4. LLM Extraction & Grounded Reasoning — returns empty string if unmentioned in resume
"""

import math
import re
import json
import logging
from typing import Dict, Any, List, Optional

from backend.app.services.vectorstore import vector_store
from backend.app.services.llm_router import llm_router, TaskType

logger = logging.getLogger("uvicorn.error")


def compute_bm25_scores(corpus: List[str], query_tokens: List[str]) -> List[float]:
    """Built-in lightweight BM25 scoring over text chunks."""
    scores = []
    tokenized_corpus = [re.findall(r'\w+', t.lower()) for t in corpus]
    doc_freqs = {}
    N = len(corpus)
    for doc in tokenized_corpus:
        seen = set(doc)
        for term in seen:
            doc_freqs[term] = doc_freqs.get(term, 0) + 1

    avgdl = sum(len(d) for d in tokenized_corpus) / max(N, 1)

    k1 = 1.5
    b = 0.75

    for doc in tokenized_corpus:
        score = 0.0
        doc_len = len(doc)
        term_counts = {}
        for t in doc:
            term_counts[t] = term_counts.get(t, 0) + 1

        for q_term in query_tokens:
            if q_term in term_counts:
                tf = term_counts[q_term]
                df = doc_freqs.get(q_term, 0)
                idf = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
                numerator = tf * (k1 + 1)
                denominator = tf + k1 * (1 - b + b * (doc_len / max(avgdl, 1)))
                score += idf * (numerator / max(denominator, 1e-5))

        scores.append(score)

    return scores


class ResumeRAGExtractor:
    """
    Hybrid RAG Extractor for candidate profile attributes and answer bank prompts.
    """

    def chunk_resume_text(self, text: str, max_chunk_words: int = 150) -> List[Dict[str, Any]]:
        """
        Splits resume text into semantic chunks (paragraphs / sections).
        Returns list of dicts with 'id', 'text', and 'word_count'.
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        chunks = []
        current_chunk = []
        current_words = 0

        for line in lines:
            words = len(line.split())
            if current_words + words > max_chunk_words and current_chunk:
                chunks.append({
                    "id": len(chunks),
                    "text": "\n".join(current_chunk),
                    "word_count": current_words
                })
                current_chunk = [line]
                current_words = words
            else:
                current_chunk.append(line)
                current_words += words

        if current_chunk:
            chunks.append({
                "id": len(chunks),
                "text": "\n".join(current_chunk),
                "word_count": current_words
            })

        return chunks

    def hybrid_retrieve_evidence(
        self,
        resume_chunks: List[Dict[str, Any]],
        query: str,
        top_k: int = 4
    ) -> str:
        """
        Hybrid retrieval combining BM25 keyword matching + Dense Cosine similarity
        + BGE Cross-Encoder reranking over resume chunks.
        """
        if not resume_chunks:
            return ""

        chunk_texts = [c["text"] for c in resume_chunks]

        # 1. Lexical BM25 Scoring
        query_tokens = re.findall(r'\w+', query.lower())
        bm25_scores = compute_bm25_scores(chunk_texts, query_tokens)
        max_bm25 = max(bm25_scores) if max(bm25_scores) > 0 else 1.0
        norm_bm25 = [s / max_bm25 for s in bm25_scores]

        # 2. Dense Vector Scoring
        try:
            embedder = vector_store.get_embedding_model()
            q_vector = embedder.encode(query, normalize_embeddings=True)
            chunk_vectors = embedder.encode(chunk_texts, normalize_embeddings=True)
            dense_scores = [float(q_vector @ c_vec) for c_vec in chunk_vectors]
        except Exception as e:
            logger.warning(f"ResumeRAGExtractor: Dense embedding fallback ({e})")
            dense_scores = [0.5] * len(chunk_texts)

        # 3. Hybrid Score Fusion
        hybrid_candidates = []
        for idx, chunk in enumerate(resume_chunks):
            score = (dense_scores[idx] * 0.6) + (norm_bm25[idx] * 0.4)
            hybrid_candidates.append({
                "chunk_id": idx,
                "text": chunk["text"],
                "score": score
            })

        hybrid_candidates.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = hybrid_candidates[:min(8, len(hybrid_candidates))]

        # 4. Cross-Encoder Reranking
        try:
            reranker = vector_store.get_reranker_model()
            pairs = [(query, c["text"]) for c in top_candidates]
            rerank_scores = reranker.predict(pairs)
            for idx, r_score in enumerate(rerank_scores):
                top_candidates[idx]["rerank_score"] = float(r_score)
            top_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        except Exception as re_err:
            logger.warning(f"ResumeRAGExtractor: Cross-encoder rerank fallback ({re_err})")

        selected_texts = [c["text"] for c in top_candidates[:top_k]]
        return "\n\n---\n\n".join(selected_texts)

    def extract_grounded_profile(self, raw_text: str) -> Dict[str, Any]:
        """
        Extracts structured Profile attributes grounded strictly in resume text.
        Returns empty strings / null for unmentioned attributes — NO mock data.
        """
        chunks = self.chunk_resume_text(raw_text)

        # Retrieve relevant evidence for profile contact & experience
        evidence = self.hybrid_retrieve_evidence(
            chunks,
            query="Candidate name email phone location experience CTC notice period work authorization",
            top_k=5
        )

        system_prompt = (
            "You are a strict zero-hallucination ATS Profile Extractor. "
            "Analyze the provided resume context and extract candidate attributes in valid JSON format.\n"
            "CRITICAL RULES:\n"
            "1. Extract ONLY facts explicitly present in or directly derived from the resume context.\n"
            "2. If an attribute (e.g. current_ctc, expected_ctc, notice_period, country_code) is NOT mentioned, set it to '' (empty string). DO NOT invent fake salaries, LPA, or notice periods.\n"
            "3. Return valid JSON only with keys:\n"
            "   - 'name': Candidate full name\n"
            "   - 'email': Candidate email\n"
            "   - 'phone': 10-digit phone number without country code\n"
            "   - 'country_code': Country dialing code e.g. '+91'\n"
            "   - 'experience_years': Total years of professional experience as float\n"
            "   - 'current_ctc': Current salary/CTC (e.g. '₹7 LPA' or '' if unmentioned)\n"
            "   - 'expected_ctc': Expected salary/CTC (or '' if unmentioned)\n"
            "   - 'notice_period': Notice period (e.g. 'Immediate', '30 Days', or '' if unmentioned)\n"
            "   - 'current_location': City / region (e.g. 'Noida')\n"
            "   - 'preferred_locations': List of preferred work cities\n"
            "   - 'pan_number': PAN Card Number (or '' if unmentioned)\n"
            "   - 'date_of_birth': Date of birth (or '' if unmentioned)\n"
            "   - 'last_working_day': Last working day / LWD (or '' if unmentioned)\n"
            "   - 'skills': List of candidate core technical skills\n"
            "   - 'linkedin_url': LinkedIn profile URL\n"
            "   - 'github_url': GitHub profile URL\n"
            "   - 'portfolio_url': Portfolio / Personal Website URL\n"
            "   - 'work_authorization': Work authorization country (e.g. 'India')\n"
            "   - 'willing_to_relocate': 'Yes', 'No', or 'Open'\n"
            "   - 'remote_preference': 'Remote', 'Hybrid', 'On-site', or 'Open'\n"
        )

        user_prompt = f"Resume Context Evidence:\n---\n{evidence}\n---\nFull Resume Header:\n{raw_text[:1500]}\n---\nExtract Profile JSON:"

        # Extract links via regex fallback
        from backend.app.services.parser import extract_links, parse_resume_text_fallback
        links = extract_links(raw_text)
        fallback_data = parse_resume_text_fallback(raw_text)

        try:
            llm_json_str = llm_router.route(
                task_type=TaskType.EXTRACTION,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                json_mode=True,
                temperature=0.1
            )
            match = re.search(r"\{.*\}", llm_json_str, re.DOTALL)
            if match:
                parsed = json.loads(match.group(0))
                return {
                    "name": str(parsed.get("name", "") or "").strip(),
                    "email": str(parsed.get("email", "") or "").strip(),
                    "phone": str(parsed.get("phone", "") or "").strip(),
                    "country_code": str(parsed.get("country_code", "+91") or "+91").strip(),
                    "pan_number": str(parsed.get("pan_number", "") or "").strip(),
                    "date_of_birth": str(parsed.get("date_of_birth", "") or "").strip(),
                    "last_working_day": str(parsed.get("last_working_day", "") or "").strip(),
                    "experience_years": round(max(float(parsed.get("experience_years") or 0.0), float(fallback_data.get("experience") or 0.0)), 1),
                    "current_ctc": str(parsed.get("current_ctc", "") or "").strip(),
                    "expected_ctc": str(parsed.get("expected_ctc", "") or "").strip(),
                    "notice_period": str(parsed.get("notice_period", "") or "").strip(),
                    "current_location": str(parsed.get("current_location", "") or fallback_data.get("location", "")).strip(),
                    "preferred_locations": parsed.get("preferred_locations") if isinstance(parsed.get("preferred_locations"), list) else [],
                    "skills": parsed.get("skills") if isinstance(parsed.get("skills"), list) and len(parsed.get("skills")) > 0 else fallback_data.get("skills", []),
                    "linkedin_url": str(parsed.get("linkedin_url") or links.get("linkedin") or "").strip(),
                    "github_url": str(parsed.get("github_url") or links.get("github") or "").strip(),
                    "portfolio_url": str(parsed.get("portfolio_url") or links.get("portfolio") or "").strip(),
                    "work_authorization": str(parsed.get("work_authorization", "") or "").strip(),
                    "willing_to_relocate": str(parsed.get("willing_to_relocate", "") or "").strip(),
                    "remote_preference": str(parsed.get("remote_preference", "") or "").strip(),
                }
        except Exception as ex:
            logger.warning(f"ResumeRAGExtractor: LLM profile extraction failed ({ex})")

        return {
            "name": fallback_data.get("name", ""),
            "email": fallback_data.get("email", ""),
            "phone": fallback_data.get("phone", ""),
            "country_code": "+91",
            "pan_number": "",
            "date_of_birth": "",
            "last_working_day": "",
            "experience_years": fallback_data.get("experience", 0.0),
            "current_ctc": "",
            "expected_ctc": "",
            "notice_period": "",
            "current_location": fallback_data.get("location", ""),
            "preferred_locations": [],
            "skills": fallback_data.get("skills", []),
            "linkedin_url": links.get("linkedin") or "",
            "github_url": links.get("github") or "",
            "portfolio_url": links.get("portfolio") or "",
            "work_authorization": "",
            "willing_to_relocate": "",
            "remote_preference": ""
        }

    def generate_grounded_answer_bank(self, raw_text: str) -> Dict[str, str]:
        """
        Generates grounded Answer Bank entries by running Hybrid RAG retrieval
        over resume sections for each recruiter prompt.
        """
        chunks = self.chunk_resume_text(raw_text)

        prompts_to_retrieve = [
            ("why_join", "motivation company technology stack building AI systems scalability impact", "Why do you want to join our engineering team?"),
            ("strengths", "key strengths technical skills core competencies backend AI architecture problem solving", "What are your key technical strengths and core competencies?"),
            ("career_goal", "career goal future ambition lead AI engineer platform scale leadership vision", "Where do you see your career heading in the next 3 to 5 years?"),
            ("why_leaving", "career growth higher impact opportunity modern tech stack new challenges", "Why are you looking for a new role/opportunity?"),
            ("key_achievements", "key projects major achievements impact metrics performance optimization scale", "Describe your top engineering achievements or project highlights."),
        ]

        answers = {}

        for key, retrieval_query, question in prompts_to_retrieve:
            evidence = self.hybrid_retrieve_evidence(chunks, query=retrieval_query, top_k=3)

            system_prompt = (
                "You are an expert candidate interview coach. "
                "Formulate a professional, highly grounded 2-3 sentence answer to the interview question based strictly on the provided resume context.\n"
                "RULES:\n"
                "1. Refer to actual projects, technologies, and experience mentioned in the resume evidence.\n"
                "2. Do NOT invent achievements, companies, or technologies not listed.\n"
                "3. Speak in the first person ('I have worked on...', 'My experience includes...').\n"
                "4. If resume context is minimal, provide a clean professional statement based on listed skills.\n"
            )

            user_prompt = (
                f"Interview Question: '{question}'\n\n"
                f"Resume Evidence Chunks:\n---\n{evidence}\n---\n"
                f"Write concise 2-3 sentence answer:"
            )

            try:
                ans_text = llm_router.route(
                    task_type=TaskType.QA_COMPLEX,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=0.3
                )
                answers[key] = ans_text.strip() if ans_text else ""
            except Exception as e:
                logger.warning(f"ResumeRAGExtractor: Failed generating answer for '{key}': {e}")
                answers[key] = ""

        return answers

    def extract_all(self, raw_text: str) -> Dict[str, Any]:
        """
        Runs full Hybrid RAG extraction returning both Profile and Answer Bank dicts.
        """
        profile = self.extract_grounded_profile(raw_text)
        answer_bank = self.generate_grounded_answer_bank(raw_text)
        return {
            "profile": profile,
            "answers": answer_bank
        }


# Singleton instance
resume_rag_extractor = ResumeRAGExtractor()
