"""
Model priority manager with rate limit tracking.

Handles fallback between Gemini models when rate limits are hit.
"""

import time
import threading
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RateLimitEntry:
    """Tracks a rate limit event for a model."""

    def __init__(self, model: str):
        self.model = model
        self.rate_limited_at = datetime.now()
        self.cooldown_until = self.rate_limited_at + timedelta(hours=1)

    def is_cooled_down(self) -> bool:
        """Check if cooldown period has passed."""
        return datetime.now() >= self.cooldown_until

    def time_remaining(self) -> float:
        """Seconds remaining until cooldown expires."""
        remaining = self.cooldown_until - datetime.now()
        return max(0, remaining.total_seconds())


class ModelPriorityManager:
    """
    Manages model priority and rate limit cooldowns.

    Priority order (newest/best first):
    1. gemini-3-flash-preview (latest, best quality)
    2. gemini-2.5-flash (stable, high quality)
    3. gemini-2.5-flash-lite (fastest, most lenient limits)
    """

    # Model priority list (highest to lowest)
    # Note: gemini-3-flash-preview is disabled due to slow performance
    MODEL_PRIORITY = [
        # "gemini-3-flash-preview",  # Disabled - too slow
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
    ]

    def __init__(self):
        self.rate_limits: Dict[str, RateLimitEntry] = {}
        self.lock = threading.Lock()

    def get_available_model(self) -> Optional[str]:
        """
        Get the highest priority model that isn't rate limited.

        Returns None if all models are on cooldown.
        """
        with self.lock:
            # Clean up expired cooldowns first
            self._cleanup_expired_cooldowns()

            # Log what models are on cooldown
            if self.rate_limits:
                logger.info(f"[MODEL SELECTOR] Rate limited models: {list(self.rate_limits.keys())}")

            for model in self.MODEL_PRIORITY:
                if model not in self.rate_limits:
                    logger.info(f"[MODEL SELECTOR] Selected {model} (highest priority available)")
                    return model

            # All models are rate limited
            logger.warning(f"[MODEL SELECTOR] All models on cooldown")
            return None

    def mark_rate_limited(self, model: str):
        """
        Mark a model as rate limited for 1 hour.

        Logs the rate limit event and timestamps it.
        """
        with self.lock:
            entry = RateLimitEntry(model)
            self.rate_limits[model] = entry

            logger.warning(
                f"[MODEL RATE LIMIT] {model} is rate limited until "
                f"{entry.cooldown_until.strftime('%H:%M:%S')} "
                f"({entry.time_remaining():.0f}s remaining)"
            )

            # Log what models are still available
            available = [m for m in self.MODEL_PRIORITY if m not in self.rate_limits]
            if available:
                logger.info(f"[MODEL SELECTOR] Falling back to: {', '.join(available)}")
            else:
                logger.error("[MODEL SELECTOR] All models are rate limited!")

    def log_model_usage(self, model: str):
        """
        Log which model is being used for a request.

        Args:
            model: The model name being used
        """
        logger.info(f"[MODEL USAGE] Using {model}")

    def get_status(self) -> Dict:
        """
        Get current status of all models.

        Returns dict with:
        - available: list of available models
        - rate_limited: list of rate limited models with cooldown info
        - all_on_cooldown: bool
        """
        with self.lock:
            self._cleanup_expired_cooldowns()

            available = []
            rate_limited = []

            for model in self.MODEL_PRIORITY:
                if model in self.rate_limits:
                    entry = self.rate_limits[model]
                    rate_limited.append({
                        "model": model,
                        "cooldown_until": entry.cooldown_until.isoformat(),
                        "seconds_remaining": entry.time_remaining()
                    })
                else:
                    available.append(model)

            return {
                "available": available,
                "rate_limited": rate_limited,
                "all_on_cooldown": len(available) == 0
            }

    def _cleanup_expired_cooldowns(self):
        """Remove expired cooldown entries."""
        now = datetime.now()
        expired = [
            model for model, entry in self.rate_limits.items()
            if now >= entry.cooldown_until
        ]

        for model in expired:
            del self.rate_limits[model]
            logger.info(f"[MODEL COOLDOWN] {model} cooldown expired, now available")


# Global singleton instance
_model_manager = None


def get_model_manager() -> ModelPriorityManager:
    """Get the global model manager instance."""
    global _model_manager
    if _model_manager is None:
        _model_manager = ModelPriorityManager()
        logger.info("[MODEL MANAGER] Initialized with priority: " + " -> ".join(ModelPriorityManager.MODEL_PRIORITY))
    return _model_manager
