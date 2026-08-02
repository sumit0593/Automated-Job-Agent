"""
Browser Session Pool — Pre-warmed Playwright session management.

Instead of launching a fresh browser for every application,
this pool maintains warm browser contexts with active cookies,
ready for immediate use. Sessions are platform-affine (LinkedIn
sessions stay warm with LinkedIn cookies).

Features:
  - Pre-warmed session pool (configurable size per platform)
  - Cookie persistence and session health checks
  - Automatic session rotation for anti-detection
  - Stealth configuration to avoid bot fingerprinting
  - Acquire/release pattern with timeout
"""

import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, List, Tuple, Any
from threading import Lock, Condition
from dataclasses import dataclass, field
from playwright.sync_api import sync_playwright, Playwright, Browser, BrowserContext, Page

from backend.app.config import settings, BROWSER_PROFILES_DIR

logger = logging.getLogger("uvicorn.error")


# ─────────────────────────────────────────────────────────────────────────────
# Session Wrapper
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BrowserSession:
    """A single managed browser session."""
    session_id: str
    platform: str
    context: BrowserContext
    page: Page
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    use_count: int = 0
    in_use: bool = False
    cookies_loaded: bool = False
    
    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at
    
    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_used_at
    
    def is_healthy(self) -> bool:
        """Check if the session is still usable."""
        try:
            # Simple health check — page must still be connected
            self.page.evaluate("() => document.readyState")
            return True
        except Exception:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Stealth Configuration
# ─────────────────────────────────────────────────────────────────────────────

# Rotating user agents to avoid fingerprinting
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:129.0) Gecko/20100101 Firefox/129.0",
]

# Viewport sizes for variety
VIEWPORTS = [
    {"width": 1920, "height": 1080},
    {"width": 1536, "height": 864},
    {"width": 1440, "height": 900},
    {"width": 1366, "height": 768},
    {"width": 1280, "height": 720},
]

# Stealth JavaScript to inject into every page
STEALTH_SCRIPTS = [
    # Override navigator.webdriver
    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})",
    # Override chrome runtime
    "window.chrome = {runtime: {}, loadTimes: function(){}, csi: function(){}}",
    # Override permissions
    """
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
        Promise.resolve({state: Notification.permission}) :
        originalQuery(parameters)
    );
    """,
    # Override plugins
    """
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5].map(() => ({
            name: 'Chrome PDF Plugin',
            description: 'Portable Document Format',
            filename: 'internal-pdf-viewer'
        }))
    });
    """,
    # Override languages
    "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']})",
]


def _get_stealth_context_options(platform: str, index: int = 0) -> Dict[str, Any]:
    """Generate browser context options with anti-detection measures."""
    ua_idx = index % len(USER_AGENTS)
    vp_idx = index % len(VIEWPORTS)
    
    storage_path = BROWSER_PROFILES_DIR / f"{platform}_profile_{index}"
    storage_path.mkdir(parents=True, exist_ok=True)
    
    return {
        "user_agent": USER_AGENTS[ua_idx],
        "viewport": VIEWPORTS[vp_idx],
        "locale": "en-US",
        "timezone_id": "Asia/Kolkata",
        "geolocation": {"longitude": 77.1025, "latitude": 28.7041},  # Delhi NCR
        "permissions": ["geolocation"],
        "color_scheme": "light",
        "storage_state": None,  # Will be loaded separately if available
    }


# ─────────────────────────────────────────────────────────────────────────────
# Session Pool
# ─────────────────────────────────────────────────────────────────────────────

class SessionPool:
    """
    Browser session pool with pre-warming, health checks, and anti-detection.
    
    Usage:
        pool = SessionPool()
        pool.initialize()
        
        # Acquire a session for LinkedIn
        session = pool.acquire("linkedin", timeout=30)
        if session:
            try:
                session.page.goto("https://linkedin.com/jobs/...")
                # ... do work ...
            finally:
                pool.release(session)
        
        # Cleanup
        pool.shutdown()
    """
    
    def __init__(
        self,
        max_sessions_per_platform: int = 2,
        max_total_sessions: int = 6,
        max_session_age_seconds: int = 1800,     # 30 min
        max_idle_seconds: int = 600,              # 10 min
        max_uses_per_session: int = 10,           # Rotate after N uses
    ):
        self._lock = Lock()
        self._condition = Condition(self._lock)
        self._sessions: Dict[str, List[BrowserSession]] = {}
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._session_counter = 0
        self._initialized = False
        
        self.max_per_platform = max_sessions_per_platform
        self.max_total = max_total_sessions
        self.max_age = max_session_age_seconds
        self.max_idle = max_idle_seconds
        self.max_uses = max_uses_per_session
    
    def initialize(self, headless: bool = True):
        """Initialize the Playwright browser instance."""
        if self._initialized:
            return
        
        try:
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=headless,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                    "--disable-popup-blocking",
                ],
            )
            self._initialized = True
            logger.info(
                f"SessionPool: Initialized (headless={headless}, "
                f"max_per_platform={self.max_per_platform}, "
                f"max_total={self.max_total})"
            )
        except Exception as e:
            logger.error(f"SessionPool: Failed to initialize: {e}")
            raise
    
    def _create_session(self, platform: str) -> BrowserSession:
        """Create a new browser session for a platform."""
        if not self._initialized:
            self.initialize()
        
        self._session_counter += 1
        session_id = f"{platform}_{self._session_counter}_{int(time.time())}"
        
        opts = _get_stealth_context_options(platform, self._session_counter)
        context = self._browser.new_context(**opts)
        
        # Inject stealth scripts on every new page
        context.add_init_script("\n".join(STEALTH_SCRIPTS))
        
        page = context.new_page()
        
        # Load saved cookies if available
        cookies_loaded = self._load_cookies(context, platform)
        
        session = BrowserSession(
            session_id=session_id,
            platform=platform,
            context=context,
            page=page,
            cookies_loaded=cookies_loaded,
        )
        
        logger.info(
            f"SessionPool: Created session '{session_id}' "
            f"for platform '{platform}' (cookies_loaded={cookies_loaded})"
        )
        return session
    
    def _load_cookies(self, context: BrowserContext, platform: str) -> bool:
        """Load saved cookies from database into the browser context."""
        try:
            from backend.app.database import SessionLocal
            from backend.app import models
            
            db = SessionLocal()
            try:
                cred = db.query(models.UserCredential).filter(
                    models.UserCredential.platform == platform
                ).first()
                
                if cred and cred.session_cookies:
                    context.add_cookies(cred.session_cookies)
                    logger.info(f"SessionPool: Loaded {len(cred.session_cookies)} cookies for '{platform}'")
                    return True
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"SessionPool: Could not load cookies for '{platform}': {e}")
        return False
    
    def _total_sessions(self) -> int:
        """Total number of sessions across all platforms."""
        return sum(len(sessions) for sessions in self._sessions.values())
    
    def _cleanup_stale(self, platform: str):
        """Remove stale/unhealthy sessions from the pool."""
        if platform not in self._sessions:
            return
        
        now = time.time()
        alive = []
        for session in self._sessions[platform]:
            if session.in_use:
                alive.append(session)
                continue
            
            stale_reason = None
            if session.age_seconds > self.max_age:
                stale_reason = f"max age exceeded ({session.age_seconds:.0f}s)"
            elif session.idle_seconds > self.max_idle:
                stale_reason = f"idle too long ({session.idle_seconds:.0f}s)"
            elif session.use_count >= self.max_uses:
                stale_reason = f"max uses reached ({session.use_count})"
            elif not session.is_healthy():
                stale_reason = "health check failed"
            
            if stale_reason:
                logger.info(
                    f"SessionPool: Closing stale session '{session.session_id}' "
                    f"({stale_reason})"
                )
                try:
                    session.context.close()
                except Exception:
                    pass
            else:
                alive.append(session)
        
        self._sessions[platform] = alive
    
    def acquire(self, platform: str, timeout: float = 30) -> Optional[BrowserSession]:
        """
        Acquire a browser session for a platform.
        
        Tries to reuse an idle session first; creates a new one if needed.
        Blocks up to `timeout` seconds if all sessions are busy.
        
        Returns:
            BrowserSession if acquired, None if timeout exceeded.
        """
        deadline = time.time() + timeout
        
        with self._condition:
            while True:
                self._cleanup_stale(platform)
                
                # 1. Try to find an idle session for this platform
                sessions = self._sessions.get(platform, [])
                for session in sessions:
                    if not session.in_use and session.is_healthy():
                        session.in_use = True
                        session.last_used_at = time.time()
                        session.use_count += 1
                        logger.info(
                            f"SessionPool: Acquired existing session "
                            f"'{session.session_id}' (use #{session.use_count})"
                        )
                        return session
                
                # 2. Try to create a new session
                platform_count = len(sessions)
                total_count = self._total_sessions()
                
                if platform_count < self.max_per_platform and total_count < self.max_total:
                    session = self._create_session(platform)
                    session.in_use = True
                    session.use_count = 1
                    
                    if platform not in self._sessions:
                        self._sessions[platform] = []
                    self._sessions[platform].append(session)
                    return session
                
                # 3. Wait for a session to be released
                remaining = deadline - time.time()
                if remaining <= 0:
                    logger.warning(
                        f"SessionPool: Timeout waiting for session "
                        f"(platform='{platform}', timeout={timeout}s)"
                    )
                    return None
                
                self._condition.wait(timeout=min(remaining, 5))
    
    def release(self, session: BrowserSession):
        """Release a session back to the pool for reuse."""
        with self._condition:
            session.in_use = False
            session.last_used_at = time.time()
            
            # Save cookies after use
            try:
                cookies = session.context.cookies()
                if cookies:
                    from backend.app.database import SessionLocal
                    from backend.app.automation.session.session_manager import update_session
                    
                    db = SessionLocal()
                    try:
                        update_session(db, session.platform, cookies)
                    finally:
                        db.close()
            except Exception as e:
                logger.debug(f"SessionPool: Could not save cookies on release: {e}")
            
            logger.info(
                f"SessionPool: Released session '{session.session_id}' "
                f"back to pool (uses={session.use_count})"
            )
            
            # Notify waiting acquirers
            self._condition.notify_all()
    
    def get_status(self) -> Dict[str, Any]:
        """Get pool status summary."""
        with self._lock:
            status = {
                "initialized": self._initialized,
                "total_sessions": self._total_sessions(),
                "max_total": self.max_total,
                "platforms": {},
            }
            for platform, sessions in self._sessions.items():
                status["platforms"][platform] = {
                    "total": len(sessions),
                    "in_use": sum(1 for s in sessions if s.in_use),
                    "idle": sum(1 for s in sessions if not s.in_use),
                    "sessions": [
                        {
                            "id": s.session_id,
                            "in_use": s.in_use,
                            "use_count": s.use_count,
                            "age_seconds": int(s.age_seconds),
                            "idle_seconds": int(s.idle_seconds),
                            "cookies_loaded": s.cookies_loaded,
                        }
                        for s in sessions
                    ],
                }
            return status
    
    def shutdown(self):
        """Close all sessions and shut down the browser."""
        with self._lock:
            for platform, sessions in self._sessions.items():
                for session in sessions:
                    try:
                        session.context.close()
                    except Exception:
                        pass
            self._sessions.clear()
            
            if self._browser:
                try:
                    self._browser.close()
                except Exception:
                    pass
            
            if self._playwright:
                try:
                    self._playwright.stop()
                except Exception:
                    pass
            
            self._initialized = False
            logger.info("SessionPool: Shutdown complete.")


# ─────────────────────────────────────────────────────────────────────────────
# Global Singleton
# ─────────────────────────────────────────────────────────────────────────────

session_pool = SessionPool()
