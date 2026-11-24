import unittest
from datetime import datetime

from models import (
    Administrator,
    Appointment,
    Doctor,
    Nurse,
    NurseAdministrator,
    Patient,
    PeopleRegistry,
)


class PeopleModelTests(unittest.TestCase):
    def test_patient_update_keeps_existing_details_when_phone_is_invalid(self):
        patient = Patient("P001", "Maya Shah", "(408) 555-0100")

        with self.assertRaises(ValueError):
            patient.update_details("Maya Patel", "408-CALL-NOW")

        self.assertEqual(patient.name, "Maya Shah")
        self.assertEqual(patient.phone, "4085550100")

    def test_nurse_administrator_is_registered_for_both_roles_as_same_object(self):
        registry = PeopleRegistry()
        staff = NurseAdministrator("NA001", "Alex")

        registry.register_nurse_administrator(staff)

        self.assertIs(registry.get_nurse("NA001"), staff)
        self.assertIs(registry.get_administrator("NA001"), staff)
        self.assertIsInstance(staff, Nurse)
        self.assertIsInstance(staff, Administrator)

    def test_doctor_must_be_assigned_to_the_registered_nurse_instance(self):
        registry = PeopleRegistry()
        registered_nurse = Nurse("N001", "Lee")
        registry.register_nurse(registered_nurse)

        doctor = Doctor("D001", "Dr. Rao", "Family Medicine", registered_nurse)
        registry.register_doctor(doctor)
        self.assertIs(registry.get_doctor("D001").assigned_nurse, registered_nurse)

        different_nurse_with_same_id = Nurse("N001", "Different Lee")
        unregistered_doctor = Doctor(
            "D002", "Dr. Chen", "Pediatrics", different_nurse_with_same_id
        )
        with self.assertRaisesRegex(ValueError, "exact registered nurse object"):
            registry.register_doctor(unregistered_doctor)

    def test_names_and_specialties_accept_unicode_and_punctuation(self):
        nurse = Nurse("N001", "  Zoë O’Neil-Smith  ")
        accented = Nurse("N002", "Jose\u0301")
        doctor = Doctor("D001", "李", "Obstetrics & Gynecology", nurse)

        self.assertEqual(nurse.name, "Zoë O’Neil-Smith")
        self.assertEqual(accented.name, "Jose\u0301")
        self.assertEqual(doctor.name, "李")
        self.assertEqual(doctor.specialty, "Obstetrics & Gynecology")

    def test_invalid_names_and_specialties_are_rejected(self):
        nurse = Nurse("N001", "Lee")
        for invalid_name in (None, 123, "", "   ", "123", "!!!"):
            with self.subTest(name=invalid_name):
                with self.assertRaises(ValueError):
                    Nurse("NX", invalid_name)
        for invalid_specialty in (None, 123, "", "   ", "123", "!!!"):
            with self.subTest(specialty=invalid_specialty):
                with self.assertRaises(ValueError):
                    Doctor("D999", "Dr. Test", invalid_specialty, nurse)


class AppointmentModelTests(unittest.TestCase):
    def test_appointment_round_trips_through_json_compatible_data(self):
        appointment = Appointment(
            appointment_id="AP001",
            patient_id="P001",
            doctor_id="D001",
            starts_at=datetime(2026, 11, 20, 9, 0),
            ends_at=datetime(2026, 11, 20, 9, 30),
        )

        restored = Appointment.from_dict(appointment.to_dict())

        self.assertEqual(restored.appointment_id, "AP001")
        self.assertEqual(restored.patient_id, "P001")
        self.assertEqual(restored.doctor_id, "D001")
        self.assertEqual(restored.starts_at, appointment.starts_at)
        self.assertEqual(restored.ends_at, appointment.ends_at)


if __name__ == "__main__":
    unittest.main()
