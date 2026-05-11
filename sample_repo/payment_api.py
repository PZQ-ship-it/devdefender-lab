import hashlib
from dataclasses import dataclass


@dataclass
class Payment:
    account_id: str
    amount_cents: int


def hash_account(account_id: str) -> str:
    return hashlib.sha256(account_id.encode("utf-8")).hexdigest()


def validate_payment(payment: Payment) -> None:
    if payment.amount_cents <= 0:
        raise ValueError("amount must be positive")
    if not payment.account_id:
        raise ValueError("account_id is required")


def authorize_payment(payment: Payment) -> str:
    validate_payment(payment)
    return hash_account(payment.account_id)


def capture_payment(payment: Payment) -> dict[str, str | int]:
    authorization = authorize_payment(payment)
    return {
        "authorization": authorization,
        "amount_cents": payment.amount_cents,
        "status": "captured",
    }
