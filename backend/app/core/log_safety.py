from __future__ import annotations

import logging
import re

_SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:key|ticket|code|state)=)[^&\s]+"
)


def scrub_sensitive_query(value: str) -> str:
    return _SENSITIVE_QUERY.sub(r"\1REDACTED", value)


class SensitiveQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        scrubbed = scrub_sensitive_query(rendered)
        if scrubbed != rendered:
            record.msg = scrubbed
            record.args = ()
        return True


def install_sensitive_query_filter() -> None:
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        logger = logging.getLogger(logger_name)
        if not any(isinstance(item, SensitiveQueryFilter) for item in logger.filters):
            logger.addFilter(SensitiveQueryFilter())
        for handler in logger.handlers:
            if not any(
                isinstance(item, SensitiveQueryFilter) for item in handler.filters
            ):
                handler.addFilter(SensitiveQueryFilter())
