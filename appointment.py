"""Appointment domain model and scheduling rules for the clinic app."""

from datetime import date, datetime, timedelta
from typing import (
    Callable,
    Iterable,
    List,
    MutableSequence,
    Optional,
    Sequence,
    Tuple,
)

from models import Appointment, AvailabilityWindow


CANCELLED_STATUS = "cancelled"


class AppointmentConflictError(ValueError):
    """Raised when a patient or doctor already has an appointment in a time range."""


def _overlaps(
    starts_at: datetime,
    ends_at: datetime,
    other_starts_at: datetime,
    other_ends_at: datetime,
) -> bool:
    return starts_at < other_ends_at and other_starts_at < ends_at


def validate_no_conflicts(
    proposed: Appointment, appointments: Iterable[Appointment]
) -> None:
    for existing in appointments:
        if existing.status.lower() == CANCELLED_STATUS:
            continue
        if not _overlaps(
            proposed.starts_at, proposed.ends_at, existing.starts_at, existing.ends_at
        ):
            continue

        conflicts = []
        if existing.doctor_id == proposed.doctor_id:
            conflicts.append("Doctor is already booked during this time.")
        if existing.patient_id == proposed.patient_id:
            conflicts.append("Patient already has an appointment during this time.")
        if conflicts:
            raise AppointmentConflictError(" ".join(conflicts))


def get_available_slots(
    doctor_id: str,
    appointment_date: date,
    availability: Sequence[AvailabilityWindow],
    appointments: Iterable[Appointment],
    duration_minutes: int,
    slot_interval_minutes: Optional[int] = None,
) -> List[Tuple[datetime, datetime]]:
    if duration_minutes <= 0:
        raise ValueError("Appointment duration must be positive.")
    interval = (
        duration_minutes
        if slot_interval_minutes is None
        else slot_interval_minutes
    )
    if interval <= 0:
        raise ValueError("Slot interval must be positive.")

    duration = timedelta(minutes=duration_minutes)
    interval_delta = timedelta(minutes=interval)
    doctor_appointments = [
        item
        for item in appointments
        if item.doctor_id == doctor_id and item.status.lower() != CANCELLED_STATUS
    ]
    slots = set()

    for window in availability:
        starts_at = datetime.combine(appointment_date, window.start)
        window_end = datetime.combine(appointment_date, window.end)
        while starts_at + duration <= window_end:
            ends_at = starts_at + duration
            if not any(
                _overlaps(starts_at, ends_at, item.starts_at, item.ends_at)
                for item in doctor_appointments
            ):
                slots.add((starts_at, ends_at))
            starts_at += interval_delta

    return sorted(slots)


def book_appointment(
    patient_id: str,
    doctor_id: str,
    starts_at: datetime,
    ends_at: datetime,
    appointments: MutableSequence[Appointment],
    save_appointment: Callable[[Appointment], None],
) -> Appointment:
    appointment = Appointment(
        patient_id=patient_id,
        doctor_id=doctor_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    validate_no_conflicts(appointment, appointments)
    save_appointment(appointment)
    appointments.append(appointment)
    return appointment
