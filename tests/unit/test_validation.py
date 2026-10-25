from decimal import Decimal

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.schemas.record import RecordCreateRequest, RecordFilterParams
from app.services.record_service import compute_risk_score, determine_initial_status


def test_valid_record_payload():
    payload = {
        "transaction_id": "txn_001",
        "account_id": "acc_001",
        "amount": 150.75,
        "currency": "usd",
        "category": "payment",
        "merchant_name": "Cloud Host Provider",
    }
    record = RecordCreateRequest.model_validate(payload)
    assert record.currency == "USD"
    assert record.amount == Decimal("150.75")
    assert record.category == "payment"


def test_invalid_currency_code():
    payload = {
        "transaction_id": "txn_001",
        "account_id": "acc_001",
        "amount": 100.0,
        "currency": "123",
        "category": "payment",
        "merchant_name": "Store",
    }
    with pytest.raises(PydanticValidationError) as exc:
        RecordCreateRequest.model_validate(payload)
    assert "Currency must be a valid 3-letter ISO code" in str(exc.value)


def test_invalid_category():
    payload = {
        "transaction_id": "txn_001",
        "account_id": "acc_001",
        "amount": 100.0,
        "currency": "USD",
        "category": "unsupported_action",
        "merchant_name": "Store",
    }
    with pytest.raises(PydanticValidationError) as exc:
        RecordCreateRequest.model_validate(payload)
    assert "Category must be one of" in str(exc.value)


def test_non_positive_amount():
    payload = {
        "transaction_id": "txn_001",
        "account_id": "acc_001",
        "amount": 0.00,
        "currency": "USD",
        "category": "payment",
        "merchant_name": "Store",
    }
    with pytest.raises(PydanticValidationError):
        RecordCreateRequest.model_validate(payload)


def test_risk_score_calculation_heuristics():
    # Base risk for modest payment
    base_risk = compute_risk_score(Decimal("50.00"), "payment")
    assert base_risk == 0.05
    assert determine_initial_status(base_risk) == "cleared"

    # High amount transfer
    large_transfer_risk = compute_risk_score(Decimal("25000.00"), "transfer")
    # 0.05 + 0.30 + 0.10 = 0.45
    assert large_transfer_risk == 0.45
    assert determine_initial_status(large_transfer_risk) == "cleared"

    # Very large withdrawal with VPN
    critical_risk = compute_risk_score(
        Decimal("75000.00"),
        "withdrawal",
        {"is_vpn": True, "device_changed": True},
    )
    # 0.05 + 0.50 (amount >= 50k) + 0.10 (withdrawal) + 0.25 (vpn) + 0.15 (device) = 1.05 -> clamped to 1.0
    assert critical_risk == 1.0
    assert determine_initial_status(critical_risk) == "rejected"


def test_record_filter_allowlist():
    valid = RecordFilterParams(sort_by="occurred_at", sort_order="desc")
    assert valid.sort_by == "occurred_at"

    with pytest.raises(PydanticValidationError, match="sort_by must be one of"):
        RecordFilterParams(sort_by="malicious_sql_injection_attempt")
