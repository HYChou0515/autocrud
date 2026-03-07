"""Background log-flush thread for job execution.

During job execution a :class:`LogFlushThread` periodically writes the
accumulated log lines from a :class:`~autocrud.message_queue.context.JobContext`
to a :class:`~autocrud.resource_manager.basic.IBlobStore`.  The structure
mirrors :class:`~autocrud.message_queue.heartbeat.HeartbeatThread`.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autocrud.message_queue.context import JobContext
    from autocrud.resource_manager.basic import IBlobStore


class LogFlushThread:
    """Daemon thread that periodically flushes job logs to blob storage.

    Args:
        ctx: The :class:`JobContext` whose log buffer is flushed.
        blob_store: The blob store to write logs to.
        key: The blob key used for the log entry
            (e.g. ``__job_log__/{resource_id}``).
        interval_seconds: Seconds between flush ticks (default 10).
    """

    def __init__(
        self,
        ctx: "JobContext",
        blob_store: "IBlobStore",
        key: str,
        interval_seconds: float = 10.0,
    ) -> None:
        self._ctx = ctx
        self._blob_store = blob_store
        self._key = key
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the log-flush background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"log-flush-{self._key}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the thread to stop, wait, then perform a final flush."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval * 2)
            self._thread = None
        # Final flush to capture any logs written since the last tick.
        self._flush()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main loop: sleep then flush."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                break
            self._flush()

    def _flush(self) -> None:
        """Perform a single flush (best-effort)."""
        try:
            self._ctx.flush_logs(self._blob_store, self._key)
        except Exception:
            pass  # Best effort — a single failed flush should not kill the thread.
