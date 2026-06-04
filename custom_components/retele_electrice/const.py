"""Constants for the Retele Electrice integration."""

DOMAIN = "retele_electrice"

CONF_POD = "pod"
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"

DEFAULT_UPDATE_INTERVAL_HOURS = 24
MIN_UPDATE_INTERVAL_HOURS = 1
MAX_UPDATE_INTERVAL_HOURS = 168  # 7 days


def stat_id_prefix(pod: str) -> str:
    """Return the statistic_id prefix used for all stats of a given POD."""
    return f"{DOMAIN}:{pod.lower()}_"


def current_update_interval_hours(entry) -> int:
    """Return the active polling interval for `entry` (options > data > default).

    Centralizes the precedence rule used by async_setup_entry, the options-flow
    update listener, and OptionsFlowHandler.async_step_init so all three paths
    can never drift apart.
    """
    return entry.options.get(
        CONF_UPDATE_INTERVAL_HOURS,
        entry.data.get(CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS),
    )
