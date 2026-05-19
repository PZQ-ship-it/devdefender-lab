import pytest

from payment_api import Payment, capture_payment


def test_capture_rejects_non_positive_amounts_before_capturing() -> None:
    with pytest.raises(ValueError, match="amount must be positive"):
        capture_payment(Payment(account_id="acct_123", amount_cents=0))


def test_capture_rejects_missing_account_before_capturing() -> None:
    with pytest.raises(ValueError, match="account_id is required"):
        capture_payment(Payment(account_id="", amount_cents=100))


def test_capture_keeps_valid_amount_in_success_response() -> None:
    response = capture_payment(Payment(account_id="acct_123", amount_cents=100))

    assert response["status"] == "captured"
    assert response["amount_cents"] == 100
    assert response["authorization"]
