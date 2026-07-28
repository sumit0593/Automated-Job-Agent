import math
import logging
from typing import List, Dict, Any, Set
from backend.app.services.matching.normalizer import expand_skills, normalize_skill

logger = logging.getLogger("uvicorn.error")

def parse_skills_list(skills: Any) -> List[str]:
    """Safely parses string or list input into a clean list of skill strings."""
    if not skills:
        return []
    if isinstance(skills, str):
        import json
        try:
            parsed = json.loads(skills)
            if isinstance(parsed, list):
                return [str(s).strip() for s in parsed if s]
        except Exception:
            pass
        return [s.strip() for s in skills.replace("[", "").replace("]", "").replace('"', '').replace("'", "").split(",") if s.strip()]
    elif isinstance(skills, list):
        return [str(s).strip() for s in skills if s]
    return []

def compute_skill_overlap_score(candidate_skills: Any, job_skills: Any) -> float:
    """
    Computes normalized skill match percentage between candidate skills and job requirements
    using expanded tech stack terms.
    """
    cand_list = parse_skills_list(candidate_skills)
    job_list = parse_skills_list(job_skills)

    if not job_list:
        return 80.0  # Neutral high score if job specifies no strict skills
    if not cand_list:
        return 60.0

    cand_set = set(expand_skills(cand_list))
    job_set = set(expand_skills(job_list))
    
    if not job_set:
        return 80.0
        
    intersection = cand_set.intersection(job_set)
    if intersection:
        ratio = len(intersection) / len(job_set)
        return min(100.0, max(60.0, round(ratio * 100.0, 1)))
    
    # Substring / partial keyword matching fallback
    matching_count = 0
    for js in job_set:
        if any(cs in js or js in cs for cs in cand_set):
            matching_count += 1
            
    if matching_count > 0:
        ratio = matching_count / len(job_set)
        return min(100.0, max(50.0, round(ratio * 100.0, 1)))

    return 30.0

def compute_experience_match_score(candidate_years: float, required_years: float) -> float:
    """
    Computes experience match score based on candidate years vs required years.
    """
    try:
        cand = float(candidate_years or 0.0)
    except Exception:
        cand = 0.0
        
    try:
        req = float(required_years or 0.0)
    except Exception:
        req = 0.0
    
    if req == 0.0 or cand == 0.0:
        return 85.0
        
    if cand >= req:
        return 100.0
    else:
        ratio = cand / req
        return round(max(50.0, ratio * 100.0), 1)

def compute_location_match_score(candidate_location: str, job_location: str) -> float:
    """Computes location compatibility score."""
    cand_loc = (candidate_location or "").lower()
    job_loc = (job_location or "").lower()
    
    if not job_loc or "remote" in job_loc or "remote" in cand_loc:
        return 100.0
        
    if not cand_loc or cand_loc == "unknown":
        return 75.0
        
    if cand_loc in job_loc or job_loc in cand_loc:
        return 100.0
        
    return 40.0

def apply_mmr(
    candidates: List[Dict[str, Any]], 
    lambda_param: float = 0.7, 
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Applies Maximum Marginal Relevance (MMR) to diversify results and eliminate
    duplicate or near-duplicate job descriptions.
    """
    if not candidates or len(candidates) <= 1:
        return candidates[:limit]

    selected = [candidates[0]]
    unselected = candidates[1:]

    while len(selected) < limit and unselected:
        best_score = -99999.0
        best_cand_idx = -1

        for idx, cand in enumerate(unselected):
            relevance = cand.get("combined_score", cand.get("hybrid_score", 0.5))
            
            # Compute max similarity to already selected candidates (title & company similarity)
            max_sim = 0.0
            cand_title = (cand.get("title") or "").lower()
            cand_comp = (cand.get("company") or "").lower()

            for sel in selected:
                sel_title = (sel.get("title") or "").lower()
                sel_comp = (sel.get("company") or "").lower()
                
                # Near-duplicate check (same company & same title)
                if cand_comp == sel_comp and cand_title == sel_title:
                    max_sim = 1.0
                    break
                elif cand_title == sel_title:
                    max_sim = max(max_sim, 0.7)

            # MMR formula: lambda * relevance - (1 - lambda) * max_similarity
            mmr_score = (lambda_param * relevance) - ((1.0 - lambda_param) * max_sim)
            
            if mmr_score > best_score:
                best_score = mmr_score
                best_cand_idx = idx

        if best_cand_idx >= 0:
            selected.append(unselected.pop(best_cand_idx))
        else:
            break

    return selected
