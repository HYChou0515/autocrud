"""#384 — auto-register ``partition_key`` / ``idempotency_key`` as indexed fields.

The queue queries these two ``Job`` fields by equality at claim time
(``partition_key``) and dedup time (``idempotency_key``). If they are not
registered as indexed fields, the equality search degrades on SQL backends
(cf. #378), which would make idempotent-enqueue dedup unreliable. ``crud``
must auto-register them on the generated Job model — alongside the existing
``status`` / ``retries`` auto-registration.
"""

import datetime as dt
import warnings

from fastapi import Body, FastAPI
from msgspec import Struct

from specstar.crud.core import SpecStar
from specstar.message_queue.simple import SimpleMessageQueueFactory


class Article(Struct):
    content: str
    title: str


class ArticleRequest(Struct):
    prompt: str
    title: str


def _build_job_rm():
    """Build a SpecStar with one async-job create_action and return its
    auto-generated Job resource manager."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec = SpecStar(
            default_user="t",
            default_now=dt.datetime.now,
            message_queue_factory=SimpleMessageQueueFactory(max_retries=1),
        )
        spec.add_model(Article, name="article")

        @spec.create_action("article", async_mode="job", label="Generate")
        def generate_article(payload: ArticleRequest = Body(...)) -> Article:
            return Article(title=payload.title, content="ok")

        app = FastAPI()
        spec.apply(app)
    return spec.resource_managers["generate-article-job"]


def test_partition_and_idempotency_keys_are_auto_indexed():
    job_rm = _build_job_rm()
    indexed = {getattr(f, "field_path", f) for f in job_rm._indexed_fields}
    # The pre-existing auto-registrations stay...
    assert {"status", "retries"} <= indexed
    # ...and the two #384 keys are now registered too.
    assert "partition_key" in indexed
    assert "idempotency_key" in indexed
