import logging

from app.core.log_safety import SensitiveQueryFilter, scrub_sensitive_query


def test_sensitive_websocket_query_values_are_scrubbed() -> None:
    original = (
        "WebSocket /ws/v1/overlay/session?key=overlay-secret&x=1 "
        "/ws/v1/dashboard/session?ticket=dashboard-secret"
    )
    scrubbed = scrub_sensitive_query(original)
    assert "overlay-secret" not in scrubbed
    assert "dashboard-secret" not in scrubbed
    assert "key=REDACTED&x=1" in scrubbed
    assert "ticket=REDACTED" in scrubbed


def test_oauth_code_and_state_are_scrubbed_from_access_logs() -> None:
    original = "/api/v1/youtube/oauth/callback?state=csrf-secret&code=auth-code"
    scrubbed = scrub_sensitive_query(original)
    assert "csrf-secret" not in scrubbed
    assert "auth-code" not in scrubbed
    assert "state=REDACTED&code=REDACTED" in scrubbed


def test_logging_filter_scrubs_formatted_arguments() -> None:
    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        "WebSocket %s",
        ("/overlay/id?key=secret",),
        None,
    )
    assert SensitiveQueryFilter().filter(record)
    assert record.getMessage() == "WebSocket /overlay/id?key=REDACTED"
