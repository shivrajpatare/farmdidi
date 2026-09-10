import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from backend.models import CheckInRecord

load_dotenv()

GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL", "").strip()


import logging

logger = logging.getLogger(__name__)


def _call_apps_script(method: str, payload: dict | None = None) -> dict:
    if not GOOGLE_APPS_SCRIPT_URL:
        raise RuntimeError("GOOGLE_APPS_SCRIPT_URL is not configured.")

    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = Request(
        GOOGLE_APPS_SCRIPT_URL,
        data=data,
        headers=headers,
        method=method,
    )

    print("\n--- [APPS SCRIPT DIAGNOSTIC: REQUEST] ---")
    print(f"Method: {method}")
    print(f"Target URL: {GOOGLE_APPS_SCRIPT_URL}")
    print(f"Request Headers: {headers}")
    if payload is not None:
        print(f"Request Payload: {json.dumps(payload)}")

    raw_body = None
    status_code = None
    response_headers = None
    final_url = None
    json_parsed = False
    result = None

    try:
        with urlopen(request, timeout=30) as response:
            status_code = response.status
            final_url = response.geturl()
            response_headers = dict(response.headers)
            content_type = response.headers.get("Content-Type", "")
            raw_body = response.read().decode("utf-8", errors="replace")

            print("\n--- [APPS SCRIPT DIAGNOSTIC: RESPONSE] ---")
            print(f"HTTP Status Code: {status_code}")
            print(f"Final URL: {final_url}")
            print(f"Content-Type: {content_type}")
            print(f"Response Headers: {response_headers}")
            print(f"Response Body: {raw_body[:500]}")

            try:
                result = json.loads(raw_body)
                json_parsed = True
                print(f"JSON Parsing Success: {json_parsed}")
                print(f"Parsed JSON Result: {result}")
            except json.JSONDecodeError as json_err:
                print(f"JSON Parsing Success: False ({json_err})")
                raise RuntimeError(
                    f"Google Apps Script returned non-JSON response (Status {status_code}): {raw_body[:200]}"
                ) from json_err

    except HTTPError as http_err:
        status_code = http_err.code
        final_url = http_err.geturl()
        response_headers = dict(http_err.headers)
        content_type = http_err.headers.get("Content-Type", "")
        raw_body = http_err.read().decode("utf-8", errors="replace")

        print("\n--- [APPS SCRIPT DIAGNOSTIC: HTTP ERROR] ---")
        print(f"HTTP Status Code: {status_code}")
        print(f"Final URL: {final_url}")
        print(f"Content-Type: {content_type}")
        print(f"Response Headers: {response_headers}")
        print(f"Response Body: {raw_body[:500]}")
        print("JSON Parsing Success: False (HTTPError)")

        raise RuntimeError(
            f"Google Apps Script HTTP Error {status_code}: {raw_body[:200] or http_err.reason}"
        ) from http_err

    except (URLError, TimeoutError) as net_err:
        print(f"\n--- [APPS SCRIPT DIAGNOSTIC: NETWORK ERROR] ---: {net_err}")
        raise RuntimeError(f"Google Apps Script connection failed: {net_err}") from net_err

    if not isinstance(result, dict) or result.get("success") is not True:
        print(f"Unsuccessful response from Apps Script: {result}")
        raise RuntimeError("Google Apps Script returned an unsuccessful response.")

    return result



def test_apps_script_connection() -> dict:
    """Call the read-only Apps Script health endpoint."""
    return _call_apps_script("GET")


_persisted_session_ids: set[str] = set()
_persisted_daily_records: set[tuple[str, str]] = set()


def is_daily_checkin_persisted(didi_id: str, checkin_date: str) -> bool:
    """Check whether a confirmed check-in for the didi_id on checkin_date has already been persisted."""
    return (didi_id, checkin_date) in _persisted_daily_records


def clear_persisted_records() -> None:
    """Clear in-memory persistence tracking (for test suites)."""
    _persisted_session_ids.clear()
    _persisted_daily_records.clear()


def save_checkin(
    record: CheckInRecord,
    *,
    state: str,
    confirmed: bool,
    session_id: str | None = None,
) -> dict:
    """Append one confirmed record after enforcing the persistence gate."""
    if state != "COMPLETE" or confirmed is not True:
        raise ValueError("Only COMPLETE and confirmed records can be persisted.")
    if record.status != "confirmed":
        raise ValueError("Only confirmed records can be persisted.")
    if session_id and session_id in _persisted_session_ids:
        raise ValueError(f"Session '{session_id}' has already been persisted to Google Sheets.")

    record_key = (record.didi_id, record.date)
    if record_key in _persisted_daily_records:
        raise ValueError(
            f"A confirmed daily check-in already exists for Didi '{record.didi_id}' on date '{record.date}'."
        )

    result = _call_apps_script("POST", {"record": record.model_dump()})
    if session_id:
        _persisted_session_ids.add(session_id)
    _persisted_daily_records.add(record_key)
    return result
