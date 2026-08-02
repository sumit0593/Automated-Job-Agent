import logging
from typing import Dict, Any
from backend.app.automation.langgraph_orchestrator import LangGraphOrchestrator

logger = logging.getLogger("uvicorn.error")

class ApplicationStateMachine:
    """
    Central Application State Machine governing the job application pipeline.
    Delegates graph execution to the LangGraph Multi-Agent Orchestrator.
    Runs entirely within a background thread for Playwright thread-safety.
    """
    def __init__(
        self,
        app_id: int,
        user_profile: Dict[str, Any],
        headful: bool = True,
        enable_human_review: bool = True
    ):
        self.app_id = app_id
        self.user_profile = user_profile
        self.headful = headful
        self.enable_human_review = enable_human_review

    async def run(self) -> Dict[str, Any]:
        """Runs the state machine asynchronously by dispatching to a background thread."""
        import asyncio
        return await asyncio.to_thread(self._run_execution)

    def _run_execution(self) -> Dict[str, Any]:
        """Synchronous core execution delegating to LangGraph Orchestrator."""
        orchestrator = LangGraphOrchestrator(
            app_id=self.app_id,
            user_profile=self.user_profile,
            headful=self.headful,
            enable_human_review=self.enable_human_review
        )
        return orchestrator.execute()
