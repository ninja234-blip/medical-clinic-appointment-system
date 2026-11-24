"""Visit records, prescriptions, and doctor-patient interactions (Teammate 3).

Class hierarchy
---------------
RecordBase                      shared id-less base: created/updated timestamps
    Prescription                one medication ordered during a visit
    MedicalRecord               one visit record per appointment; AGGREGATES
                                Prescription objects
    DoctorPatientInteraction    an explicit doctor <-> patient contact

ClinicRecordService is the facade the GUI/main use. It validates every request
against the people registry and the appointment store, and it is transactional:
if saving fails, the in-memory change is rolled back and the error is raised so
the app never reports success for data that was not stored.

Nothing here imports tkinter or touches files; persistence is injected through
``save_callback`` (see storage.py).
"""

from contextlib import contextmanager
from datetime import datetime
from typing import Callable, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from models import Appointment, PeopleRegistry


CANCELLED_STATUS = "cancelled"

MAX_SUMMARY_LENGTH = 2000
MAX_NOTES_LENGTH = 2000
MAX_MEDICATION_LENGTH = 100
MAX_DOSAGE_LENGTH = 100
MAX_FREQUENCY_LENGTH = 100
MAX_INSTRUCTIONS_LENGTH = 500
MAX_DURATION_DAYS = 365

PRESCRIPTION_ACTIVE = "active"
PRESCRIPTION_DISCONTINUED = "discontinued"
PRESCRIPTION_STATUSES = (PRESCRIPTION_ACTIVE, PRESCRIPTION_DISCONTINUED)

INTERACTION_TYPES = (
    "consultation",
    "follow_up",
    "phone_call",
    "prescription_review",
    "referral",
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class RecordError(ValueError):
    """Raised when visit-record, prescription, or interaction data is invalid."""


class RecordNotFoundError(RecordError):
    """Raised when a visit record or prescription does not exist."""


class InvalidAppointmentError(RecordError):
    """Raised when an appointment is unknown, cancelled, or has missing people."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _clean_text(value, label: str, max_length: int, required: bool = True) -> str:
    if not isinstance(value, str):
        raise RecordError(f"{label} must be text.")
    cleaned = value.strip()
    if required and not cleaned:
        raise RecordError(f"{label} cannot be blank.")
    if len(cleaned) > max_length:
        raise RecordError(f"{label} cannot be longer than {max_length} characters.")
    return cleaned


def _clean_id(value, label: str) -> str:
    return _clean_text(value, label, 100)


def _clean_duration(value) -> int:
    if isinstance(value, bool):
        raise RecordError("Duration must be a whole number of days.")
    if isinstance(value, str):
        value = value.strip()
        if not value.isascii() or not value.isdigit():
            raise RecordError("Duration must be a whole number of days.")
        value = int(value)
    if not isinstance(value, int):
        raise RecordError("Duration must be a whole number of days.")
    if not 1 <= value <= MAX_DURATION_DAYS:
        raise RecordError(f"Duration must be between 1 and {MAX_DURATION_DAYS} days.")
    return value


def _clean_timestamp(value, label: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError as error:
            raise RecordError(f"{label} is not a valid ISO date/time.") from error
    if not isinstance(value, datetime):
        raise RecordError(f"{label} must be a date/time.")
    if value.tzinfo is not None:
        raise RecordError(f"{label} must be a local, timezone-naive date/time.")
    return value


# ---------------------------------------------------------------------------
# Domain classes
# ---------------------------------------------------------------------------
class RecordBase:
    """Base class giving every clinical record created/updated timestamps."""

    def __init__(self, created_at=None, updated_at=None):
        created = _clean_timestamp(
            created_at if created_at is not None else datetime.now(), "Created time"
        )
        updated = _clean_timestamp(
            updated_at if updated_at is not None else created, "Updated time"
        )
        if updated < created:
            raise RecordError("Updated time cannot be before created time.")
        self.created_at = created
        self.updated_at = updated

    def touch(self, when: Optional[datetime] = None) -> None:
        self.updated_at = _clean_timestamp(
            when if when is not None else datetime.now(), "Updated time"
        )

    def to_dict(self) -> Dict[str, str]:
        return {
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


class Prescription(RecordBase):
    """A single medication prescribed during a visit."""

    def __init__(
        self,
        medication,
        dosage,
        frequency,
        duration_days,
        instructions="",
        prescription_id=None,
        status=PRESCRIPTION_ACTIVE,
        created_at=None,
        updated_at=None,
    ):
        super().__init__(created_at, updated_at)
        self.prescription_id = (
            str(uuid4())
            if prescription_id is None
            else _clean_id(prescription_id, "Prescription ID")
        )
        self.medication = _clean_text(medication, "Medication", MAX_MEDICATION_LENGTH)
        self.dosage = _clean_text(dosage, "Dosage", MAX_DOSAGE_LENGTH)
        self.frequency = _clean_text(frequency, "Frequency", MAX_FREQUENCY_LENGTH)
        self.duration_days = _clean_duration(duration_days)
        self.instructions = _clean_text(
            instructions, "Instructions", MAX_INSTRUCTIONS_LENGTH, required=False
        )
        if status not in PRESCRIPTION_STATUSES:
            raise RecordError(
                "Prescription status must be one of: "
                + ", ".join(PRESCRIPTION_STATUSES)
                + "."
            )
        self.status = status

    @property
    def is_active(self) -> bool:
        return self.status == PRESCRIPTION_ACTIVE

    def update(
        self,
        medication=None,
        dosage=None,
        frequency=None,
        duration_days=None,
        instructions=None,
        when: Optional[datetime] = None,
    ) -> None:
        """Change any supplied fields. Everything is validated before anything
        is changed, so a bad value leaves the prescription untouched."""
        if all(
            value is None
            for value in (medication, dosage, frequency, duration_days, instructions)
        ):
            raise RecordError("No prescription changes were supplied.")

        new_values = {}
        if medication is not None:
            new_values["medication"] = _clean_text(
                medication, "Medication", MAX_MEDICATION_LENGTH
            )
        if dosage is not None:
            new_values["dosage"] = _clean_text(dosage, "Dosage", MAX_DOSAGE_LENGTH)
        if frequency is not None:
            new_values["frequency"] = _clean_text(
                frequency, "Frequency", MAX_FREQUENCY_LENGTH
            )
        if duration_days is not None:
            new_values["duration_days"] = _clean_duration(duration_days)
        if instructions is not None:
            new_values["instructions"] = _clean_text(
                instructions, "Instructions", MAX_INSTRUCTIONS_LENGTH, required=False
            )
        touched_at = _clean_timestamp(
            when if when is not None else datetime.now(), "Updated time"
        )

        for name, value in new_values.items():
            setattr(self, name, value)
        self.updated_at = touched_at

    def discontinue(self, when: Optional[datetime] = None) -> None:
        if not self.is_active:
            raise RecordError("This prescription is already discontinued.")
        touched_at = _clean_timestamp(
            when if when is not None else datetime.now(), "Updated time"
        )
        self.status = PRESCRIPTION_DISCONTINUED
        self.updated_at = touched_at

    def to_dict(self) -> Dict[str, object]:
        data = super().to_dict()
        data.update(
            {
                "prescription_id": self.prescription_id,
                "medication": self.medication,
                "dosage": self.dosage,
                "frequency": self.frequency,
                "duration_days": self.duration_days,
                "instructions": self.instructions,
                "status": self.status,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "Prescription":
        return cls(
            prescription_id=data["prescription_id"],
            medication=data["medication"],
            dosage=data["dosage"],
            frequency=data["frequency"],
            duration_days=data["duration_days"],
            instructions=data.get("instructions", ""),
            status=data.get("status", PRESCRIPTION_ACTIVE),
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
        )


class MedicalRecord(RecordBase):
    """The visit record for one appointment.

    Aggregation: a MedicalRecord *has* Prescription objects, and refers to its
    patient, doctor, and appointment by stable ID (not by embedding them).
    """

    def __init__(
        self,
        appointment_id,
        patient_id,
        doctor_id,
        summary="",
        prescriptions: Optional[Iterable[Prescription]] = None,
        record_id=None,
        created_at=None,
        updated_at=None,
    ):
        super().__init__(created_at, updated_at)
        self.record_id = (
            str(uuid4()) if record_id is None else _clean_id(record_id, "Record ID")
        )
        self.appointment_id = _clean_id(appointment_id, "Appointment ID")
        self.patient_id = _clean_id(patient_id, "Patient ID")
        self.doctor_id = _clean_id(doctor_id, "Doctor ID")
        self.summary = _clean_text(
            summary, "Summary", MAX_SUMMARY_LENGTH, required=False
        )
        self._prescriptions: List[Prescription] = []
        for prescription in prescriptions or ():
            self._append_prescription(prescription)

    @property
    def prescriptions(self) -> Tuple[Prescription, ...]:
        return tuple(self._prescriptions)

    def active_prescriptions(self) -> List[Prescription]:
        return [item for item in self._prescriptions if item.is_active]

    def _append_prescription(self, prescription) -> None:
        if not isinstance(prescription, Prescription):
            raise RecordError("Only Prescription objects can be added to a record.")
        if any(
            item.prescription_id == prescription.prescription_id
            for item in self._prescriptions
        ):
            raise RecordError(
                f"Prescription '{prescription.prescription_id}' is already on this record."
            )
        self._prescriptions.append(prescription)

    def update_summary(self, summary, when: Optional[datetime] = None) -> None:
        cleaned = _clean_text(summary, "Summary", MAX_SUMMARY_LENGTH)
        touched_at = _clean_timestamp(
            when if when is not None else datetime.now(), "Updated time"
        )
        self.summary = cleaned
        self.updated_at = touched_at

    def add_prescription(
        self, prescription: Prescription, when: Optional[datetime] = None
    ) -> Prescription:
        self._append_prescription(prescription)
        self.touch(when)
        return prescription

    def get_prescription(self, prescription_id) -> Prescription:
        wanted = str(prescription_id).strip() if prescription_id is not None else ""
        for item in self._prescriptions:
            if item.prescription_id == wanted:
                return item
        raise RecordNotFoundError(f"Unknown prescription ID: '{wanted}'.")

    def remove_prescription(
        self, prescription_id, when: Optional[datetime] = None
    ) -> Prescription:
        prescription = self.get_prescription(prescription_id)
        self._prescriptions.remove(prescription)
        self.touch(when)
        return prescription

    def to_dict(self) -> Dict[str, object]:
        data = super().to_dict()
        data.update(
            {
                "record_id": self.record_id,
                "appointment_id": self.appointment_id,
                "patient_id": self.patient_id,
                "doctor_id": self.doctor_id,
                "summary": self.summary,
                "prescriptions": [item.to_dict() for item in self._prescriptions],
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "MedicalRecord":
        return cls(
            record_id=data["record_id"],
            appointment_id=data["appointment_id"],
            patient_id=data["patient_id"],
            doctor_id=data["doctor_id"],
            summary=data.get("summary", ""),
            prescriptions=[Prescription.from_dict(p) for p in data["prescriptions"]],
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
        )


class DoctorPatientInteraction(RecordBase):
    """An explicit contact between one doctor and one patient.

    ``created_at`` is when the interaction happened. ``appointment_id`` is
    optional because some contacts (a phone call) are not tied to a visit.
    """

    def __init__(
        self,
        patient_id,
        doctor_id,
        interaction_type,
        notes,
        appointment_id=None,
        interaction_id=None,
        created_at=None,
        updated_at=None,
    ):
        super().__init__(created_at, updated_at)
        self.interaction_id = (
            str(uuid4())
            if interaction_id is None
            else _clean_id(interaction_id, "Interaction ID")
        )
        self.patient_id = _clean_id(patient_id, "Patient ID")
        self.doctor_id = _clean_id(doctor_id, "Doctor ID")

        normalized_type = _clean_text(interaction_type, "Interaction type", 50).lower()
        if normalized_type not in INTERACTION_TYPES:
            raise RecordError(
                "Interaction type must be one of: " + ", ".join(INTERACTION_TYPES) + "."
            )
        self.interaction_type = normalized_type
        self.notes = _clean_text(notes, "Interaction notes", MAX_NOTES_LENGTH)
        self.appointment_id = (
            None
            if appointment_id is None
            else _clean_id(appointment_id, "Appointment ID")
        )

    def to_dict(self) -> Dict[str, object]:
        data = super().to_dict()
        data.update(
            {
                "interaction_id": self.interaction_id,
                "patient_id": self.patient_id,
                "doctor_id": self.doctor_id,
                "interaction_type": self.interaction_type,
                "notes": self.notes,
                "appointment_id": self.appointment_id,
            }
        )
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, object]) -> "DoctorPatientInteraction":
        return cls(
            interaction_id=data["interaction_id"],
            patient_id=data["patient_id"],
            doctor_id=data["doctor_id"],
            interaction_type=data["interaction_type"],
            notes=data["notes"],
            appointment_id=data.get("appointment_id"),
            created_at=data["created_at"],
            updated_at=data.get("updated_at"),
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------
class ClinicRecordService:
    """Validated, transactional operations on visit records and interactions.

    ``appointments`` is the shared ``{appointment_id: Appointment}`` store that
    scheduling writes to. ``save_callback`` (no arguments) persists everything;
    if it raises, the change is rolled back and the exception propagates.
    """

    def __init__(
        self,
        registry: PeopleRegistry,
        appointments: Dict[str, Appointment],
        save_callback: Optional[Callable[[], None]] = None,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self._registry = registry
        self._appointments = appointments
        self._save_callback = save_callback
        self._clock = clock
        self._records: Dict[str, MedicalRecord] = {}  # keyed by appointment_id
        self._interactions: List[DoctorPatientInteraction] = []

    @property
    def registry(self) -> PeopleRegistry:
        return self._registry

    # -- persistence plumbing ------------------------------------------------
    def export_state(self) -> Dict[str, List[Dict[str, object]]]:
        return {
            "medical_records": [r.to_dict() for r in self._records.values()],
            "interactions": [i.to_dict() for i in self._interactions],
        }

    def import_state(self, state: Dict[str, List[Dict[str, object]]]) -> None:
        """Replace all records/interactions. Builds first, swaps only on success."""
        records: Dict[str, MedicalRecord] = {}
        for item in state.get("medical_records", []):
            record = MedicalRecord.from_dict(item)
            if record.appointment_id in records:
                raise RecordError(
                    f"Appointment '{record.appointment_id}' has more than one visit record."
                )
            records[record.appointment_id] = record
        interactions = [
            DoctorPatientInteraction.from_dict(item)
            for item in state.get("interactions", [])
        ]
        self._records = records
        self._interactions = interactions

    @contextmanager
    def _transaction(self):
        snapshot = self.export_state()
        try:
            yield
            if self._save_callback is not None:
                self._save_callback()
        except BaseException:
            self.import_state(snapshot)
            raise

    # -- lookups ------------------------------------------------------------
    def _require_appointment(self, appointment_id) -> Appointment:
        key = str(appointment_id).strip() if appointment_id is not None else ""
        if not key:
            raise InvalidAppointmentError("Appointment ID cannot be blank.")
        appointment = self._appointments.get(key)
        if appointment is None:
            raise InvalidAppointmentError(f"Unknown appointment ID: '{key}'.")
        return appointment

    def _require_editable_appointment(self, appointment_id) -> Appointment:
        appointment = self._require_appointment(appointment_id)
        if appointment.status.lower() == CANCELLED_STATUS:
            raise InvalidAppointmentError(
                "Cancelled appointments cannot have visit records changed."
            )
        try:
            self._registry.get_patient(appointment.patient_id)
            self._registry.get_doctor(appointment.doctor_id)
        except ValueError as error:
            raise InvalidAppointmentError(
                f"Appointment {appointment.appointment_id} refers to someone who is "
                f"not registered: {error}"
            ) from error
        return appointment

    def list_recordable_appointments(self) -> List[Appointment]:
        """Non-cancelled appointments, soonest first (for the GUI's picker)."""
        return sorted(
            (
                item
                for item in self._appointments.values()
                if item.status.lower() != CANCELLED_STATUS
            ),
            key=lambda item: item.starts_at,
        )

    def find_record(self, appointment_id) -> Optional[MedicalRecord]:
        key = str(appointment_id).strip() if appointment_id is not None else ""
        return self._records.get(key)

    def get_record(self, appointment_id) -> MedicalRecord:
        record = self.find_record(appointment_id)
        if record is None:
            raise RecordNotFoundError(
                f"No visit record exists yet for appointment '{appointment_id}'."
            )
        return record

    def get_visit_summary(self, appointment_id) -> Dict[str, object]:
        """Everything about one visit with readable names, proving the links
        between patient, doctor, nurse, appointment, and prescriptions."""
        appointment = self._require_appointment(appointment_id)
        try:
            patient = self._registry.get_patient(appointment.patient_id)
            doctor = self._registry.get_doctor(appointment.doctor_id)
        except ValueError as error:
            raise InvalidAppointmentError(str(error)) from error
        record = self.find_record(appointment.appointment_id)
        return {
            "appointment_id": appointment.appointment_id,
            "status": appointment.status,
            "starts_at": appointment.starts_at,
            "ends_at": appointment.ends_at,
            "patient_id": patient.person_id,
            "patient_name": patient.name,
            "doctor_id": doctor.person_id,
            "doctor_name": doctor.name,
            "nurse_id": doctor.assigned_nurse.person_id,
            "nurse_name": doctor.assigned_nurse.name,
            "summary": record.summary if record else "",
            "prescriptions": (
                [item.to_dict() for item in record.prescriptions] if record else []
            ),
        }

    # -- visit record operations ----------------------------------------------
    def get_or_create_record(self, appointment_id) -> MedicalRecord:
        existing = self.find_record(appointment_id)
        if existing is not None:
            return existing
        appointment = self._require_editable_appointment(appointment_id)
        with self._transaction():
            record = MedicalRecord(
                appointment_id=appointment.appointment_id,
                patient_id=appointment.patient_id,
                doctor_id=appointment.doctor_id,
                created_at=self._clock(),
            )
            self._records[record.appointment_id] = record
        return self._records[appointment.appointment_id]

    def update_summary(self, appointment_id, summary) -> MedicalRecord:
        appointment = self._require_editable_appointment(appointment_id)
        with self._transaction():
            record = self._ensure_record(appointment)
            record.update_summary(summary, when=self._clock())
        return self._records[appointment.appointment_id]

    def add_prescription(
        self,
        appointment_id,
        medication,
        dosage,
        frequency,
        duration_days,
        instructions="",
    ) -> Prescription:
        appointment = self._require_editable_appointment(appointment_id)
        with self._transaction():
            record = self._ensure_record(appointment)
            now = self._clock()
            prescription = Prescription(
                medication,
                dosage,
                frequency,
                duration_days,
                instructions,
                created_at=now,
            )
            record.add_prescription(prescription, when=now)
        return self._records[appointment.appointment_id].get_prescription(
            prescription.prescription_id
        )

    def update_prescription(self, appointment_id, prescription_id, **changes) -> Prescription:
        appointment = self._require_editable_appointment(appointment_id)
        with self._transaction():
            record = self.get_record(appointment.appointment_id)
            prescription = record.get_prescription(prescription_id)
            prescription.update(when=self._clock(), **changes)
            record.touch(self._clock())
        return self._records[appointment.appointment_id].get_prescription(prescription_id)

    def discontinue_prescription(self, appointment_id, prescription_id) -> Prescription:
        appointment = self._require_editable_appointment(appointment_id)
        with self._transaction():
            record = self.get_record(appointment.appointment_id)
            record.get_prescription(prescription_id).discontinue(when=self._clock())
            record.touch(self._clock())
        return self._records[appointment.appointment_id].get_prescription(prescription_id)

    def remove_prescription(self, appointment_id, prescription_id) -> None:
        appointment = self._require_editable_appointment(appointment_id)
        with self._transaction():
            self.get_record(appointment.appointment_id).remove_prescription(
                prescription_id, when=self._clock()
            )

    def _ensure_record(self, appointment: Appointment) -> MedicalRecord:
        """Inside a transaction: fetch the appointment's record or create it."""
        record = self._records.get(appointment.appointment_id)
        if record is None:
            record = MedicalRecord(
                appointment_id=appointment.appointment_id,
                patient_id=appointment.patient_id,
                doctor_id=appointment.doctor_id,
                created_at=self._clock(),
            )
            self._records[appointment.appointment_id] = record
        return record

    # -- doctor <-> patient interactions --------------------------------------
    def record_interaction(
        self,
        patient_id,
        doctor_id,
        interaction_type,
        notes,
        appointment_id=None,
    ) -> DoctorPatientInteraction:
        try:
            patient = self._registry.get_patient(patient_id)
            doctor = self._registry.get_doctor(doctor_id)
        except ValueError as error:
            raise RecordError(str(error)) from error

        linked_appointment_id = None
        if appointment_id is not None and str(appointment_id).strip():
            appointment = self._require_appointment(appointment_id)
            if (
                appointment.patient_id != patient.person_id
                or appointment.doctor_id != doctor.person_id
            ):
                raise RecordError(
                    "That appointment belongs to a different patient or doctor."
                )
            linked_appointment_id = appointment.appointment_id

        with self._transaction():
            interaction = DoctorPatientInteraction(
                patient_id=patient.person_id,
                doctor_id=doctor.person_id,
                interaction_type=interaction_type,
                notes=notes,
                appointment_id=linked_appointment_id,
                created_at=self._clock(),
            )
            self._interactions.append(interaction)
        return interaction

    def list_interactions(
        self, patient_id: Optional[str] = None, doctor_id: Optional[str] = None
    ) -> List[DoctorPatientInteraction]:
        return sorted(
            (
                item
                for item in self._interactions
                if (patient_id is None or item.patient_id == patient_id)
                and (doctor_id is None or item.doctor_id == doctor_id)
            ),
            key=lambda item: item.created_at,
        )

    # -- queries for prescription tracking -----------------------------------
    def list_records_for_patient(self, patient_id) -> List[MedicalRecord]:
        try:
            patient = self._registry.get_patient(patient_id)
        except ValueError as error:
            raise RecordError(str(error)) from error
        return sorted(
            (r for r in self._records.values() if r.patient_id == patient.person_id),
            key=lambda r: self._appointments[r.appointment_id].starts_at
            if r.appointment_id in self._appointments
            else r.created_at,
        )

    def list_prescriptions_for_patient(
        self, patient_id, active_only: bool = False
    ) -> List[Tuple[str, Prescription]]:
        """(appointment_id, Prescription) pairs across all of a patient's visits."""
        return [
            (record.appointment_id, prescription)
            for record in self.list_records_for_patient(patient_id)
            for prescription in record.prescriptions
            if prescription.is_active or not active_only
        ]
