import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path

from main import build_persistent_scheduling_services, load_or_seed_clinic
from models import AvailabilityWindow, NurseAdministrator
from services import ClinicService
from storage import StorageError, load_clinic


class ServiceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "clinic.json"
        self.clinic, _ = load_or_seed_clinic(self.path)
        self.svc = ClinicService(self.clinic)

    def reload(self):
        return load_clinic(self.path)

    def break_saving(self):
        self.clinic.path = self.path / "nested.json"  # parent is a file -> OSError

    def test_register_everyone_and_persist(self):
        p = self.svc.register_patient("Sam Lee", "(214) 555-0199")
        n = self.svc.register_nurse("Pat")
        na = self.svc.register_nurse_administrator("Alex")
        a = self.svc.register_administrator("Robin")
        d = self.svc.register_doctor("Dr. Chen", "Pediatrics", na.person_id)
        self.assertEqual((p.person_id, d.person_id), ("P002", "D002"))
        self.assertEqual(len({n.person_id, na.person_id, a.person_id}), 3)
        loaded = self.reload()
        self.assertEqual(loaded.registry.get_patient("P002").phone, "2145550199")
        self.assertIs(loaded.registry.get_doctor("D002").assigned_nurse,
                      loaded.registry.get_nurse(na.person_id))
        self.assertIsInstance(loaded.registry.get_nurse(na.person_id), NurseAdministrator)
        self.assertEqual(loaded.availability["D002"][0].start, time(9, 0))

    def test_validation_errors_leave_nothing_behind(self):
        for call in (
            lambda: self.svc.register_patient("", "4085550100"),
            lambda: self.svc.register_patient("X", "123"),
            lambda: self.svc.register_patient("X", "4085550100", person_id="P001"),
            lambda: self.svc.register_doctor("Dr. X", "Cardio", "N404"),
            lambda: self.svc.register_doctor("Dr. X", " ", "N001"),
        ):
            with self.assertRaises(ValueError):
                call()
        self.assertEqual(len(self.clinic.registry.list_patients()), 1)
        self.assertEqual(len(self.clinic.registry.list_doctors()), 1)
        self.assertEqual(len(self.reload().registry.list_doctors()), 1)

    def test_update_patient_and_admin_duty_and_nurse_duty(self):
        na = self.svc.register_nurse_administrator("Alex")
        self.svc.update_patient("P001", "Maya Patel", "408-555-0111")
        self.svc.update_patient_contact_as_administrator(na.person_id, "P001", "408-555-0122")
        self.svc.add_care_note(na.person_id, "P001", "Allergic to latex")
        p = self.reload().registry.get_patient("P001")
        self.assertEqual((p.name, p.phone, p.care_notes), ("Maya Patel", "4085550122", ["Allergic to latex"]))
        with self.assertRaises(ValueError):
            self.svc.update_patient("P001", "Maya", "bad")
        with self.assertRaises(ValueError):
            self.svc.add_care_note(na.person_id, "P001", "  ")
        self.assertEqual(self.clinic.registry.get_patient("P001").phone, "4085550122")

    def test_assign_nurse(self):
        n2 = self.svc.register_nurse("Pat")
        self.svc.assign_nurse("D001", n2.person_id)
        self.assertEqual(self.reload().registry.get_doctor("D001").assigned_nurse.name, "Pat")
        self.assertEqual(self.svc.get_doctor_overview("D001")["nurse_name"], "Pat")
        with self.assertRaises(ValueError):
            self.svc.assign_nurse("D001", "N404")

    def test_save_failure_rolls_back_every_operation(self):
        n2 = self.svc.register_nurse("Pat")
        self.break_saving()
        ops = [
            lambda: self.svc.register_patient("Sam", "2145550199"),
            lambda: self.svc.register_nurse("Z"),
            lambda: self.svc.register_administrator("Z"),
            lambda: self.svc.register_nurse_administrator("Z"),
            lambda: self.svc.register_doctor("Dr. Z", "ENT", "N001"),
            lambda: self.svc.update_patient("P001", "Changed", "2145550100"),
            lambda: self.svc.add_care_note("N001", "P001", "note"),
            lambda: self.svc.assign_nurse("D001", n2.person_id),
            lambda: self.svc.set_availability("D001", []),
        ]
        for op in ops:
            with self.assertRaises(StorageError):
                op()
        reg = self.clinic.registry
        self.assertEqual(list(reg.patients), ["P001"])
        self.assertEqual(sorted(reg.nurses), ["N001", "N002"])
        self.assertEqual(reg.administrators, {})
        self.assertEqual(list(reg.doctors), ["D001"])
        self.assertEqual(reg.get_patient("P001").name, "Maya Shah")
        self.assertEqual(reg.get_patient("P001").care_notes, [])
        self.assertEqual(reg.get_doctor("D001").assigned_nurse.name, "Lee")
        self.assertEqual(len(self.clinic.availability["D001"]), 1)

    def test_availability_management_changes_bookable_slots(self):
        self.svc.set_availability("D001", [AvailabilityWindow(time(9, 0), time(10, 0))])
        self.svc.add_availability_window("D001", "13:00", "14:00")
        load_slots, _ = build_persistent_scheduling_services(self.reload())
        slots = load_slots("D001", date(2026, 11, 23))
        self.assertEqual([s[0].strftime("%H:%M") for s in slots], ["09:00", "09:30", "13:00", "13:30"])

        with self.assertRaisesRegex(ValueError, "overlap"):
            self.svc.add_availability_window("D001", "13:30", "15:00")
        with self.assertRaises(ValueError):
            self.svc.add_availability_window("D001", "17:00", "09:00")
        with self.assertRaises(ValueError):
            self.svc.add_availability_window("D001", "9am", "10:00")
        with self.assertRaises(ValueError):
            self.svc.remove_availability_window("D001", 5)
        self.svc.remove_availability_window("D001", 0)
        self.svc.set_availability("D001", [])
        load_slots2, _ = build_persistent_scheduling_services(self.reload())
        self.assertEqual(load_slots2("D001", date(2026, 11, 23)), [])
        with self.assertRaises(ValueError):
            self.svc.get_availability("D404")

    def test_cancel_appointment_frees_slot_and_blocks_record_edits(self):
        load_slots, book = build_persistent_scheduling_services(self.clinic)
        slot = load_slots("D001", date(2026, 11, 23))[0]
        appt = book("P001", "D001", *slot)
        self.svc.cancel_appointment(appt.appointment_id)
        reopened = self.reload()
        self.assertEqual(reopened.appointments[appt.appointment_id].status, "cancelled")
        load_slots2, _ = build_persistent_scheduling_services(reopened)
        self.assertIn(slot, load_slots2("D001", date(2026, 11, 23)))
        self.assertEqual(self.svc.list_appointments(include_cancelled=False), [])
        self.assertEqual(len(self.svc.list_appointments(patient_id="P001")), 1)
        with self.assertRaises(ValueError):
            self.svc.cancel_appointment(appt.appointment_id)
        with self.assertRaises(ValueError):
            self.svc.cancel_appointment("nope")
        from records import InvalidAppointmentError
        with self.assertRaises(InvalidAppointmentError):
            self.clinic.records.update_summary(appt.appointment_id, "x")

    def test_cancel_rolls_back_when_save_fails(self):
        load_slots, book = build_persistent_scheduling_services(self.clinic)
        appt = book("P001", "D001", *load_slots("D001", date(2026, 11, 23))[0])
        self.break_saving()
        with self.assertRaises(StorageError):
            self.svc.cancel_appointment(appt.appointment_id)
        self.assertEqual(appt.status, "booked")

    def test_duplicate_patient_registration_is_rejected_without_changes(self):
        existing = self.svc.register_patient("Anita Das", "4085550126", person_id="P007")
        before_ids = list(self.clinic.registry.patients)
        before_json = self.path.read_bytes()

        duplicate_inputs = (
            ("Anita Das", "4085550126"),
            ("  ANITA   DAS  ", "408-555-0126"),
            ("Anita   Das", "(408) 555-0126"),
        )
        for name, phone in duplicate_inputs:
            with self.assertRaisesRegex(ValueError, "(?i)P007.*select that patient"):
                self.svc.register_patient(name, phone)

        self.assertEqual(list(self.clinic.registry.patients), before_ids)
        self.assertEqual(self.path.read_bytes(), before_json)
        loaded = self.reload()
        self.assertEqual(list(loaded.registry.patients), before_ids)
        self.assertEqual(existing.person_id, "P007")

    def test_duplicate_detection_requires_matching_normalized_name_and_phone(self):
        self.svc.register_patient("Anita Das", "4085550126", person_id="P007")

        name_only = self.svc.register_patient("Anita Das", "4085550999")
        phone_only = self.svc.register_patient("Another Person", "4085550126")

        self.assertEqual(name_only.name, "Anita Das")
        self.assertEqual(phone_only.phone, "4085550126")

    def test_duplicate_patient_updates_are_rejected_and_preserved(self):
        first = self.svc.register_patient("Anita Das", "4085550126", person_id="P007")
        second = self.svc.register_patient("Bob Stone", "2145550101", person_id="P008")
        before_json = self.path.read_bytes()

        with self.assertRaisesRegex(ValueError, "P007.*Select that patient"):
            self.svc.update_patient(second.person_id, "  ANITA   DAS ", "408-555-0126")

        self.assertEqual((second.name, second.phone), ("Bob Stone", "2145550101"))
        self.assertEqual((first.name, first.phone), ("Anita Das", "4085550126"))
        self.assertEqual(self.path.read_bytes(), before_json)

    def test_duplicate_contact_update_and_invalid_phone_preserve_patient(self):
        first = self.svc.register_patient("Anita Das", "4085550126", person_id="P007")
        second = self.svc.register_patient("Anita Das", "2145550101", person_id="P008")
        administrator = self.svc.register_administrator("Admin")
        before_json = self.path.read_bytes()

        with self.assertRaises(ValueError):
            self.svc.update_patient_contact_as_administrator(
                administrator.person_id, second.person_id, "408-555-0126"
            )
        with self.assertRaises(ValueError):
            self.svc.update_patient_contact_as_administrator(
                administrator.person_id, second.person_id, "bad"
            )

        self.assertEqual((second.name, second.phone), ("Anita Das", "2145550101"))
        self.assertEqual((first.name, first.phone), ("Anita Das", "4085550126"))
        self.assertEqual(self.path.read_bytes(), before_json)

    def test_note_and_phone_updates_survive_save_load(self):
        nurse_admin = self.svc.register_nurse_administrator("Alex")
        self.svc.add_care_note(nurse_admin.person_id, "P001", "Follow-up required")
        self.svc.update_patient_contact_as_administrator(
            nurse_admin.person_id, "P001", "408-555-0199"
        )

        loaded = self.reload()
        patient = loaded.registry.get_patient("P001")
        self.assertEqual(patient.phone, "4085550199")
        self.assertIn("Follow-up required", patient.care_notes)

    def test_administrator_contact_duplicate_is_rejected_without_changes(self):
        first = self.svc.register_patient("Anita Das", "4085550126", person_id="P007")
        second = self.svc.register_patient("Anita Das", "2145550101", person_id="P008")
        administrator = self.svc.register_administrator("Admin")
        before_json = self.path.read_bytes()

        with self.assertRaisesRegex(ValueError, "P007.*Select that patient"):
            self.svc.update_patient_contact_as_administrator(
                administrator.person_id, second.person_id, "408-555-0126"
            )

        self.assertEqual((second.name, second.phone), ("Anita Das", "2145550101"))
        self.assertEqual((first.name, first.phone), ("Anita Das", "4085550126"))
        self.assertEqual(self.path.read_bytes(), before_json)

    def test_unchanged_and_distinct_updates_are_allowed(self):
        patient = self.svc.register_patient("Anita Das", "4085550126", person_id="P007")

        unchanged = self.svc.update_patient(f"  {patient.person_id}  ", "Anita Das", "408-555-0126")
        self.assertEqual((unchanged.name, unchanged.phone), ("Anita Das", "4085550126"))

        same_name = self.svc.update_patient(patient.person_id, "Anita Das", "4085550999")
        self.assertEqual(same_name.phone, "4085550999")

        same_phone = self.svc.update_patient(patient.person_id, "Other Name", "4085550999")
        self.assertEqual(same_phone.name, "Other Name")


if __name__ == "__main__":
    unittest.main()
