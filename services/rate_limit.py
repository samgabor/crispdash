"""Shared request pacing for concurrent REST callers in this app process."""
from threading import Lock
import time


class RequestRateLimiter:
    def __init__(self, requests_per_second, *, clock=None, sleep=None):
        self.interval = 1.0 / requests_per_second + 0.001
        self.clock = clock or time.monotonic
        self.sleep = sleep or time.sleep
        self.lock = Lock()
        self.next_request = 0.0

    def wait(self):
        # Only starting requests is serialized; network responses can overlap.
        with self.lock:
            delay = self.next_request - self.clock()
            if delay > 0:
                self.sleep(delay)
            self.next_request = self.clock() + self.interval
