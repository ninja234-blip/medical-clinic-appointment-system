"""Checks SchedulingScreen's error dialogs without needing a display.

tkinter is replaced by light stand-ins, so only the handler logic is tested.
"""
import sys
import types
import unittest
from datetime import datetime
from unittest import mock


def _install_fake_tk():
    tk = types.ModuleType("tkinter")
    ttk = types.ModuleType("tkinter.ttk")
    ttk.Frame = type("Frame", (), {})
    tk.Widget = type("Widget", (), {})
    tk.Tk = type("Tk", (), {})
    messagebox = types.ModuleType("tkinter.messagebox")
    tk.ttk, tk.messagebox = ttk, messagebox
    sys.modules.update({"tkinter": tk, "tkinter.ttk": ttk, "tkinter.messagebox": messagebox})


try:
    import tkinter  # noqa: F401
except ModuleNotFoundError:
    _install_fake_tk()

import scheduling_screen  # noqa: E402
from gui import DoctorAvailabilityScreen, VisitRecordsScreen  # noqa: E402
from appointment import AppointmentConflictError  # noqa: E402
from storage import StorageError  # noqa: E402


class _Choice:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Entry:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class _Status:
    def __init__(self):
        self.text = ""

    def configure(self, text):
        self.text = text


class SchedulingErrorDialogTests(unittest.TestCase):
    def make_screen(self, on_book):
        screen = scheduling_screen.SchedulingScreen.__new__(scheduling_screen.SchedulingScreen)
        slot = (datetime(2026, 11, 23, 9), datetime(2026, 11, 23, 9, 30))
        screen._on_book = on_book
        screen._on_load_slots = lambda doctor_id, day: [slot]
        screen._patient_ids = {"Maya [P001]": "P001"}
        screen._doctor_ids = {"Dr. Rao [D001]": "D001"}
        screen._slots = {"09:00 - 09:30": slot}
        screen.patient_choice = _Choice("Maya [P001]")
        screen.doctor_choice = _Choice("Dr. Rao [D001]")
        screen.slot_choice = _Choice("09:00 - 09:30")
        screen.refresh_slots = mock.Mock()
        return screen

    def run_book(self, error):
        def on_book(*args):
            raise error

        screen = self.make_screen(on_book)
        with mock.patch.object(scheduling_screen.messagebox, "showerror", create=True) as err, \
                mock.patch.object(scheduling_screen.messagebox, "showinfo", create=True) as info:
            screen.book_selected()
        return screen, err, info

    def test_storage_failure_shows_error_and_no_success_message(self):
        screen, err, info = self.run_book(StorageError("disk full"))
        self.assertEqual(err.call_args.args[0], "Booking not saved")
        self.assertIn("disk full", err.call_args.args[1])
        info.assert_not_called()
        screen.refresh_slots.assert_called_once()

    def test_conflict_still_shows_conflict_dialog(self):
        screen, err, info = self.run_book(AppointmentConflictError("Doctor is already booked"))
        self.assertEqual(err.call_args.args[0], "Time slot unavailable")
        info.assert_not_called()
        screen.refresh_slots.assert_called_once()

    def test_other_validation_error_shows_dialog(self):
        _, err, info = self.run_book(ValueError("Unknown patient ID: 'P9'."))
        self.assertEqual(err.call_args.args[0], "Booking")
        info.assert_not_called()

    def test_successful_booking_still_confirms(self):
        screen = self.make_screen(lambda *a: object())
        with mock.patch.object(scheduling_screen.messagebox, "showerror", create=True) as err, \
                mock.patch.object(scheduling_screen.messagebox, "showinfo", create=True) as info:
            screen.book_selected()
        err.assert_not_called()
        info.assert_called_once()


class VisitRecordsScreenTests(unittest.TestCase):
    def make_screen(self, selected_prescription_id=None):
        screen = VisitRecordsScreen.__new__(VisitRecordsScreen)
        screen._records = mock.Mock()
        screen._selected_appointment_id = "AP001"
        screen._selected_prescription_id = selected_prescription_id
        screen._prescription_fields = {
            "medication": _Entry("Amoxicillin"),
            "dosage": _Entry("500 mg"),
            "frequency": _Entry("3x daily"),
            "duration_days": _Entry("7"),
            "instructions": _Entry("Take with food"),
        }
        screen._load_visit = mock.Mock()
        screen.status_label = _Status()
        return screen

    def test_save_prescription_adds_when_no_existing_prescription_is_selected(self):
        screen = self.make_screen()
        screen._records.add_prescription.return_value = types.SimpleNamespace(
            prescription_id="RX001"
        )

        screen.save_prescription()

        screen._records.add_prescription.assert_called_once_with(
            "AP001",
            "Amoxicillin",
            "500 mg",
            "3x daily",
            "7",
            "Take with food",
        )
        screen._load_visit.assert_called_once_with("AP001", "RX001")
        self.assertEqual(screen.status_label.text, "Prescription saved.")

    def test_save_prescription_updates_selected_prescription(self):
        screen = self.make_screen("RX001")
        screen._records.update_prescription.return_value = types.SimpleNamespace(
            prescription_id="RX001"
        )

        screen.save_prescription()

        screen._records.update_prescription.assert_called_once_with(
            "AP001",
            "RX001",
            medication="Amoxicillin",
            dosage="500 mg",
            frequency="3x daily",
            duration_days="7",
            instructions="Take with food",
        )
        screen._records.add_prescription.assert_not_called()


class DoctorAvailabilityScreenTests(unittest.TestCase):
    def make_screen(self):
        screen = DoctorAvailabilityScreen.__new__(DoctorAvailabilityScreen)
        screen._service = mock.Mock()
        screen._selected_doctor_id = "D001"
        screen.start_entry = mock.Mock()
        screen.start_entry.get.return_value = "09:00"
        screen.end_entry = mock.Mock()
        screen.end_entry.get.return_value = "17:00"
        screen.window_list = mock.Mock()
        screen._refresh_windows = mock.Mock()
        screen.status_label = _Status()
        return screen

    def test_add_window_persists_and_clears_inputs(self):
        screen = self.make_screen()

        with mock.patch("gui.messagebox.showerror") as error:
            screen.add_window()

        screen._service.add_availability_window.assert_called_once_with(
            "D001", "09:00", "17:00"
        )
        screen.start_entry.delete.assert_called_once_with(0, "end")
        screen.end_entry.delete.assert_called_once_with(0, "end")
        screen._refresh_windows.assert_called_once_with()
        self.assertEqual(screen.status_label.text, "Doctor availability saved.")
        error.assert_not_called()

    def test_add_window_reports_validation_or_storage_errors(self):
        screen = self.make_screen()
        screen._service.add_availability_window.side_effect = StorageError("disk full")

        with mock.patch("gui.messagebox.showerror") as error:
            screen.add_window()

        self.assertEqual(error.call_args.args[0], "Availability not saved")
        self.assertIn("disk full", error.call_args.args[1])
        screen._refresh_windows.assert_not_called()

    def test_remove_window_uses_selected_window_index(self):
        screen = self.make_screen()
        screen.window_list.selection.return_value = ("1",)

        with mock.patch("gui.messagebox.showerror") as error:
            screen.remove_window()

        screen._service.remove_availability_window.assert_called_once_with("D001", 1)
        screen._refresh_windows.assert_called_once_with()
        self.assertEqual(screen.status_label.text, "Doctor availability saved.")
        error.assert_not_called()


if __name__ == "__main__":
    unittest.main()
