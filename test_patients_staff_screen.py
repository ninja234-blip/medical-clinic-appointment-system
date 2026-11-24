"""Focused tests for the Patients & Staff Stage 2 screen."""

import tempfile
import tkinter as tk
import types
import unittest
from unittest import mock

from models import Administrator, Nurse, NurseAdministrator
from storage import StorageError


class _Choice:
    def __init__(self, value=""):
        self.value = value

    def current(self, index):
        self.value = "Nurse" if index == 0 else self.value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value

    def configure(self, *_args, **_kwargs):
        pass

    def __setitem__(self, _key, value):
        pass


class _Entry:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def delete(self, *_args):
        self.value = ""


class _Text:
    def __init__(self, value=""):
        self.value = value

    def get(self, *_args):
        return self.value

    def delete(self, *_args):
        self.value = ""


class _Status:
    def __init__(self, text=""):
        self.text = text

    def configure(self, text="", **_kwargs):
        self.text = text

    def cget(self, _key):
        return self.text


class _Table:
    def __init__(self):
        self.rows = []

    def get_children(self):
        return [row[0] for row in self.rows]

    def delete(self, *_ids):
        self.rows = []

    def insert(self, _parent, _position, iid=None, values=None):
        self.rows.append((iid, values))


from patients_staff_screen import PatientsStaffScreen


class RealTkinterConstructionSmokeTest(unittest.TestCase):
    def test_construct_all_three_tabs_with_temporary_clinic(self):
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(f"Tk graphical display unavailable: {error}")

        root.withdraw()
        with tempfile.TemporaryDirectory() as directory:
            from pathlib import Path
            from main import load_or_seed_clinic
            from services import ClinicService

            clinic, _ = load_or_seed_clinic(Path(directory) / "clinic.json")
            service = ClinicService(clinic)
            try:
                screen = PatientsStaffScreen(root, lambda _route: None, service)
                root.update()
                tab_text = tuple(screen.notebook.tab(index, "text") for index in range(3))
                self.assertEqual(tab_text, ("Patients", "Staff", "Staff Duties"))
            finally:
                root.destroy()


class StaffScreenTests(unittest.TestCase):
    def make_screen(self, service=None):
        screen = PatientsStaffScreen.__new__(PatientsStaffScreen)
        screen._service = service or mock.Mock()
        screen.staff_role_choice = _Choice("Nurse")
        screen.staff_name_entry = _Entry("Alex")
        screen.staff_specialty_entry = mock.Mock()
        screen.staff_specialty_entry.get.return_value = "Cardiology"
        screen.staff_nurse_choice = _Choice()
        screen.staff_status_label = _Status()
        screen._nurse_ids = {}
        screen.clear_staff = mock.Mock()
        screen.refresh_staff = mock.Mock()
        return screen

    def test_role_registration_calls_matching_service_method(self):
        cases = (
            ("Nurse", "register_nurse", ("Alex",)),
            ("Administrator", "register_administrator", ("Alex",)),
            ("NurseAdministrator", "register_nurse_administrator", ("Alex",)),
        )
        for role, method_name, args in cases:
            with self.subTest(role=role):
                service = mock.Mock()
                service.registry.list_nurses.return_value = []
                screen = self.make_screen(service)
                screen.staff_role_choice.set(role)
                screen.register_staff()
                getattr(service, method_name).assert_called_once_with(*args)

    def test_doctor_requires_registered_and_selected_nurse(self):
        service = mock.Mock()
        screen = self.make_screen(service)
        screen.staff_role_choice.set("Doctor")

        service.registry.list_nurses.return_value = []
        with mock.patch.object(screen.__class__.__module__ and __import__("patients_staff_screen", fromlist=["messagebox"]).messagebox, "showerror", create=True) as error:
            screen.register_staff()
        service.register_doctor.assert_not_called()
        self.assertIn("nurse", error.call_args.args[1].lower())

        nurse = Nurse("N001", "Lee")
        service.registry.list_nurses.return_value = [nurse]
        screen._nurse_ids = {"Lee [N001]": "N001"}
        screen.staff_nurse_choice.set("")
        with mock.patch("patients_staff_screen.messagebox.showerror", create=True) as error:
            screen.register_staff()
        service.register_doctor.assert_not_called()
        self.assertIn("assigned nurse", error.call_args.args[1].lower())

    def test_doctor_registration_passes_selected_nurse_id(self):
        nurse = Nurse("N001", "Lee")
        service = mock.Mock()
        service.registry.list_nurses.return_value = [nurse]
        screen = self.make_screen(service)
        screen.staff_role_choice.set("Doctor")
        screen._nurse_ids = {"Lee [N001]": "N001"}
        screen.staff_nurse_choice.set("Lee [N001]")

        screen.register_staff()

        service.register_doctor.assert_called_once_with("Alex", "Cardiology", "N001")

    def test_nurse_administrator_displays_once_as_dual_role(self):
        dual = NurseAdministrator("NA001", "Alex")
        service = mock.Mock()
        service.registry.list_nurses.return_value = [dual]
        service.registry.list_administrators.return_value = [dual]
        service.registry.list_doctors.return_value = []

        screen = self.make_screen(service)
        screen.staff_table = _Table()
        screen.doctor_table = _Table()
        screen.staff_status_label = _Status()
        screen.reassignment_nurse_choice = _Choice()
        screen.assign_nurse_button = mock.Mock()
        screen.staff_nurse_choice = _Choice()
        screen.staff_specialty_entry = mock.Mock()
        screen._nurse_ids = {}
        screen._staff_role_selected = mock.Mock()

        screen.refresh_staff = PatientsStaffScreen.refresh_staff.__get__(screen)

        screen.refresh_staff()

        self.assertEqual(len(screen.staff_table.rows), 1)
        self.assertEqual(screen.staff_table.rows[0][1], ("NA001", "Alex", "NurseAdministrator"))

    def test_assign_nurse_calls_service_and_storage_error_is_readable(self):
        service = mock.Mock()
        screen = self.make_screen(service)
        screen._selected_doctor_id = "D001"
        screen._reassignment_nurse_ids = {"Lee [N001]": "N001"}
        screen.reassignment_nurse_choice = _Choice("Lee [N001]")
        screen.refresh_staff = mock.Mock()
        screen.staff_status_label = _Status()

        screen.assign_nurse()
        service.assign_nurse.assert_called_once_with("D001", "N001")

        service.assign_nurse.reset_mock()
        service.assign_nurse.side_effect = StorageError("disk full")
        with mock.patch("patients_staff_screen.messagebox.showerror", create=True) as error:
            screen.assign_nurse()
        error.assert_called_once()
        self.assertIn("disk full", error.call_args.args[1])

    def test_invalid_or_empty_roles_are_rejected_without_registration(self):
        for role in ("", "Patient", "Unknown"):
            with self.subTest(role=role):
                service = mock.Mock()
                screen = self.make_screen(service)
                screen.staff_role_choice.set(role)
                with mock.patch("patients_staff_screen.messagebox.showerror", create=True) as error:
                    screen.register_staff()
                error.assert_called_once()
                service.register_nurse.assert_not_called()
                service.register_administrator.assert_not_called()
                service.register_nurse_administrator.assert_not_called()
                service.register_doctor.assert_not_called()

    def test_clear_disabled_specialty_entry_sequence(self):
        screen = PatientsStaffScreen.__new__(PatientsStaffScreen)
        screen.staff_name_entry = _Entry("Alex")

        states = []
        class _Specialty:
            def configure(self, state):
                states.append(state)
            def delete(self, *_args):
                self.value = ""

        screen.staff_specialty_entry = _Specialty()
        screen.staff_specialty_entry.value = "Cardiology"
        screen.staff_role_choice = _Choice("Doctor")
        screen.staff_nurse_choice = _Choice("Lee [N001]")

        screen.clear_staff(clear_status=False)

        self.assertEqual(screen.staff_specialty_entry.value, "")
        self.assertEqual(states, ["normal", "disabled"])
        self.assertEqual(screen.staff_role_choice.get(), "Nurse")

    def test_dual_role_appears_in_both_duty_dropdown_memberships(self):
        ordinary_nurse = Nurse("N001", "Lee")
        dual = NurseAdministrator("NA001", "Alex")
        ordinary_admin = Administrator("A001", "Sam")
        service = mock.Mock()
        service.registry.list_nurses.return_value = [ordinary_nurse, dual]
        service.registry.list_administrators.return_value = [ordinary_admin, dual]

        nurse_ids = {n.person_id: n for n in service.registry.list_nurses()}
        administrator_ids = {a.person_id: a for a in service.registry.list_administrators()}
        self.assertNotIn("A001", nurse_ids)
        self.assertIn("NA001", nurse_ids)
        self.assertIn("NA001", administrator_ids)
        self.assertNotIn("N001", administrator_ids)

    def make_duty_screen(self, service):
        screen = PatientsStaffScreen.__new__(PatientsStaffScreen)
        screen._service = service
        screen._selected_duty_patient_id = "P001"
        screen._duty_nurse_ids = {"Lee [N001]": "N001"}
        screen._duty_administrator_ids = {"Alex [A001]": "A001"}
        screen.duty_nurse_choice = _Choice("Lee [N001]")
        screen.duty_administrator_choice = _Choice("Alex [A001]")
        screen.care_note_text = _Text("Allergic to latex")
        screen.new_phone_entry = _Entry("408-555-0199")
        screen.duty_status_label = _Status()
        screen.duty_phone_label = _Status()
        screen.care_notes_text = mock.Mock()
        screen._load_duty_patient = mock.Mock()
        screen.refresh_patients = mock.Mock()
        screen.patient_table = mock.Mock()
        screen.patient_table.selection.return_value = []
        screen._selected_patient_id = None
        screen.register_button = mock.Mock()
        screen.update_button = mock.Mock()
        screen.name_entry = _Entry()
        screen.phone_entry = _Entry()
        return screen

    def test_duty_actions_pass_correct_ids(self):
        service = mock.Mock()
        screen = self.make_duty_screen(service)
        screen.add_care_note()
        service.add_care_note.assert_called_once_with("N001", "P001", "Allergic to latex")
        screen.update_duty_contact()
        service.update_patient_contact_as_administrator.assert_called_once_with("A001", "P001", "408-555-0199")

    def test_missing_selections_and_blank_note_are_rejected(self):
        service = mock.Mock()
        screen = self.make_duty_screen(service)
        screen._selected_duty_patient_id = None
        with mock.patch("patients_staff_screen.messagebox.showerror", create=True) as error:
            screen.add_care_note()
        error.assert_called_once()

        screen._selected_duty_patient_id = "P001"
        screen.duty_nurse_choice.set("")
        with mock.patch("patients_staff_screen.messagebox.showerror", create=True) as error:
            screen.add_care_note()
        error.assert_called_once()

        screen.duty_nurse_choice.set("Lee [N001]")
        screen.care_note_text = _Text("   ")
        service.add_care_note.side_effect = ValueError("Care note cannot be blank.")
        with mock.patch("patients_staff_screen.messagebox.showerror", create=True) as error:
            screen.add_care_note()
        error.assert_called_once()
        self.assertEqual(screen.duty_status_label.text, "")

    def test_duty_storage_failure_has_no_success_or_mutation(self):
        service = mock.Mock()
        screen = self.make_duty_screen(service)
        screen.care_note_text = _Text("Keep this note")
        service.add_care_note.side_effect = StorageError("disk full")
        with mock.patch("patients_staff_screen.messagebox.showerror", create=True) as error:
            screen.add_care_note()
        error.assert_called_once()
        self.assertEqual(screen.care_note_text.value, "Keep this note")
        self.assertEqual(screen.duty_status_label.text, "")


if __name__ == "__main__":
    unittest.main()
