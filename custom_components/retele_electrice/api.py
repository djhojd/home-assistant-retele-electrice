"""API client for Rețele Electrice (contulmeu.reteleelectrice.ro).

Authentication flow:
  1. GET /s/new-load-curves-client?pod=<POD> — follows JS redirect to login page.
  2. POST /PEDRO_SiteLogin with Salesforce ViewState tokens + credentials.
  3. Follow the frontdoor.jsp JS redirect to establish the `sid` session cookie.

Data retrieval:
  The portal embeds a Visualforce page (PED_ProxyCallWSAsync_Curve_VF) inside
  an iframe. The parent LWC sends a postMessage with the method name and date
  parameters, and the VF page makes a server-side web service callout via an
  Ajax4JSF (a4j) postback.

  We replicate this by:
  1. GET /PED_ProxyCallWSAsync_Curve_VF to obtain the ViewState.
  2. POST with a4j parameters (AJAXREQUEST=_viewRoot, methodN=ValoriDiEnergia,
     params=<date_range,POD,type>).
  3. Parse the JSON from the <span id="j_id0:j_id2:asyncResponse"> element.

  The response contains daily records with 24 semicolon-separated hourly kWh
  values in comma-decimal format (e.g. "0,384000;0,277000;...").
"""

import html
import json
import logging
import re
import uuid
from datetime import date, timedelta
from typing import Any

import aiohttp
from bs4 import BeautifulSoup

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://contulmeu.reteleelectrice.ro"
PAGE_URL_TEMPLATE = f"{BASE_URL}/s/new-load-curves-client?pod={{pod}}"
VF_URL = f"{BASE_URL}/PED_ProxyCallWSAsync_Curve_VF"


# Snake_case keys in the queryPOD response that should be coerced to float.
# `precizie` and `constanta` are deliberately excluded — they're meter-level
# metadata the integration treats as opaque strings.
_POD_INFO_FLOAT_KEYS = frozenset({"kw_aprobata", "kw_evacuata", "constant_group"})

# Sentinel string values the portal uses for "no value"; normalize to None.
_POD_INFO_SENTINELS = frozenset({"", "-", " - "})

# Salesforce SOAP metadata keys to strip from any dict before exposing to the integration.
_POD_INFO_METADATA_KEYS = frozenset({"apex_schema_type_info", "field_order_type_info"})


def _strip_metadata(d: dict[str, Any]) -> dict[str, Any]:
    """Remove Salesforce SOAP schema metadata from a queryPOD response dict."""
    return {
        k: v
        for k, v in d.items()
        if not k.endswith("_type_info") and k not in _POD_INFO_METADATA_KEYS
    }


def _normalize_pod_value(key: str, value: Any) -> Any:
    """Apply per-key normalisation for queryPOD values."""
    if isinstance(value, str):
        decoded = html.unescape(value).strip()
        if decoded in _POD_INFO_SENTINELS:
            return None
        if key in _POD_INFO_FLOAT_KEYS:
            try:
                return float(decoded)
            except ValueError:
                return None
        return decoded
    if value is None and key in _POD_INFO_FLOAT_KEYS:
        return None
    return value


def _parse_pod_info_response(raw: str) -> dict[str, Any]:
    """Parse a queryPOD asyncResponse payload into a normalised dict.

    The portal's response is a single JSON object with snake_case Romanian
    keys plus per-key Salesforce SOAP metadata (`<key>_type_info`,
    `apex_schema_type_info`, `field_order_type_info`). One or more meter
    records are nested under a `Contor` array; the first is flattened into
    the top-level dict with `meter_` prefixes. Sentinel values
    ("", "-", " - ", whitespace-only) are normalised to None. HTML entities
    are decoded. Numeric fields listed in `_POD_INFO_FLOAT_KEYS` are coerced
    to float. Unknown keys are passed through.
    """
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError(
            f"queryPOD response was not a JSON object: got {type(parsed).__name__}"
        )

    # Pull out the meter array before we strip metadata (Contor's items contain
    # their own _type_info / apex_schema_type_info keys).
    meters_raw = parsed.get("Contor") or []

    # Strip metadata + normalise top-level keys/values.
    cleaned = _strip_metadata(parsed)
    cleaned.pop("Contor", None)
    result: dict[str, Any] = {
        k: _normalize_pod_value(k, v) for k, v in cleaned.items()
    }

    # Flatten the first meter (if any) with `meter_` prefix.
    if meters_raw:
        first_meter = _strip_metadata(meters_raw[0])
        for k, v in first_meter.items():
            result[f"meter_{k}"] = _normalize_pod_value(k, v)

    return result


class ReteleElectriceAuthError(Exception):
    """Raised when authentication fails."""


def _default_date_range(end_date: date | None = None) -> tuple[date, date]:
    """Default fetch window: covers the full current calendar month and at
    least the last 14 days, whichever is wider.

    Why: the smart meter's data uploads typically lag by 1-2 days. If we
    only query "first of current month → today", late-arriving data from
    the previous month is permanently missed once the calendar rolls over.
    Extending start backwards by ≥14 days ensures the previous month's
    tail re-appears in the query for the first 14 days of the new month.
    """
    if end_date is None:
        end_date = date.today()
    return (
        min(end_date.replace(day=1), end_date - timedelta(days=14)),
        end_date,
    )


class ReteleElectriceApi:
    """Async API Client for Rețele Electrice portal."""

    def __init__(self, email: str, password: str) -> None:
        self._email = email
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._vf_viewstate: dict[str, str] = {}

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                }
            )
        return self._session

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_js_redirect(html: str) -> str | None:
        """Extract a JS redirect URL from page HTML."""
        for pattern in [
            r"window\.location\.replace\(['\"]([^'\"]+)['\"]\)",
            r"window\.location\.href\s*=\s*['\"]([^'\"]+)['\"]",
        ]:
            m = re.search(pattern, html)
            if m:
                return m.group(1)
        return None

    async def _follow_js_redirects(
        self, session: aiohttp.ClientSession, url: str, max_hops: int = 8
    ) -> str:
        """GET a URL, following JS redirects until a real page is reached."""
        for _ in range(max_hops):
            async with session.get(url, allow_redirects=True) as resp:
                resp.raise_for_status()
                html = await resp.text()
            redir = self._find_js_redirect(html)
            if redir:
                url = redir if redir.startswith("http") else BASE_URL + redir
                continue
            return html
        return html

    @staticmethod
    def _extract_viewstate(soup: BeautifulSoup) -> dict[str, str]:
        """Extract Salesforce ViewState fields from a parsed page."""
        vs: dict[str, str] = {}
        for field_id in [
            "com.salesforce.visualforce.ViewState",
            "com.salesforce.visualforce.ViewStateVersion",
            "com.salesforce.visualforce.ViewStateMAC",
            "com.salesforce.visualforce.ViewStateCSRF",
        ]:
            el = soup.find(id=field_id)
            if el:
                vs[field_id] = el.get("value", "")
        return vs

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self, pod: str) -> bool:
        """Log in and establish a Salesforce session (sid cookie).

        Steps:
          1. GET the load-curves page → follow JS redirect to login form.
          2. POST credentials with ViewState + jsfcljs dynamic field.
          3. Follow the frontdoor.jsp redirect from the POST response.
        """
        session = await self._get_session()
        page_url = PAGE_URL_TEMPLATE.format(pod=pod)

        try:
            # Step 1 — Navigate to login form (follow JS redirects)
            html = await self._follow_js_redirects(session, page_url)
            soup = BeautifulSoup(html, "html.parser")
            form = soup.find("form", id="loginPage:loginForm")

            if not form:
                # Check if already authenticated (sid cookie present)
                if any(c.key == "sid" for c in session.cookie_jar):
                    _LOGGER.info("Already authenticated (sid cookie present)")
                    return True
                _LOGGER.error("No login form found and no sid cookie")
                raise ReteleElectriceAuthError("Login page not found")

            # Step 2 — Build login payload
            payload: dict[str, str] = {}

            # Form inputs
            for inp in form.find_all("input"):
                name = inp.get("name")
                if name:
                    payload[name] = inp.get("value", "")

            # ViewState fields (outside <form>, in ajax-view-state-page-container)
            vs_container = soup.find("span", id="ajax-view-state-page-container")
            if vs_container:
                for inp in vs_container.find_all("input"):
                    name = inp.get("name")
                    if name:
                        payload[name] = inp.get("value", "")

            # Dynamic jsfcljs field (e.g. loginPage:loginForm:j_id25)
            for script in soup.find_all("script"):
                text = script.string or script.get_text()
                m = re.search(r"jsfcljs\([^,]+,\s*'([^']+)'", text)
                if m:
                    parts = m.group(1).split(",")
                    for i in range(0, len(parts) - 1, 2):
                        payload[parts[i]] = parts[i + 1]

            # Inject credentials
            for inp in form.find_all("input"):
                itype = (inp.get("type") or "").lower()
                name = inp.get("name", "")
                if itype == "text" or "username" in name.lower() or "email" in name.lower():
                    payload[name] = self._email
                elif itype == "password" or "password" in name.lower():
                    payload[name] = self._password

            form_action = form.get("action", "").replace("&amp;", "&")
            post_url = form_action if form_action.startswith("http") else f"{BASE_URL}/PEDRO_SiteLogin"

            _LOGGER.debug("Login POST with fields: %s", list(payload.keys()))

            async with session.post(post_url, data=payload, allow_redirects=True) as resp:
                resp.raise_for_status()
                html_post = await resp.text()

            # Step 3 — Follow frontdoor.jsp redirect to establish sid cookie
            post_redir = self._find_js_redirect(html_post)
            if not post_redir:
                raise ReteleElectriceAuthError(
                    "No redirect after login POST — credentials may be invalid"
                )
            if post_redir.startswith("/"):
                post_redir = BASE_URL + post_redir
            await self._follow_js_redirects(session, post_redir)

            if not any(c.key == "sid" for c in session.cookie_jar):
                raise ReteleElectriceAuthError("sid cookie not set after login")

            _LOGGER.info("Login successful (sid cookie established)")
            return True

        except ReteleElectriceAuthError:
            raise
        except Exception as exc:
            _LOGGER.error("Login failed: %s", exc)
            raise

    # ------------------------------------------------------------------
    # Data retrieval via VF page a4j postback
    # ------------------------------------------------------------------

    async def _get_vf_viewstate(self, session: aiohttp.ClientSession) -> dict[str, str]:
        """GET the VF page and extract its ViewState."""
        async with session.get(VF_URL, allow_redirects=True) as resp:
            resp.raise_for_status()
            html = await resp.text()
        soup = BeautifulSoup(html, "html.parser")
        vs = self._extract_viewstate(soup)
        if not vs.get("com.salesforce.visualforce.ViewState"):
            raise ReteleElectriceAuthError(
                "VF page ViewState not found — session may have expired"
            )
        return vs

    async def _vf_postback(
        self,
        session: aiohttp.ClientSession,
        viewstate: dict[str, str],
        method_name: str,
        params: str,
    ) -> tuple[str, dict[str, str]]:
        """Make an a4j postback to the VF page.

        Returns (response_html, updated_viewstate).
        """
        post_data = {
            "AJAXREQUEST": "_viewRoot",
            "j_id0:j_id2": "j_id0:j_id2",
            "methodN": method_name,
            "params": params,
            "uniqueId": str(uuid.uuid4()),
            **viewstate,
            "j_id0:j_id2:j_id3": "j_id0:j_id2:j_id3",
        }

        async with session.post(
            VF_URL,
            data=post_data,
            allow_redirects=True,
            headers={
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": VF_URL,
            },
        ) as resp:
            resp.raise_for_status()
            html = await resp.text()

        # Update ViewState from response (it changes after each postback)
        soup = BeautifulSoup(html, "html.parser")
        new_vs = self._extract_viewstate(soup)
        if new_vs:
            viewstate.update(new_vs)

        return html, viewstate

    @staticmethod
    def _extract_async_response(html_text: str) -> str | None:
        """Return the raw text inside <span id="j_id0:j_id2:asyncResponse"> or None."""
        m = re.search(
            r'<span id="j_id0:j_id2:asyncResponse">\s*(.*?)\s*</span>',
            html_text,
            re.DOTALL,
        )
        if not m:
            return None
        raw = m.group(1).strip()
        return raw or None

    @staticmethod
    def _parse_async_response(html: str) -> list[dict[str, Any]]:
        """Extract and parse JSON records from the VF asyncResponse span."""
        raw = ReteleElectriceApi._extract_async_response(html)
        if raw is None:
            return []
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                error_code = parsed.get("errorCode")
                if error_code:
                    _LOGGER.warning(
                        "Portal returned error code %s for POD %s",
                        error_code,
                        parsed.get("serviceDeliveryPoint", {}).get("podId", "?"),
                    )
                return []
        except json.JSONDecodeError:
            _LOGGER.warning("Failed to parse asyncResponse JSON: %s", raw[:200])
        return []

    async def get_consumption_data(
        self,
        pod: str,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch hourly consumption data from the portal.

        Returns a list of dicts with keys:
            sampleDate  : str  "DD/MM/YYYY HH:MM"
            sampleValues: str  semicolon-separated floats (e.g. "0,384000;0,277000;...")
            energyType  : str  "WI" (withdraw/import) | "WE" (export)
        """
        if start_date is None or end_date is None:
            defaults_start, defaults_end = _default_date_range(end_date)
            if start_date is None:
                start_date = defaults_start
            if end_date is None:
                end_date = defaults_end

        session = await self._get_session()

        start_str = start_date.strftime("%d/%m/%Y") + " 00:00:00"
        end_str = end_date.strftime("%d/%m/%Y") + " 23:59:59"

        try:
            # Get fresh ViewState from the VF page
            vs = await self._get_vf_viewstate(session)

            all_records: list[dict[str, Any]] = []

            # Fetch import (WI) data
            params = f"{start_str},{end_str},{pod},WI,"
            _LOGGER.debug("VF postback ValoriDiEnergia: %s", params)
            html, vs = await self._vf_postback(session, vs, "ValoriDiEnergia", params)
            records = self._parse_async_response(html)
            _LOGGER.debug("ValoriDiEnergia returned %d records", len(records))
            all_records.extend(records)

            # Fetch export (WE) data
            params_we = f"{start_str},{end_str},{pod},WE,"
            _LOGGER.debug("VF postback ValoriDiEnergia (export): %s", params_we)
            html_we, vs = await self._vf_postback(session, vs, "ValoriDiEnergia", params_we)
            records_we = self._parse_async_response(html_we)
            _LOGGER.debug("ValoriDiEnergia (export) returned %d records", len(records_we))
            all_records.extend(records_we)

            return all_records

        except Exception as exc:
            _LOGGER.error("Failed to fetch consumption data: %s", exc)
            raise

    async def get_pod_info(self, pod: str) -> dict[str, Any]:
        """Fetch POD metadata via the queryPOD method on the VF data proxy.

        Returns a normalised dict (see _parse_pod_info_response). Caller MUST
        have called login(pod) first.
        """
        session = await self._get_session()
        vs = await self._get_vf_viewstate(session)

        method_name = "queryPOD"
        params = f"{pod},Client_Company"
        _LOGGER.debug(
            "POD-info request: methodN=%s params=%s", method_name, params
        )

        html_resp, _ = await self._vf_postback(session, vs, method_name, params)

        # Extract the raw asyncResponse string. The existing
        # _parse_async_response helper is shaped for the load-curves list
        # response; the queryPOD payload is a single JSON object that the
        # module-level _parse_pod_info_response handles.
        raw = self._extract_async_response(html_resp)
        if not raw:
            raise ReteleElectriceAuthError(
                f"queryPOD response was empty for POD {pod}"
            )

        _LOGGER.debug(
            "POD-info response: %d chars, asyncResponse first 200: %s",
            len(html_resp), raw[:200],
        )
        parsed = _parse_pod_info_response(raw)
        _LOGGER.debug(
            "POD-info parsed: %d fields, keys=%s",
            len(parsed), sorted(parsed.keys()),
        )
        return parsed
