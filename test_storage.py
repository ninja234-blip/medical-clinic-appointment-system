import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

from appointment import AppointmentConflictError
from main import (
    build_persistent_scheduling_services,
    load_or_seed_clinic,
)
from models import Doctor, Nurse, NurseAdministrator
from storage import ClinicData, StorageError, load_clinic, save_clinic


class StorageTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "data" / "clinic_data.json"

    def test_first_run_seeds_and_second_run_loads_same_data(self):
        clinic, warning = load_or_seed_clinic(self.path)
        self.assertIsNone(warning)
        self.assertTrue(self.path.exists())
        clinic2, warning2 = load_or_seed_clinic(self.path)
        self.assertTrue(clinic2.loaded_from_disk)
        self.assertEqual(clinic2.registry.get_doctor("D001").assigned_nurse.name, "Lee")

    def test_full_visit_survives_close_and_reopen(self):
        clinic, _ = load_or_seed_clinic(self.path)
        load_slots, book = build_persistent_scheduling_services(clinic)
        slot = load_slots("D001", date(2026, 11, 23))[0]
        appt = book("P001", "D001", *slot)
        clinic.records.update_summary(appt.appointment_id, "Annual checkup")
        rx = clinic.records.add_prescription(
            appt.appointment_id, "Lisinopril", "10 mg", "daily", 30, "Take in the morning")
        clinic.records.record_interaction(
            "P001", "D001", "consultation", "Reviewed blood pressure", appt.appointment_id)

        # "close and reopen the app"
        reopened, _ = load_or_seed_clinic(self.path)
        summary = reopened.records.get_visit_summary(appt.appointment_id)
        self.assertEqual(summary["patient_name"], "Maya Shah")
        self.assertEqual(summary["doctor_name"], "Dr. Rao")
        self.assertEqual(summary["nurse_name"], "Lee")
        self.assertEqual(summary["summary"], "Annual checkup")
        self.assertEqual(summary["prescriptions"][0]["prescription_id"], rx.prescription_id)
        self.assertEqual(len(reopened.records.list_interactions(patient_id="P001")), 1)

        # booked slot is still taken after reopening
        load_slots2, book2 = build_persistent_scheduling_services(reopened)
        self.assertNotIn(slot, load_slots2("D001", date(2026, 11, 23)))
        with self.assertRaises(AppointmentConflictError):
            book2("P001", "D001", *slot)

    def test_nurse_administrator_and_care_notes_round_trip(self):
        clinic = ClinicData(self.path)
        reg = clinic.registry
        staff = NurseAdministrator("NA1", "Alex")
        reg.register_nurse_administrator(staff)
        reg.register_doctor(Doctor("D9", "Dr. Chen", "Pediatrics", staff))
        from models import Patient
        p = Patient("P9", "Jo", "(408) 555-0111")
        staff.record_care_note(p, "Allergic to penicillin")
        reg.register_patient(p)
        save_clinic(clinic)

        loaded = load_clinic(self.path)
        again = loaded.registry.get_nurse("NA1")
        self.assertIsInstance(again, NurseAdministrator)
        self.assertIs(again, loaded.registry.get_administrator("NA1"))
        self.assertIs(loaded.registry.get_doctor("D9").assigned_nurse, again)
        self.assertEqual(loaded.registry.get_patient("P9").care_notes, ["Allergic to penicillin"])
        self.assertEqual(loaded.registry.get_patient("P9").phone, "4085550111")

    def test_corrupt_json_is_kept_as_backup_and_raises_storage_error(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ not json", encoding="utf-8")
        with self.assertRaises(StorageError) as ctx:
            load_clinic(self.path)
        self.assertIn("not valid JSON", str(ctx.exception))
        self.assertFalse(self.path.exists())
        self.assertEqual(len(list(self.path.parent.glob("*.corrupt-*.json"))), 1)

    def test_app_recovers_from_corrupt_file_with_warning(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("", encoding="utf-8")
        clinic, warning = load_or_seed_clinic(self.path)
        self.assertIn("not valid JSON", warning)
        self.assertTrue(clinic.registry.list_doctors())
        self.assertTrue(self.path.exists())

    def test_broken_links_and_bad_values_are_rejected(self):
        clinic, _ = load_or_seed_clinic(self.path)
        load_slots, book = build_persistent_scheduling_services(clinic)
        appt = book("P001", "D001", *load_slots("D001", date(2026, 11, 23))[0])
        clinic.records.update_summary(appt.appointment_id, "x")
        good = json.loads(self.path.read_text())

        def broken(mutate):
            data = json.loads(json.dumps(good))
            mutate(data)
            self.path.write_text(json.dumps(data))
            with self.assertRaises(StorageError):
                load_clinic(self.path)
            for f in self.path.parent.glob("*.corrupt-*"):
                f.unlink()

        broken(lambda d: d["appointments"][0].update(patient_id="P404"))
        broken(lambda d: d["medical_records"][0].update(appointment_id="nope"))
        broken(lambda d: d["patients"][0].update(phone="123"))
        broken(lambda d: d["doctors"][0].update(assigned_nurse_id="N404"))
        broken(lambda d: d.update(schema_version=99))
        broken(lambda d: d.pop("doctors"))  # appointments now reference missing doctor
        broken(lambda d: d["medical_records"][0]["prescriptions"].append({"prescription_id": "x"}))

    def test_save_failure_is_reported_and_booking_rolled_back(self):
        clinic, _ = load_or_seed_clinic(self.path)
        load_slots, book = build_persistent_scheduling_services(clinic)
        slot = load_slots("D001", date(2026, 11, 23))[0]
        # make the data path unwritable: its parent "directory" is now a file
        clinic.path = Path(self._tmp.name) / "data" / "clinic_data.json" / "x.json"
        with self.assertRaises(StorageError):
            book("P001", "D001", *slot)
        self.assertEqual(clinic.appointments, {})
        self.assertIn(slot, load_slots("D001", date(2026, 11, 23)))

    def test_atomic_save_leaves_no_temp_files(self):
        clinic, _ = load_or_seed_clinic(self.path)
        clinic.save()
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["clinic_data.json"])


if __name__ == "__main__":
    unittest.main()
