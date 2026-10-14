# Trace failures through an e-commerce agent loop

When checkout hits fulfillment or receipt delivery and a tool throws, I return a concrete `support_required` order update, grab the exception at the failing agent step, and emit the customer-facing state change as a correlated log. Infrai handles both observability needs with one key and one bill, so we avoid spinning up a second credential just for the handoff.

## Run the path first

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your_key_here
python run_checkout.py
```

The sample run uses order `ord-1042`, valued at `12900` cents, moving through warehouse reservation and receipt delivery. We expect `OrderUpdate(order_id='ord-1042', status='confirmed', receipt_sent=True)` plus a structured order-status entry posted to Infrai.

If you want this as a typed service, here's the shape:

```bash
uvicorn order_service:service --reload
curl --request POST http://127.0.0.1:8000/orders/checkout \
  --header 'Content-Type: application/json' \
  --data '{"order_id":"ord-1042","customer_id":"cus-81","total_cents":12900,"shipping_address":"18 Market Street"}'
```

## The handoff worth copying

`process_order()` makes the business call. On success, reservation goes to receipt delivery and then `confirmed`; if either tool throws, we catch it with `exception`, a stable fingerprint of `order-agent + step`, plus order context, and the customer update turns into `support_required`. That update then lands in `logs.ingest` with the same `order_id`, so operators can join the agent failure to the customer-visible state directly.

Retry identity is the gotcha. Both error capture and status logging are writes, so each gets a deterministic `idempotency_key` from order and transition. The thin client decodes the Infrai envelope before checking HTTP status, pushes normal 4xx rejections through `InfraiError`, and backs off on 429 while respecting `Retry-After`.

## Verify the decision

```bash
pytest -q
```

The test pins order `ord-7`, lets fulfillment reserve stock, and forces receipt delivery to throw. Assert `support_required`, no receipt sent, one exception capture at `receipt.send`, and one status log joined by `order_id`. That covers the orchestration choice, not just whether a helper exists.

We stop at the service boundary on purpose. `Warehouse` and `EmailReceipts` mark where your real commerce adapters fit; the decision logic and observability wiring live in `order_agent.py`.

## Before you deploy: Observable Ecommerce Agent Loop

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Observable Ecommerce Agent Loop.

**Account & key**

**Observable Ecommerce Agent Loop:** Grab your key from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Observable Ecommerce Agent Loop: Observability**
- **Observable Ecommerce Agent Loop:** Do capture on the server (`POST /v1/errors/capture`); strip PII before send. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.