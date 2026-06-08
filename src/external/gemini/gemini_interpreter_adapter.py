"""Adapter that lets the intent interpreter call a Gemini client."""
from __future__ import annotations

import concurrent.futures
import logging

logger = logging.getLogger(__name__)


class GeminiInterpreterAdapter:
    """Wrap a Gemini-like client as generate(prompt, timeout_s) -> str."""

    def __init__(self, client):
        self._client = client

    def generate(self, prompt: str, timeout_s: float = 3.0) -> str:
        """Return model text for prompt, or raise on timeout/error."""
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            future = executor.submit(self._call, prompt)
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            logger.debug("Gemini call timed out after %.2fs", timeout_s)
            raise TimeoutError(
                f"Gemini call timed out after {timeout_s:.2f}s"
            ) from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    def _call(self, prompt: str) -> str:
        if hasattr(self._client, "generate"):
            return str(self._client.generate(prompt=prompt))
        if hasattr(self._client, "analyze"):
            response = self._client.analyze(scene_text=prompt)
            return str(getattr(response, "raw_text", response))
        raise TypeError("Gemini client must expose generate() or analyze()")
