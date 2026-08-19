from types import SimpleNamespace
from unittest.mock import Mock

from order_agent import OrderRequest, process_order


def test_receipt_failure_becomes_support_update_and_two_linkable_signals() -> None:
    fulfillment = Mock()
    fulfillment.reserve.return_value = "res-7"
    receipts = Mock()
    receipts.send.side_effect = ValueError("mailbox rejected receipt")
    capture = Mock()
    ingest = Mock()
    observer = SimpleNamespace(
        errors=SimpleNamespace(capture=capture), logs=SimpleNamespace(ingest=ingest)
    )
    order = OrderRequest("ord-7", "cus-3", 4200, "7 Pine Road")

    result = process_order(order, fulfillment, receipts, observer)

    assert result.status == "support_required"
    assert result.receipt_sent is False
    capture_payload = capture.call_args.kwargs
    log_payload = ingest.call_args.kwargs
    assert capture_payload["context"]["order_id"] == "ord-7"
    assert capture_payload["context"]["agent_step"] == "receipt.send"
    assert capture_payload["exception"].startswith("Traceback")
    assert log_payload["entries"][0]["order_id"] == "ord-7"
    assert log_payload["entries"][0]["status"] == "support_required"
    assert capture_payload["idempotency_key"] == "order:ord-7:receipt.send:error"
    receipts.send.assert_called_once_with(order, "res-7")
