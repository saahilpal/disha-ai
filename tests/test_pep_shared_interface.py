"""Tests for PEP Shared Update Interface (on_turn, on_session_end, context_slice, slot schema)."""

import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from disha_core.pep.shared_interface import (
    ClinicalStatus,
    PEPSlotRecord,
    SlotOperation,
    SlotSource,
    VerificationStatus,
    context_slice,
    get_pep_update_mode,
    on_session_end,
    on_turn,
    record_slot,
)


class TestPEPSharedInterface(unittest.IsolatedAsyncioTestCase):
    def test_slot_schema_validation(self) -> None:
        rec = PEPSlotRecord(
            slot="wake_time",
            value="06:30",
            source=SlotSource.ONBOARDING,
            clinical_status=ClinicalStatus.ACTIVE,
            verification_status=VerificationStatus.CONFIRMED,
            evidence="onboarding:chat:wake_time",
        )
        self.assertEqual(rec.slot, "wake_time")
        self.assertEqual(rec.value, "06:30")
        self.assertEqual(rec.source, SlotSource.ONBOARDING)
        self.assertEqual(rec.clinical_status, ClinicalStatus.ACTIVE)
        self.assertEqual(rec.verification_status, VerificationStatus.CONFIRMED)
        self.assertEqual(rec.evidence, "onboarding:chat:wake_time")
        self.assertIsInstance(rec.valid_from, datetime)
        self.assertIsNone(rec.valid_until)

    def test_slot_operation_validation(self) -> None:
        op = SlotOperation(op="ADD", slot="allergies", value=["peanuts"], evidence="I have a peanut allergy")
        self.assertEqual(op.op, "ADD")
        self.assertEqual(op.slot, "allergies")
        self.assertEqual(op.value, ["peanuts"])

    def test_pep_update_mode_selection(self) -> None:
        with patch.dict(os.environ, {"PEP_UPDATE_MODE": "classifier"}):
            self.assertEqual(get_pep_update_mode(), "classifier")
        with patch.dict(os.environ, {"PEP_UPDATE_MODE": "summary"}):
            self.assertEqual(get_pep_update_mode(), "summary")
        with patch.dict(os.environ, {"PEP_UPDATE_MODE": "off"}):
            self.assertEqual(get_pep_update_mode(), "off")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(get_pep_update_mode(), "off")

    async def test_on_turn_off_mode(self) -> None:
        with patch.dict(os.environ, {"PEP_UPDATE_MODE": "off"}):
            res = await on_turn("pt_test", "I woke up at 6", "Good to know", "s1")
            self.assertEqual(res["mode"], "off")
            self.assertEqual(res["status"], "skipped")

    async def test_on_session_end_off_mode(self) -> None:
        with patch.dict(os.environ, {"PEP_UPDATE_MODE": "off"}):
            res = await on_session_end("pt_test", "s1")
            self.assertEqual(res["mode"], "off")
            self.assertEqual(res["status"], "skipped")

    def test_context_slice_off_mode(self) -> None:
        with patch.dict(os.environ, {"PEP_UPDATE_MODE": "off"}):
            res = context_slice("pt_test", "exercise_query", {})
            self.assertEqual(res, {"slots": {}})

    async def test_record_slot_in_memory(self) -> None:
        rec = await record_slot(
            patient_id="pt_test_01",
            slot="dietary_restrictions",
            value=["gluten_free"],
            source=SlotSource.ONBOARDING,
            clinical_status=ClinicalStatus.ACTIVE,
            verification_status=VerificationStatus.CONFIRMED,
            evidence="onboarding:voice:dietary_restrictions",
            conn=None,
        )
        self.assertEqual(rec.slot, "dietary_restrictions")
        self.assertEqual(rec.source, SlotSource.ONBOARDING)
        self.assertEqual(rec.verification_status, VerificationStatus.CONFIRMED)


if __name__ == "__main__":
    unittest.main()
