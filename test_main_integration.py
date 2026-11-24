import unittest
from datetime import date

from appointment import AppointmentConflictError
from main import build_demo_registry, build_demo_scheduling_services


class MainIntegrationTests(unittest.TestCase):
    def test_demo_registry_is_connected_to_booking_and_availability(self):
        registry = build_demo_registry()
        load_slots, book_slot, appointment_records = (
            build_demo_scheduling_services(registry)
        )

        slots = load_slots("D001", date(2026, 11, 23))
        appointment = book_slot("P001", "D001", *slots[0])

        self.assertIs(
            registry.get_patient(appointment.patient_id),
            registry.get_patient("P001"),
        )
        self.assertEqual(appointment.doctor_id, registry.get_doctor("D001").person_id)
        self.assertIn(appointment.appointment_id, appointment_records)
        self.assertNotIn(slots[0], load_slots("D001", date(2026, 11, 23)))

        with self.assertRaises(AppointmentConflictError):
            book_slot("P001", "D001", *slots[0])


if __name__ == "__main__":
    unittest.main()
