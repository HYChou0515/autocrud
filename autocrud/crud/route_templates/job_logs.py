"""Route template that exposes job execution logs as ``text/plain``."""

import datetime as dt
import textwrap
from typing import TypeVar

from fastapi import APIRouter, Depends

from autocrud.crud.route_templates.basic import BaseRouteTemplate
from autocrud.crud.route_templates.exception_handlers import to_http_exception
from autocrud.types import IResourceManager

T = TypeVar("T")


class JobLogsRouteTemplate(BaseRouteTemplate):
    """``GET /{model_name}/{resource_id}/logs`` — plain-text job logs."""

    def apply(
        self,
        model_name: str,
        resource_manager: IResourceManager[T],
        router: APIRouter,
    ) -> None:
        # Only register when a message queue is configured
        if resource_manager.message_queue is None:
            return

        @router.get(
            f"/{model_name}/{{resource_id}}/logs",
            response_class=None,
            summary=f"Get logs for a {model_name} job",
            tags=[f"{model_name}"],
            description=textwrap.dedent(
                f"""\
                Retrieve the execution log of a `{model_name}` job.

                Returns the log as plain text (``text/plain``).  If no logs
                have been recorded (e.g. the job hasn't started yet or no
                blob store is configured), returns HTTP 204 No Content.""",
            ),
        )
        async def get_job_logs(
            resource_id: str,
            current_user: str = Depends(self.deps.get_user),
            current_time: dt.datetime = Depends(self.deps.get_now),
        ):
            from fastapi.responses import PlainTextResponse, Response

            try:
                with resource_manager.meta_provide(current_user, current_time):
                    # Ensure the resource exists (raises 404 otherwise)
                    resource_manager.get(resource_id)

                    logs = resource_manager.message_queue.get_logs(resource_id)
                    if logs is None:
                        return Response(status_code=204)
                    return PlainTextResponse(logs)
            except Exception as e:
                raise to_http_exception(e)
