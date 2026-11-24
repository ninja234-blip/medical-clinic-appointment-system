import unittest
from datetime import datetime

from models import Appointment
from main import build_demo_registry
from records import (
    ClinicRecordService,
    DoctorPatientInteraction,
    InvalidAppointmentError,
    MedicalRecord,
    Prescription,
    RecordBase,
    RecordError,
    RecordNotFoundError,
)


class PrescriptionTests(unittest.TestCase):
    def test_valid_prescription_accepts_numeric_text_duration(self):
        p = Prescription(" Amoxicillin ", "500 mg", "3x daily", "7")
        self.assertEqual((p.medication, p.duration_days), ("Amoxicillin", 7))

    def test_invalid_fields_are_rejected(self):
        bad = [
            dict(medication="", dosage="1", frequency="d", duration_days=1),
            dict(medication="A", dosage=" ", frequency="d", duration_days=1),
            dict(medication="A", dosage="1", frequency=None, duration_days=1),
            dict(medication="A", dosage="1", frequency="d", duration_days=0),
            dict(medication="A", dosage="1", frequency="d", duration_days=366),
            dict(medication="A", dosage="1", frequency="d", duration_days="2.5"),
            dict(medication="A", dosage="1", frequency="d", duration_days=True),
            dict(medication="A" * 101, dosage="1", frequency="d", duration_days=1),
        ]
        for kwargs in bad:
            with self.subTest(kwargs=kwargs), self.assertRaises(RecordError):
                Prescription(**kwargs)

    def test_failed_update_changes_nothing(self):
        p = Prescription("A", "1 mg", "daily", 5)
        with self.assertRaises(RecordError):
            p.update(medication="B", duration_days=-3)
        self.assertEqual((p.medication, p.duration_days), ("A", 5))
        with self.assertRaises(RecordError):
            p.update()

    def test_discontinue_twice_fails(self):
        p = Prescription("A", "1 mg", "daily", 5)
        p.discontinue()
        self.assertFalse(p.is_active)
        with self.assertRaises(RecordError):
            p.discontinue()

    def test_round_trip(self):
        p = Prescription("A", "1 mg", "daily", 5, "with food")
        r = Prescription.from_dict(p.to_dict())
        self.assertEqual(r.to_dict(), p.to_dict())


class ModelTests(unittest.TestCase):
    def test_inheritance(self):
        for cls in (Prescription, MedicalRecord, DoctorPatientInteraction):
            self.assertTrue(issubclass(cls, RecordBase))

    def test_record_aggregates_prescriptions_and_rejects_duplicates(self):
        record = MedicalRecord("A1", "P001", "D001")
        p = Prescription("A", "1", "d", 1, prescription_id="RX1")
        record.add_prescription(p)
        with self.assertRaises(RecordError):
            record.add_prescription(Prescription("B", "1", "d", 1, prescription_id="RX1"))
        with self.assertRaises(RecordError):
            record.add_prescription("not a prescription")
        self.assertIs(record.get_prescription("RX1"), p)
        record.remove_prescription("RX1")
        with self.assertRaises(RecordNotFoundError):
            record.get_prescription("RX1")

    def test_summary_validation_and_round_trip(self):
        record = MedicalRecord("A1", "P001", "D001")
        with self.assertRaises(RecordError):
            record.update_summary("   ")
        with self.assertRaises(RecordError):
            record.update_summary("x" * 2001)
        record.update_summary("Flu symptoms")
        record.add_prescription(Prescription("A", "1", "d", 1))
        again = MedicalRecord.from_dict(record.to_dict())
        self.assertEqual(again.to_dict(), record.to_dict())

    def test_interaction_validation(self):
        with self.assertRaises(RecordError):
            DoctorPatientInteraction("P1", "D1", "gossip", "notes")
        with self.assertRaises(RecordError):
            DoctorPatientInteraction("P1", "D1", "consultation", " ")
        i = DoctorPatientInteraction("P1", "D1", " Follow_Up ", "Checked in")
        self.assertEqual(i.interaction_type, "follow_up")
        self.assertEqual(DoctorPatientInteraction.from_dict(i.to_dict()).to_dict(), i.to_dict())

    def test_timezone_aware_times_rejected(self):
        from datetime import timezone
        with self.assertRaises(RecordError):
            MedicalRecord("A1", "P", "D", created_at=datetime.now(timezone.utc))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.registry = build_demo_registry()
        self.appt = Appointment("P001", "D001", datetime(2026, 11, 23, 9), datetime(2026, 11, 23, 9, 30))
        self.appointments = {self.appt.appointment_id: self.appt}
        self.saves = 0
        self.fail_save = False

        def save():
            if self.fail_save:
                raise OSError("disk full")
            self.saves += 1

        self.service = ClinicRecordService(self.registry, self.appointments, save)
        self.aid = self.appt.appointment_id

    def test_summary_and_prescription_are_linked_and_saved(self):
        self.service.update_summary(self.aid, "Seasonal flu")
        rx = self.service.add_prescription(self.aid, "Oseltamivir", "75 mg", "2x daily", 5)
        record = self.service.get_record(self.aid)
        self.assertEqual((record.patient_id, record.doctor_id), ("P001", "D001"))
        self.assertEqual(record.summary, "Seasonal flu")
        self.assertIn(rx, record.prescriptions)
        self.assertEqual(self.saves, 2)

        summary = self.service.get_visit_summary(self.aid)
        self.assertEqual(
            (summary["patient_name"], summary["doctor_name"], summary["nurse_name"]),
            ("Maya Shah", "Dr. Rao", "Lee"),
        )
        self.assertEqual(summary["prescriptions"][0]["medication"], "Oseltamivir")

    def test_update_and_discontinue_and_remove_prescription(self):
        rx = self.service.add_prescription(self.aid, "A", "1 mg", "daily", 5)
        self.service.update_prescription(self.aid, rx.prescription_id, dosage="2 mg")
        self.assertEqual(self.service.get_record(self.aid).get_prescription(rx.prescription_id).dosage, "2 mg")
        self.service.discontinue_prescription(self.aid, rx.prescription_id)
        self.assertEqual(self.service.list_prescriptions_for_patient("P001", active_only=True), [])
        self.assertEqual(len(self.service.list_prescriptions_for_patient("P001")), 1)
        self.service.remove_prescription(self.aid, rx.prescription_id)
        self.assertEqual(self.service.list_prescriptions_for_patient("P001"), [])

    def test_save_failure_rolls_back_and_raises(self):
        self.service.update_summary(self.aid, "First")
        self.fail_save = True
        with self.assertRaises(OSError):
            self.service.update_summary(self.aid, "Second")
        with self.assertRaises(OSError):
            self.service.add_prescription(self.aid, "A", "1", "d", 1)
        record = self.service.get_record(self.aid)
        self.assertEqual(record.summary, "First")
        self.assertEqual(record.prescriptions, ())

    def test_validation_failure_does_not_save_or_create_record(self):
        before = self.saves
        with self.assertRaises(RecordError):
            self.service.add_prescription(self.aid, "", "1", "d", 1)
        self.assertEqual(self.saves, before)
        self.assertIsNone(self.service.find_record(self.aid))

    def test_unknown_and_cancelled_appointments_rejected(self):
        with self.assertRaises(InvalidAppointmentError):
            self.service.update_summary("nope", "x")
        with self.assertRaises(InvalidAppointmentError):
            self.service.update_summary("  ", "x")
        self.service.update_summary(self.aid, "ok")
        self.appt.status = "Cancelled"
        with self.assertRaises(InvalidAppointmentError):
            self.service.update_summary(self.aid, "changed")
        self.assertEqual(self.service.list_recordable_appointments(), [])

    def test_missing_record_errors(self):
        with self.assertRaises(RecordNotFoundError):
            self.service.get_record(self.aid)
        with self.assertRaises(RecordNotFoundError):
            self.service.update_prescription(self.aid, "x", dosage="1")

    def test_interactions(self):
        i = self.service.record_interaction("P001", "D001", "consultation", "Discussed flu", self.aid)
        self.service.record_interaction("P001", "D001", "phone_call", "Called to check symptoms")
        self.assertEqual(len(self.service.list_interactions(patient_id="P001")), 2)
        self.assertEqual(self.service.list_interactions(doctor_id="D999"), [])
        self.assertEqual(i.appointment_id, self.aid)
        for args in (
            ("P999", "D001", "consultation", "x"),
            ("P001", "D999", "consultation", "x"),
            ("P001", "D001", "consultation", ""),
            ("P001", "D001", "nonsense", "x"),
        ):
            with self.subTest(args=args), self.assertRaises(RecordError):
                self.service.record_interaction(*args)
        with self.assertRaises(RecordError):  # appointment is for a different patient
            self.registry.register_patient(__import__("models").Patient("P002", "Sam", "4085550101"))
            self.service.record_interaction("P002", "D001", "consultation", "x", self.aid)
        self.assertEqual(len(self.service.list_interactions()), 2)


if __name__ == "__main__":
    unittest.main()
