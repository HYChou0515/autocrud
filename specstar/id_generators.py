"""Built-in ID generator callables.

``id_generator`` on ``add_model`` accepts ``Callable[[], str]``. Most
projects want either ``uuid4`` (default boring), ``ulid``, or
something domain-specific. The first two are shipped here; anything
custom uses ``specstar.string_ref(...)`` against a user module.
"""

from __future__ import annotations

import uuid


def uuid4() -> str:
    """Return a new random UUID4 as a string."""
    return str(uuid.uuid4())
