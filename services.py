"""Backend operations the GUI screens call (no tkinter here).

``ClinicService`` wraps ``ClinicData`` so every change is validated, saved to
JSON, and *rolled back* if saving fails. Error contract for screens:

    ValueError     bad input or a broken rule (models.py, records.py, here)
    StorageError   the change could not be saved (nothing was changed)

Screens should catch both and show a message dialog.
"""

from datetime import time
from typing import Dict, List, Optional, Sequence, Union

from appointment import CANCELLED_STATUS
from models import (
    Administrator,
    Appointment,
    AvailabilityWindow,
    Doctor,
    Nurse,
    NurseAdministrator,
    Patient,
)
from storage import ClinicData

DEFAULT_WINDOW = AvailabilityWindow(time(9, 0), time(17, 0))

TimeLike = Union[time, str]


def _parse_time(value: TimeLike, label: str) -> time:
    if isinstance(value, time):
        return value
    if isinstance(value, str):
        try:
            return time.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ValueError(f"{label} must be a time in HH:MM format.")


class ClinicService:
    def __init__(self, clinic: ClinicData) -> None:
        self._clinic = clinic

    @property
    def registry(self):
        return self._clinic.registry

    # -- plumbing ------------------------------------------------------------
    def _commit(self, undo) -> None:
        """Save; if saving fails, undo the in-memory change and re-raise."""
        try:
            self._clinic.save()
        except BaseException:
            undo()
            raise

    def _next_id(self, prefix: str, existing: Sequence[str]) -> str:
        highest = 0
        for identifier in existing:
            if identifier.startswith(prefix) and identifier[len(prefix):].isdigit():
                highest = max(highest, int(identifier[len(prefix):]))
        return f"{prefix}{highest + 1:03d}"

    # -- registration --------------------------------------------------------
    def _validate_patient_details(
        self, name, phone, exclude_patient_id: Optional[str] = None
    ):
        """Validate proposed details and reject an exact normalized duplicate."""
        validated = Patient("VALIDATION", name, phone)
        normalized_name = " ".join(validated.name.split()).casefold()

        for existing in self.registry.list_patients():
            if exclude_patient_id is not None and existing.person_id == exclude_patient_id:
                continue
            existing_name = " ".join(existing.name.split()).casefold()
            if normalized_name == existing_name and validated.phone == existing.phone:
                raise ValueError(
                    f"Patient '{existing.person_id}' already has this name and phone. "
                    "Select that patient to update their details."
                )

        return validated.name, validated.phone

    def register_patient(self, name, phone, person_id: Optional[str] = None) -> Patient:
        registry = self.registry
        if person_id is None:
            person_id = self._next_id("P", list(registry.patients))
        validated_name, validated_phone = self._validate_patient_details(name, phone)
        patient = Patient(person_id, validated_name, validated_phone)

        registry.register_patient(patient)
        self._commit(lambda: registry.patients.pop(patient.person_id, None))
        return patient

    def register_nurse(self, name, person_id: Optional[str] = None) -> Nurse:
        registry = self.registry
        if person_id is None:
            person_id = self._next_id("N", self._staff_ids())
        nurse = Nurse(person_id, name)
        registry.register_nurse(nurse)
        self._commit(lambda: registry.nurses.pop(nurse.person_id, None))
        return nurse

    def register_administrator(
        self, name, person_id: Optional[str] = None
    ) -> Administrator:
        registry = self.registry
        if person_id is None:
            person_id = self._next_id("A", self._staff_ids())
        admin = Administrator(person_id, name)
        registry.register_administrator(admin)
        self._commit(lambda: registry.administrators.pop(admin.person_id, None))
        return admin

    def register_nurse_administrator(
        self, name, person_id: Optional[str] = None
    ) -> NurseAdministrator:
        registry = self.registry
        if person_id is None:
            person_id = self._next_id("NA", self._staff_ids())
        staff = NurseAdministrator(person_id, name)
        registry.register_nurse_administrator(staff)

        def undo():
            registry.nurses.pop(staff.person_id, None)
            registry.administrators.pop(staff.person_id, None)

        self._commit(undo)
        return staff

    def register_doctor(
        self, name, specialty, nurse_id, person_id: Optional[str] = None
    ) -> Doctor:
        registry = self.registry
        nurse = registry.get_nurse(nurse_id)
        if person_id is None:
            person_id = self._next_id("D", list(registry.doctors))
        doctor = Doctor(person_id, name, specialty, nurse)
        registry.register_doctor(doctor)
        had_availability = doctor.person_id in self._clinic.availability
        self._clinic.availability.setdefault(doctor.person_id, [DEFAULT_WINDOW])

        def undo():
            registry.doctors.pop(doctor.person_id, None)
            if not had_availability:
                self._clinic.availability.pop(doctor.person_id, None)

        self._commit(undo)
        return doctor

    def _staff_ids(self) -> List[str]:
        return list(self.registry.nurses) + list(self.registry.administrators)

    # -- updates -------------------------------------------------------------
    def update_patient(self, patient_id, name, phone) -> Patient:
        patient = self.registry.get_patient(patient_id)
        validated_name, validated_phone = self._validate_patient_details(
            name, phone, exclude_patient_id=patient.person_id
        )
        old_name, old_phone = patient.name, patient.phone
        patient.update_details(validated_name, validated_phone)

        def undo():
            patient.name, patient.phone = old_name, old_phone

        self._commit(undo)
        return patient

    def update_patient_contact_as_administrator(
        self, administrator_id, patient_id, phone
    ) -> Patient:
        admin = self.registry.get_administrator(administrator_id)
        patient = self.registry.get_patient(patient_id)
        validated_name, validated_phone = self._validate_patient_details(
            patient.name, phone, exclude_patient_id=patient.person_id
        )
        old_phone = patient.phone
        admin.update_patient_contact(patient, validated_phone)
        self._commit(lambda: setattr(patient, "phone", old_phone))
        return patient

    def add_care_note(self, nurse_id, patient_id, note) -> Patient:
        nurse = self.registry.get_nurse(nurse_id)
        patient = self.registry.get_patient(patient_id)
        nurse.record_care_note(patient, note)
        self._commit(lambda: patient.care_notes.pop())
        return patient

    def assign_nurse(self, doctor_id, nurse_id) -> Doctor:
        doctor = self.registry.get_doctor(doctor_id)
        nurse = self.registry.get_nurse(nurse_id)
        previous = doctor.assigned_nurse
        doctor.assigned_nurse = nurse
        self._commit(lambda: setattr(doctor, "assigned_nurse", previous))
        return doctor

    def get_doctor_overview(self, doctor_id) -> Dict[str, str]:
        doctor = self.registry.get_doctor(doctor_id)
        return {
            "doctor_id": doctor.person_id,
            "doctor_name": doctor.name,
            "specialty": doctor.specialty,
            "nurse_id": doctor.assigned_nurse.person_id,
            "nurse_name": doctor.assigned_nurse.name,
        }

    # -- doctor availability ---------------------------------------------------
    def get_availability(self, doctor_id) -> List[AvailabilityWindow]:
        doctor = self.registry.get_doctor(doctor_id)
        return list(self._clinic.availability.get(doctor.person_id, []))

    def set_availability(
        self, doctor_id, windows: Sequence[AvailabilityWindow]
    ) -> List[AvailabilityWindow]:
        """Replace a doctor's daily working windows (empty = unavailable).
        Windows must not overlap each other."""
        doctor = self.registry.get_doctor(doctor_id)
        windows = list(windows)
        if not all(isinstance(w, AvailabilityWindow) for w in windows):
            raise ValueError("Availability must be AvailabilityWindow objects.")
        ordered = sorted(windows, key=lambda w: w.start)
        for first, second in zip(ordered, ordered[1:]):
            if second.start < first.end:
                raise ValueError(
                    f"Availability windows overlap: {first.start:%H:%M}-{first.end:%H:%M} "
                    f"and {second.start:%H:%M}-{second.end:%H:%M}."
                )
        store = self._clinic.availability
        missing = object()
        previous = store.get(doctor.person_id, missing)
        store[doctor.person_id] = ordered

        def undo():
            if previous is missing:
                store.pop(doctor.person_id, None)
            else:
                store[doctor.person_id] = previous

        self._commit(undo)
        return list(ordered)

    def add_availability_window(
        self, doctor_id, start: TimeLike, end: TimeLike
    ) -> List[AvailabilityWindow]:
        window = AvailabilityWindow(_parse_time(start, "Start"), _parse_time(end, "End"))
        return self.set_availability(
            doctor_id, self.get_availability(doctor_id) + [window]
        )

    def remove_availability_window(self, doctor_id, index: int) -> List[AvailabilityWindow]:
        windows = self.get_availability(doctor_id)
        if isinstance(index, bool) or not isinstance(index, int) or not (
            0 <= index < len(windows)
        ):
            raise ValueError("That availability window does not exist.")
        del windows[index]
        return self.set_availability(doctor_id, windows)

    # -- appointments ----------------------------------------------------------
    def list_appointments(
        self,
        patient_id: Optional[str] = None,
        doctor_id: Optional[str] = None,
        include_cancelled: bool = True,
    ) -> List[Appointment]:
        return sorted(
            (
                a
                for a in self._clinic.appointments.values()
                if (patient_id is None or a.patient_id == patient_id)
                and (doctor_id is None or a.doctor_id == doctor_id)
                and (include_cancelled or a.status.lower() != CANCELLED_STATUS)
            ),
            key=lambda a: a.starts_at,
        )

    def cancel_appointment(self, appointment_id) -> Appointment:
        key = str(appointment_id).strip() if appointment_id is not None else ""
        appointment = self._clinic.appointments.get(key)
        if appointment is None:
            raise ValueError(f"Unknown appointment ID: '{key}'.")
        if appointment.status.lower() == CANCELLED_STATUS:
            raise ValueError("This appointment is already cancelled.")
        previous = appointment.status
        appointment.status = CANCELLED_STATUS
        self._commit(lambda: setattr(appointment, "status", previous))
        return appointment
