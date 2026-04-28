# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "aiohttp",
#   "beautifulsoup4",
#   "pytz",
# ]
# ///
"""Standalone test script — exercises login + data fetch against the live portal.

Run with:
    uv run test_api.py
"""

import asyncio
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Logging — show everything at DEBUG level so we can see what's happening
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
# Quieten the noisy aiohttp internals
logging.getLogger("aiohttp").setLevel(logging.WARNING)

# ---------------------------------------------------------------------------
# Import the real api.py from the component
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent / "custom_components" / "retele_electrice"))
from api import ReteleElectriceApi, ReteleElectriceAuthError  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
POD = "RO005E513888412"

# Fetch from start of current month to today
END_DATE = date.today()
START_DATE = END_DATE.replace(day=1)


async def main() -> None:
    # Force UTF-8 output on Windows consoles
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    creds = json.loads(CREDENTIALS_FILE.read_text())
    email = creds["email"]
    password = creds["password"]

    print(f"\n{'='*60}")
    print(f"  Retele Electrice API Test")
    print(f"  Email : {email}")
    print(f"  POD   : {POD}")
    print(f"  Range : {START_DATE} -> {END_DATE}")
    print(f"{'='*60}\n")

    api = ReteleElectriceApi(email, password)

    try:
        # ------------------------------------------------------------------
        # Step 1 — Login
        # ------------------------------------------------------------------
        await api.login(POD)
        print(f"  Login successful\n")

        # ------------------------------------------------------------------
        # Step 2 — Fetch consumption data
        # ------------------------------------------------------------------
        print("Fetching consumption data ...")
        records = await api.get_consumption_data(POD, start_date=START_DATE, end_date=END_DATE)

        if not records:
            print("  No records returned.\n")
            return

        print(f"  Got {len(records)} record(s)\n")

        # ------------------------------------------------------------------
        # Step 3 — Display results
        # ------------------------------------------------------------------
        print(f"{'_'*60}")
        print(f"  {'Date':<22} {'Type':<6} {'Hours':>6}  {'Total kWh':>10}")
        print(f"{'_'*60}")

        for record in records:
            date_str = record.get("sampleDate", "?")
            etype = record.get("energyType", "?")
            values_str = record.get("sampleValues", "")

            hourly: list[float] = []
            for v in values_str.split(";"):
                v = v.strip()
                if v:
                    try:
                        hourly.append(float(v.replace(",", ".")))
                    except ValueError:
                        hourly.append(0.0)

            total = sum(hourly)
            print(f"  {date_str:<22} {etype:<6} {len(hourly):>6}  {total:>10.3f} kWh")

        print(f"{'_'*60}\n")

        # ------------------------------------------------------------------
        # Step 4 — Print first record in full (raw hourly breakdown)
        # ------------------------------------------------------------------
        first = records[0]
        print(f"Hourly breakdown for first record ({first.get('sampleDate')}):")
        values_str = first.get("sampleValues", "")
        for i, v in enumerate(values_str.split(";")):
            v = v.strip()
            if not v:
                continue
            kwh = float(v.replace(",", "."))
            bar = "#" * int(kwh * 20)
            print(f"  {i:02d}:00  {kwh:>8.3f} kWh  {bar}")

    except ReteleElectriceAuthError as exc:
        print(f"\n  Authentication error: {exc}")
    except Exception as exc:
        print(f"\n  Unexpected error: {exc}")
        raise
    finally:
        await api.close()
        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
