"""Typed HTTP boundary for the order agent workflow."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from infrai import InfraiClient, InfraiError
from order_agent import OrderRequest, process_order

service = FastAPI(title="Observable order agent")


class CheckoutRequest(BaseModel):
    order_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    total_cents: int = Field(gt=0)
    shipping_address: str = Field(min_length=1)


class CheckoutResult(BaseModel):
    order_id: str
    status: str
    receipt_sent: bool


class Warehouse:
    def reserve(self, order: OrderRequest) -> str:
        return f"reservation-{order.order_id}"


class EmailReceipts:
    def send(self, order: OrderRequest, reservation_id: str) -> None:
        print(f"receipt sent for {order.order_id} using {reservation_id}")


@service.post("/orders/checkout", response_model=CheckoutResult)
def checkout(body: CheckoutRequest) -> CheckoutResult:
    try:
        update = process_order(
            OrderRequest(**body.model_dump()), Warehouse(), EmailReceipts(), InfraiClient()
        )
    except InfraiError as exc:
        status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(status_code=status, detail=exc.detail) from exc
    return CheckoutResult(**update.__dict__)
