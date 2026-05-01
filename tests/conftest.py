"""Shared test helpers for the Retele Electrice integration.

Tests in this suite do NOT boot Home Assistant. They import the production
modules (which triggers real HA submodule imports — that's how we catch
import-level regressions) and use unittest.mock for any runtime HA behavior.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Make the integration importable as `custom_components.retele_electrice`.
# pytest doesn't add the project root to sys.path automatically when there is
# no `src/` layout.
_PROJECT_ROOT = Path(__file__).parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


@pytest.fixture
def make_records():
    """Build the records list shape that _import_statistics expects.

    Default: one day, 24 hourly values 0.1, 0.2, ..., 2.4, energyType WI.
    """

    def _build(
        date_str: str = "01/04/2026 00:00",
        hourly_values: list[float] | None = None,
        energy_type: str = "WI",
    ) -> list[dict[str, Any]]:
        if hourly_values is None:
            hourly_values = [round(0.1 * (i + 1), 6) for i in range(24)]
        sample_values = ";".join(
            f"{v:.6f}".replace(".", ",") for v in hourly_values
        )
        return [
            {
                "sampleDate": date_str,
                "sampleValues": sample_values,
                "energyType": energy_type,
            }
        ]

    return _build


@pytest.fixture
def mock_hass():
    """A MagicMock standing in for HomeAssistant.

    Methods that real tests need are pre-wired:
        - `mock_hass.config_entries.async_entries(DOMAIN)` returns []
        - `mock_hass.async_add_executor_job` is an AsyncMock returning {} by default
        - `mock_hass.services.has_service(...)` returns False
        - `mock_hass.services.async_register(...)` is a MagicMock

    Tests override these per-test as needed.
    """
    hass = MagicMock()
    hass.config_entries.async_entries = MagicMock(return_value=[])
    hass.async_add_executor_job = AsyncMock(return_value={})
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    return hass


@pytest.fixture
def fake_api():
    """A MagicMock spec'd to the real ReteleElectriceApi class."""
    from custom_components.retele_electrice.api import ReteleElectriceApi

    api = MagicMock(spec=ReteleElectriceApi)
    api.login = AsyncMock(return_value=True)
    api.get_consumption_data = AsyncMock(return_value=[])
    api.close = AsyncMock(return_value=None)
    return api
