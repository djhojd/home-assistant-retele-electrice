"""Tests for ReteleElectriceApi parsing helpers."""
from __future__ import annotations

from pathlib import Path

import pytest

from custom_components.retele_electrice.api import _parse_pod_info_response

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_pod_info_response_returns_normalized_dict():
    """Captured response parses into the expected snake_case dict."""
    raw = (FIXTURE_DIR / "pod_info_RO005E510252818.json").read_text(encoding="utf-8")
    result = _parse_pod_info_response(raw)

    # No Salesforce metadata leaked
    assert isinstance(result, dict)
    assert not any(k.endswith("_type_info") for k in result)
    assert "apex_schema_type_info" not in result
    assert "field_order_type_info" not in result
    assert "Contor" not in result, "Contor array should be flattened with meter_ prefix"

    # Top-level fields
    assert result["POD"] == "RO005E510252818"
    assert result["nume_client"] == "HOJDA OLIMPIA"
    assert result["cui"] == "18680651"
    assert result["kw_aprobata"] == pytest.approx(6.0)
    assert result["kw_evacuata"] is None  # was JSON null
    assert result["furnizor"] == "NOVA POWER & GAS S.A."  # &amp; decoded
    assert result["furnizor_pre"] == "CIGA ENERGY SA"
    assert result["u_delimitare"] == "JT"
    assert result["activ"] == "D"
    assert result["activ_furnizor_la"] == "2021-03-15"
    assert result["adresa_client"].startswith("STRADA BELGRAD")
    assert result["adresa_locons"].startswith("STRADA")
    assert result["atr_number"] == "218038"
    assert result["atr_date"] == "2001-11-02"
    assert result["deconectat"] is None  # JSON null
    assert result["racordare"] is None  # was " - ", normalized
    assert result["corectii"] is None   # was "-", normalized

    # Meter fields flattened from Contor[0]
    assert result["meter_seria"] == "004000860528410"
    assert result["meter_marca"] == "ACE2000 : 5/60A, 230 V"
    assert result["meter_det_tip"] == "CONTOR_ELECTRONIC"
    assert result["meter_data_montare"] == "2010-08-27"
    assert result["meter_precizie"] == "2"  # NOT numerically coerced
    assert result["meter_constanta"] == "1.0"  # NOT numerically coerced

    # Meter section's _type_info keys also stripped
    assert not any(k.endswith("_type_info") for k in result if k.startswith("meter_"))
