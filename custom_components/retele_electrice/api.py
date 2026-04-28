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


class ReteleElectriceAuthError(Exception):
    """Raised when authentication fails."""


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
    def _parse_async_response(html: str) -> list[dict[str, Any]]:
        """Extract and parse JSON records from the VF asyncResponse span."""
        m = re.search(
            r'<span id="j_id0:j_id2:asyncResponse">\s*(.*?)\s*</span>',
            html,
            re.DOTALL,
        )
        if not m:
            return []
        raw = m.group(1).strip()
        if not raw:
            return []
        try:
            records = json.loads(raw)
            if isinstance(records, list):
                return records
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
        if end_date is None:
            end_date = date.today()
        if start_date is None:
            start_date = end_date.replace(day=1)

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
