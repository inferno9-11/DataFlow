import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import request_id_ctx_var


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Ensures every request has a unique correlation ID for end-to-end tracing.
    If incoming request specifies 'X-Request-ID', that ID is propagated.
    Otherwise, a new UUID v4 is generated.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())

        # Set in context variable for logging
        token = request_id_ctx_var.set(request_id)
        request.state.request_id = request_id

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_ctx_var.reset(token)
