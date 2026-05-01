"""Module-load regression checks.

These tests exist to fail fast if a future commit reintroduces a bad import in
production code (e.g. importing a symbol that doesn't exist in current HA, like
the previous `async_clear_statistics` regression). They are deliberately
shallow — the value is in *triggering* the import path, not in any assertion.
"""


def test_services_module_loads():
    """services.py must import cleanly under current HA. Catches symbols that
    were removed/renamed upstream (e.g. async_clear_statistics)."""
    from custom_components.retele_electrice import services  # noqa: F401


def test_coordinator_module_loads():
    """coordinator.py must import cleanly under current HA."""
    from custom_components.retele_electrice import coordinator  # noqa: F401


def test_const_module_loads_and_has_helper():
    """const.py must import cleanly and expose stat_id_prefix(pod)."""
    from custom_components.retele_electrice.const import DOMAIN, stat_id_prefix

    assert stat_id_prefix("RO005E_X") == f"{DOMAIN}:ro005e_x_"
