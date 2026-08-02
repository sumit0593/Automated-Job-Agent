---
name: langsmith-trace
description: Add LangSmith tracing, run tracking, evaluation, and observability to LangChain and LangGraph applications.
---

# LangSmith Tracing & Observability

Use this skill when adding or configuring LangSmith tracing for LangChain / LangGraph applications.

## Setup Instructions

1. **Environment Variables**:
   Set `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` in your environment or `.env` file.

```bash
LANGSMITH_API_KEY="ls__your_api_key_here"
LANGSMITH_PROJECT="Automated-Job-Agent"
LANGCHAIN_TRACING_V2="true"
```

2. **Python Tracing Setup**:
   Configure environment variables before launching your agent or StateGraph.

```python
import os
from langsmith import Client

os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "your_langsmith_api_key"
os.environ["LANGCHAIN_PROJECT"] = "Automated-Job-Agent"

client = Client()
```
