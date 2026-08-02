---
name: langfuse-trace
description: Add Langfuse tracing, observability, cost tracking, and prompt management to LangChain, LangGraph, and Python LLM applications following best practices.
---

# Langfuse Observability & Tracing Skill

Use this skill when integrating Langfuse tracing, LLM cost tracking, and evaluation callbacks into Python applications.

## Key Setup & Configuration

1. **Environment Variables**:
   Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and host in `.env`:

   - **US Cloud Region**: `LANGFUSE_HOST="https://us.cloud.langfuse.com"`
   - **EU Cloud Region (Default)**: `LANGFUSE_HOST="https://cloud.langfuse.com"`

```bash
LANGFUSE_PUBLIC_KEY="pk-lf-..."
LANGFUSE_SECRET_KEY="sk-lf-..."
LANGFUSE_HOST="https://cloud.langfuse.com"
```

2. **LangChain & LangGraph Integration (CallbackHandler)**:
   Pass `CallbackHandler` to `config={"callbacks": [langfuse_handler]}` when invoking chains or graphs.

```python
from langfuse.callback import CallbackHandler

langfuse_handler = CallbackHandler(
    public_key=settings.LANGFUSE_PUBLIC_KEY,
    secret_key=settings.LANGFUSE_SECRET_KEY,
    host=settings.LANGFUSE_BASE_URL or settings.LANGFUSE_HOST
)

result = graph.invoke(initial_state, config={"callbacks": [langfuse_handler]})
```
