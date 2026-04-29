"""Constants for the Rețele Electrice integration."""

DOMAIN = "retele_electrice"

CONF_POD = "pod"
CONF_UPDATE_INTERVAL = "update_interval"

DEFAULT_UPDATE_INTERVAL = 720  # default 12 hours in minutes


def stat_id_prefix(pod: str) -> str:
    """Return the statistic_id prefix used for all stats of a given POD."""
    return f"{DOMAIN}:{pod.lower()}_"
