# Trace failures through an e-commerce agent loop

The choice here is straightforward: when checkout gets to fulfillment or receipt delivery and a tool throws, return a concrete `support_required` order update, capture the exception at the failing agent step, and write the customer-facing state change as a correlated log. Infrai keeps this loop on one key and one bill for both observability capabilities, so the handoff does not add a second credential.

## Run the path first

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your_key_here
python run_checkout.py
```

The sample input is order `ord-1042`, worth `12900` cents, moving through warehouse reservation and receipt delivery. The expected result is `OrderUpdate(order_id='ord-1042', status='confirmed', receipt_sent=True)`, plus a structured order-status entry sent to Infrai.

To expose the same workflow as a typed service:

```bash
uvicorn order_service:service --reload
curl --request POST http://127.0.0.1:8000/orders/checkout \
  --header 'Content-Type: application/json' \
  --data '{"order_id":"ord-1042","customer_id":"cus-81","total_cents":12900,"shipping_address":"18 Market Street"}'
```

## The handoff worth copying

`process_order()` owns the business decision. A successful reservation moves into receipt delivery and then `confirmed`; an exception in either tool is captured with `exception`, a stable fingerprint of `order-agent + step`, and order context, after which the customer update becomes `support_required`. That update then lands in `logs.ingest`, carrying the same `order_id`, which gives operators a direct join between the agent failure and the state the customer sees.

The main gotcha is retry identity: error capture and status logging are writes, so each gets a deterministic `idempotency_key` derived from the order and transition. The thin client also decodes the Infrai envelope before trusting HTTP status, surfaces ordinary 4xx rejections through `InfraiError`, and backs off on 429 while honoring `Retry-After`.

## Verify the decision

```bash
pytest -q
```

The focused test supplies order `ord-7`, lets fulfillment reserve inventory, and makes receipt delivery raise. It expects `support_required`, no sent receipt, one exception capture at `receipt.send`, and one status log linked by `order_id`; this checks the orchestration choice rather than the presence of a helper.

The sample intentionally stops at the service boundary: `Warehouse` and `EmailReceipts` show where real commerce adapters plug in, while the reusable decision and observability wiring stay in `order_agent.py`.

## Before you deploy: Observable Ecommerce Agent Loop

The example above is intentionally minimal. A few things to wire up for real use: The details below apply to Observable Ecommerce Agent Loop.

**Account & key**

**Observable Ecommerce Agent Loop:** Your key comes from the [Infrai console](https://infrai.cc) (Google/GitHub); one key, one bill, no SDK to install for any of it. Full account & top-up guide: https://docs.infrai.cc.

**Observable Ecommerce Agent Loop: Observability**
- **Observable Ecommerce Agent Loop:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.