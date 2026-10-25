from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# HTTP Request Metrics
HTTP_REQUESTS_TOTAL = Counter(
    "dataflow_http_requests_total",
    "Total count of HTTP requests processed by DataFlow",
    ["method", "endpoint", "status_code"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "dataflow_http_request_duration_seconds",
    "HTTP request execution latency in seconds",
    ["method", "endpoint"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Job Processing Metrics
JOB_EXECUTION_DURATION_SECONDS = Histogram(
    "dataflow_job_execution_duration_seconds",
    "Duration of asynchronous batch job processing in seconds",
    ["job_type", "status"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0),
)

JOB_RECORDS_PROCESSED_TOTAL = Counter(
    "dataflow_job_records_processed_total",
    "Total count of individual records processed by worker",
    ["status"],  # "success", "failed", "duplicate"
)

ACTIVE_JOBS_GAUGE = Gauge(
    "dataflow_active_jobs",
    "Current number of processing jobs actively executing in workers",
)

QUEUE_DEPTH_GAUGE = Gauge(
    "dataflow_queue_depth",
    "Estimated number of jobs pending execution in Redis queue",
)


def get_latest_metrics() -> tuple[bytes, str]:
    """Returns Prometheus serialized metrics and content-type header."""
    return generate_latest(), CONTENT_TYPE_LATEST
