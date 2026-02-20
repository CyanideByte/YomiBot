"""
Model priority manager with rate limit tracking.

Handles fallback between models when rate limits are hit.
Models are rate limited for 15 minutes after hitting a rate limit.
Uses persistent file storage to track usage across bot restarts.
"""

import time
import threading
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# File path for usage tracking
USAGE_FILE = Path(__file__).parent.parent.parent.parent / "data" / "api_usage.json"


class APIUsageTracker:
    """Tracks API usage and rate limits with persistent storage."""

    def __init__(self, usage_file: Path):
        self.usage_file = usage_file
        self.data = {}
        self.lock = threading.Lock()
        self._load_usage_data()

    def _load_usage_data(self):
        """Load usage data from file, or create fresh data."""
        try:
            if self.usage_file.exists():
                with open(self.usage_file, 'r') as f:
                    self.data = json.load(f)

                # Check if any rate limits have expired
                self._check_and_reset_expired_limits()
                logger.info(f"[USAGE TRACKER] Loaded usage data from {self.usage_file}")
            else:
                logger.info(f"[USAGE TRACKER] No usage file found, creating fresh tracking")
                self._create_fresh_data()
        except Exception as e:
            logger.error(f"[USAGE TRACKER] Error loading usage data: {e}")
            self._create_fresh_data()

    def _create_fresh_data(self):
        """Create fresh usage tracking data."""
        self.data = {}
        self._save_usage_data()

    def _check_and_reset_expired_limits(self):
        """Reset rate limits that have expired (15-minute cooldown)."""
        now = datetime.now(timezone.utc)

        for model, usage in self.data.items():
            if usage.get("rate_limit_until"):
                try:
                    reset_time = datetime.fromisoformat(usage["rate_limit_until"])
                    if now >= reset_time:
                        # Rate limit has expired, reset
                        usage["rate_limited"] = False
                        usage["rate_limit_until"] = None
                        logger.info(f"[USAGE TRACKER] Rate limit expired for {model}")
                except:
                    pass

        self._save_usage_data()

    def _save_usage_data(self):
        """Save usage data to file."""
        try:
            self.usage_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.usage_file, 'w') as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            logger.error(f"[USAGE TRACKER] Error saving usage data: {e}")

    def is_rate_limited(self, model: str) -> bool:
        """Check if a model is currently rate limited."""
        with self.lock:
            if model not in self.data:
                return False

            usage = self.data[model]

            # Check if rate limit has expired
            if usage.get("rate_limited") and usage.get("rate_limit_until"):
                try:
                    reset_time = datetime.fromisoformat(usage["rate_limit_until"])
                    if datetime.now(timezone.utc) >= reset_time:
                        # Rate limit has expired, unmark it
                        usage["rate_limited"] = False
                        usage["rate_limit_until"] = None
                        self._save_usage_data()
                        logger.info(f"[USAGE TRACKER] Rate limit expired for {model}")
                        return False
                except:
                    pass

            return usage.get("rate_limited", False)

    def record_request(self, model: str, tokens: int = 0):
        """Record an API request and update usage tracking."""
        with self.lock:
            # Create entry for new models
            if model not in self.data:
                self.data[model] = {
                    "requests_used": 0,
                    "tokens_used": 0,
                    "rate_limited": False,
                    "rate_limit_until": None,
                    "last_reset": datetime.now(timezone.utc).isoformat()
                }
                logger.info(f"[USAGE TRACKER] Created tracking entry for {model}")

            usage = self.data[model]
            usage["requests_used"] += 1
            usage["tokens_used"] += tokens
            self._save_usage_data()

    def get_usage(self, model: str) -> Dict:
        """Get current usage stats for a model. Creates entry if missing."""
        with self.lock:
            if model not in self.data:
                # Return default stats for unknown models
                return {
                    "requests_used": 0,
                    "tokens_used": 0,
                    "rate_limited": False,
                    "rate_limit_until": None
                }
            return self.data[model]


class ModelPriorityManager:
    """
    Manages model priority and rate limit cooldowns.
    """

    # Model priority list (highest to lowest)
    # All models stored WITH provider prefix for consistency
    # gemini-3-flash-preview removed: 20-40s per call vs 1-3s for 2.5 models
    MODEL_PRIORITY = [
        "groq/moonshotai/kimi-k2-instruct-0905",
        "groq/meta-llama/llama-4-scout-17b-16e-instruct",
        "groq/meta-llama/llama-4-maverick-17b-128e-instruct",
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/llama-3.3-70b-versatile",
        "groq/qwen/qwen3-32b",
        "gemini/gemini-2.5-flash",
        "gemini/gemini-2.5-flash-lite",
        "openrouter/stepfun/step-3.5-flash:free",
        "gemini/gemini-3-flash-preview",
        "gemini/gemma-3-27b-it"
    ]

    def __init__(self, usage_tracker: APIUsageTracker):
        self.usage_tracker = usage_tracker
        self.lock = threading.Lock()

    def get_available_model(self) -> Optional[str]:
        """
        Get the highest priority model that isn't rate limited.
        """
        with self.lock:
            # Check each model in priority order
            for model in self.MODEL_PRIORITY:
                usage = self.usage_tracker.get_usage(model)

                # Skip if rate limited
                if self.usage_tracker.is_rate_limited(model):
                    continue

                # This model is available
                logger.info(f"[MODEL SELECTOR] Selected {model} ({usage['requests_used']} requests used)")
                return model

            # All models are rate limited
            logger.warning("[MODEL SELECTOR] All models rate limited")
            return None

    def mark_rate_limited(self, model: str):
        """
        Mark a model as rate limited for 15 minutes.
        """
        with self.lock:
            # Ensure model exists in data before marking
            if model not in self.usage_tracker.data:
                self.usage_tracker.data[model] = {
                    "requests_used": 0,
                    "tokens_used": 0,
                    "rate_limited": False,
                    "rate_limit_until": None,
                    "last_reset": datetime.now(timezone.utc).isoformat()
                }

            # Calculate cooldown time (15 minutes from now)
            cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=15)

            # Mark it as rate limited in the actual data
            usage = self.usage_tracker.data[model]
            if not usage.get("rate_limited"):
                usage["rate_limited"] = True
                usage["rate_limit_until"] = cooldown_until.isoformat()
                self.usage_tracker._save_usage_data()

            # Format time for logging (HH:MM:SS)
            time_str = cooldown_until.strftime("%H:%M:%S")
            logger.warning(
                f"[MODEL RATE LIMIT] {model} is rate limited for 15 minutes until {time_str} UTC"
            )

    def log_model_usage(self, model: str):
        """
        Log which model is being used for a request.
        """
        usage = self.usage_tracker.get_usage(model)
        logger.info(
            f"[MODEL USAGE] Using {model} "
            f"({usage['requests_used']} requests used)"
        )

    def get_status(self) -> Dict:
        """
        Get current status of all models.
        """
        available = []
        rate_limited = []

        for model in self.MODEL_PRIORITY:
            usage = self.usage_tracker.get_usage(model)

            if self.usage_tracker.is_rate_limited(model):
                reset_time = usage.get("rate_limit_until")
                if reset_time:
                    reset_time = datetime.fromisoformat(reset_time)
                    remaining = (reset_time - datetime.now(timezone.utc)).total_seconds()
                else:
                    remaining = 0

                rate_limited.append({
                    "model": model,
                    "rate_limit_until": usage.get("rate_limit_until"),
                    "seconds_remaining": max(0, int(remaining)),
                    "requests_used": usage["requests_used"]
                })
            else:
                available.append(model)

        return {
            "available": available,
            "rate_limited": rate_limited,
            "all_on_cooldown": len(available) == 0
        }


# Global singleton instance
_model_manager = None
_usage_tracker = None


def get_model_manager() -> ModelPriorityManager:
    """Get the global model manager instance."""
    global _model_manager, _usage_tracker
    if _model_manager is None:
        _usage_tracker = APIUsageTracker(USAGE_FILE)
        _model_manager = ModelPriorityManager(_usage_tracker)
        logger.info("[MODEL MANAGER] Initialized with priority: " + " -> ".join(ModelPriorityManager.MODEL_PRIORITY))
    return _model_manager
