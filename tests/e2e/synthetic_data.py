"""Deterministic synthetic event generators for the CUJ1->CUJ2 E2E suite.

Every generator returns (spec_md_text, events, expected) where `expected` is
ground truth computed independently in Python -- never re-derived from the
SQL the tests assert against. Field shapes mirror
`problem statment/specs/01_express_checkout/events.ndjson` (event, id,
timestamp, device_type, os, geoip_country_code, user_id, application_id,
destination, plus stage-specific fields like shown_amount/otp_success/
nested payment.amount).
"""
from __future__ import annotations

DEVICES = ["ios", "android", "Desktop", "web-user-b2c"]
COUNTRIES = ["IN", "SG", "AE", "US"]

SPEC_MD_TEMPLATE = """# Feature spec — E2E Synthetic {title}

## What it does
Synthetic data generated for the CUJ1->CUJ2 end-to-end test suite. Not a real
feature spec -- do not treat as production instrumentation.

## User actions (raw events emitted)
- `express_checkout_shown`
- `express_checkout_selected`
- `otp_entered`
- `express_payment_confirmed`
"""


def happy_path(num_applications: int = 50) -> tuple[str, list[dict], dict]:
    """`num_applications` funnels; every 5th applicant fails OTP and never
    confirms. Returns the exact confirmed count and SUM(payment_amount)
    computed independently of any SQL, for parity assertions."""
    events: list[dict] = []
    confirmed_count = 0
    confirmed_sum = 0.0
    sample_application: dict | None = None

    for i in range(num_applications):
        device = DEVICES[i % len(DEVICES)]
        country = COUNTRIES[i % len(COUNTRIES)]
        user_id = f"e2e_user_{i:04d}"
        application_id = f"e2e_app_{i:04d}"
        shown_amount = round(1000.0 + i * 7.5, 2)
        currency = "INR"
        otp_success = i % 5 != 0
        minute = i

        shown = {
            "event": "express_checkout_shown",
            "id": f"e2e_{i:04d}_shown",
            "timestamp": f"2026-06-01T00:{minute:02d}:00.000",
            "device_type": device,
            "os": device,
            "geoip_country_code": country,
            "user_id": user_id,
            "application_id": application_id,
            "destination": country,
            "eligible": True,
            "shown_amount": shown_amount,
            "currency": currency,
        }
        selected = {
            "event": "express_checkout_selected",
            "id": f"e2e_{i:04d}_selected",
            "timestamp": f"2026-06-01T00:{minute:02d}:30.000",
            "device_type": device,
            "os": device,
            "geoip_country_code": country,
            "user_id": user_id,
            "application_id": application_id,
            "destination": country,
            "saved_method_type": "card" if i % 2 == 0 else "upi",
        }
        otp = {
            "event": "otp_entered",
            "id": f"e2e_{i:04d}_otp",
            "timestamp": f"2026-06-01T00:{minute:02d}:45.000",
            "device_type": device,
            "os": device,
            "geoip_country_code": country,
            "user_id": user_id,
            "application_id": application_id,
            "destination": country,
            "otp_attempts": 1,
            "otp_success": otp_success,
        }
        events.extend([shown, selected, otp])

        if otp_success:
            confirmed = {
                "event": "express_payment_confirmed",
                "id": f"e2e_{i:04d}_confirmed",
                "timestamp": f"2026-06-01T00:{minute:02d}:50.000",
                "device_type": device,
                "os": device,
                "geoip_country_code": country,
                "user_id": user_id,
                "application_id": application_id,
                "destination": country,
                "payment": {
                    "amount": shown_amount,
                    "currency": currency,
                    "latency_ms": 2000 + i * 3,
                },
            }
            events.append(confirmed)
            confirmed_count += 1
            confirmed_sum = round(confirmed_sum + shown_amount, 2)

        if i == 0:
            sample_application = {
                "application_id": application_id,
                "user_id": user_id,
                "device_type": device,
                "shown_amount": shown_amount,
            }

    expected = {
        "total_events": len(events),
        "confirmed_count": confirmed_count,
        "confirmed_sum_payment_amount": confirmed_sum,
        "sample_application": sample_application,
    }
    return SPEC_MD_TEMPLATE.format(title="Happy Path"), events, expected


def boundary_cases() -> tuple[str, list[dict], dict]:
    """One event missing an optional numeric field entirely (exercises
    Nullable), one with a unicode + SQL-lookalike string (exercises the safe
    JSONEachRow insert path -- no manual SQL string interpolation), one with
    a long string, one with an unrounded float, and two sitting exactly on a
    January/February toYYYYMM() partition boundary."""
    long_city = "x" * 500
    unicode_city = "北京 — 'quoted'; DROP TABLE nope; --"
    precise_amount = 0.1 + 0.2  # 0.30000000000000004

    events = [
        {  # no shown_amount / currency at all -> exercises Nullable(Float64)
            "event": "express_checkout_shown",
            "id": "e2e_boundary_null_amount",
            "timestamp": "2026-06-01T00:00:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_boundary_user_1",
            "application_id": "e2e_boundary_app_1",
            "destination": "IN",
            "eligible": True,
        },
        {
            "event": "express_checkout_shown",
            "id": "e2e_boundary_unicode",
            "timestamp": "2026-06-01T00:01:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "CN",
            "city": unicode_city,
            "user_id": "e2e_boundary_user_2",
            "application_id": "e2e_boundary_app_2",
            "destination": "CN",
            "eligible": True,
            "shown_amount": 100.0,
            "currency": "CNY",
        },
        {
            "event": "express_checkout_shown",
            "id": "e2e_boundary_long_string",
            "timestamp": "2026-06-01T00:02:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "city": long_city,
            "user_id": "e2e_boundary_user_3",
            "application_id": "e2e_boundary_app_3",
            "destination": "IN",
            "eligible": True,
            "shown_amount": 100.0,
            "currency": "INR",
        },
        {
            "event": "express_payment_confirmed",
            "id": "e2e_boundary_float_precision",
            "timestamp": "2026-06-01T00:03:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_boundary_user_4",
            "application_id": "e2e_boundary_app_4",
            "destination": "IN",
            "payment": {"amount": precise_amount, "currency": "INR", "latency_ms": 1000},
        },
        {  # last moment of the January partition
            "event": "express_checkout_shown",
            "id": "e2e_boundary_jan_edge",
            "timestamp": "2026-01-31T23:59:59.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_boundary_user_5",
            "application_id": "e2e_boundary_app_5",
            "destination": "IN",
            "eligible": True,
            "shown_amount": 50.0,
            "currency": "INR",
        },
        {  # first moment of the February partition
            "event": "express_checkout_shown",
            "id": "e2e_boundary_feb_edge",
            "timestamp": "2026-02-01T00:00:00.000",
            "device_type": "ios",
            "os": "iOS",
            "geoip_country_code": "IN",
            "user_id": "e2e_boundary_user_6",
            "application_id": "e2e_boundary_app_6",
            "destination": "IN",
            "eligible": True,
            "shown_amount": 50.0,
            "currency": "INR",
        },
    ]

    expected = {
        "total_events": len(events),
        "unicode_city": unicode_city,
        "long_city_length": len(long_city),
        "precise_amount": precise_amount,
        "jan_partition": "202601",
        "feb_partition": "202602",
    }
    return SPEC_MD_TEMPLATE.format(title="Boundary Cases"), events, expected
