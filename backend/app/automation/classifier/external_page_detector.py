import logging
from typing import Callable

logger = logging.getLogger("uvicorn.error")

def detect_new_external_page(context, action_trigger: Callable, timeout_ms: int = 5000):
    """
    Listens for new page events when clicking external apply links on portals using Playwright sync API.
    Detects if a new tab/window is opened (context.expect_page) or falls back to inspecting context.pages length.
    """
    old_pages_count = len(context.pages)
    logger.info(f"ExternalPageDetector: Monitoring for new tab opening (current tabs: {old_pages_count})...")

    try:
        with context.expect_page(timeout=timeout_ms) as page_info:
            action_trigger()
        new_page = page_info.value
        logger.info(f"ExternalPageDetector: Caught new page event! URL: {new_page.url}")
        try:
            new_page.wait_for_load_state("domcontentloaded", timeout=10000)
        except Exception:
            pass
        return new_page
    except Exception as e:
        logger.info(f"ExternalPageDetector event check ({e}). Checking open context pages...")

    current_pages = context.pages
    if len(current_pages) > old_pages_count:
        latest_page = current_pages[-1]
        logger.info(f"ExternalPageDetector: Detected new page in context.pages list! URL: {latest_page.url}")
        return latest_page

    return context.pages[-1] if context.pages else None
