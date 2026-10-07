from app.services.export_fingerprint import (
    export_fingerprint,
    normalize_contract_filters,
    normalize_invoice_filters,
)


def test_invoice_fingerprint_stable_and_ignores_key_order():
    a = normalize_invoice_filters(invoice_type=None, search="  foo ", status_filter="active")
    b = normalize_invoice_filters(search="foo", status_filter="active", invoice_type=None)
    assert a == b
    assert export_fingerprint(a) == export_fingerprint(b)
    assert a["resource_type"] == "invoice"
    assert a["search"] == "foo"


def test_invoice_and_contract_fingerprints_differ():
    inv = normalize_invoice_filters()
    con = normalize_contract_filters()
    assert export_fingerprint(inv) != export_fingerprint(con)


def test_contract_risk_level_in_fingerprint():
    hi = normalize_contract_filters(risk_level="high")
    all_ = normalize_contract_filters(risk_level=None)
    assert export_fingerprint(hi) != export_fingerprint(all_)
