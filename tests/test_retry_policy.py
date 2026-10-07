import httpx
import pytest

from ingestion.retry import RetryPolicy, classify_failure, run_with_retry


def _status_error(code: int):
    request = httpx.Request("GET", "https://example.test/job")
    response = httpx.Response(code, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_retry_classification():
    assert classify_failure(_status_error(429)) == (True, "HTTP_429", 429)
    assert classify_failure(_status_error(503)) == (True, "HTTP_503", 503)
    assert classify_failure(_status_error(404)) == (False, "HTTP_404", 404)


def test_retry_transient_then_success(monkeypatch):
    monkeypatch.setattr("ingestion.retry.time.sleep", lambda _: None)
    calls = {"n": 0}
    failures = []

    def operation():
        calls["n"] += 1
        if calls["n"] < 3:
            raise _status_error(503)
        return "ok"

    result, attempt = run_with_retry(
        operation,
        policy=RetryPolicy(max_attempts=3, base_delay_seconds=0),
        on_attempt_failure=lambda *args: failures.append(args),
    )
    assert result == "ok"
    assert attempt == 3
    assert len(failures) == 2
    assert all(item[2] is True for item in failures)


def test_terminal_failure_is_not_retried(monkeypatch):
    monkeypatch.setattr("ingestion.retry.time.sleep", lambda _: None)
    calls = {"n": 0}

    def operation():
        calls["n"] += 1
        raise _status_error(404)

    with pytest.raises(httpx.HTTPStatusError):
        run_with_retry(
            operation,
            policy=RetryPolicy(max_attempts=3, base_delay_seconds=0),
            on_attempt_failure=lambda *args: None,
        )
    assert calls["n"] == 1
