"""JSON persistence for the whole clinic (Teammate 3).

One file, ``data/clinic_data.json``, holds every collection. IDs link them:

    patients, nurses, administrators, nurse_administrators, doctors
        doctors store ``assigned_nurse_id`` (aggregation by ID)
    availability   {doctor_id: [{"start": "09:00", "end": "17:00"}, ...]}
    appointments   patient_id / doctor_id
    medical_records  appointment_id / patient_id / doctor_id + nested prescriptions
    interactions   patient_id / doctor_id / optional appointment_id

Loading is automatic: ``load_clinic()`` returns a ready ``ClinicData`` (empty on
first run). Saving is atomic: data is written to a temporary file and swapped
into place, so a crash mid-save cannot leave a half-written file.
"""

import json
import os
import tempfile
from datetime import datetime, time
from pathlib import Path
from typing import Dict, List, Optional

from models import (
    Administrator,
    Appointment,
    AvailabilityWindow,
    Doctor,
    Nurse,
    NurseAdministrator,
    Patient,
    PeopleRegistry,
)
from records import ClinicRecordService


SCHEMA_VERSION = 1
DEFAULT_DATA_PATH = Path(__file__).resolve().parent / "data" / "clinic_data.json"


class StorageError(Exception):
    """Raised when clinic data cannot be saved or loaded."""


class ClinicData:
    """Everything the app keeps: people, schedules, appointments, and records."""

    def __init__(
        self,
        path=DEFAULT_DATA_PATH,
        registry: Optional[PeopleRegistry] = None,
        appointments: Optional[Dict[str, Appointment]] = None,
        availability: Optional[Dict[str, List[AvailabilityWindow]]] = None,
        loaded_from_disk: bool = False,
    ) -> None:
        self.path = Path(path)
        self.registry = registry if registry is not None else PeopleRegistry()
        self.appointments = appointments if appointments is not None else {}
        self.availability = availability if availability is not None else {}
        self.loaded_from_disk = loaded_from_disk
        self.records = ClinicRecordService(
            self.registry, self.appointments, save_callback=self.save
        )

    def save(self) -> None:
        save_clinic(self)

    def save_appointment(self, appointment: Appointment) -> None:
        """Store one appointment and persist. If saving fails the appointment is
        removed again and the error is raised, so nothing is reported as booked."""
        self.appointments[appointment.appointment_id] = appointment
        try:
            self.save()
        except BaseException:
            self.appointments.pop(appointment.appointment_id, None)
            raise


# ---------------------------------------------------------------------------
# Saving
# ---------------------------------------------------------------------------
def clinic_to_dict(data: ClinicData) -> Dict[str, object]:
    registry = data.registry
    nurses, nurse_admins, admins = [], [], []
    for nurse in registry.list_nurses():
        entry = {"person_id": nurse.person_id, "name": nurse.name}
        (nurse_admins if isinstance(nurse, NurseAdministrator) else nurses).append(entry)
    for admin in registry.list_administrators():
        if not isinstance(admin, NurseAdministrator):
            admins.append({"person_id": admin.person_id, "name": admin.name})

    state = data.records.export_state()
    return {
        "schema_version": SCHEMA_VERSION,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "patients": [
            {
                "person_id": p.person_id,
                "name": p.name,
                "phone": p.phone,
                "care_notes": list(p.care_notes),
            }
            for p in registry.list_patients()
        ],
        "nurses": nurses,
        "administrators": admins,
        "nurse_administrators": nurse_admins,
        "doctors": [
            {
                "person_id": d.person_id,
                "name": d.name,
                "specialty": d.specialty,
                "assigned_nurse_id": d.assigned_nurse.person_id,
            }
            for d in registry.list_doctors()
        ],
        "availability": {
            doctor_id: [
                {
                    "start": w.start.isoformat(timespec="minutes"),
                    "end": w.end.isoformat(timespec="minutes"),
                }
                for w in windows
            ]
            for doctor_id, windows in data.availability.items()
        },
        "appointments": [
            a.to_dict()
            for a in sorted(data.appointments.values(), key=lambda a: a.starts_at)
        ],
        "medical_records": state["medical_records"],
        "interactions": state["interactions"],
    }


def save_clinic(data: ClinicData) -> None:
    """Write all clinic data to ``data.path`` atomically."""
    path = data.path
    try:
        text = json.dumps(clinic_to_dict(data), indent=2)
    except (TypeError, ValueError) as error:
        raise StorageError(f"Clinic data could not be converted to JSON: {error}") from error

    temp_name = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temp_name = tempfile.mkstemp(
            dir=path.parent, prefix=path.name + ".", suffix=".tmp"
        )
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except OSError as error:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise StorageError(f"Could not save clinic data to '{path}': {error}") from error


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _quarantine(path: Path) -> Optional[Path]:
    """Rename an unreadable data file so it is kept but never overwritten."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_name(f"{path.stem}.corrupt-{stamp}{path.suffix}")
    try:
        os.replace(path, backup)
    except OSError:
        return None
    return backup


def _build_clinic(raw: object, path: Path) -> ClinicData:
    if not isinstance(raw, dict):
        raise StorageError("The data file must contain a JSON object at the top level.")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise StorageError(
            f"Unsupported data version {raw.get('schema_version')!r}; "
            f"this program reads version {SCHEMA_VERSION}."
        )

    try:
        registry = PeopleRegistry()
        for item in raw.get("nurses", []):
            registry.register_nurse(Nurse(item["person_id"], item["name"]))
        for item in raw.get("administrators", []):
            registry.register_administrator(Administrator(item["person_id"], item["name"]))
        for item in raw.get("nurse_administrators", []):
            registry.register_nurse_administrator(
                NurseAdministrator(item["person_id"], item["name"])
            )
        for item in raw.get("patients", []):
            patient = Patient(item["person_id"], item["name"], item["phone"])
            notes = item.get("care_notes", [])
            if not isinstance(notes, list) or not all(isinstance(n, str) for n in notes):
                raise StorageError("Patient care notes must be a list of text.")
            patient.care_notes = list(notes)
            registry.register_patient(patient)
        for item in raw.get("doctors", []):
            nurse = registry.get_nurse(item["assigned_nurse_id"])
            registry.register_doctor(
                Doctor(item["person_id"], item["name"], item["specialty"], nurse)
            )

        availability: Dict[str, List[AvailabilityWindow]] = {}
        for doctor_id, windows in raw.get("availability", {}).items():
            registry.get_doctor(doctor_id)
            availability[doctor_id] = [
                AvailabilityWindow(
                    time.fromisoformat(w["start"]), time.fromisoformat(w["end"])
                )
                for w in windows
            ]

        appointments: Dict[str, Appointment] = {}
        for item in raw.get("appointments", []):
            appointment = Appointment.from_dict(item)
            if appointment.appointment_id in appointments:
                raise StorageError(
                    f"Duplicate appointment ID '{appointment.appointment_id}'."
                )
            registry.get_patient(appointment.patient_id)
            registry.get_doctor(appointment.doctor_id)
            appointments[appointment.appointment_id] = appointment

        clinic = ClinicData(
            path, registry, appointments, availability, loaded_from_disk=True
        )
        clinic.records.import_state(
            {
                "medical_records": raw.get("medical_records", []),
                "interactions": raw.get("interactions", []),
            }
        )
        _check_record_links(clinic)
        return clinic
    except StorageError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        raise StorageError(
            f"The data file is incomplete or invalid ({type(error).__name__}: {error})."
        ) from error


def _check_record_links(clinic: ClinicData) -> None:
    """Every record/interaction must point at people and appointments that exist."""
    state = clinic.records.export_state()
    for record in state["medical_records"]:
        appointment = clinic.appointments.get(record["appointment_id"])
        if appointment is None:
            raise StorageError(
                f"A visit record refers to missing appointment '{record['appointment_id']}'."
            )
        if (
            appointment.patient_id != record["patient_id"]
            or appointment.doctor_id != record["doctor_id"]
        ):
            raise StorageError(
                f"Visit record for appointment '{appointment.appointment_id}' does not "
                "match the appointment's patient and doctor."
            )
    for interaction in state["interactions"]:
        clinic.registry.get_patient(interaction["patient_id"])
        clinic.registry.get_doctor(interaction["doctor_id"])
        appointment_id = interaction.get("appointment_id")
        if appointment_id is not None and appointment_id not in clinic.appointments:
            raise StorageError(
                f"An interaction refers to missing appointment '{appointment_id}'."
            )


def load_clinic(path=DEFAULT_DATA_PATH) -> ClinicData:
    """Load saved clinic data automatically.

    * No file yet (first run) -> an empty ``ClinicData`` (``loaded_from_disk`` False).
    * Unreadable JSON or inconsistent data -> the file is renamed to
      ``*.corrupt-<time>.json`` (kept, not overwritten) and ``StorageError`` is raised.
    """
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except FileNotFoundError:
        return ClinicData(path)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        backup = _quarantine(path)
        kept = f" The damaged file was kept as '{backup.name}'." if backup else ""
        raise StorageError(f"The data file '{path.name}' is not valid JSON.{kept}") from error
    except OSError as error:
        raise StorageError(f"Could not read clinic data from '{path}': {error}") from error

    try:
        return _build_clinic(raw, path)
    except StorageError as error:
        backup = _quarantine(path)
        kept = f" The file was kept as '{backup.name}'." if backup else ""
        raise StorageError(f"{error}{kept}") from error
