# solvehub-python

Python client for the [SolveHub](https://www.tiam.codes) CAPTCHA API — **one REST endpoint** for
Cloudflare Turnstile, Cloudflare Interstitial, DataDome, Akamai, PerimeterX / HUMAN, Imperva,
AWS WAF, Alibaba Cloud CAPTCHA 2.0, Arkose FunCaptcha and image-text OCR.

- **Zero dependencies.** Standard library only (`urllib`), Python 3.8+.
- **Pay per solved task.** Each task's price is frozen at creation and charged only when it completes;
  failed or cancelled tasks are refunded automatically.
- **Idempotent.** Every create request carries an `Idempotency-Key`, so a network timeout never turns
  into a duplicate charge.
- **Proxy aware.** Cookie-based challenges (DataDome, Akamai, PerimeterX, Imperva, AWS WAF) accept your
  own proxy and return cookies you reuse **with the same IP and User-Agent**.

## Install

```bash
pip install "git+https://github.com/seencxy/solvehub-python.git"
```

Or just drop [`solvehub/__init__.py`](solvehub/__init__.py) next to your code — it is a single file.

## Quick start

```python
from solvehub import SolveHub

client = SolveHub("sh_live_xxx")          # your API key

task = client.solve("turnstile", {
"websiteURL": "https://example.com/login",
"websiteKey": "0x4AAAAAAA_SITE_KEY",
})
print(task["solution"]["value"])           # the token you post back to the site
```

`solve()` creates the task, polls every 2–3 seconds and returns the finished task. Use
`create_task()` + `wait()` if you would rather drive the polling yourself.

### Cookie-based challenges

```python
task = client.solve(
"datadome",
{"websiteURL": "https://example.com", "captchaUrl": "https://example.com/captcha"},
proxy="http://user:pass@host:port",
)

cookies = task["solution"]["cookies"]       # e.g. {"datadome": "..."}
user_agent = task["solution"]["userAgent"]

# reuse BOTH, from the same IP, in your scraping session
```

### Webhooks instead of polling

```python
client.set_webhook("https://your-app.example/solvehub", secret="whsec_...")
```

Deliveries are signed with **HMAC-SHA256** over the raw body, so you can verify them without trusting
the network. `client.webhook()` returns the current configuration and
`client.webhook_deliveries()` lists recent attempts.

## Async / concurrency

Every call is a plain blocking HTTPS request, so any thread or process pool works:

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=8) as pool:
    results = list(pool.map(lambda url: client.solve("turnstile", {
        "websiteURL": url, "websiteKey": "0x4AAAAAAA_SITE_KEY"}), urls))
```

## API surface

| Method | Endpoint | Notes |
| --- | --- | --- |
| `prices()` | `GET /v1/prices` | public price catalogue, no login needed |
| `create_task(type, task, proxy=...)` | `POST /v1/tasks` | returns `202` with `queued` |
| `get_task(task_id)` | `GET /v1/tasks/{id}` | status + solution |
| `list_tasks(limit=50)` | `GET /v1/tasks` | most recent tasks |
| `cancel_task(task_id)` | `POST /v1/tasks/{id}/cancel` | refunds the reserved amount |
| `balance()` | `GET /v1/balance` | available and reserved balance |
| `set_webhook(url, secret=...)` | `PUT /v1/webhook` | HTTPS callback |

Task statuses: `queued` → `dispatching` → `processing` → `completed`, or `failed` / `cancelled`.
`uncertain` is **not** final — keep polling the same `taskId` instead of creating a new task.

## Errors

```python
from solvehub import SolveHub, SolveHubError, TaskTimeout

try:
    task = client.solve("turnstile", {...}, timeout=120)
except TaskTimeout as exc:
    print("still running:", exc.task_id, exc.last["status"])
except SolveHubError as exc:
    print(exc.status, exc.code, exc.trace_id)   # include trace_id in support requests
```

## Pricing

USD per 1,000 **successful** tasks — Turnstile and OCR from $0.20, Interstitial and Aliyun $0.40,
Akamai $0.80, PerimeterX and AWS WAF $1.00, DataDome $1.20, Imperva $1.60, FunCaptcha $2.00.
Live prices: `client.prices()`. Linking your Telegram account to the console gives $0.10 of trial credit.

## Links

- Website and docs: <https://www.tiam.codes>
- API reference: <https://www.tiam.codes/docs>
- JavaScript / TypeScript client: [solvehub-node](https://github.com/seencxy/solvehub-node)
- Issues: <https://github.com/seencxy/solvehub-python/issues>
- Cookie glossary: <https://seencxy.github.io/glossary/> - what `_abck`, `reese84`, `_px3` and `cf_clearance` each contain, and why they expire (English, 日本語, Bahasa Indonesia)

## Authorized use only

SolveHub is meant for automated testing of systems **you own or are authorized to access**, and for
CAPTCHA research. Do not use it to bypass protections on sites you have no permission to test. All site
keys, URLs and proxies above are placeholders.

## License

MIT
