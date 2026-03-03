"""Background heartbeat thread for job liveness detection.

During job execution, a HeartbeatThread periodically updates
``job.last_heartbeat_at`` using ``rm.modify`` (draft revision) so that
``recover_stale_jobs`` can distinguish between 'still running' and 'dead' jobs.
"""

import datetime as dt
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from autocrud.message_queue.basic import BasicMessageQueue


class HeartbeatThread:
    """Background thread that periodically updates a job's ``last_heartbeat_at``.

    Uses ``rm.modify`` (draft revision) to avoid creating new stable revisions
    on every heartbeat tick.  The thread is a daemon so it won't block process
    shutdown if ``stop()`` is not called.

    Args:
        mq: The message queue instance (provides ``rm`` and ``_rm_meta_provide``).
        resource_id: The job resource to heartbeat.
        interval_seconds: Seconds between heartbeat ticks.
    """

    def __init__(
        self,
        mq: "BasicMessageQueue",
        resource_id: str,
        interval_seconds: float = 5.0,
    ):
        self._mq = mq
        self._resource_id = resource_id
        self._interval = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the heartbeat background thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"heartbeat-{self._resource_id}",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        """Signal the heartbeat to stop and wait for the thread to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._interval * 2)
            self._thread = None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Main loop: sleep then update ``last_heartbeat_at``."""
        while not self._stop_event.is_set():
            self._stop_event.wait(self._interval)
            if self._stop_event.is_set():
                break
            self._tick()

    def _tick(self) -> None:
        """Perform a single heartbeat update (best-effort)."""
        try:
            rm = self._mq.rm
            resource = rm.get(self._resource_id)
            resource.data.last_heartbeat_at = dt.datetime.now(dt.timezone.utc)
            with self._mq._rm_meta_provide(resource.info.created_by):
                rm.modify(self._resource_id, resource.data)
        except Exception:
            # Best effort – a single failed tick should not kill the thread.
            pass
