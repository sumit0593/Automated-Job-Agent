import re
from typing import List, Set, Dict

# Canonical mapping dictionary for technical skills and domain synonyms
SYNONYM_MAP: Dict[str, str] = {
    # JavaScript / TypeScript Ecosystem
    "node": "Node.js",
    "node.js": "Node.js",
    "nodejs": "Node.js",
    "react": "React",
    "react.js": "React",
    "reactjs": "React",
    "vue": "Vue.js",
    "vue.js": "Vue.js",
    "vuejs": "Vue.js",
    "next": "Next.js",
    "next.js": "Next.js",
    "nextjs": "Next.js",
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "express": "Express.js",
    "expressjs": "Express.js",
    "express.js": "Express.js",
    "nest": "NestJS",
    "nestjs": "NestJS",
    
    # Python & AI/ML Ecosystem
    "py": "Python",
    "python": "Python",
    "fastapi": "FastAPI",
    "django": "Django",
    "flask": "Flask",
    "llm": "Generative AI",
    "large language models": "Generative AI",
    "genai": "Generative AI",
    "generative ai": "Generative AI",
    "ml": "Machine Learning",
    "machine learning": "Machine Learning",
    "dl": "Deep Learning",
    "deep learning": "Deep Learning",
    "nlp": "Natural Language Processing",
    "natural language processing": "Natural Language Processing",
    "pytorch": "PyTorch",
    "tensorflow": "TensorFlow",
    "tf": "TensorFlow",
    "langchain": "LangChain",
    "llama-index": "LlamaIndex",
    "llamaindex": "LlamaIndex",
    "langgraph": "LangGraph",
    "rag": "Retrieval Augmented Generation",
    "retrieval augmented generation": "Retrieval Augmented Generation",

    # Databases & Vector DBs
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "postgres sql": "PostgreSQL",
    "mongo": "MongoDB",
    "mongodb": "MongoDB",
    "qdrant": "Qdrant",
    "chroma": "ChromaDB",
    "chromadb": "ChromaDB",
    "pinecone": "Pinecone",
    "redis": "Redis",

    # Cloud & DevOps
    "k8s": "Kubernetes",
    "kubernetes": "Kubernetes",
    "docker": "Docker",
    "aws": "Amazon Web Services",
    "amazon web services": "Amazon Web Services",
    "gcp": "Google Cloud Platform",
    "google cloud": "Google Cloud Platform",
    "azure": "Microsoft Azure",
    "cicd": "CI/CD",
    "ci/cd": "CI/CD",
    "git": "Git",
    "github": "GitHub"
}

# Reverse lookup dictionary to map canonical name back to all synonym terms
REVERSE_SYNONYM_MAP: Dict[str, Set[str]] = {}
for term, canonical in SYNONYM_MAP.items():
    if canonical not in REVERSE_SYNONYM_MAP:
        REVERSE_SYNONYM_MAP[canonical] = set()
    REVERSE_SYNONYM_MAP[canonical].add(term)
    REVERSE_SYNONYM_MAP[canonical].add(canonical.lower())

def normalize_skill(skill: str) -> str:
    """Normalizes a raw skill string into its canonical display name."""
    if not skill:
        return ""
    cleaned = skill.strip().lower()
    return SYNONYM_MAP.get(cleaned, skill.strip())

def expand_skills(skills: List[str]) -> List[str]:
    """
    Given a list of skills, returns an expanded list containing canonical names
    plus all synonym variations for comprehensive lexical matching.
    """
    expanded: Set[str] = set()
    for s in skills:
        if not s:
            continue
        s_clean = s.strip().lower()
        canonical = SYNONYM_MAP.get(s_clean, s.strip())
        expanded.add(canonical.lower())
        expanded.add(s_clean)
        
        # Add all known synonyms for this canonical skill
        if canonical in REVERSE_SYNONYM_MAP:
            for syn in REVERSE_SYNONYM_MAP[canonical]:
                expanded.add(syn)

    return list(expanded)

def categorize_seniority(years: float) -> str:
    """Categorizes years of experience into a seniority level string."""
    try:
        y = float(years)
    except (ValueError, TypeError):
        y = 0.0

    if y < 2.0:
        return "Entry Level"
    elif y < 5.0:
        return "Mid Level"
    elif y < 8.0:
        return "Senior"
    else:
        return "Lead / Principal"
