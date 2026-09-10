"""Regression test suite for field-aware production clarification and multi-turn accumulation."""

import unittest
from fastapi.testclient import TestClient

from backend.main import app, sessions
from backend.services.conversation import ConversationState
from backend.services.google_sheets import clear_persisted_records
from backend.services.issues import clear_issues


class TestProductionClarification(unittest.TestCase):
    def setUp(self):
        clear_persisted_records()
        clear_issues()
        sessions.clear()
        self.client = TestClient(app)

    def tearDown(self):
        clear_persisted_records()
        clear_issues()
        sessions.clear()

    def test_01_ambiguous_product_no_guess(self):
        """'me lemon or aam' must not guess product, and asks product clarification."""
        self.client.post("/api/checkin/start", json={"session_id": "S_AMBIG_PROD", "didi_id": "D001"})
        res = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_AMBIG_PROD", "message": "me lemon or aam"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["state"], ConversationState.ASK_PRODUCTION.value)
        self.assertNotEqual(data["validation_status"], "valid")
        # Must ask specific product clarification without guessing
        self.assertEqual(data["message"], "Aap Lemon Achar bana rahi hain ya Mango Achar?")
        session = sessions["S_AMBIG_PROD"]
        self.assertIn("Lemon Achar", session.production.product)
        self.assertIn("Mango Achar", session.production.product)

    def test_02_ambiguous_product_then_quantity(self):
        """'me lemon or aam' then '20 kg' preserves quantity/unit and asks only product clarification."""
        self.client.post("/api/checkin/start", json={"session_id": "S_AMBIG_QTY", "didi_id": "D001"})
        self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_AMBIG_QTY", "message": "me lemon or aam"},
        )
        res_qty = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_AMBIG_QTY", "message": "20 kg"},
        )
        self.assertEqual(res_qty.status_code, 200)
        session = sessions["S_AMBIG_QTY"]
        self.assertEqual(session.production.quantity, 20.0)
        self.assertEqual(session.production.unit, "kg")
        # Still asks ONLY product clarification, does not ask to repeat quantity
        self.assertEqual(res_qty.json()["message"], "Aap Lemon Achar bana rahi hain ya Mango Achar?")

        # Resolving product resolves the candidate and moves to ASK_ISSUE
        res_resolve = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_AMBIG_QTY", "message": "Lemon"},
        )
        self.assertEqual(res_resolve.status_code, 200)
        self.assertEqual(res_resolve.json()["state"], ConversationState.ASK_ISSUE.value)
        self.assertEqual(session.production.product, "Lemon Achar")
        self.assertEqual(session.production.quantity, 20.0)
        self.assertEqual(session.production.unit, "kg")

    def test_03_product_quantity_separate_messages(self):
        """'aam ka achar' then '20' then 'kg' accumulates candidate to Mango Achar, 20 kg."""
        self.client.post("/api/checkin/start", json={"session_id": "S_SEP", "didi_id": "D001"})
        
        # 1. Product only
        res1 = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_SEP", "message": "aam ka achar"},
        )
        self.assertEqual(res1.status_code, 200)
        self.assertEqual(res1.json()["message"], "Kitna Mango Achar bana rahi hain?")
        session = sessions["S_SEP"]
        self.assertEqual(session.production.product, "Mango Achar")

        # 2. Quantity only
        res2 = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_SEP", "message": "20"},
        )
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res2.json()["message"], "Quantity kg mein hai?")
        self.assertEqual(session.production.product, "Mango Achar")
        self.assertEqual(session.production.quantity, 20.0)

        # 3. Unit only
        res3 = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_SEP", "message": "kg"},
        )
        self.assertEqual(res3.status_code, 200)
        self.assertEqual(res3.json()["state"], ConversationState.ASK_ISSUE.value)
        self.assertEqual(session.production.product, "Mango Achar")
        self.assertEqual(session.production.quantity, 20.0)
        self.assertEqual(session.production.unit, "kg")

    def test_04_product_quantity_unit_mixed_messages(self):
        """'aam ka achar' -> '20' -> '20kg' preserves previous fields and transitions to ASK_ISSUE."""
        self.client.post("/api/checkin/start", json={"session_id": "S_MIXED", "didi_id": "D001"})
        
        self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_MIXED", "message": "aam ka achar"},
        )
        self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_MIXED", "message": "20"},
        )
        res3 = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_MIXED", "message": "20kg"},
        )
        self.assertEqual(res3.status_code, 200)
        session = sessions["S_MIXED"]
        self.assertEqual(session.state, ConversationState.ASK_ISSUE)
        self.assertEqual(session.production.product, "Mango Achar")
        self.assertEqual(session.production.quantity, 20.0)
        self.assertEqual(session.production.unit, "kg")

    def test_05_field_specific_clarification_no_generic_repeat(self):
        """Field-specific messages are sent instead of generic 'Thoda aur production detail batayein.'"""
        self.client.post("/api/checkin/start", json={"session_id": "S_FIELD_AWARE", "didi_id": "D001"})
        
        # Missing product: '20 kg'
        res_prod_missing = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_FIELD_AWARE", "message": "20 kg"},
        )
        self.assertEqual(res_prod_missing.json()["message"], "Aap kaunsa achar bana rahi hain?")

        # Ambiguous product
        res_ambig_prod = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_FIELD_AWARE", "message": "nimbu ya mirchi"},
        )
        self.assertEqual(res_ambig_prod.json()["message"], "Aap Lemon Achar bana rahi hain ya Chilli Achar?")

        # Affirmative unit response when unit was missing
        self.client.post("/api/checkin/start", json={"session_id": "S_UNIT_CONFIRM", "didi_id": "D001"})
        self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_UNIT_CONFIRM", "message": "aam ka achar 15"},
        )
        res_unit = self.client.post(
            "/api/checkin/production",
            json={"session_id": "S_UNIT_CONFIRM", "message": "haan"},
        )
        self.assertEqual(res_unit.json()["state"], ConversationState.ASK_ISSUE.value)
        self.assertEqual(sessions["S_UNIT_CONFIRM"].production.unit, "kg")


if __name__ == "__main__":
    unittest.main()
