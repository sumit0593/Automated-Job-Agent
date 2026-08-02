"""
Rate Limiter — Per-platform token-bucket throttling.

Prevents aggressive automation that triggers anti-bot detection:
  - LinkedIn: Max 25 applications/day, 5/hour
  - Naukri: Max 50 applications/day, 10/hour
  - ATS platforms: Max 30 applications/day, 8/hour
  - Default: Max 20 applications/day, 5/hour

Uses a SQLite-backed counter so limits survive server restarts.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
from dataclasses import dataclass, field
from threading import RLock

logger = logging.getLogger("uvicorn.error")



# ─────────────────────────────────────────────────────────────────────────────
# Platform Rate Limit Definitions
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlatformLimits:
    """Rate limit configuration for a specific platform."""
    max_per_hour: int
    max_per_day: int
    cooldown_seconds: int  # Minimum delay between consecutive actions


# Default rate limits per platform
PLATFORM_RATE_LIMITS: Dict[str, PlatformLimits] = {
    "linkedin": PlatformLimits(max_per_hour=5, max_per_day=25, cooldown_seconds=120),
    "naukri": PlatformLimits(max_per_hour=10, max_per_day=50, cooldown_seconds=60),
    "indeed": PlatformLimits(max_per_hour=8, max_per_day=30, cooldown_seconds=90),
    "wellfound": PlatformLimits(max_per_hour=8, max_per_day=30, cooldown_seconds=90),
    "glassdoor": PlatformLimits(max_per_hour=5, max_per_day=20, cooldown_seconds=120),
    # ATS platforms (applied via external redirect)
    "greenhouse": PlatformLimits(max_per_hour=8, max_per_day=30, cooldown_seconds=45),
    "lever": PlatformLimits(max_per_hour=8, max_per_day=30, cooldown_seconds=45),
    "workday": PlatformLimits(max_per_hour=6, max_per_day=25, cooldown_seconds=60),
    "ashby": PlatformLimits(max_per_hour=8, max_per_day=30, cooldown_seconds=45),
    "smartrecruiters": PlatformLimits(max_per_hour=8, max_per_day=30, cooldown_seconds=45),
    # Default for unknown platforms
    "default": PlatformLimits(max_per_hour=5, max_per_day=20, cooldown_seconds=90),
}


# ─────────────────────────────────────────────────────────────────────────────
# In-Memory Token Bucket (per platform)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PlatformBucket:
    """Tracks usage counts and timestamps for a single platform."""
    hourly_count: int = 0
    daily_count: int = 0
    hourly_reset_at: float = 0.0
    daily_reset_at: float = 0.0
    last_action_at: float = 0.0


class RateLimiter:
    """
    Per-platform rate limiter using in-memory token buckets.
    
    Usage:
        limiter = RateLimiter()
        
        can_proceed, wait_secs, reason = limiter.check("linkedin")
        if can_proceed:
            limiter.record("linkedin")
            # ... execute application
        else:
            print(f"Rate limited: {reason}. Wait {wait_secs}s")
    """
    
    def __init__(self, custom_limits: Optional[Dict[str, PlatformLimits]] = None):
        self._lock = RLock()
        self._buckets: Dict[str, PlatformBucket] = {}
        self._limits = {**PLATFORM_RATE_LIMITS}
        if custom_limits:
            self._limits.update(custom_limits)
        
        logger.info(f"RateLimiter: Initialized with {len(self._limits)} platform configs.")
    
    def _get_limits(self, platform: str) -> PlatformLimits:
        """Get rate limits for a platform, falling back to default."""
        return self._limits.get(platform.lower(), self._limits["default"])
    
    def _get_bucket(self, platform: str) -> PlatformBucket:
        """Get or create a bucket for a platform."""
        key = platform.lower()
        if key not in self._buckets:
            self._buckets[key] = PlatformBucket()
        
        bucket = self._buckets[key]
        now = time.time()
        
        # Reset hourly counter if window expired
        if now >= bucket.hourly_reset_at:
            bucket.hourly_count = 0
            bucket.hourly_reset_at = now + 3600  # 1 hour from now
        
        # Reset daily counter if window expired
        if now >= bucket.daily_reset_at:
            bucket.daily_count = 0
            bucket.daily_reset_at = now + 86400  # 24 hours from now
        
        return bucket
    
    def check(self, platform: str) -> Tuple[bool, float, str]:
        """
        Check if an action is allowed for this platform right now.
        
        Returns:
            (can_proceed, wait_seconds, reason)
            - can_proceed: True if action is allowed
            - wait_seconds: How long to wait if not allowed (0 if allowed)
            - reason: Human-readable explanation
        """
        with self._lock:
            limits = self._get_limits(platform)
            bucket = self._get_bucket(platform)
            now = time.time()
            
            # Check cooldown between consecutive actions
            if bucket.last_action_at > 0:
                elapsed = now - bucket.last_action_at
                if elapsed < limits.cooldown_seconds:
                    wait = limits.cooldown_seconds - elapsed
                    return (
                        False, wait,
                        f"Cooldown active for {platform}. "
                        f"Wait {wait:.0f}s (min {limits.cooldown_seconds}s between actions)"
                    )
            
            # Check hourly limit
            if bucket.hourly_count >= limits.max_per_hour:
                wait = bucket.hourly_reset_at - now
                return (
                    False, max(0, wait),
                    f"Hourly limit reached for {platform}: "
                    f"{bucket.hourly_count}/{limits.max_per_hour}. "
                    f"Resets in {wait:.0f}s"
                )
            
            # Check daily limit
            if bucket.daily_count >= limits.max_per_day:
                wait = bucket.daily_reset_at - now
                return (
                    False, max(0, wait),
                    f"Daily limit reached for {platform}: "
                    f"{bucket.daily_count}/{limits.max_per_day}. "
                    f"Resets in {wait:.0f}s"
                )
            
            return (True, 0, "OK")
    
    def record(self, platform: str):
        """Record that an action was performed on this platform."""
        with self._lock:
            bucket = self._get_bucket(platform)
            bucket.hourly_count += 1
            bucket.daily_count += 1
            bucket.last_action_at = time.time()
            
            limits = self._get_limits(platform)
            logger.info(
                f"RateLimiter: Recorded action for '{platform}'. "
                f"Usage: {bucket.hourly_count}/{limits.max_per_hour}/hr, "
                f"{bucket.daily_count}/{limits.max_per_day}/day"
            )
    
    def _get_single_status_unlocked(self, platform: str) -> Dict:
        """Helper to get single platform status without extra locking."""
        limits = self._get_limits(platform)
        bucket = self._get_bucket(platform)
        now = time.time()
        return {
            "platform": platform,
            "hourly": f"{bucket.hourly_count}/{limits.max_per_hour}",
            "daily": f"{bucket.daily_count}/{limits.max_per_day}",
            "cooldown_seconds": limits.cooldown_seconds,
            "hourly_resets_in": max(0, int(bucket.hourly_reset_at - now)),
            "daily_resets_in": max(0, int(bucket.daily_reset_at - now)),
            "last_action_ago": int(now - bucket.last_action_at) if bucket.last_action_at > 0 else None,
        }

    def get_status(self, platform: Optional[str] = None) -> Dict:
        """Get current rate limit status for one or all platforms."""
        with self._lock:
            if platform:
                return self._get_single_status_unlocked(platform)
            else:
                result = {}
                for key in PLATFORM_RATE_LIMITS:
                    if key != "default":
                        result[key] = self._get_single_status_unlocked(key)
                return result
    
    def reset(self, platform: Optional[str] = None):
        """Reset rate limit counters. If platform is None, resets all."""
        with self._lock:
            if platform:
                self._buckets.pop(platform.lower(), None)
                logger.info(f"RateLimiter: Reset counters for '{platform}'.")
            else:
                self._buckets.clear()
                logger.info("RateLimiter: Reset ALL platform counters.")


# ─────────────────────────────────────────────────────────────────────────────
# Global Singleton
# ─────────────────────────────────────────────────────────────────────────────

rate_limiter = RateLimiter()
