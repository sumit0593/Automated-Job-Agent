from backend.app.automation.ats.base_ats import BaseATS
from backend.app.automation.ats.ats_router import (
    register_ats,
    detect_ats,
    get_ats_plugin,
    ATS_REGISTRY
)

# Import adapters to trigger registration decorators
import backend.app.automation.ats.ats_adapters
import backend.app.automation.ats.generic.generic_ats
