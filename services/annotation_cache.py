"""Cache annotation snapshots; explicitly optional failures can be retried separately."""
from copy import deepcopy
from threading import Lock
from time import monotonic


class AnnotationCache:
    def __init__(self, ttl=3600):
        self.ttl = ttl
        self.entries = {}
        self.lock = Lock()

    def get(self, key):
        with self.lock:
            now = monotonic()
            for expired in [k for k, (expires, _) in self.entries.items() if expires <= now]:
                del self.entries[expired]
            entry = self.entries.get(key)
            return deepcopy(entry[1]) if entry else None

    def put(self, key, result, *, optional_errors=()):
        if any(error_key[0] not in optional_errors for error_key in result["errors"]):
            return
        with self.lock:
            self.entries[key] = (monotonic() + self.ttl, deepcopy(result))

    def update(self, key, result):
        """Refresh supplemental results without extending the core data's expiry."""
        with self.lock:
            if key in self.entries:
                expires, _ = self.entries[key]
                self.entries[key] = (expires, deepcopy(result))
