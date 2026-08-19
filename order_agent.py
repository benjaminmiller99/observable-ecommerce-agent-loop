"""Checkout-to-receipt agent loop with an observable failure handoff."""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Protocol


class OrderObserver(Protocol):
    errors: object
    logs: object


@dataclass(frozen=True)
class OrderRequest:
    order_id: str
    customer_id: str
    total_cents: int
    shipping_address: str


@dataclass(frozen=True)
class OrderUpdate:
    order_id: str
    status: str
    receipt_sent: bool


class FulfillmentGateway(Protocol):
    def reserve(self, order: OrderRequest) -> str: ...


class ReceiptSender(Protocol):
    def send(self, order: OrderRequest, reservation_id: str) -> None: ...


def process_order(
    order: OrderRequest,
    fulfillment: FulfillmentGateway,
    receipts: ReceiptSender,
    observer: OrderObserver,
) -> OrderUpdate:
    """Run checkout handoffs and turn an agent-step exception into an order update."""
    step = "fulfillment.reserve"
    try:
        reservation_id = fulfillment.reserve(order)
        step = "receipt.send"
        receipts.send(order, reservation_id)
        update = OrderUpdate(order.order_id, "confirmed", True)
    except Exception as exc:
        correlation_id = f"order:{order.order_id}:{step}"
        # Copyable call shape: infrai.errors.capture(...)
        observer.errors.capture(
            title=f"Order agent failed at {step}",
            message=f"{type(exc).__name__}: {exc}",
            level="error",
            fingerprint=["order-agent", step],
            exception=traceback.format_exc(),
            context={
                "order_id": order.order_id,
                "customer_id": order.customer_id,
                "agent_step": step,
                "correlation_id": correlation_id,
            },
            idempotency_key=f"{correlation_id}:error",
        )
        update = OrderUpdate(order.order_id, "support_required", False)

    observer.logs.ingest(
        entries=[
            {
                "message": "customer order status updated",
                "level": "info",
                "order_id": update.order_id,
                "status": update.status,
                "receipt_sent": update.receipt_sent,
            }
        ],
        idempotency_key=f"order:{order.order_id}:status:{update.status}",
    )
    return update
