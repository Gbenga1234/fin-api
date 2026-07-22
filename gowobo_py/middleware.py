import logging
import time
import uuid

logger = logging.getLogger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware:
    """
    Logs one structured line per request:

        {"level": "INFO", "message": "request completed", "method": "POST",
         "path": "/api/v1/transactions/transfer/", "status_code": 201,
         "duration_ms": 12.4, "request_id": "..."}

    Also echoes the request id back as a response header so it can be
    correlated with client-side logs / support tickets.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(f"HTTP_{REQUEST_ID_HEADER.upper().replace('-', '_')}") or str(uuid.uuid4())
        request.request_id = request_id

        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        response[REQUEST_ID_HEADER] = request_id

        log_level = logging.INFO if response.status_code < 500 else logging.ERROR
        logger.log(
            log_level,
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
                "remote_addr": request.META.get("REMOTE_ADDR"),
            },
        )
        return response
