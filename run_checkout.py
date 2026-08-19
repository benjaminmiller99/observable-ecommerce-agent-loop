"""Explanatory entry point: run one successful checkout and print its update."""

from infrai import InfraiClient
from order_agent import OrderRequest, process_order
from order_service import EmailReceipts, Warehouse


def main() -> None:
    update = process_order(
        OrderRequest(
            order_id="ord-1042",
            customer_id="cus-81",
            total_cents=12900,
            shipping_address="18 Market Street",
        ),
        Warehouse(),
        EmailReceipts(),
        InfraiClient(),
    )
    print(update)


if __name__ == "__main__":
    main()
