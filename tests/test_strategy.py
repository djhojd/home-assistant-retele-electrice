"""Python side of the dashboard strategy: registration and the entity-key contract."""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import custom_components.retele_electrice as integration
from custom_components.retele_electrice import STRATEGY_PATH, STRATEGY_URL, async_setup
from custom_components.retele_electrice.button import (
    RefreshPodInfoButton,
    ReteleElectriceSyncButton,
)
from custom_components.retele_electrice.sensor import (
    _POD_FIELD_DESCRIPTORS,
    PodFieldSensor,
    PodInfoSensor,
    ReteleElectriceSensor,
)

POD = "RO005EXXXXXXXXX"


async def test_async_setup_serves_strategy_with_versioned_url():
    hass = MagicMock()
    hass.http.async_register_static_paths = AsyncMock()

    with (
        patch.object(integration, "async_get_integration",
                     AsyncMock(return_value=MagicMock(version="9.9.9"))),
        patch.object(integration, "add_extra_js_url") as add_js,
    ):
        assert await async_setup(hass, {}) is True

    (config,), _ = hass.http.async_register_static_paths.call_args
    assert config[0].url_path == STRATEGY_URL
    assert config[0].path == str(STRATEGY_PATH)
    add_js.assert_called_once_with(hass, f"{STRATEGY_URL}?v=9.9.9")


def test_strategy_file_ships_with_the_integration():
    assert STRATEGY_PATH.is_file()


def test_every_entity_key_the_strategy_reads_is_set_by_an_entity():
    """The JS finds entities by translation_key; a renamed or missing key
    would silently drop a tile from every user's dashboard."""
    used = set(re.findall(r"pod\.entities\.(\w+)", STRATEGY_PATH.read_text(encoding="utf-8")))
    entry = MagicMock(data={})
    # Instances, not classes: HA's entity metaclass turns class _attr_* into properties.
    entities = [
        ReteleElectriceSensor(MagicMock(), POD, {}),
        PodInfoSensor(MagicMock(), entry, POD),
        ReteleElectriceSyncButton(MagicMock(), POD, {}),
        RefreshPodInfoButton(MagicMock(), POD, {}),
        *(PodFieldSensor(entry, POD, d) for d in _POD_FIELD_DESCRIPTORS),
    ]
    provided = {e.translation_key for e in entities}

    assert used, "pattern found no keys; did the JS stop using pod.entities.<key>?"
    assert used <= provided, f"strategy reads keys no entity sets: {used - provided}"
