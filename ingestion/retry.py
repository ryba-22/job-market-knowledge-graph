from __future__ import annotations

from dataclasses import dataclass
import time
from typing import Callable, TypeVar

import httpx


T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.5

    def delay_for(self, attempt_no: int) -> float:
        return self.base_delay_seconds * (2 ** (attempt_no - 1))


def classify_failure(exc: Exception) -> tuple[bool, str, int | None]:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429 or 500 <= status <= 599:
            return True, f"HTTP_{status}", status
        return False, f"HTTP_{status}", status
    if isinstance(exc, (httpx.TimeoutException, httpx.NetworkError)):
        return True, type(exc).__name__, None
    return False, type(exc).__name__, None


def run_with_retry(
    fn: Callable[[], T],
    *,
    policy: RetryPolicy,
    on_attempt_failure: Callable[[int, Exception, bool, str, int | None], None],
) -> tuple[T, int]:
    last_exc = None
    for attempt_no in range(1, policy.max_attempts + 1):
        try:
            return fn(), attempt_no
        except Exception as exc:
            last_exc = exc
            retryable, failure_type, status = classify_failure(exc)
            will_retry = retryable and attempt_no < policy.max_attempts
            on_attempt_failure(attempt_no, exc, will_retry, failure_type, status)
            if not will_retry:
                raise
            time.sleep(policy.delay_for(attempt_no))
    assert last_exc is not None
    raise last_exc
