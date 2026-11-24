"""Tests for the pure logic behind the availability day view, record filters, and dashboard."""

import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path

from gui import build_day_schedule, describe_day, filter_visits
from main import build_home_summary, build_persistent_scheduling_services, load_or_seed_clinic
from models import Appointment, AvailabilityWindow

DAY = date(2026, 11, 23)
NINE_TO_ELEVEN = [AvailabilityWindow(time(9, 0), time(11, 0))]


def appt(start_hour, start_min=0, minutes=30, patient="P001", status="booked", doctor="D001"):
    start = datetime(2026, 11, 23, start_hour, start_min)
    return Appointment(patient, doctor, start, start + timedelta(minutes=minutes), status=status)


class DayScheduleTests(unittest.TestCase):
    def test_booked_slot_is_marked_and_names_the_patient(self):
        rows = build_day_schedule(DAY, NINE_TO_ELEVEN, [appt(9, 30)], {"P001": "Maya Shah"})
        states = [(f"{r['start']:%H:%M}", r["state"]) for r in rows]
        self.assertEqual(
            states, [("09:00", "open"), ("09:30", "booked"), ("10:00", "open"), ("10:30", "open")]
        )
        self.assertEqual(rows[1]["patient_name"], "Maya Shah")

    def test_cancelled_and_other_day_appointments_do_not_block(self):
        other_day = Appointment(
            "P001", "D001", datetime(2026, 11, 24, 9), datetime(2026, 11, 24, 9, 30)
        )
        rows = build_day_schedule(
            DAY, NINE_TO_ELEVEN, [appt(9, status="cancelled"), other_day]
        )
        self.assertTrue(all(r["state"] == "open" for r in rows))

    def test_appointment_outside_working_hours_is_still_shown(self):
        rows = build_day_schedule(DAY, NINE_TO_ELEVEN, [appt(14)], {})
        self.assertEqual(rows[-1]["state"], "outside")

    def test_fully_booked_day_is_reported(self):
        full = [appt(9, 0, 60), appt(10, 0, 60, patient="P002")]
        rows = build_day_schedule(DAY, NINE_TO_ELEVEN, full)
        kind, text, appointments, open_count = describe_day(
            rows, NINE_TO_ELEVEN, DAY, now=datetime(2026, 11, 23, 8, 0)
        )
        self.assertEqual((kind, text, appointments, open_count), ("booked", "Fully booked", 2, 0))

    def test_open_day_reports_first_free_time_and_ignores_the_past(self):
        rows = build_day_schedule(DAY, NINE_TO_ELEVEN, [appt(9)])
        morning = describe_day(rows, NINE_TO_ELEVEN, DAY, now=datetime(2026, 11, 23, 8, 0))
        self.assertEqual(morning[:2], ("open", "Free from 09:30"))
        late = describe_day(rows, NINE_TO_ELEVEN, DAY, now=datetime(2026, 11, 23, 10, 10))
        self.assertEqual(late[:2], ("open", "Free from 10:30"))
        over = describe_day(rows, NINE_TO_ELEVEN, DAY, now=datetime(2026, 11, 23, 12, 0))
        self.assertEqual(over[:2], ("off", "Day is over"))

    def test_no_working_hours_means_not_working(self):
        rows = build_day_schedule(DAY, [], [])
        self.assertEqual(describe_day(rows, [], DAY)[:2], ("off", "Not working"))


class FilterVisitsTests(unittest.TestCase):
    def visit(self, aid, patient, doctor, nurse, when, summary="", meds=()):
        return {
            "appointment_id": aid, "patient_id": patient[0], "patient_name": patient[1],
            "doctor_id": doctor[0], "doctor_name": doctor[1],
            "nurse_id": nurse[0], "nurse_name": nurse[1], "starts_at": when,
            "summary": summary,
            "prescriptions": [{"medication": m, "status": "active"} for m in meds],
        }

    def setUp(self):
        rao, chen = ("D001", "Dr. Rao"), ("D002", "Dr. Chen")
        lee, priya = ("N001", "Lee"), ("N002", "Priya Nair")
        self.visits = [
            self.visit("a", ("P001", "Maya Shah"), rao, lee, datetime(2026, 11, 22, 9), "Flu", ["Oseltamivir"]),
            self.visit("b", ("P002", "Liam Carter"), chen, priya, datetime(2026, 11, 23, 10), "Ear infection", ["Amoxicillin"]),
            self.visit("c", ("P001", "Maya Shah"), chen, priya, datetime(2026, 11, 25, 11)),
        ]
        self.today = date(2026, 11, 23)

    def ids(self, **kwargs):
        return [v["appointment_id"] for v in filter_visits(self.visits, today=self.today, **kwargs)]

    def test_each_filter(self):
        self.assertEqual(self.ids(patient_id="P001"), ["a", "c"])
        self.assertEqual(self.ids(doctor_id="D002"), ["b", "c"])
        self.assertEqual(self.ids(nurse_id="N001"), ["a"])
        self.assertEqual(self.ids(nurse_id="N002", patient_id="P001"), ["c"])

    def test_when_filter(self):
        self.assertEqual(self.ids(when="Today"), ["b"])
        self.assertEqual(self.ids(when="Past"), ["a"])
        self.assertEqual(self.ids(when="Upcoming"), ["b", "c"])

    def test_text_search_matches_names_ids_summary_and_medication(self):
        self.assertEqual(self.ids(text="amox"), ["b"])
        self.assertEqual(self.ids(text="priya"), ["b", "c"])
        self.assertEqual(self.ids(text="p001 chen"), ["c"])
        self.assertEqual(self.ids(text="ear infection"), ["b"])
        self.assertEqual(self.ids(text="nothing here"), [])


class HomeSummaryTests(unittest.TestCase):
    def test_summary_counts_todays_booked_appointments(self):
        with tempfile.TemporaryDirectory() as directory:
            clinic, _ = load_or_seed_clinic(Path(directory) / "clinic.json")
            load_slots, book = build_persistent_scheduling_services(clinic)
            slot = load_slots("D001", DAY)[0]
            book("P001", "D001", *slot)
            summary = build_home_summary(clinic, today=DAY)
        stats = dict(summary["stats"])
        self.assertEqual(stats["Patients"], 1)
        self.assertEqual(stats["Doctors"], 1)
        self.assertEqual(stats["Appointments today"], 1)
        self.assertEqual(summary["today"][0][:3], ("09:00", "Maya Shah", "Dr. Rao"))


if __name__ == "__main__":
    unittest.main()
