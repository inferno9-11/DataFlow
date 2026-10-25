import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.metrics import HTTP_REQUEST_DURATION_SECONDS, HTTP_REQUESTS_TOTAL


class TimingAndMetricsMiddleware(BaseHTTPMiddleware):
    """
    Measures request processing latency, sets X-Process-Time header,
    and updates Prometheus metrics.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time

        response.headers["X-Process-Time"] = f"{process_time:.4f}s"

        # Prometheus metrics update
        path = request.url.path
        # Collapse IDs in metrics paths to avoid high-cardinality explosions
        normalized_path = self._normalize_path(path)
        status_code = str(response.status_code)

        HTTP_REQUESTS_TOTAL.labels(
            method=request.method,
            endpoint=normalized_path,
            status_code=status_code,
        ).inc()

        HTTP_REQUEST_DURATION_SECONDS.labels(
            method=request.method,
            endpoint=normalized_path,
        ).observe(process_time)

        return response

    @staticmethod
    def _normalize_path(path: str) -> str:
        parts = path.split("/")
        normalized = []
        for p in parts:
            if len(p) > 20 or (len(p) == 36 and "-" in p):
                normalized.append("{id}")
            else:
                normalized.append(p)
        return "/".join(normalized)
