"""Job execution context with logging and artifact support.

:class:`JobContext` wraps a ``Resource[Job[T, D]]`` and exposes
convenience helpers for the job handler:

* **Logging** — ``log()``, ``info()``, ``debug()``, ``warning()``,
  ``error()`` append formatted lines to an in-memory buffer that is
  periodically flushed to blob storage by :class:`LogFlushThread`.
* **Artifact** — ``set_artifact(data)`` stores a typed output on the
  job.
* **Duck-compatibility** — ``.revision_info`` and ``.data`` delegate to the
  underlying ``Resource`` so existing handlers that accept
  ``Resource[Job[T]]`` keep working when receiving a ``JobContext``.
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import TYPE_CHECKING, Generic

from typing_extensions import TypeVar as TypeVarExt

from autocrud.resource_manager.basic import IBlobStore
from autocrud.types import Job, Resource

if TYPE_CHECKING:
    pass

_logger = logging.getLogger("autocrud.job")

_LEVEL_MAP: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

T = TypeVarExt("T")
D = TypeVarExt("D", default=None)


class JobContext(Generic[T, D]):
    """Execution context handed to a job handler.

    Provides structured logging, artifact storage, and backward-compatible
    access to the underlying ``Resource[Job[T, D]]``.

    Args:
        resource: The job resource being processed.
    """

    def __init__(self, resource: Resource[Job[T, D]]) -> None:
        self._resource = resource
        self._log_buffer: list[str] = []

    # ------------------------------------------------------------------
    # Duck-compatible with Resource[Job[T, D]]
    # ------------------------------------------------------------------

    @property
    def revision_info(self):
        """Revision info (delegates to ``resource.info``)."""
        return self._resource.info

    @property
    def data(self) -> Job[T, D]:
        """Job data (delegates to ``resource.data``)."""
        return self._resource.data

    @data.setter
    def data(self, value: Job[T, D]) -> None:
        self._resource.data = value

    @property
    def resource(self) -> Resource[Job[T, D]]:
        """The underlying ``Resource[Job[T, D]]`` instance."""
        return self._resource

    @property
    def payload(self) -> T:
        """Shortcut for ``resource.data.payload``."""
        return self._resource.data.payload

    # ------------------------------------------------------------------
    # Artifact
    # ------------------------------------------------------------------

    def set_artifact(self, data: D) -> None:
        """Store a typed artifact on the job.

        Args:
            data: The artifact value to store.
        """
        self._resource.data.artifact = data

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, message: str, level: str = "INFO") -> None:
        """Append a formatted log line to the in-memory buffer and emit
        to Python's :mod:`logging` module.

        Format (buffer): ``{ISO timestamp} [{LEVEL}] {message}``

        The standard logger (``autocrud.job``) always receives the
        message regardless of whether a blob store is configured,
        ensuring operators can observe job activity in real time.

        Args:
            message: The log message.
            level: Log level string (e.g. ``'INFO'``, ``'ERROR'``).
        """
        ts = dt.datetime.now(dt.timezone.utc).isoformat()
        self._log_buffer.append(f"{ts} [{level}] {message}")

        # Also emit via Python's standard logging.
        resource_id = self._resource.info.resource_id
        py_level = _LEVEL_MAP.get(level.upper(), logging.INFO)
        _logger.log(py_level, "[%s] %s", resource_id, message)

    def info(self, msg: str) -> None:
        """Log at INFO level."""
        self.log(msg, "INFO")

    def debug(self, msg: str) -> None:
        """Log at DEBUG level."""
        self.log(msg, "DEBUG")

    def warning(self, msg: str) -> None:
        """Log at WARNING level."""
        self.log(msg, "WARNING")

    def error(self, msg: str) -> None:
        """Log at ERROR level."""
        self.log(msg, "ERROR")

    # ------------------------------------------------------------------
    # Flush helpers
    # ------------------------------------------------------------------

    def get_log_text(self) -> str:
        """Return the current log buffer as a single newline-joined string."""
        return "\n".join(self._log_buffer)

    def flush_logs(self, blob_store: IBlobStore, key: str) -> None:
        """Encode the log buffer and write (overwrite) to *blob_store*.

        Args:
            blob_store: Target blob store.
            key: The blob key (e.g. ``__job_log__/{resource_id}``).
        """
        text = self.get_log_text()
        if text:
            blob_store.put(text.encode("utf-8"), key=key)
