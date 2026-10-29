"""Retry helper."""
import time


def retry(fn, attempts=3, delay=1):
    for i in range(attempts):
        try:
            return fn()
        except Exception:
            time.sleep(delay)
    return None
