"""Application entry point and temporary in-memory demo data."""

from datetime import date, time

from appointment import book_appointment, get_available_slots
from models import (
    Appointment,
    AvailabilityWindow,
    Doctor,
    Nurse,
    Patient,
    PeopleRegistry,
)
from services import DEFAULT_WINDOW, ClinicService
from storage import DEFAULT_DATA_PATH, ClinicData, StorageError, load_clinic


APPOINTMENT_DURATION_MINUTES = 30


def seed_demo_people(registry: PeopleRegistry) -> None:
    """Add the sample people (Maya, Lee, Dr. Rao) to a registry."""
    patient = Patient("P001", "Maya Shah", "408-555-0100")
    nurse = Nurse("N001", "Lee")
    doctor = Doctor("D001", "Dr. Rao", "Family Medicine", nurse)

    registry.register_patient(patient)
    registry.register_nurse(nurse)
    registry.register_doctor(doctor)


def build_demo_registry() -> PeopleRegistry:
    """Create sample people (used by tests and by first-run seeding)."""
    registry = PeopleRegistry()
    seed_demo_people(registry)
    return registry


def build_demo_scheduling_services(registry: PeopleRegistry):
    appointment_records = {}
    availability_by_doctor = {
        doctor.person_id: [AvailabilityWindow(time(9, 0), time(17, 0))]
        for doctor in registry.list_doctors()
    }

    def load_available_slots(doctor_id, selected_date):
        doctor = registry.get_doctor(doctor_id)
        return get_available_slots(
            doctor_id=doctor.person_id,
            appointment_date=selected_date,
            availability=availability_by_doctor[doctor.person_id],
            appointments=appointment_records.values(),
            duration_minutes=APPOINTMENT_DURATION_MINUTES,
        )

    def save_appointment_in_memory(appointment: Appointment) -> None:
        # Replace this session-only store with storage.py when its API is ready.
        appointment_records[appointment.appointment_id] = appointment

    def book_selected_slot(patient_id, doctor_id, starts_at, ends_at):
        registry.get_patient(patient_id)
        registry.get_doctor(doctor_id)
        return book_appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            starts_at=starts_at,
            ends_at=ends_at,
            appointments=list(appointment_records.values()),
            save_appointment=save_appointment_in_memory,
        )

    return load_available_slots, book_selected_slot, appointment_records


def load_or_seed_clinic(path=DEFAULT_DATA_PATH):
    """Load saved data automatically; seed demo data on the very first run.

    Returns ``(clinic, warning)``. ``warning`` is None unless the saved file was
    unreadable (it is kept as a ``.corrupt-*`` backup) or could not be written.
    """
    warning = None
    try:
        clinic = load_clinic(path)
    except StorageError as error:
        warning = f"{error}\nStarting with fresh sample data."
        clinic = ClinicData(path)

    if not clinic.loaded_from_disk and not clinic.registry.list_doctors():
        seed_demo_people(clinic.registry)
    for doctor in clinic.registry.list_doctors():
        clinic.availability.setdefault(doctor.person_id, [DEFAULT_WINDOW])
    if not clinic.loaded_from_disk:
        try:
            clinic.save()
        except StorageError as error:
            warning = f"{warning}\n{error}" if warning else str(error)
    return clinic, warning


def build_persistent_scheduling_services(clinic: ClinicData):
    """Scheduling callbacks that read and write the shared, saved clinic data."""
    registry = clinic.registry

    def load_available_slots(doctor_id, selected_date):
        doctor = registry.get_doctor(doctor_id)
        return get_available_slots(
            doctor_id=doctor.person_id,
            appointment_date=selected_date,
            availability=clinic.availability.get(doctor.person_id, [DEFAULT_WINDOW]),
            appointments=clinic.appointments.values(),
            duration_minutes=APPOINTMENT_DURATION_MINUTES,
        )

    def book_selected_slot(patient_id, doctor_id, starts_at, ends_at):
        registry.get_patient(patient_id)
        registry.get_doctor(doctor_id)
        return book_appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            starts_at=starts_at,
            ends_at=ends_at,
            appointments=list(clinic.appointments.values()),
            save_appointment=clinic.save_appointment,
        )

    return load_available_slots, book_selected_slot


def build_home_summary(clinic: ClinicData, today=None) -> dict:
    """Numbers and today's appointments for the dashboard."""
    today = today or date.today()
    registry = clinic.registry
    service = ClinicService(clinic)
    todays = [
        a for a in service.list_appointments(include_cancelled=False)
        if a.starts_at.date() == today
    ]
    active_prescriptions = sum(
        len(clinic.records.list_prescriptions_for_patient(patient.person_id, active_only=True))
        for patient in registry.list_patients()
    )

    def name(lookup, person_id):
        try:
            return lookup(person_id).name
        except ValueError:
            return person_id

    return {
        "stats": [
            ("Patients", len(registry.list_patients())),
            ("Doctors", len(registry.list_doctors())),
            ("Appointments today", len(todays)),
            ("Active prescriptions", active_prescriptions),
        ],
        "today": [
            (
                f"{a.starts_at:%H:%M}",
                name(registry.get_patient, a.patient_id),
                name(registry.get_doctor, a.doctor_id),
                a.status.title(),
            )
            for a in todays
        ],
    }


def main() -> None:
    import tkinter as tk
    from tkinter import messagebox

    from gui import ClinicApp, DoctorAvailabilityScreen, VisitRecordsScreen
    from patients_staff_screen import PatientsStaffScreen
    from scheduling_screen import SchedulingScreen

    clinic, warning = load_or_seed_clinic()
    registry = clinic.registry
    service = ClinicService(clinic)  # pass to Patients & Staff / scheduling admin screens
    load_available_slots, book_selected_slot = build_persistent_scheduling_services(
        clinic
    )

    def make_scheduling_screen(parent, navigate):
        screen = SchedulingScreen(
            parent,
            navigate,
            on_load_slots=load_available_slots,
            on_book=book_selected_slot,
            persistence_notice=f"Bookings are saved to {clinic.path.name}.",
        )
        screen.set_patients(
            {patient.person_id: patient.name for patient in registry.list_patients()}
        )
        screen.set_doctors(
            {doctor.person_id: doctor.name for doctor in registry.list_doctors()}
        )
        return screen

    def make_visit_records_screen(parent, navigate):
        return VisitRecordsScreen(parent, navigate, clinic.records, registry)

    def make_availability_screen(parent, navigate):
        return DoctorAvailabilityScreen(parent, navigate, service, registry)

    def make_patients_staff_screen(parent, navigate):
        return PatientsStaffScreen(parent, navigate, service)

    root = tk.Tk()
    if warning:
        messagebox.showwarning("Saved data", warning, parent=root)
    ClinicApp(
        root,
        screen_factories={
            "scheduling": make_scheduling_screen,
            "availability": make_availability_screen,
            "visit_records": make_visit_records_screen,
            "patients_staff": make_patients_staff_screen,
        },
        stats_provider=lambda: build_home_summary(clinic),
    )
    root.mainloop()


if __name__ == "__main__":
    main()
