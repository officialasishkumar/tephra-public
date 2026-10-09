"""HTTP API: the FastAPI app, desk sessions and the Server-Sent Events stream.

Import-light on purpose: ``tephra.api.server`` pulls in the whole pipeline, so only the
error type every API module raises lives here.
"""

from collections.abc import Mapping, Sequence

from tephra.models import Advisory, ErrorBody

__all__ = ["ApiError"]


class ApiError(Exception):
    """An error answered as an :class:`ErrorBody` with a machine code from MODULES.md 8."""

    def __init__(
        self,
        status_code: int,
        error: str,
        detail: str,
        *,
        problems: Sequence[str] = (),
        current: Advisory | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(f"{status_code} {error}: {detail}")
        self.status_code = status_code
        self.error = error
        self.detail = detail
        self.problems = list(problems)
        self.current = current
        self.headers = dict(headers or {})

    def body(self) -> ErrorBody:
        return ErrorBody(
            error=self.error, detail=self.detail, problems=self.problems, current=self.current
        )
