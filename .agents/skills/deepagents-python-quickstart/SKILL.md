---
name: deepagents-python-quickstart
description: Build deep agentic workflows, multi-agent state graphs, and autonomous tools using LangChain and LangGraph in Python.
---

# DeepAgents Python Quickstart

Use this skill when building or configuring LangChain / LangGraph stateful multi-agent workflows in Python.

## Core Concepts

1. **StateGraph**:
   Use `langgraph.graph.StateGraph` to define stateful multi-agent graphs governed by a `TypedDict` state schema.

```python
from typing import TypedDict, List, Dict, Any
from langgraph.graph import StateGraph, END

class AgentState(TypedDict):
    input: str
    plan: List[str]
    current_step: int
    results: List[Dict[str, Any]]
    final_output: str

def plan_node(state: AgentState) -> Dict[str, Any]:
    return {"plan": ["step_1", "step_2"], "current_step": 0}

def execute_node(state: AgentState) -> Dict[str, Any]:
    step = state["plan"][state["current_step"]]
    return {"results": [{"step": step, "status": "completed"}], "current_step": state["current_step"] + 1}

def route_next(state: AgentState) -> str:
    if state["current_step"] < len(state["plan"]):
        return "execute"
    return END

workflow = StateGraph(AgentState)
workflow.add_node("plan", plan_node)
workflow.add_node("execute", execute_node)

workflow.set_entry_point("plan")
workflow.add_edge("plan", "execute")
workflow.add_conditional_edges("execute", route_next)

app = workflow.compile()
```
