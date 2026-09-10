"""Tests for Phase 10 Step 2: Single Daily Check-in Enforcement."""

import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app, sessions
from backend.models import CheckInRecord, IssueRecord, IssueUpdate, ProductionUpdate
from backend.services.conversation import ConversationEngine, ConversationSession, ConversationState
from backend.services.google_sheets import (
    _persisted_daily_records,
    _persisted_session_ids,
    clear_persisted_records,
    is_daily_checkin_persisted,
    save_checkin,
)
from backend.services.issues import ISSUES, clear_issues


class TestDailyDeduplication(unittest.TestCase):
    def setUp(self):
        clear_persisted_records()
        clear_issues()
        sessions.clear()

    def tearDown(self):
        clear_persisted_records()
        clear_issues()
        sessions.clear()

    # -----------------------------------------------------------------------
    # Unit Tests for Persistence Service
    # -----------------------------------------------------------------------

    def test_clear_persisted_records(self):
        """clear_persisted_records() clears both session and daily records."""
        _persisted_session_ids.add("S1")
        _persisted_daily_records.add(("D001", "2026-09-10"))
        self.assertTrue(is_daily_checkin_persisted("D001", "2026-09-10"))

        clear_persisted_records()

        self.assertFalse(is_daily_checkin_persisted("D001", "2026-09-10"))
        self.assertEqual(len(_persisted_session_ids), 0)
        self.assertEqual(len(_persisted_daily_records), 0)

    @patch("backend.services.google_sheets._call_apps_script")
    def test_first_confirmed_checkin_succeeds(self, mock_apps_script):
        """First confirmed check-in for a Didi/date successfully persists."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        record = CheckInRecord(
            date="2026-09-10",
            didi_id="D001",
            didi_name="Meena",
            production_status="planned",
            product="Mango Achar",
            quantity=20,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )

        res = save_checkin(record, state="COMPLETE", confirmed=True, session_id="S_TEST_1")
        self.assertTrue(res["success"])
        self.assertTrue(is_daily_checkin_persisted("D001", "2026-09-10"))
        mock_apps_script.assert_called_once()

    @patch("backend.services.google_sheets._call_apps_script")
    def test_same_didi_same_date_raises_value_error(self, mock_apps_script):
        """Second check-in for same Didi and date raises ValueError in save_checkin."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        record1 = CheckInRecord(
            date="2026-09-10",
            didi_id="D001",
            didi_name="Meena",
            production_status="planned",
            product="Mango Achar",
            quantity=20,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )
        save_checkin(record1, state="COMPLETE", confirmed=True, session_id="S_TEST_1")

        record2 = CheckInRecord(
            date="2026-09-10",
            didi_id="D001",
            didi_name="Meena",
            production_status="planned",
            product="Mango Achar",
            quantity=30,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )
        with self.assertRaises(ValueError) as ctx:
            save_checkin(record2, state="COMPLETE", confirmed=True, session_id="S_TEST_2")

        self.assertIn("already exists for Didi 'D001' on date '2026-09-10'", str(ctx.exception))
        # Apps Script should only have been called once (for the first record)
        self.assertEqual(mock_apps_script.call_count, 1)

    @patch("backend.services.google_sheets._call_apps_script")
    def test_different_didi_same_date_allowed(self, mock_apps_script):
        """Different Didi on the same date is allowed."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        record_d1 = CheckInRecord(
            date="2026-09-10",
            didi_id="D001",
            didi_name="Meena",
            production_status="planned",
            product="Mango Achar",
            quantity=20,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )
        record_d2 = CheckInRecord(
            date="2026-09-10",
            didi_id="D002",
            didi_name="Sunita",
            production_status="planned",
            product="Lemon Achar",
            quantity=15,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )

        save_checkin(record_d1, state="COMPLETE", confirmed=True, session_id="S1")
        save_checkin(record_d2, state="COMPLETE", confirmed=True, session_id="S2")

        self.assertTrue(is_daily_checkin_persisted("D001", "2026-09-10"))
        self.assertTrue(is_daily_checkin_persisted("D002", "2026-09-10"))
        self.assertEqual(mock_apps_script.call_count, 2)

    @patch("backend.services.google_sheets._call_apps_script")
    def test_same_didi_different_date_allowed(self, mock_apps_script):
        """Same Didi on a different date is allowed."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        record_day1 = CheckInRecord(
            date="2026-09-09",
            didi_id="D001",
            didi_name="Meena",
            production_status="planned",
            product="Mango Achar",
            quantity=20,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )
        record_day2 = CheckInRecord(
            date="2026-09-10",
            didi_id="D001",
            didi_name="Meena",
            production_status="planned",
            product="Mango Achar",
            quantity=25,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )

        save_checkin(record_day1, state="COMPLETE", confirmed=True, session_id="S1")
        save_checkin(record_day2, state="COMPLETE", confirmed=True, session_id="S2")

        self.assertTrue(is_daily_checkin_persisted("D001", "2026-09-09"))
        self.assertTrue(is_daily_checkin_persisted("D001", "2026-09-10"))
        self.assertEqual(mock_apps_script.call_count, 2)

    @patch("backend.services.google_sheets._call_apps_script")
    def test_failed_sheets_write_does_not_mark_daily_record(self, mock_apps_script):
        """A failed Apps Script write does NOT mark the daily record as persisted."""
        mock_apps_script.side_effect = RuntimeError("Network error")

        record = CheckInRecord(
            date="2026-09-10",
            didi_id="D001",
            didi_name="Meena",
            production_status="planned",
            product="Mango Achar",
            quantity=20,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )

        with self.assertRaises(RuntimeError):
            save_checkin(record, state="COMPLETE", confirmed=True, session_id="S1")

        self.assertFalse(is_daily_checkin_persisted("D001", "2026-09-10"))
        self.assertNotIn("S1", _persisted_session_ids)

    # -----------------------------------------------------------------------
    # Integration Tests with FastAPI TestClient
    # -----------------------------------------------------------------------

    @patch("backend.services.google_sheets._call_apps_script")
    def test_api_duplicate_confirmation_rejected_409(self, mock_apps_script):
        """FastAPI confirm endpoint returns 409 on second confirmation attempt for same Didi/date."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}
        client = TestClient(app)

        # Setup session 1 for D001 in CONFIRM state with issue
        s1 = ConversationSession(
            session_id="S_SESSION_1",
            didi_id="D001",
            didi_name="Meena",
            state=ConversationState.CONFIRM,
            production=ProductionUpdate(production_status="planned", product="Mango Achar", quantity=20, unit="kg"),
            issue=IssueUpdate(has_issue=True, issue_type="inventory", issue="Bottle shortage", details="Only 30 left"),
        )
        sessions[s1.session_id] = s1

        # 1. First confirmation succeeds
        res1 = client.post("/api/checkin/confirm", json={"session_id": "S_SESSION_1", "decision": "yes"})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["state"], "COMPLETE")
        self.assertTrue(res1.json()["sheet_saved"])
        self.assertEqual(mock_apps_script.call_count, 1)
        self.assertEqual(len(ISSUES), 1)

        # Setup session 2 for D001 on the same day in CONFIRM state with different issue
        s2 = ConversationSession(
            session_id="S_SESSION_2",
            didi_id="D001",
            didi_name="Meena",
            state=ConversationState.CONFIRM,
            production=ProductionUpdate(production_status="planned", product="Mango Achar", quantity=25, unit="kg"),
            issue=IssueUpdate(has_issue=True, issue_type="raw_material", issue="Oil shortage", details="No oil"),
        )
        sessions[s2.session_id] = s2

        # 2. Second confirmation for same Didi on same date -> 409 Conflict
        res2 = client.post("/api/checkin/confirm", json={"session_id": "S_SESSION_2", "decision": "yes"})
        self.assertEqual(res2.status_code, 409)
        today_str = date.today().isoformat()
        expected_msg = f"A daily check-in for Meena (D001) on {today_str} has already been confirmed and recorded."
        self.assertEqual(res2.json()["detail"], expected_msg)

        # Verify no second Apps Script call occurred
        self.assertEqual(mock_apps_script.call_count, 1)

        # Verify no second IssueRecord was created
        self.assertEqual(len(ISSUES), 1)

        # Verify session 2 state was NOT altered to COMPLETE
        self.assertEqual(s2.state, ConversationState.CONFIRM)
        self.assertFalse(s2.confirmed)

        # 3. Third session for different Didi D002 on same date succeeds
        s3 = ConversationSession(
            session_id="S_SESSION_3",
            didi_id="D002",
            didi_name="Sunita",
            state=ConversationState.CONFIRM,
            production=ProductionUpdate(production_status="planned", product="Lemon Achar", quantity=15, unit="kg"),
            issue=IssueUpdate(has_issue=True, issue_type="equipment", issue="Gas cylinder low", details="Low gas"),
        )
        sessions[s3.session_id] = s3

        res3 = client.post("/api/checkin/confirm", json={"session_id": "S_SESSION_3", "decision": "yes"})
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.json()["state"], "COMPLETE")
        self.assertTrue(res3.json()["sheet_saved"])
        self.assertEqual(mock_apps_script.call_count, 2)
        self.assertEqual(len(ISSUES), 2)


if __name__ == "__main__":
    unittest.main()
