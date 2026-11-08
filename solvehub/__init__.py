"""SolveHub - Python client for the SolveHub CAPTCHA API.

One REST endpoint for Cloudflare Turnstile / Interstitial, DataDome, Akamai,
PerimeterX (HUMAN), Imperva, AWS WAF, Alibaba Cloud CAPTCHA 2.0, Arkose
FunCaptcha and image-text OCR.

Docs: https://www.tiam.codes
License: MIT

    from solvehub import SolveHub

    client = SolveHub("sh_live_xxx")
    task = client.solve("turnstile", {
        "websiteURL": "https://example.com/login",
        "websiteKey": "0x4AAAAAAA_SITE_KEY",
    })
    print(task["solution"]["value"])

This module is deliberately dependency free: it is a single file you can also
drop next to your code instead of installing it.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

__version__ = "0.1.0"
__all__ = [
    "SolveHub",
    "SolveHubError",
    "TaskTimeout",
    "TaskFailed",
    "verify_webhook",
    "TASK_TYPES",
    "PENDING_STATUSES",
    "TERMINAL_STATUSES",
]

DEFAULT_BASE_URL = "https://api.tiam.codes"
DEFAULT_TIMEOUT = 30.0
DEFAULT_POLL_INTERVAL = 2.5

#: Challenge types accepted by POST /v1/tasks.
TASK_TYPES = (
    "turnstile",
    "interstitial",
    "datadome",
    "akamai",
    "perimeterx",
    "imperva",
    "aws_waf",
    "alibaba",
    "funcaptcha",
    "image",
)

QUEUED = "queued"
PROCESSING = "processing"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"
UNCERTAIN = "uncertain"

PENDING_STATUSES = (QUEUED, PROCESSING)
TERMINAL_STATUSES = (DONE, FAILED, CANCELLED)


class SolveHubError(Exception):
    """Any error returned by the API or by the network layer."""

    def __init__(self, message, status_code=None, payload=None, request_id=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}
        self.request_id = request_id

    def __str__(self):
        base = super().__str__()
        if self.status_code is not None:
            return "[%s] %s" % (self.status_code, base)
        return base


class TaskTimeout(SolveHubError):
    """The task never reached a terminal state inside the given timeout."""

    def __init__(self, task, timeout):
        super().__init__(
            "task %s still %r after %.0fs; it may still complete - keep polling "
            "with get_task() or cancel it" % (task.get("id"), task.get("status"), timeout)
        )
        self.task = task


class TaskFailed(SolveHubError):
    """The task finished without a usable solution."""

    def __init__(self, task):
        reason = task.get("error") or task.get("status")
        super().__init__("task %s ended as %r: %s" % (task.get("id"), task.get("status"), reason))
        self.task = task


def verify_webhook(raw_body, signature, secret):
    """Return True when an HMAC-SHA256 delivery signature matches.

    ``raw_body`` must be the exact bytes received (do not re-serialise the
    JSON first), ``signature`` the hex digest from the delivery header.
    """
    if isinstance(raw_body, str):
        raw_body = raw_body.encode("utf-8")
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, (signature or "").strip().lower())


class SolveHub:
    """Blocking client for the SolveHub API.

    :param api_key: console API key (``sh_live_...``).
    :param base_url: override for self-hosted or staging endpoints.
    :param timeout: per-request socket timeout in seconds.
    """

    def __init__(self, api_key, base_url=DEFAULT_BASE_URL, timeout=DEFAULT_TIMEOUT):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ HTTP
    def _request(self, method, path, body=None, headers=None, query=None):
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)

        data = None
        hdrs = {
            "Authorization": "Bearer " + self.api_key,
            "Accept": "application/json",
            "User-Agent": "solvehub-python/" + __version__,
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        if headers:
            hdrs.update(headers)

        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                payload = json.loads(raw) if raw else {}
                payload.setdefault("_status", resp.status)
                return payload
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload = json.loads(raw) if raw else {}
            except ValueError:
                payload = {"message": raw.decode("utf-8", "replace")}
            message = payload.get("message") or payload.get("error") or exc.reason
            raise SolveHubError(
                message,
                status_code=exc.code,
                payload=payload,
                request_id=payload.get("requestId"),
            ) from None
        except urllib.error.URLError as exc:
            raise SolveHubError("network error: %s" % (exc.reason,)) from None

    # ------------------------------------------------------------------ meta
    def prices(self):
        """Public price catalogue. No API key is charged for this call."""
        return self._request("GET", "/v1/prices")

    def balance(self):
        """Available and reserved balance."""
        return self._request("GET", "/v1/balance")

    # ------------------------------------------------------------------ tasks
    def create_task(self, task_type, task, proxy=None, idempotency_key=None):
        """Create a task. Returns the task as ``202 queued``.

        The price is frozen at creation time; it is only charged once the task
        completes, and refunded when it fails or is cancelled.
        """
        if task_type not in TASK_TYPES:
            raise ValueError("unknown task type %r; expected one of %s" % (task_type, ", ".join(TASK_TYPES)))
        body = {"type": task_type, "task": dict(task)}
        if proxy:
            body["proxy"] = proxy
        headers = {"Idempotency-Key": idempotency_key or uuid.uuid4().hex}
        return self._request("POST", "/v1/tasks", body=body, headers=headers)

    def get_task(self, task_id):
        """Status and, once finished, the solution for one task."""
        return self._request("GET", "/v1/tasks/" + urllib.parse.quote(str(task_id), safe=""))

    def list_tasks(self, limit=50):
        """Most recent tasks, newest first."""
        return self._request("GET", "/v1/tasks", query={"limit": limit})

    def cancel_task(self, task_id):
        """Cancel a queued task; the reserved amount is refunded."""
        return self._request("POST", "/v1/tasks/%s/cancel" % urllib.parse.quote(str(task_id), safe=""))

    def wait(self, task_id, timeout=300.0, interval=DEFAULT_POLL_INTERVAL):
        """Poll until the task reaches a terminal state and return it.

        ``uncertain`` (a challenge that could not be judged) is *not* treated
        as terminal: keep polling, it can still resolve. Raise :class:`TaskFailed`
        for failed / cancelled tasks and :class:`TaskTimeout` on timeout.
        """
        deadline = time.monotonic() + timeout
        delay = interval
        task = {}
        while True:
            task = self.get_task(task_id)
            status = task.get("status")
            if status == DONE:
                return task
            if status in (FAILED, CANCELLED):
                raise TaskFailed(task)
            if time.monotonic() >= deadline:
                raise TaskTimeout(task, timeout)
            time.sleep(min(delay, max(0.0, deadline - time.monotonic())))
            delay = min(delay * 1.5, 10.0)

    def solve(self, task_type, task, proxy=None, timeout=300.0, interval=DEFAULT_POLL_INTERVAL):
        """Create a task and wait for it in one call."""
        created = self.create_task(task_type, task, proxy=proxy)
        return self.wait(created["id"], timeout=timeout, interval=interval)

    # ------------------------------------------------------------------ webhook
    def set_webhook(self, url, secret=None):
        """Register an HTTPS callback URL. Deliveries are signed (HMAC-SHA256)."""
        body = {"url": url}
        if secret:
            body["secret"] = secret
        return self._request("PUT", "/v1/webhook", body=body)

    def webhook(self):
        """Current webhook configuration."""
        return self._request("GET", "/v1/webhook")

    def webhook_deliveries(self, limit=50):
        """Recent delivery attempts, useful when debugging a callback."""
        return self._request("GET", "/v1/webhook/deliveries", query={"limit": limit})

    def __repr__(self):
        return "SolveHub(base_url=%r)" % (self.base_url,)
