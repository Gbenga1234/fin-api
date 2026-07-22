import json
import logging
import traceback


class JsonFormatter(logging.Formatter):
    """
    Renders each log record as a single JSON line, e.g.:

        {"level": "INFO", "logger": "transactions.services", "message": "...",
         "time": "2026-07-21T18:50:00Z", "request_id": "...", "account_id": "..."}

    Anything passed via `extra={...}` on the logging call is merged in, so
    call sites can attach structured fields (request_id, account_id,
    transaction_id, status, duration_ms, ...) without string-formatting them
    into the message.
    """

    # Standard LogRecord attributes to exclude when pulling in `extra` fields
    _RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime", "taskName",
    }

    def format(self, record):
        payload = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key not in self._RESERVED and not key.startswith("_"):
                payload[key] = value

        if record.exc_info:
            payload["exception"] = "".join(traceback.format_exception(*record.exc_info))

        return json.dumps(payload, default=str)
