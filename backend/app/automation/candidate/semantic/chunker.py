from typing import List, Dict, Any

def chunk_candidate_profile(profile: Dict[str, Any], raw_resume_text: str) -> List[Dict[str, Any]]:
    """
    Chunks a Candidate Profile into discrete sections to build a Semantic Profile.
    Each chunk contains a category and text content representation.
    """
    chunks = []

    # 1. Full Resume Raw Text
    if raw_resume_text:
        chunks.append({
            "category": "resume",
            "content": f"Full Resume:\n{raw_resume_text.strip()}"
        })

    # 2. Personal info
    personal = profile.get("personal", {})
    if personal:
        personal_lines = [f"Name: {personal.get('first_name', '')} {personal.get('last_name', '')}"]
        for k, v in personal.items():
            if v and k not in ["first_name", "last_name"]:
                personal_lines.append(f"{k.capitalize()}: {v}")
        chunks.append({
            "category": "personal",
            "content": "Personal Details:\n" + "\n".join(personal_lines)
        })

    # 3. Projects
    projects = profile.get("projects", [])
    if projects:
        for idx, proj in enumerate(projects):
            name = proj.get("name", f"Project {idx+1}")
            techs = ", ".join(proj.get("technologies", []))
            resp = proj.get("responsibilities", "")
            ach = proj.get("achievements", "")
            
            proj_text = f"Project Name: {name}\n"
            if techs:
                proj_text += f"Technologies Used: {techs}\n"
            if resp:
                proj_text += f"Responsibilities: {resp}\n"
            if ach:
                proj_text += f"Achievements: {ach}\n"
                
            chunks.append({
                "category": "projects",
                "content": proj_text.strip()
            })

    # 4. Employment / Experience
    employment = profile.get("employment", {})
    if employment:
        emp_text = "Employment Details:\n"
        for k, v in employment.items():
            if v:
                emp_text += f"{k.replace('_', ' ').capitalize()}: {v}\n"
        chunks.append({
            "category": "experience",
            "content": emp_text.strip()
        })

    # 5. Skills
    skills = profile.get("skills", {})
    if skills:
        skills_text = "Skills & Competencies:\n"
        categories = skills.get("skill_categories", {})
        for cat, items in categories.items():
            if items:
                skills_text += f"- {cat}: {', '.join(items)}\n"
        
        years_exp = skills.get("years_of_experience_per_skill", {})
        if years_exp:
            skills_text += "Years of Experience per skill:\n"
            for sk, yrs in years_exp.items():
                skills_text += f"  * {sk}: {yrs} years\n"
                
        tot_exp = skills.get("total_experience", 0.0)
        if tot_exp:
            skills_text += f"Total Experience: {tot_exp} years\n"
            
        chunks.append({
            "category": "skills",
            "content": skills_text.strip()
        })

    # 6. Education
    education = profile.get("education", [])
    if education:
        for idx, edu in enumerate(education):
            degree = edu.get("degree", "")
            univ = edu.get("university", "")
            year = edu.get("graduation_year", "")
            edu_text = f"Education {idx+1}:\nDegree: {degree}\nUniversity: {univ}\nGraduation Year: {year}"
            chunks.append({
                "category": "education",
                "content": edu_text.strip()
            })

    # 7. Certifications
    certs = profile.get("certifications", [])
    if certs:
        chunks.append({
            "category": "certifications",
            "content": "Certifications:\n" + "\n".join(f"- {c}" for c in certs if c)
        })

    # 8. Achievements
    achievements = profile.get("achievements", [])
    if achievements:
        chunks.append({
            "category": "achievements",
            "content": "Professional Achievements:\n" + "\n".join(f"- {a}" for a in achievements if a)
        })
        
    # 9. Career Summary
    summary = profile.get("career_summary", "")
    if summary:
        chunks.append({
            "category": "career_summary",
            "content": f"Career Summary:\n{summary.strip()}"
        })

    return chunks
