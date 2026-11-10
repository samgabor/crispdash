"""Request timings isolated to each concurrent annotation lookup."""
from contextlib import contextmanager
from contextvars import ContextVar
import time
from urllib.parse import urlsplit

import requests


_request_timings = ContextVar("request_timings", default=None)


@contextmanager
def capture_request_timings(records):
    token = _request_timings.set(records)
    try:
        yield
    finally:
        _request_timings.reset(token)


def timed_get(provider, url, **kwargs):
    """Measure dispatch through complete response-body receipt, even on errors.

    Call after request pacing. Do not record full URLs or arbitrary parameters:
    those may contain API keys, email addresses, or other credentials.
    """
    records = _request_timings.get()
    started = time.perf_counter()
    status = "Failed"
    try:
        response = requests.get(url, **kwargs)
        status = f"HTTP {response.status_code}"
        return response
    except Exception as error:
        status = type(error).__name__
        raise
    finally:
        elapsed = time.perf_counter() - started
        if records is not None:
            params = kwargs.get("params") or {}
            # These fields identify the public annotation query without secrets.
            query = "; ".join(
                f"{key}={params[key]}"
                for key in ("db", "id", "term", "feature", "retstart")
                if key in params
            )
            records.append({
                "provider": provider,
                "endpoint": urlsplit(url).path,
                "query": query,
                "elapsed_seconds": elapsed,
                "status": status,
            })


def timed_lookup(function, *args, **kwargs):
    """Return a value/error and timings without mutating coordinator state."""
    records = []
    started = time.perf_counter()
    value, error = None, None
    with capture_request_timings(records):
        try:
            value = function(*args, **kwargs)
        except Exception as exception:
            error = str(exception)
    return {
        "value": value,
        "error": error,
        "elapsed_seconds": time.perf_counter() - started,
        "requests": records,
    }
