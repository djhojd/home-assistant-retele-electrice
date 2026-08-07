"""Tests for ReteleElectriceApi parsing helpers."""
from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import pytest

from custom_components.retele_electrice.api import (
    ReteleElectriceApi,
    _default_date_range,
    _parse_pod_info_response,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_pod_info_response_returns_normalized_dict():
    """Captured response parses into the expected snake_case dict."""
    raw = (FIXTURE_DIR / "pod_info_RO005EXXXXXXXXX.json").read_text(encoding="utf-8")
    result = _parse_pod_info_response(raw)

    # No Salesforce metadata leaked
    assert isinstance(result, dict)
    assert not any(k.endswith("_type_info") for k in result)
    assert "apex_schema_type_info" not in result
    assert "field_order_type_info" not in result
    assert "Contor" not in result, "Contor array should be flattened with meter_ prefix"

    # Top-level fields
    assert result["POD"] == "RO005EXXXXXXXXX"
    assert result["nume_client"] == "EXAMPLE CUSTOMER"
    assert result["cui"] == "00000000"
    assert result["kw_aprobata"] == pytest.approx(6.0)
    assert result["kw_evacuata"] is None  # was JSON null
    assert result["furnizor"] == "EXAMPLE POWER & GAS S.A."  # &amp; decoded
    assert result["furnizor_pre"] == "EXAMPLE PREVIOUS S.A."
    assert result["u_delimitare"] == "JT"
    assert result["activ"] == "D"
    assert result["activ_furnizor_la"] == "2020-01-01"
    assert result["adresa_client"].startswith("STRADA")
    assert result["adresa_locons"].startswith("STRADA")
    assert result["atr_number"] == "000000"
    assert result["atr_date"] == "2020-01-01"
    assert result["deconectat"] is None  # JSON null
    assert result["racordare"] is None  # was " - ", normalized
    assert result["corectii"] is None   # was "-", normalized

    # Meter fields flattened from Contor[0]
    assert result["meter_seria"] == "000000000000000"
    assert result["meter_marca"] == "EXAMPLE-METER : 5/60A, 230 V"
    assert result["meter_det_tip"] == "CONTOR_ELECTRONIC"
    assert result["meter_data_montare"] == "2020-01-01"
    assert result["meter_precizie"] == "2"  # NOT numerically coerced
    assert result["meter_constanta"] == "1.0"  # NOT numerically coerced

    # Meter section's _type_info keys also stripped
    assert not any(k.endswith("_type_info") for k in result if k.startswith("meter_"))


def test_default_date_range_early_in_month_uses_lookback_buffer():
    """Day 2 of month → buffer wins, start = today − 14 days."""
    start, end = _default_date_range(end_date=date(2026, 5, 2))
    assert end == date(2026, 5, 2)
    assert start == date(2026, 4, 18)


def test_default_date_range_late_in_month_uses_first_of_month():
    """Day 20 of month → first-of-month wins, buffer doesn't extend further."""
    start, end = _default_date_range(end_date=date(2026, 5, 20))
    assert end == date(2026, 5, 20)
    assert start == date(2026, 5, 1)


def test_default_date_range_at_day_15_picks_first_of_month():
    """Day 15 (boundary): both candidates yield May 1; first-of-month wins."""
    start, end = _default_date_range(end_date=date(2026, 5, 15))
    assert end == date(2026, 5, 15)
    assert start == date(2026, 5, 1)


async def test_login_serializes_concurrent_calls_for_the_same_email(monkeypatch):
    """Two PODs sharing a portal account must not send concurrent login
    POSTs. Confirmed live: two coordinators on the same account raced their
    first-refresh logins 3ms apart and both got a false "invalid
    credentials" error from the portal's account-scoped Salesforce session,
    even though the password was correct. The per-email lock in `login`
    must force one call to fully finish before the other starts."""
    order: list[str] = []

    async def fake_login_locked(self, pod):
        order.append(f"{pod}:start")
        await asyncio.sleep(0.01)
        order.append(f"{pod}:end")
        return True

    monkeypatch.setattr(ReteleElectriceApi, "_login_locked", fake_login_locked)

    api_a = ReteleElectriceApi("shared@example.com", "pw")
    api_b = ReteleElectriceApi("shared@example.com", "pw")

    await asyncio.gather(api_a.login("PODA"), api_b.login("PODB"))

    first_pod = order[0].split(":")[0]
    second_pod = order[2].split(":")[0]
    assert order[1] == f"{first_pod}:end"  # first call fully finished...
    assert second_pod != first_pod  # ...before the other one started
    assert order[3] == f"{second_pod}:end"


async def test_login_does_not_serialize_calls_for_different_emails(monkeypatch):
    """Different portal accounts must not block each other's logins."""
    order: list[str] = []

    async def fake_login_locked(self, pod):
        order.append(f"{pod}:start")
        await asyncio.sleep(0.01)
        order.append(f"{pod}:end")
        return True

    monkeypatch.setattr(ReteleElectriceApi, "_login_locked", fake_login_locked)

    api_a = ReteleElectriceApi("a@example.com", "pw")
    api_b = ReteleElectriceApi("b@example.com", "pw")

    await asyncio.gather(api_a.login("PODA"), api_b.login("PODB"))

    # Both calls started before either finished — they ran concurrently.
    assert set(order[:2]) == {"PODA:start", "PODB:start"}
    assert set(order[2:]) == {"PODA:end", "PODB:end"}
