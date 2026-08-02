"""
DeepAgents & LangSmith Quickstart Simple Agent

Demonstrates a simple stateful agent with LangSmith & Langfuse tracing.
"""

import os
import logging
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, END
from backend.app.config import settings

logger = logging.getLogger("uvicorn.error")

# Configure LangSmith environment
if settings.LANGSMITH_API_KEY:
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
    os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT or "Automated-Job-Agent"

class SimpleAgentState(TypedDict):
    task: str
    steps: List[str]
    current_step: int
    status: str
    output: Optional[str]

def plan_task_node(state: SimpleAgentState) -> Dict[str, Any]:
    """Plans steps for the input task."""
    logger.info(f"QuickstartAgent: Planning task '{state['task']}'")
    return {
        "steps": ["analyze_requirements", "execute_automation", "verify_results"],
        "current_step": 0,
        "status": "planned"
    }

def execute_step_node(state: SimpleAgentState) -> Dict[str, Any]:
    """Executes the current step."""
    step_name = state["steps"][state["current_step"]]
    logger.info(f"QuickstartAgent: Executing step {state['current_step'] + 1}/{len(state['steps'])}: {step_name}")
    return {
        "current_step": state["current_step"] + 1,
        "status": "in_progress"
    }

def route_next_step(state: SimpleAgentState) -> str:
    """Routes execution to next step or END."""
    if state["current_step"] < len(state["steps"]):
        return "execute_step"
    return END

def build_quickstart_agent():
    """Builds and compiles the StateGraph agent."""
    builder = StateGraph(SimpleAgentState)
    builder.add_node("plan_task", plan_task_node)
    builder.add_node("execute_step", execute_step_node)
    
    builder.set_entry_point("plan_task")
    builder.add_edge("plan_task", "execute_step")
    builder.add_conditional_edges("execute_step", route_next_step)
    
    return builder.compile()

quickstart_agent = build_quickstart_agent()

if __name__ == "__main__":
    initial_state = {
        "task": "Test Job Application Dispatch",
        "steps": [],
        "current_step": 0,
        "status": "initialized",
        "output": None
    }
    result = quickstart_agent.invoke(initial_state)
    print("Agent Execution Completed:", result)
