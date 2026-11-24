"""Tkinter booking screen; patient, doctor, and storage data are injected."""

from datetime import date, datetime
from tkinter import ttk, messagebox
from typing import Callable, Dict, Mapping, Optional, Sequence, Tuple

import theme
from appointment import AppointmentConflictError
from models import Appointment
from storage import StorageError


Slot = Tuple[datetime, datetime]


class SchedulingScreen(ttk.Frame):
    def __init__(
        self,
        master,
        on_navigate: Callable[[str], None],
        on_load_slots: Optional[Callable[[str, date], Sequence[Slot]]] = None,
        on_book: Optional[Callable[[str, str, datetime, datetime], Appointment]] = None,
        persistence_notice: Optional[str] = None,
    ) -> None:
        super().__init__(master, padding=(28, 22))
        self._on_load_slots = on_load_slots
        self._on_book = on_book
        self._patient_ids: Dict[str, str] = {}
        self._doctor_ids: Dict[str, str] = {}
        self._slots: Dict[str, Slot] = {}

        theme.screen_header(
            self, "Scheduling & Booking",
            "Choose a patient, doctor, and day, then pick one of the open times.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 16))

        form = ttk.LabelFrame(self, text="New appointment", padding=(22, 18))
        form.grid(row=1, column=0, sticky="nw")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Patient", style="Clinic.Field.TLabel").grid(
            row=0, column=0, sticky="w", pady=8, padx=(0, 18)
        )
        self.patient_choice = ttk.Combobox(form, state="readonly", width=44)
        self.patient_choice.grid(row=0, column=1, columnspan=2, sticky="ew", pady=8)

        ttk.Label(form, text="Doctor", style="Clinic.Field.TLabel").grid(
            row=1, column=0, sticky="w", pady=8, padx=(0, 18)
        )
        self.doctor_choice = ttk.Combobox(form, state="readonly", width=44)
        self.doctor_choice.grid(row=1, column=1, columnspan=2, sticky="ew", pady=8)
        self.doctor_choice.bind("<<ComboboxSelected>>", self._doctor_selected)

        ttk.Label(form, text="Date (YYYY-MM-DD)", style="Clinic.Field.TLabel").grid(
            row=2, column=0, sticky="w", pady=8, padx=(0, 18)
        )
        self.date_entry = ttk.Entry(form)
        self.date_entry.insert(0, date.today().isoformat())
        self.date_entry.grid(row=2, column=1, sticky="ew", pady=8)
        self.date_entry.bind("<KeyRelease>", self._date_edited)
        self.date_entry.bind("<Return>", self._date_submitted)
        ttk.Button(form, text="Find available times", command=self.refresh_slots).grid(
            row=2, column=2, sticky="ew", padx=(10, 0), pady=8
        )

        ttk.Label(form, text="Available time", style="Clinic.Field.TLabel").grid(
            row=3, column=0, sticky="w", pady=8, padx=(0, 18)
        )
        self.slot_choice = ttk.Combobox(form, state="readonly", width=44)
        self.slot_choice.grid(row=3, column=1, columnspan=2, sticky="ew", pady=8)

        self.slot_status = ttk.Label(
            form, text="Choose a doctor and date to see open times.", style="Muted.TLabel"
        )
        self.slot_status.grid(row=4, column=1, columnspan=2, sticky="w", pady=(0, 8))

        self.book_button = ttk.Button(
            form, text="Book appointment", style="Primary.TButton", command=self.book_selected
        )
        self.book_button.grid(row=5, column=1, columnspan=2, sticky="e", pady=(12, 0))

        if self._on_load_slots is None or self._on_book is None:
            self.book_button.state(["disabled"])
            ttk.Label(
                self,
                text="Booking will be enabled when patient, doctor, and storage "
                "services are connected.",
                wraplength=480, style="Muted.TLabel",
            ).grid(row=2, column=0, sticky="w", pady=(12, 0))
        elif persistence_notice:
            ttk.Label(
                self, text=persistence_notice, wraplength=480, style="Muted.TLabel"
            ).grid(row=2, column=0, sticky="w", pady=(12, 0))

    def set_patients(self, patients: Mapping[str, str]) -> None:
        self._patient_ids = self._make_choices(patients)
        self.patient_choice["values"] = tuple(self._patient_ids)
        self.patient_choice.set("")

    def set_doctors(self, doctors: Mapping[str, str]) -> None:
        self._doctor_ids = self._make_choices(doctors)
        self.doctor_choice["values"] = tuple(self._doctor_ids)
        self.doctor_choice.set("")

    def set_available_slots(self, slots: Sequence[Slot]) -> None:
        self._slots = {
            "{} - {}".format(start.strftime("%H:%M"), end.strftime("%H:%M")): (
                start,
                end,
            )
            for start, end in slots
        }
        self.slot_choice["values"] = tuple(self._slots)
        self.slot_choice.set("")
        if self._slots:
            self.slot_status.configure(
                text="{} available time{}".format(
                    len(self._slots), "" if len(self._slots) == 1 else "s"
                )
            )
        else:
            self.slot_status.configure(text="No available times for this doctor and date.")

    @staticmethod
    def _make_choices(options: Mapping[str, str]) -> Dict[str, str]:
        return {
            "{} [{}]".format(label, identifier): identifier
            for identifier, label in options.items()
        }

    def refresh_slots(self, show_errors: bool = True) -> None:
        doctor_label = self.doctor_choice.get()
        self.set_available_slots(())
        if not doctor_label:
            if show_errors:
                messagebox.showerror("Booking", "Select a doctor first.", parent=self)
            return
        if self._on_load_slots is None:
            if show_errors:
                messagebox.showerror(
                    "Booking", "Availability lookup is not connected yet.", parent=self
                )
            return
        try:
            selected_date = date.fromisoformat(self.date_entry.get().strip())
        except ValueError:
            if show_errors:
                messagebox.showerror(
                    "Booking", "Enter a valid date in YYYY-MM-DD format.", parent=self
                )
            else:
                self.slot_status.configure(text="Enter a valid date in YYYY-MM-DD format.")
            return

        try:
            slots = self._on_load_slots(self._doctor_ids[doctor_label], selected_date)
        except ValueError as error:
            if show_errors:
                messagebox.showerror("Booking", str(error), parent=self)
            else:
                self.slot_status.configure(text=str(error))
            return
        self.set_available_slots(slots)

    def book_selected(self) -> None:
        patient_label = self.patient_choice.get()
        doctor_label = self.doctor_choice.get()
        selected_slot = self.slot_choice.get()
        if not patient_label or not doctor_label or not selected_slot:
            messagebox.showerror(
                "Booking", "Select a patient, doctor, and available time.", parent=self
            )
            return
        if self._on_book is None:
            messagebox.showerror("Booking", "Booking is not connected yet.", parent=self)
            return

        starts_at, ends_at = self._slots[selected_slot]
        try:
            self._on_book(
                self._patient_ids[patient_label],
                self._doctor_ids[doctor_label],
                starts_at,
                ends_at,
            )
        except AppointmentConflictError as error:
            messagebox.showerror("Time slot unavailable", str(error), parent=self)
            self.refresh_slots(show_errors=False)
            return
        except StorageError as error:
            # The booking was rolled back; nothing was saved or booked.
            messagebox.showerror(
                "Booking not saved",
                f"The appointment was not booked because it could not be saved.\n\n{error}",
                parent=self,
            )
            self.refresh_slots(show_errors=False)
            return
        except ValueError as error:
            messagebox.showerror("Booking", str(error), parent=self)
            return

        messagebox.showinfo("Booking", "Appointment booked successfully.", parent=self)
        self.refresh_slots(show_errors=False)

    def _doctor_selected(self, _event=None) -> None:
        self.refresh_slots(show_errors=False)

    def _date_edited(self, _event=None) -> None:
        self.set_available_slots(())

    def _date_submitted(self, _event=None) -> None:
        self.refresh_slots()
