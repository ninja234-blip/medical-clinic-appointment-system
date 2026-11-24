"""Shared domain models for patients, staff, and clinic appointments."""

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Dict
from uuid import uuid4


class Person:
    """Base class for people associated with the clinic."""

    def __init__(self, person_id, name):
        self.person_id = self._validate_person_id(person_id)
        self.name = self._validate_name(name)

    @staticmethod
    def _validate_person_id(person_id):
        if person_id is None or not str(person_id).strip():
            raise ValueError("Person ID cannot be blank.")
        return str(person_id).strip()

    @staticmethod
    def _validate_name(name):
        if not isinstance(name, str):
            raise ValueError("Name must be a string.")
        trimmed = name.strip()
        if not trimmed:
            raise ValueError("Name cannot be blank.")
        if not any(character.isalpha() for character in trimmed):
            raise ValueError("Name must contain at least one alphabetic character.")
        return trimmed


class Patient(Person):
    """A patient with a phone number and care notes."""

    def __init__(self, person_id, name, phone):
        super().__init__(person_id, name)
        self.phone = self._validate_phone(phone)
        self.care_notes = []

    @staticmethod
    def _validate_phone(phone):
        if not isinstance(phone, str):
            raise ValueError("Phone number must be a string.")
        if not phone.strip():
            raise ValueError("Phone number cannot be blank.")

        allowed_characters = "0123456789 ()-"
        if any(character not in allowed_characters for character in phone):
            raise ValueError(
                "Phone number can contain only digits, spaces, hyphens, and parentheses."
            )

        digits = "".join(character for character in phone if character in "0123456789")
        if len(digits) != 10:
            raise ValueError("Phone number must contain exactly 10 ASCII digits.")

        return digits

    def update_details(self, name, phone):
        """Update the patient's name and phone after validating both."""
        validated_name = self._validate_name(name)
        validated_phone = self._validate_phone(phone)

        self.name = validated_name
        self.phone = validated_phone


class Nurse(Person):
    """A nurse associated with the clinic."""

    def __init__(self, person_id, name):
        super().__init__(person_id, name)

    def record_care_note(self, patient, note):
        if not isinstance(patient, Patient):
            raise ValueError("Care note patient must be a Patient object.")
        if not isinstance(note, str):
            raise ValueError("Care note must be a string.")

        stripped_note = note.strip()
        if not stripped_note:
            raise ValueError("Care note cannot be blank.")

        patient.care_notes.append(stripped_note)


class Administrator(Person):
    """An administrator who can update patient contact details."""

    def __init__(self, person_id, name):
        super().__init__(person_id, name)

    def update_patient_contact(self, patient, phone):
        if not isinstance(patient, Patient):
            raise ValueError("Patient must be a Patient object.")

        patient.update_details(patient.name, phone)


class NurseAdministrator(Nurse, Administrator):
    """Staff member who has both nurse and administrator responsibilities."""

    def __init__(self, person_id, name):
        super().__init__(person_id, name)


class Doctor(Person):
    """A doctor with a specialty and an assigned nurse."""

    def __init__(self, person_id, name, specialty, assigned_nurse):
        super().__init__(person_id, name)

        if specialty is None or not str(specialty).strip():
            raise ValueError("Specialty cannot be blank.")
        if not isinstance(specialty, str):
            raise ValueError("Specialty must be a string.")
        specialty = specialty.strip()
        if not specialty:
            raise ValueError("Specialty cannot be blank.")
        if not any(character.isalpha() for character in specialty):
            raise ValueError("Specialty must contain at least one alphabetic character.")
        if not isinstance(assigned_nurse, Nurse):
            raise ValueError("Assigned nurse must be a Nurse instance.")

        self.specialty = str(specialty).strip()
        self.assigned_nurse = assigned_nurse


class PeopleRegistry:
    """Stores registered people by person ID."""

    def __init__(self):
        self.patients = {}
        self.nurses = {}
        self.doctors = {}
        self.administrators = {}

    def register_patient(self, patient):
        if not isinstance(patient, Patient):
            raise ValueError("Only Patient records can be registered.")

        if patient.person_id in self.patients:
            raise ValueError(f"Patient ID '{patient.person_id}' is already registered.")

        self.patients[patient.person_id] = patient

    def get_patient(self, person_id):
        if person_id is None or not str(person_id).strip():
            raise ValueError("Person ID cannot be blank.")

        patient_id = str(person_id).strip()
        if patient_id not in self.patients:
            raise ValueError(f"Unknown patient ID: '{patient_id}'.")

        return self.patients[patient_id]

    def list_patients(self):
        return list(self.patients.values())

    def register_nurse(self, nurse):
        if not isinstance(nurse, Nurse):
            raise ValueError("Only Nurse records can be registered.")

        if nurse.person_id in self.nurses:
            raise ValueError(f"Nurse ID '{nurse.person_id}' is already registered.")

        self.nurses[nurse.person_id] = nurse

    def register_administrator(self, administrator):
        if not isinstance(administrator, Administrator):
            raise ValueError("Only Administrator records can be registered.")

        if administrator.person_id in self.administrators:
            raise ValueError(
                f"Administrator ID '{administrator.person_id}' is already registered."
            )

        self.administrators[administrator.person_id] = administrator

    def register_nurse_administrator(self, staff):
        if not isinstance(staff, NurseAdministrator):
            raise ValueError("Only NurseAdministrator records can be registered.")

        if staff.person_id in self.nurses:
            raise ValueError(
                f"Nurse ID '{staff.person_id}' is already registered."
            )
        if staff.person_id in self.administrators:
            raise ValueError(
                f"Administrator ID '{staff.person_id}' is already registered."
            )

        self.nurses[staff.person_id] = staff
        self.administrators[staff.person_id] = staff

    def register_doctor(self, doctor):
        if not isinstance(doctor, Doctor):
            raise ValueError("Only Doctor records can be registered.")

        if doctor.person_id in self.doctors:
            raise ValueError(f"Doctor ID '{doctor.person_id}' is already registered.")

        nurse_id = doctor.assigned_nurse.person_id
        registered_nurse = self.nurses.get(nurse_id)
        if registered_nurse is None:
            raise ValueError(f"Nurse ID '{nurse_id}' is not registered.")
        if registered_nurse is not doctor.assigned_nurse:
            raise ValueError(
                f"Assigned nurse '{nurse_id}' must be the exact registered nurse object."
            )

        self.doctors[doctor.person_id] = doctor

    def get_nurse(self, person_id):
        if person_id is None or not str(person_id).strip():
            raise ValueError("Person ID cannot be blank.")

        nurse_id = str(person_id).strip()
        if nurse_id not in self.nurses:
            raise ValueError(f"Unknown nurse ID: '{nurse_id}'.")

        return self.nurses[nurse_id]

    def get_administrator(self, person_id):
        if person_id is None or not str(person_id).strip():
            raise ValueError("Person ID cannot be blank.")

        administrator_id = str(person_id).strip()
        if administrator_id not in self.administrators:
            raise ValueError(
                f"Unknown administrator ID: '{administrator_id}'."
            )

        return self.administrators[administrator_id]

    def get_doctor(self, person_id):
        if person_id is None or not str(person_id).strip():
            raise ValueError("Person ID cannot be blank.")

        doctor_id = str(person_id).strip()
        if doctor_id not in self.doctors:
            raise ValueError(f"Unknown doctor ID: '{doctor_id}'.")

        return self.doctors[doctor_id]

    def list_nurses(self):
        return list(self.nurses.values())

    def list_administrators(self):
        return list(self.administrators.values())

    def list_doctors(self):
        return list(self.doctors.values())


@dataclass(frozen=True)
class AvailabilityWindow:
    start: time
    end: time

    def __post_init__(self) -> None:
        if self.start >= self.end:
            raise ValueError("Availability window end must be after its start.")


@dataclass
class Appointment:
    patient_id: str
    doctor_id: str
    starts_at: datetime
    ends_at: datetime
    appointment_id: str = field(default_factory=lambda: str(uuid4()))
    status: str = "booked"

    def __post_init__(self) -> None:
        if not self.appointment_id.strip():
            raise ValueError("Appointment ID cannot be empty.")
        if not self.patient_id.strip():
            raise ValueError("Patient ID cannot be empty.")
        if not self.doctor_id.strip():
            raise ValueError("Doctor ID cannot be empty.")
        if self.starts_at.tzinfo is not None or self.ends_at.tzinfo is not None:
            raise ValueError("Appointments must use local, timezone-naive datetimes.")
        if self.ends_at <= self.starts_at:
            raise ValueError("Appointment end must be after its start.")

    def to_dict(self) -> Dict[str, str]:
        return {
            "appointment_id": self.appointment_id,
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "starts_at": self.starts_at.isoformat(),
            "ends_at": self.ends_at.isoformat(),
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> "Appointment":
        return cls(
            appointment_id=data["appointment_id"],
            patient_id=data["patient_id"],
            doctor_id=data["doctor_id"],
            starts_at=datetime.fromisoformat(data["starts_at"]),
            ends_at=datetime.fromisoformat(data["ends_at"]),
            status=data.get("status", "booked"),
        )