# Medical Clinic Appointment System

A desktop clinic-management application built with Python, Tkinter, and JSON
storage.

## Features

- **Dashboard:** today's appointments, clinic totals, and shortcuts to each section.
- **Patients & Staff:** register and update patients; register nurses, doctors,
  administrators, and nurse-administrators; assign a nurse to a doctor; record
  nursing care notes; and update patient contact information as an administrator.
- **Scheduling & Booking:** find available 30-minute slots and book appointments.
  The system prevents overlapping appointments for a doctor or patient.
- **Doctor Availability:** view a doctor's daily schedule and add or remove
  working-hour windows. Availability windows repeat every day; weekday-specific
  schedules are not supported.
- **Records & Prescriptions:** search/filter visits, update visit summaries, and
  add, edit, or discontinue prescriptions.
- **Persistent data:** clinic information is loaded from and saved to JSON.

## Requirements

- Python 3.9 or newer
- Tkinter (included with most Python installers; on Ubuntu/Debian, install it
  with `sudo apt install python3-tk`)
- No third-party Python packages

## Run the application

Open the project folder (the folder containing `main.py`) in VS Code, or open a
terminal in that folder, then run:

```text
python main.py
```

In VS Code, you can also open `main.py` and select **Run**, or press **F5**.

## Clinic data

The application automatically loads and saves clinic information in
`data/clinic_data.json`. If that file does not exist, the application creates
starter clinic data on its first run.

To add the extra example people, appointments, visit records, and prescriptions,
run this once from the project folder:

```text
python add_sample_data.py
```

The sample-data script skips adding those examples if patient `P002` is already
present. To start over, remove `data/clinic_data.json` while the application is
closed; the next launch will create starter data again. This permanently
removes the saved clinic data, so keep a backup if you need it.

The included JSON file contains patient details and care notes. Use only
synthetic data in shared or public copies of the project.

## Run the tests

From the project folder, run:

```text
python -m unittest discover -v
```

## Project layout

| File | Purpose |
|---|---|
| `main.py` | Loads clinic data, wires services to screens, and launches the app. |
| `gui.py` | Dashboard/navigation, doctor availability, and visit-record screens. |
| `patients_staff_screen.py` | Patient, staff, and staff-duty interface. |
| `scheduling_screen.py` | Appointment search and booking interface. |
| `models.py` | People, appointment, and availability domain models. |
| `appointment.py` | Available-slot generation and appointment conflict checks. |
| `services.py` | Validated clinic operations, including registration and availability updates. |
| `records.py` | Visit records, prescriptions, and doctor-patient interaction data. |
| `storage.py` | JSON serialization, validation, loading, and saving. |
| `theme.py` | Shared Tkinter styles and UI helpers. |
| `add_sample_data.py` | Optional script for adding extra example records. |
| `test_*.py` | Unit and integration tests. |

## Current limitation

The records backend can store doctor-patient interactions, but the GUI does not
currently provide a dedicated screen or form for creating or viewing them.
