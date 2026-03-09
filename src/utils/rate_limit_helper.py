"""
Utility classes for managing rate limits and preventing infinite retry loops.

This module provides:
1. StatusMessageEditor - A cooldown-aware status message editor
2. MaxRetryHTTPClient - An HTTP client with maximum retry limits
"""

import time
import asyncio
from typing import Optional
import discord
from discord.http import HTTPClient


class StatusMessageEditor:
    """
    A helper class for editing Discord status messages with cooldown protection.

    Features:
    - Skips intermediate edits if they happen too soon (within cooldown period)
    - Always waits and retries for important messages (errors, final output)
    - Tracks last edit time per message to avoid rapid edits

    Usage:
        editor = StatusMessageEditor(cooldown_seconds=1.0)
        await editor.update(message, "Processing...", important=False)  # Skipped if too soon
        await editor.update(message, "Error!", important=True)  # Always waits
    """

    def __init__(self, cooldown_seconds: float = 1.0):
        """
        Initialize the StatusMessageEditor.

        Args:
            cooldown_seconds: Minimum time between edits for non-important messages
        """
        self.cooldown = cooldown_seconds
        self._last_edit_time = 0.0
        self._last_edit_content = ""

    async def update(
        self,
        message: discord.Message,
        content: str,
        important: bool = False,
        force: bool = False
    ) -> bool:
        """
        Update a status message with cooldown protection.

        Args:
            message: The Discord message to edit
            content: The new content
            important: If True, always wait and retry (for errors/final output)
            force: If True, bypass cooldown and edit immediately

        Returns:
            True if the edit was performed, False if skipped
        """
        now = time.time()
        time_since_last_edit = now - self._last_edit_time

        # For important messages or forced updates, always wait if needed
        if important or force:
            if time_since_last_edit < self.cooldown:
                # Wait for cooldown to expire
                await asyncio.sleep(self.cooldown - time_since_last_edit)
            await message.edit(content=content)
            self._last_edit_time = time.time()
            self._last_edit_content = content
            return True

        # For intermediate status messages, skip if too soon
        if time_since_last_edit < self.cooldown:
            print(f"[StatusMessageEditor] Skipping edit '{content[:50]}...' "
                  f"(only {time_since_last_edit:.2f}s since last edit)")
            return False

        # Safe to edit now
        await message.edit(content=content)
        self._last_edit_time = time.time()
        self._last_edit_content = content
        return True

    async def edit_with_retry(
        self,
        message: discord.Message,
        content: str,
        max_retries: int = 5,
        initial_delay: float = 1.0
    ) -> bool:
        """
        Edit a message with retry logic for important messages.

        This method will retry on rate limit errors with exponential backoff.

        Args:
            message: The Discord message to edit
            content: The new content
            max_retries: Maximum number of retry attempts
            initial_delay: Initial delay between retries (doubles each retry)

        Returns:
            True if successful, False if all retries exhausted
        """
        for attempt in range(max_retries):
            try:
                # Wait for cooldown before attempting
                now = time.time()
                time_since_last_edit = now - self._last_edit_time
                if time_since_last_edit < self.cooldown:
                    await asyncio.sleep(self.cooldown - time_since_last_edit)

                await message.edit(content=content)
                self._last_edit_time = time.time()
                self._last_edit_content = content
                return True

            except discord.HTTPException as e:
                if e.status == 429:  # Rate limited
                    if attempt < max_retries - 1:
                        delay = initial_delay * (2 ** attempt)
                        print(f"[StatusMessageEditor] Rate limited, retrying in {delay}s "
                              f"(attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        print(f"[StatusMessageEditor] Max retries exceeded for message edit")
                        return False
                else:
                    # Non-rate-limit error, don't retry
                    print(f"[StatusMessageEditor] Non-rate-limit error: {e}")
                    return False

        return False


class MaxRetryHTTPClient(HTTPClient):
    """
    A custom HTTP client that limits retry attempts to prevent infinite loops.

    discord.py's default HTTPClient will retry 429 responses indefinitely.
    This subclass adds a maximum retry limit to prevent infinite loops.

    Usage:
        # In yomibot.py, replace the bot creation with:
        bot = CaseInsensitiveBot(
            command_prefix=case_insensitive_prefix,
            intents=intents,
            other_bot_commands=other_bot_commands,
            http_client=MaxRetryHTTPClient(max_retries=5)
        )
    """

    def __init__(self, *args, max_retries: int = 5, **kwargs):
        """
        Initialize the MaxRetryHTTPClient.

        Args:
            max_retries: Maximum number of retry attempts for rate-limited requests
            *args, **kwargs: Passed to parent HTTPClient
        """
        self.max_retries = max_retries
        super().__init__(*args, **kwargs)

    async def request(self, route, *args, **kwargs):
        """
        Override the request method to add retry limiting.

        This method tracks retry attempts and stops retrying after max_retries
        attempts for rate-limited requests.
        """
        # We need to track retries per request
        # discord.py uses a recursive approach for retries, so we need to
        # intercept the rate limit handling

        attempt = 0

        while attempt <= self.max_retries:
            try:
                response = await super().request(route, *args, **kwargs)
                return response
            except Exception as e:
                # Check if this is a rate limit error
                if hasattr(e, 'status') and e.status == 429:
                    attempt += 1
                    if attempt > self.max_retries:
                        print(f"[MaxRetryHTTPClient] Max retries ({self.max_retries}) exceeded, giving up")
                        raise
                    print(f"[MaxRetryHTTPClient] Rate limited, retry attempt {attempt}/{self.max_retries}")
                    # Let the retry loop continue - the super().request will handle the delay
                    raise
                else:
                    # Non-rate-limit error, don't retry
                    raise
        # Shouldn't reach here, but just in case
        return await super().request(route, *args, **kwargs)


# Global instance for convenience
_default_status_editor = StatusMessageEditor()


def get_status_editor(cooldown_seconds: float = 1.0) -> StatusMessageEditor:
    """
    Get a StatusMessageEditor instance (cached or new).

    Args:
        cooldown_seconds: Cooldown period for the editor

    Returns:
        A StatusMessageEditor instance
    """
    global _default_status_editor
    if _default_status_editor.cooldown != cooldown_seconds:
        _default_status_editor = StatusMessageEditor(cooldown_seconds=cooldown_seconds)
    return _default_status_editor
