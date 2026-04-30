import datetime as dt
import textwrap
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException

from autocrud.crud.route_templates.basic import (
    BaseRouteTemplate,
    MsgspecResponse,
    struct_to_responses_type,
)
from autocrud.crud.route_templates.exception_handlers import to_http_exception
from autocrud.types import (
    IResourceManager,
    RevisionInfo,
    TaskStatus,
)

T = TypeVar("T")


class RerunRouteTemplate(BaseRouteTemplate):
    """Route template for re-enqueuing a completed or failed job."""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        # Only register the route when the resource manager has a message queue
        if resource_manager.message_queue is None:  # ty:ignore[unresolved-attribute]
            return

        @router.post(
            f"/{model_name}/{{resource_id}}/rerun",
            responses=struct_to_responses_type(RevisionInfo),
            summary=f"Rerun a {model_name} job",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""\
                Re-enqueue a completed or failed `{model_name}` job.

                Resets the job status to `pending`, clears `retries`, `errmsg`,
                and `artifact`, then places the job back into the message queue
                for processing.  The original `payload` is preserved.

                **Allowed source statuses:** `completed`, `failed`.
                Jobs that are `pending` or `processing` cannot be rerun.

                **Response:** Returns the new revision info after the reset.""",
            ),
        )
        async def rerun_job(
            resource_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            try:
                with resource_manager.using(current_user, current_time):
                    resource = resource_manager.get(resource_id)
                    job = resource.data

                    if job.status in (TaskStatus.PENDING, TaskStatus.PROCESSING):  # ty:ignore[unresolved-attribute]
                        raise HTTPException(
                            status_code=400,
                            detail=f"Cannot rerun a job with status '{job.status}'. "  # ty:ignore[unresolved-attribute]
                            f"Only completed or failed jobs can be rerun.",
                        )

                    # Reset job fields
                    job.status = TaskStatus.PENDING  # ty:ignore[unresolved-attribute]
                    job.retries = 0  # ty:ignore[unresolved-attribute]
                    job.errmsg = None  # ty:ignore[unresolved-attribute]
                    job.artifact = None  # ty:ignore[unresolved-attribute]

                    info = resource_manager.create_or_update(resource_id, job)
                    resource_manager.message_queue.put(resource_id)  # ty:ignore[unresolved-attribute]

                return MsgspecResponse(info)
            except Exception as e:
                raise to_http_exception(e)
