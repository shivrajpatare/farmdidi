"""Comprehensive failure and edge behavior test suite for Phase 10 Step 4.

Covers:
1. Duplicate confirmed check-in
2. Unknown Didi
3. Invalid quantity
4. Ambiguous quantity
5. No-production response
6. Issue reported
7. No issue reported
8. Correction before confirmation
9. Already-resolved issue
10. Unknown issue ID
11. Google Sheets failure (controlled test environment)
"""

import unittest
from datetime import date
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.main import app, sessions
from backend.models import (
    CheckInRecord,
    IssueRecord,
    IssueUpdate,
    ProductionUpdate,
)
from backend.services.conversation import ConversationEngine, ConversationSession, ConversationState
from backend.services.google_sheets import (
    clear_persisted_records,
    is_daily_checkin_persisted,
    save_checkin,
)
from backend.services.issues import ISSUES, clear_issues, get_issue, resolve_issue


class TestFailureBehavior(unittest.TestCase):
    def setUp(self):
        clear_persisted_records()
        clear_issues()
        sessions.clear()
        self.client = TestClient(app)

    def tearDown(self):
        clear_persisted_records()
        clear_issues()
        sessions.clear()

    # -----------------------------------------------------------------------
    # Case 1: Duplicate confirmed check-in
    # -----------------------------------------------------------------------
    @patch("backend.services.google_sheets._call_apps_script")
    def test_case_01_duplicate_confirmed_checkin(self, mock_apps_script):
        """Second confirmation attempt for same Didi on same date returns 409 and does not corrupt state."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        # 1. First session confirmed
        s1 = ConversationSession(
            session_id="S_DUP_1",
            didi_id="D001",
            didi_name="Meena",
            state=ConversationState.CONFIRM,
            production=ProductionUpdate(production_status="planned", product="Mango Achar", quantity=20, unit="kg"),
            issue=IssueUpdate(has_issue=False),
        )
        sessions[s1.session_id] = s1

        res1 = self.client.post("/api/checkin/confirm", json={"session_id": "S_DUP_1", "decision": "yes"})
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["state"], "COMPLETE")
        self.assertTrue(res1.json()["sheet_saved"])
        self.assertEqual(mock_apps_script.call_count, 1)

        # 2. Second session for same Didi on same date
        s2 = ConversationSession(
            session_id="S_DUP_2",
            didi_id="D001",
            didi_name="Meena",
            state=ConversationState.CONFIRM,
            production=ProductionUpdate(production_status="planned", product="Mango Achar", quantity=25, unit="kg"),
            issue=IssueUpdate(has_issue=True, issue_type="inventory", issue="Jar shortage"),
        )
        sessions[s2.session_id] = s2

        res2 = self.client.post("/api/checkin/confirm", json={"session_id": "S_DUP_2", "decision": "yes"})
        self.assertEqual(res2.status_code, 409)
        self.assertIn("already been confirmed and recorded", res2.json()["detail"])
        # Sheets was not called a second time
        self.assertEqual(mock_apps_script.call_count, 1)
        # Session 2 was not corrupted to COMPLETE
        self.assertEqual(s2.state, ConversationState.CONFIRM)
        self.assertFalse(s2.confirmed)
        # No IssueRecord was created for session 2
        self.assertEqual(len(ISSUES), 0)

    # -----------------------------------------------------------------------
    # Case 2: Unknown Didi
    # -----------------------------------------------------------------------
    def test_case_02_unknown_didi(self):
        """Starting a check-in with an unknown Didi ID returns 404 and creates no session."""
        res = self.client.post("/api/checkin/start", json={"session_id": "S_UNKNOWN", "didi_id": "D999"})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"], "Didi not found")
        self.assertNotIn("S_UNKNOWN", sessions)

    # -----------------------------------------------------------------------
    # Case 3: Invalid quantity
    # -----------------------------------------------------------------------
    def test_case_03_invalid_quantity(self):
        """Production input with invalid quantity prompts for clarification without state corruption."""
        # Start session for D001
        res_start = self.client.post("/api/checkin/start", json={"session_id": "S_INV_QTY", "didi_id": "D001"})
        self.assertEqual(res_start.status_code, 200)

        # Send invalid 0 quantity
        res_prod = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_INV_QTY", "message": "Aaj 0 kg aam ka achar banaya"},
        )
        self.assertEqual(res_prod.status_code, 200)
        session = sessions["S_INV_QTY"]
        # State remains ASK_PRODUCTION so Didi can re-enter
        self.assertEqual(session.state, ConversationState.ASK_PRODUCTION)
        self.assertNotEqual(res_prod.json()["validation_status"], "valid")
        self.assertTrue(len(res_prod.json()["message"]) > 0)

    # -----------------------------------------------------------------------
    # Case 4: Ambiguous quantity
    # -----------------------------------------------------------------------
    def test_case_04_ambiguous_quantity(self):
        """Production input with ambiguous range quantity prompts for clarification and preserves state."""
        self.client.post("/api/checkin/start", json={"session_id": "S_AMBIG", "didi_id": "D001"})

        res_prod = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_AMBIG", "message": "Aaj aam ka achar banaungi, 20 ya 30 kilo"},
        )
        self.assertEqual(res_prod.status_code, 200)
        session = sessions["S_AMBIG"]
        self.assertEqual(session.state, ConversationState.ASK_PRODUCTION)
        self.assertEqual(res_prod.json()["validation_status"], "incomplete")
        self.assertIn("quantity", res_prod.json()["message"].lower())

    # -----------------------------------------------------------------------
    # Case 5: No-production response
    # -----------------------------------------------------------------------
    @patch("backend.services.google_sheets._call_apps_script")
    def test_case_05_no_production_response(self, mock_apps_script):
        """Explicit no-production message proceeds cleanly through confirmation and saves valid record."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        self.client.post("/api/checkin/start", json={"session_id": "S_NO_PROD", "didi_id": "D001"})

        # Send no-production message
        res_prod = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_NO_PROD", "message": "Aaj koi production nahi hoga, tabiyat kharab hai"},
        )
        self.assertEqual(res_prod.status_code, 200)
        session = sessions["S_NO_PROD"]
        self.assertEqual(session.state, ConversationState.ASK_ISSUE)
        self.assertEqual(session.production.production_status, "none")
        self.assertIsNone(session.production.product)
        self.assertIsNone(session.production.quantity)

        # Send no issue
        res_issue = self.client.post(
            "/api/checkin/issue",
            json={"session_id": "S_NO_PROD", "message": "Koi dikkat nahi"},
        )
        self.assertEqual(res_issue.status_code, 200)
        self.assertEqual(session.state, ConversationState.CONFIRM)

        # Confirm
        res_conf = self.client.post(
            "/api/checkin/confirm",
            json={"session_id": "S_NO_PROD", "decision": "yes"},
        )
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(session.state, ConversationState.COMPLETE)
        self.assertTrue(res_conf.json()["sheet_saved"])
        self.assertEqual(mock_apps_script.call_count, 1)

    # -----------------------------------------------------------------------
    # Case 6: Issue reported
    # -----------------------------------------------------------------------
    @patch("backend.services.google_sheets._call_apps_script")
    def test_case_06_issue_reported(self, mock_apps_script):
        """When an issue is reported, confirmation creates an IssueRecord with status 'open'."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        self.client.post("/api/checkin/start", json={"session_id": "S_ISS_REP", "didi_id": "D001"})
        self.client.post("/api/checkin/production", json={"session_id": "S_ISS_REP", "message": "20 kg mango achar"})
        self.client.post("/api/checkin/issue", json={"session_id": "S_ISS_REP", "message": "Bottle shortage ho gayi"})

        res_conf = self.client.post("/api/checkin/confirm", json={"session_id": "S_ISS_REP", "decision": "yes"})
        self.assertEqual(res_conf.status_code, 200)

        # Verify IssueRecord
        self.assertEqual(len(ISSUES), 1)
        issue = list(ISSUES.values())[0]
        self.assertEqual(issue.didi_id, "D001")
        self.assertEqual(issue.status, "open")
        self.assertEqual(issue.issue_type, "inventory")
        self.assertIn("bottle", issue.issue.lower())
        self.assertIsNone(issue.resolved_at)

    # -----------------------------------------------------------------------
    # Case 7: No issue reported
    # -----------------------------------------------------------------------
    @patch("backend.services.google_sheets._call_apps_script")
    def test_case_07_no_issue_reported(self, mock_apps_script):
        """When no issue is reported, confirmation creates NO IssueRecord."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        self.client.post("/api/checkin/start", json={"session_id": "S_NO_ISS", "didi_id": "D001"})
        self.client.post("/api/checkin/production", json={"session_id": "S_NO_ISS", "message": "20 kg mango achar"})
        self.client.post("/api/checkin/issue", json={"session_id": "S_NO_ISS", "message": "Nahi, sab theek hai"})

        res_conf = self.client.post("/api/checkin/confirm", json={"session_id": "S_NO_ISS", "decision": "yes"})
        self.assertEqual(res_conf.status_code, 200)
        self.assertEqual(res_conf.json()["state"], "COMPLETE")

        # Verify no IssueRecord created
        self.assertEqual(len(ISSUES), 0)

    # -----------------------------------------------------------------------
    # Case 8: Correction before confirmation
    # -----------------------------------------------------------------------
    @patch("backend.services.google_sheets._call_apps_script")
    def test_case_08_correction_before_confirmation(self, mock_apps_script):
        """Rejecting confirmation transitions to AWAITING_CORRECTION, allows update, and confirms with new data."""
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        self.client.post("/api/checkin/start", json={"session_id": "S_CORRECT", "didi_id": "D001"})
        self.client.post("/api/checkin/production", json={"session_id": "S_CORRECT", "message": "20 kg mango achar"})
        self.client.post("/api/checkin/issue", json={"session_id": "S_CORRECT", "message": "Koi dikkat nahi"})

        session = sessions["S_CORRECT"]
        self.assertEqual(session.state, ConversationState.CONFIRM)

        # Didi says "no, change"
        res_no = self.client.post("/api/checkin/confirm", json={"session_id": "S_CORRECT", "decision": "no"})
        self.assertEqual(res_no.status_code, 200)
        self.assertEqual(session.state, ConversationState.AWAITING_CORRECTION)

        # Apply correction: changed to 25 kg
        res_corr = self.client.post(
            "/api/checkin/correct",
            json={"session_id": "S_CORRECT", "message": "20 nahi 25 kilo banaya"},
        )
        self.assertEqual(res_corr.status_code, 200)
        self.assertEqual(session.state, ConversationState.CONFIRM)
        self.assertEqual(session.production.quantity, 25.0)

        # Confirm corrected details
        res_yes = self.client.post("/api/checkin/confirm", json={"session_id": "S_CORRECT", "decision": "yes"})
        self.assertEqual(res_yes.status_code, 200)
        self.assertEqual(session.state, ConversationState.COMPLETE)
        self.assertTrue(res_yes.json()["sheet_saved"])
        self.assertEqual(mock_apps_script.call_count, 1)

    # -----------------------------------------------------------------------
    # Case 9: Already-resolved issue
    # -----------------------------------------------------------------------
    def test_case_09_already_resolved_issue(self):
        """Attempting to resolve an already-resolved issue returns HTTP 400 and preserves state."""
        # Setup an issue in ISSUES
        issue = IssueRecord(
            issue_id="ISS-20260910-D001",
            date="2026-09-10",
            didi_id="D001",
            didi_name="Meena",
            issue_type="inventory",
            issue="Bottle shortage",
            status="open",
        )
        ISSUES[issue.issue_id] = issue

        # 1. Resolve first time -> 200 OK
        res1 = self.client.post(
            f"/api/issues/{issue.issue_id}/resolve",
            json={"resolution_notes": "Delivered 50 bottles."},
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["status"], "resolved")
        self.assertEqual(res1.json()["resolution_notes"], "Delivered 50 bottles.")
        self.assertIsNotNone(res1.json()["resolved_at"])

        # 2. Second resolve attempt -> 400 Bad Request
        res2 = self.client.post(
            f"/api/issues/{issue.issue_id}/resolve",
            json={"resolution_notes": "Again."},
        )
        self.assertEqual(res2.status_code, 400)
        self.assertIn("already resolved and cannot be resolved again", res2.json()["detail"])

        # Preserved state
        stored = get_issue(issue.issue_id)
        self.assertEqual(stored.status, "resolved")
        self.assertEqual(stored.resolution_notes, "Delivered 50 bottles.")

    # -----------------------------------------------------------------------
    # Case 10: Unknown issue ID
    # -----------------------------------------------------------------------
    def test_case_10_unknown_issue_id(self):
        """Resolving or fetching a non-existent issue ID returns HTTP 404."""
        # GET unknown issue
        res_get = self.client.get("/api/issues/ISS-NONEXISTENT-999")
        self.assertEqual(res_get.status_code, 404)
        self.assertIn("not found", res_get.json()["detail"].lower())

        # POST resolve unknown issue
        res_post = self.client.post(
            "/api/issues/ISS-NONEXISTENT-999/resolve",
            json={"resolution_notes": "None."},
        )
        self.assertEqual(res_post.status_code, 404)
        self.assertIn("not found", res_post.json()["detail"].lower())

    # -----------------------------------------------------------------------
    # Case 11: Google Sheets failure
    # -----------------------------------------------------------------------
    @patch("backend.services.google_sheets._call_apps_script")
    def test_case_11_google_sheets_failure(self, mock_apps_script):
        """Simulated Sheets failure handles error gracefully, preserves retryability, and does not record dedup key."""
        mock_apps_script.side_effect = RuntimeError("Apps Script network timeout")

        s = ConversationSession(
            session_id="S_FAIL_SHEET",
            didi_id="D001",
            didi_name="Meena",
            state=ConversationState.CONFIRM,
            production=ProductionUpdate(production_status="planned", product="Mango Achar", quantity=20, unit="kg"),
            issue=IssueUpdate(has_issue=False),
        )
        sessions[s.session_id] = s

        # Confirm attempt when Google Sheets fails
        res = self.client.post("/api/checkin/confirm", json={"session_id": "S_FAIL_SHEET", "decision": "yes"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["sheet_saved"], False)
        self.assertIn("save nahi ho paya", res.json()["message"])

        # Crucial checks:
        # 1. session.persisted is False
        self.assertFalse(s.persisted)

        # 2. Daily dedup key was NOT recorded
        today_str = date.today().isoformat()
        self.assertFalse(is_daily_checkin_persisted("D001", today_str))

        # 3. Retry remains possible: now simulate Sheets recovery
        mock_apps_script.side_effect = None
        mock_apps_script.return_value = {"success": True, "sheet": "Daily Check-ins", "row_written": True}

        record = CheckInRecord(
            date=today_str,
            didi_id=s.didi_id,
            didi_name=s.didi_name,
            production_status="planned",
            product="Mango Achar",
            quantity=20,
            unit="kg",
            has_issue=False,
            status="confirmed",
        )
        # Direct save_checkin retry succeeds
        retry_res = save_checkin(record, state="COMPLETE", confirmed=True, session_id="S_FAIL_SHEET_RETRY")
        self.assertTrue(retry_res["success"])
        self.assertTrue(is_daily_checkin_persisted("D001", today_str))


if __name__ == "__main__":
    unittest.main()
