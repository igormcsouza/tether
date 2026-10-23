"""HTTP client used by every service call."""
import json
import urllib.request

from svc.config import BASE_URL, TIMEOUT


def get(path):
    with urllib.request.urlopen(BASE_URL + path, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())


def post(path, payload):
    req = urllib.request.Request(
        BASE_URL + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read())
