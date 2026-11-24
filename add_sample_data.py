"""Adds extra sample people, appointments, visit records, and prescriptions.

Run once from the project folder:   python3 add_sample_data.py
Uses the same validated backend as the app, so everything is saved to
data/clinic_data.json. Safe to run twice: it stops if the sample data is there.
"""

import sys
from datetime import date

from main import build_persistent_scheduling_services, load_or_seed_clinic
from services import ClinicService
from storage import DEFAULT_DATA_PATH


def add_sample_data(path=DEFAULT_DATA_PATH) -> str:
    clinic, warning = load_or_seed_clinic(path)
    if warning:
        print("Note:", warning)
    registry = clinic.registry
    if "P002" in registry.patients:
        return "Sample data is already there; nothing added."

    svc = ClinicService(clinic)

    # Staff: two nurses and one NurseAdministrator (dual role), one administrator.
    if "N002" not in registry.nurses:
        svc.register_nurse("Priya Nair", person_id="N002")
    if "N003" not in registry.nurses:
        svc.register_nurse("Jordan Brooks", person_id="N003")
    if "NA001" not in registry.nurses:  # may already exist in the starter data
        svc.register_nurse_administrator("Alex Rivera", person_id="NA001")
    if "A001" not in registry.administrators:
        svc.register_administrator("Sam Ortiz", person_id="A001")

    # Doctors, each with an assigned nurse (aggregation).
    if "D002" not in registry.doctors:
        svc.register_doctor("Dr. Chen", "Pediatrics", "N002", person_id="D002")
    if "D003" not in registry.doctors:
        svc.register_doctor("Dr. Okafor", "Cardiology", "N003", person_id="D003")
    if "D004" not in registry.doctors:
        svc.register_doctor("Dr. Nguyen", "Dermatology", "NA001", person_id="D004")

    # Patients.
    for pid, name, phone in (
        ("P002", "Liam Carter", "(214) 555-0142"),
        ("P003", "Sofia Hernandez", "972-555-0178"),
        ("P004", "Noah Kim", "469-555-0113"),
        ("P005", "Ava Johnson", "(817) 555-0166"),
        ("P006", "Ethan Brooks", "214-555-0190"),
    ):
        svc.register_patient(name, phone, person_id=pid)

    svc.add_care_note("N002", "P002", "Allergic to penicillin.")
    svc.add_care_note("NA001", "P003", "Prefers morning appointments.")
    svc.update_patient_contact_as_administrator("A001", "P004", "469-555-0114")

    # Appointments (booked through the normal conflict-checked path).
    load_slots, book = build_persistent_scheduling_services(clinic)

    def book_slot(patient_id, doctor_id, day, slot_index):
        slot = load_slots(doctor_id, day)[slot_index]
        return book(patient_id, doctor_id, *slot)

    a2 = book_slot("P002", "D002", date(2026, 11, 23), 2)
    a3 = book_slot("P003", "D003", date(2026, 11, 23), 4)
    a4 = book_slot("P004", "D004", date(2026, 11, 24), 1)
    book_slot("P005", "D001", date(2026, 11, 24), 3)
    cancelled = book_slot("P006", "D002", date(2026, 11, 24), 0)
    svc.cancel_appointment(cancelled.appointment_id)

    records = clinic.records
    records.update_summary(a2.appointment_id, "Ear infection; follow up in one week.")
    records.add_prescription(
        a2.appointment_id, "Amoxicillin", "250 mg", "Three times daily", 7,
        "Finish the full course.")
    records.record_interaction(
        "P002", "D002", "consultation", "Examined ears; discussed treatment.",
        a2.appointment_id)

    records.update_summary(a3.appointment_id, "Routine heart check; blood pressure slightly high.")
    records.add_prescription(
        a3.appointment_id, "Lisinopril", "10 mg", "Once daily", 30, "Take in the morning.")
    records.add_prescription(
        a3.appointment_id, "Aspirin", "81 mg", "Once daily", 30)
    records.record_interaction(
        "P003", "D003", "prescription_review", "Reviewed medications and dosage.",
        a3.appointment_id)

    records.update_summary(a4.appointment_id, "Mild eczema on both arms.")
    records.add_prescription(
        a4.appointment_id, "Hydrocortisone cream", "1% topical", "Twice daily", 14)
    records.record_interaction("P004", "D004", "phone_call", "Called to check on rash.")

    return "Sample data added and saved."


if __name__ == "__main__":
    print(add_sample_data())
    sys.exit(0)
