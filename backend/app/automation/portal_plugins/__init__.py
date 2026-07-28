from backend.app.automation.portal_plugins.base_portal import BasePortal
from backend.app.automation.portal_plugins.registry import (
    register_portal,
    get_portal_plugin,
    PORTAL_REGISTRY
)

# Import plugins to trigger decorators
import backend.app.automation.portal_plugins.linkedin.linkedin_plugin
import backend.app.automation.portal_plugins.naukri.naukri_plugin
import backend.app.automation.portal_plugins.portals_extra
