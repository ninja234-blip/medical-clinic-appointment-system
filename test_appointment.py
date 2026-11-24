import unittest
from datetime import date, datetime, time

from appointment import (
    AppointmentConflictError,
    book_appointment,
    get_available_slots,
)
from models import Appointment, AvailabilityWindow


class AppointmentTests(unittest.TestCase):
    def setUp(self):
        self.existing = Appointment(
            patient_id="patient-1",
            doctor_id="doctor-1",
            starts_at=datetime(2026, 11, 18, 9, 0),
            ends_at=datetime(2026, 11, 18, 9, 30),
        )

    def test_booking_rejects_doctor_double_booking_before_saving(self):
        saved = []

        with self.assertRaisesRegex(AppointmentConflictError, "Doctor"):
            book_appointment(
                patient_id="patient-2",
                doctor_id="doctor-1",
                starts_at=datetime(2026, 11, 18, 9, 15),
                ends_at=datetime(2026, 11, 18, 9, 45),
                appointments=[self.existing],
                save_appointment=saved.append,
            )

        self.assertEqual(saved, [])

    def test_booking_rejects_patient_overlap_with_another_doctor(self):
        with self.assertRaisesRegex(AppointmentConflictError, "Patient"):
            book_appointment(
                patient_id="patient-1",
                doctor_id="doctor-2",
                starts_at=datetime(2026, 11, 18, 9, 15),
                ends_at=datetime(2026, 11, 18, 9, 45),
                appointments=[self.existing],
                save_appointment=lambda appointment: None,
            )

    def test_cancelled_appointment_does_not_block_an_available_slot(self):
        self.existing.status = "cancelled"
        slots = get_available_slots(
            doctor_id="doctor-1",
            appointment_date=date(2026, 11, 18),
            availability=[AvailabilityWindow(time(9, 0), time(10, 0))],
            appointments=[self.existing],
            duration_minutes=30,
        )

        self.assertEqual(
            slots,
            [
                (datetime(2026, 11, 18, 9, 0), datetime(2026, 11, 18, 9, 30)),
                (datetime(2026, 11, 18, 9, 30), datetime(2026, 11, 18, 10, 0)),
            ],
        )


if __name__ == "__main__":
    unittest.main()
