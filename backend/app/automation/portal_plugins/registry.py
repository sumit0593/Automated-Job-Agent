import logging
from typing import Dict, Any, Type, Optional
from backend.app.automation.portal_plugins.base_portal import BasePortal

logger = logging.getLogger("uvicorn.error")

PORTAL_REGISTRY: Dict[str, Type[BasePortal]] = {}

def register_portal(name: str):
    """Decorator to register a job portal plugin."""
    def decorator(cls: Type[BasePortal]):
        PORTAL_REGISTRY[name.lower().strip()] = cls
        return cls
    return decorator

def get_portal_plugin(name: str) -> Optional[BasePortal]:
    """Instantiates and returns the portal plugin for the given name."""
    cls = PORTAL_REGISTRY.get(name.lower().strip())
    if cls:
        return cls()
    return None
