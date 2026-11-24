"""Application shell, dashboard, doctor availability, and visit-records screens."""

import tkinter as tk
from datetime import date, datetime, timedelta
from tkinter import messagebox, ttk
from typing import Callable, Dict, Iterable, List, Mapping, Optional

import theme
from appointment import CANCELLED_STATUS
from main import APPOINTMENT_DURATION_MINUTES
from scheduling_screen import SchedulingScreen
from storage import StorageError


ScreenFactory = Callable[[tk.Widget, Callable[[str], None]], tk.Widget]

NAV_ITEMS = (
    ("home", "Dashboard"),
    ("patients_staff", "Patients & Staff"),
    ("scheduling", "Scheduling & Booking"),
    ("availability", "Doctor Availability"),
    ("visit_records", "Records & Prescriptions"),
)

HOME_SHORTCUTS = (
    ("patients_staff", "Patients & Staff",
     "Register patients and staff, assign nurses, add care notes."),
    ("scheduling", "Scheduling & Booking",
     "Find an open time and book an appointment."),
    ("availability", "Doctor Availability",
     "See who is free or fully booked, and set working hours."),
    ("visit_records", "Records & Prescriptions",
     "Find visit records by patient, doctor, or nurse."),
)


# ---------------------------------------------------------------------------
# Pure helpers (no widgets, so they are easy to test)
# ---------------------------------------------------------------------------
def build_day_schedule(
    day: date,
    windows,
    appointments: Iterable,
    patient_names: Optional[Mapping[str, str]] = None,
    slot_minutes: int = APPOINTMENT_DURATION_MINUTES,
) -> List[dict]:
    """One row per bookable slot on ``day``: open, booked, or booked outside hours.

    ``windows`` are the doctor's AvailabilityWindows; ``appointments`` should be
    that doctor's appointments (cancelled ones are ignored here).
    """
    names = patient_names or {}
    step = timedelta(minutes=slot_minutes)
    rows: Dict[tuple, dict] = {}
    for window in windows:
        start = datetime.combine(day, window.start)
        end = datetime.combine(day, window.end)
        while start + step <= end:
            rows[(start, start + step)] = {
                "start": start, "end": start + step, "state": "open",
                "patient_id": None, "patient_name": "", "appointment_id": None,
            }
            start += step

    day_appointments = sorted(
        (
            a for a in appointments
            if a.status.lower() != CANCELLED_STATUS and a.starts_at.date() == day
        ),
        key=lambda a: a.starts_at,
    )
    for appointment in day_appointments:
        patient_name = names.get(appointment.patient_id, appointment.patient_id)
        touched = False
        for row in rows.values():
            if row["start"] < appointment.ends_at and appointment.starts_at < row["end"]:
                row.update(
                    state="booked", patient_id=appointment.patient_id,
                    patient_name=patient_name, appointment_id=appointment.appointment_id,
                )
                touched = True
        if not touched:  # booked outside the doctor's working hours
            rows[(appointment.starts_at, appointment.ends_at)] = {
                "start": appointment.starts_at, "end": appointment.ends_at,
                "state": "outside", "patient_id": appointment.patient_id,
                "patient_name": patient_name, "appointment_id": appointment.appointment_id,
            }
    return sorted(rows.values(), key=lambda r: (r["start"], r["end"]))


def describe_day(rows: List[dict], windows, day: date, now: Optional[datetime] = None):
    """Summarize a day as ``(kind, short_text, appointment_count, open_count)``.

    kind is "open" (can still be booked), "booked" (no time left because of
    appointments), or "off" (no working hours).
    """
    now = now or datetime.now()
    appointments = len({r["appointment_id"] for r in rows if r["appointment_id"]})
    open_rows = [
        r for r in rows
        if r["state"] == "open"
        and (day > now.date() or (day == now.date() and r["start"] >= now))
    ]
    if not windows:
        return "off", "Not working", appointments, 0
    if day < now.date():
        return "off", "Past day", appointments, 0
    if not open_rows:
        has_open_earlier = any(r["state"] == "open" for r in rows)
        if has_open_earlier:
            return "off", "Day is over", appointments, 0
        return "booked", "Fully booked", appointments, 0
    return "open", "Free from {:%H:%M}".format(open_rows[0]["start"]), appointments, len(open_rows)


def filter_visits(
    visits: Iterable[dict],
    text: str = "",
    patient_id: Optional[str] = None,
    doctor_id: Optional[str] = None,
    nurse_id: Optional[str] = None,
    when: str = "Any date",
    today: Optional[date] = None,
) -> List[dict]:
    """Narrow visit summaries by patient, doctor, nurse, date, and free text."""
    today = today or date.today()
    words = text.lower().split()
    result = []
    for visit in visits:
        if patient_id and visit["patient_id"] != patient_id:
            continue
        if doctor_id and visit["doctor_id"] != doctor_id:
            continue
        if nurse_id and visit["nurse_id"] != nurse_id:
            continue
        visit_day = visit["starts_at"].date()
        if when == "Today" and visit_day != today:
            continue
        if when == "Upcoming" and visit_day < today:
            continue
        if when == "Past" and visit_day >= today:
            continue
        if words:
            haystack = " ".join(
                [
                    visit["patient_name"], visit["patient_id"], visit["doctor_name"],
                    visit["doctor_id"], visit["nurse_name"], visit["nurse_id"],
                    visit["summary"],
                ]
                + [rx["medication"] for rx in visit["prescriptions"]]
            ).lower()
            if not all(word in haystack for word in words):
                continue
        result.append(visit)
    return result


def _label(person) -> str:
    return "{} [{}]".format(person.name, person.person_id)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
class HomeScreen(ttk.Frame):
    """Dashboard: today at a glance plus shortcuts to every section."""

    def __init__(self, master, on_navigate: Callable[[str], None], stats_provider=None) -> None:
        super().__init__(master, padding=(32, 26))
        summary = {}
        if stats_provider is not None:
            try:
                summary = stats_provider() or {}
            except Exception:  # the dashboard must never block the app from opening
                summary = {}

        now = datetime.now()
        greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 17 else "Good evening"
        theme.screen_header(
            self, greeting, "{:%A, %B %d, %Y}".format(now)
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 20))

        stats = ttk.Frame(self)
        stats.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 22))
        items = summary.get("stats", ())
        for column, (label, value) in enumerate(items):
            stats.columnconfigure(column, weight=1, uniform="stat")
            card = ttk.Frame(stats, style="Card.TFrame", padding=(18, 14))
            card.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 8, 0))
            ttk.Label(card, text=str(value), style="Stat.TLabel").pack(anchor="w")
            ttk.Label(card, text=label, style="CardMuted.TLabel").pack(anchor="w")

        today_panel = ttk.Frame(self)
        today_panel.grid(row=2, column=0, sticky="nsew", padx=(0, 24))
        today_panel.columnconfigure(0, weight=1)
        today_panel.rowconfigure(1, weight=1)
        ttk.Label(today_panel, text="Today's appointments", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        today = summary.get("today", ())
        if today:
            frame, table = theme.make_table(
                today_panel,
                (("time", "Time", 80, "w"), ("patient", "Patient", 170, "w"),
                 ("doctor", "Doctor", 150, "w"), ("status", "Status", 90, "w")),
                height=max(4, min(len(today), 12)),
            )
            for index, row in enumerate(today):
                table.insert("", "end", values=row, tags=("odd",) if index % 2 else ())
            frame.grid(row=1, column=0, sticky="new")
        else:
            empty = ttk.Frame(today_panel, style="Card.TFrame", padding=24)
            empty.grid(row=1, column=0, sticky="new")
            ttk.Label(empty, text="No appointments today.", style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(
                empty, text="Open Scheduling & Booking to book one.", style="CardMuted.TLabel"
            ).pack(anchor="w", pady=(2, 0))

        shortcuts = ttk.Frame(self)
        shortcuts.grid(row=2, column=1, sticky="nsew")
        shortcuts.columnconfigure(0, weight=1)
        ttk.Label(shortcuts, text="Go to", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        for row, (route, title, description) in enumerate(HOME_SHORTCUTS, start=1):
            self._shortcut_card(shortcuts, title, description, route, on_navigate).grid(
                row=row, column=0, sticky="ew", pady=(0, 10)
            )

        self.columnconfigure(0, weight=3)
        self.columnconfigure(1, weight=2, minsize=300)
        self.rowconfigure(2, weight=1)

    @staticmethod
    def _shortcut_card(parent, title, description, route, on_navigate):
        card = ttk.Frame(parent, style="Card.TFrame", padding=(16, 12))
        title_label = ttk.Label(card, text=title, style="CardTitle.TLabel")
        title_label.pack(anchor="w")
        body = ttk.Label(card, text=description, style="CardMuted.TLabel", wraplength=300)
        body.pack(anchor="w", pady=(2, 0))
        widgets = (card, title_label, body)

        def inside(widget) -> bool:
            while widget is not None:
                if widget is card:
                    return True
                widget = getattr(widget, "master", None)
            return False

        def hover(_event=None):
            card.configure(style="CardHover.TFrame")
            title_label.configure(style="CardHoverTitle.TLabel")
            body.configure(style="CardHoverMuted.TLabel")

        def unhover(event=None):
            if event is not None:
                under = card.winfo_containing(event.x_root, event.y_root)
                if inside(under):
                    return
            card.configure(style="Card.TFrame")
            title_label.configure(style="CardTitle.TLabel")
            body.configure(style="CardMuted.TLabel")

        for widget in widgets:
            widget.bind("<Enter>", hover)
            widget.bind("<Leave>", unhover)
            widget.bind("<Button-1>", lambda _e, r=route: on_navigate(r))
            widget.configure(cursor="hand2")
        return card


# ---------------------------------------------------------------------------
# Doctor availability
# ---------------------------------------------------------------------------
class DoctorAvailabilityScreen(ttk.Frame):
    """A doctor's day at a glance: open times, booked times, and working hours."""

    def __init__(self, master, on_navigate, clinic_service, registry) -> None:
        super().__init__(master, padding=(28, 22))
        self._service = clinic_service
        self._registry = registry
        self._selected_doctor_id: Optional[str] = None
        self._day: date = date.today()

        theme.screen_header(
            self, "Doctor Availability",
            "Pick a doctor and a day to see which times are open and which are taken by appointments.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 16))

        # Left: every doctor, with their status on the chosen day.
        left = ttk.Frame(self)
        left.grid(row=1, column=0, sticky="ns", padx=(0, 20))
        left.columnconfigure(0, minsize=300)
        left.rowconfigure(1, weight=1)
        ttk.Label(left, text="Doctors", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        list_frame, self.doctor_list = theme.make_table(
            left, (("name", "Doctor", 120, "w"), ("status", "On this day", 150, "w")),
            height=5,
        )
        list_frame.grid(row=1, column=0, sticky="nsew")
        self.doctor_list.bind("<<TreeviewSelect>>", self._doctor_selected)
        ttk.Label(
            left, text="Red = fully booked   Green = open   Grey = off",
            style="Muted.TLabel", justify="left",
        ).grid(row=2, column=0, sticky="w", pady=(10, 0))

        # Right: the selected doctor's day.
        right = ttk.Frame(self)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)

        self.doctor_title = ttk.Label(right, text="", style="Section.TLabel")
        self.doctor_title.grid(row=0, column=0, sticky="w")
        self.doctor_subtitle = ttk.Label(right, text="", style="Muted.TLabel")
        self.doctor_subtitle.grid(row=1, column=0, sticky="w", pady=(0, 10))

        date_bar = ttk.Frame(right)
        date_bar.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(date_bar, text="Previous day", command=lambda: self._shift_day(-1)).pack(side="left")
        self.date_entry = ttk.Entry(date_bar, width=12, justify="center")
        self.date_entry.pack(side="left", padx=8)
        self.date_entry.bind("<Return>", self._date_submitted)
        ttk.Button(date_bar, text="Next day", command=lambda: self._shift_day(1)).pack(side="left")
        ttk.Button(date_bar, text="Today", command=lambda: self._set_day(date.today())).pack(
            side="left", padx=(8, 0)
        )

        self._week_frame = ttk.Frame(right)
        self._week_frame.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        self._day_buttons: List[ttk.Button] = []
        for column in range(7):
            self._week_frame.columnconfigure(column, weight=1, uniform="day")
            button = ttk.Button(self._week_frame, text="", style="Day.TButton")
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else 4, 0))
            self._day_buttons.append(button)

        schedule_box = ttk.Frame(right)
        schedule_box.grid(row=4, column=0, sticky="nsew")
        schedule_box.columnconfigure(0, weight=1)
        schedule_box.rowconfigure(1, weight=1)
        self.day_banner = ttk.Label(schedule_box, text="", style="BannerOff.TLabel")
        self.day_banner.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        schedule_frame, self.schedule_list = theme.make_table(
            schedule_box,
            (("time", "Time", 120, "w"), ("state", "Status", 150, "w"),
             ("detail", "Patient", 260, "w")),
            height=12,
        )
        schedule_frame.grid(row=1, column=0, sticky="nsew")

        window_panel = ttk.LabelFrame(left, text="Working hours (every day)", padding=10)
        window_panel.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        window_panel.columnconfigure(0, weight=1, uniform="hours")
        window_panel.columnconfigure(1, weight=1, uniform="hours")
        self.window_list = ttk.Treeview(
            window_panel, columns=("start", "end"), show="headings", height=3,
            selectmode="browse",
        )
        self.window_list.heading("start", text="Start")
        self.window_list.heading("end", text="End")
        self.window_list.column("start", width=100, anchor="center")
        self.window_list.column("end", width=100, anchor="center")
        self.window_list.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(window_panel, text="Start (HH:MM)", style="Clinic.Field.TLabel").grid(
            row=1, column=0, sticky="w", pady=(10, 0)
        )
        ttk.Label(window_panel, text="End (HH:MM)", style="Clinic.Field.TLabel").grid(
            row=1, column=1, sticky="w", padx=(8, 0), pady=(10, 0)
        )
        self.start_entry = ttk.Entry(window_panel, width=8)
        self.start_entry.grid(row=2, column=0, sticky="ew", pady=(2, 8))
        self.end_entry = ttk.Entry(window_panel, width=8)
        self.end_entry.grid(row=2, column=1, sticky="ew", padx=(8, 0), pady=(2, 8))
        ttk.Button(window_panel, text="Add hours", style="Primary.TButton", command=self.add_window).grid(
            row=3, column=0, sticky="ew"
        )
        ttk.Button(window_panel, text="Remove selected", command=self.remove_window).grid(
            row=3, column=1, sticky="ew", padx=(8, 0)
        )

        self.status_label = ttk.Label(self, text="", style="Status.TLabel")
        self.status_label.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._refresh_doctors()

    # -- data ---------------------------------------------------------------
    def _patient_names(self) -> Dict[str, str]:
        return {p.person_id: p.name for p in self._registry.list_patients()}

    def _doctor_day(self, doctor_id: str, day: date):
        windows = self._service.get_availability(doctor_id)
        appointments = self._service.list_appointments(
            doctor_id=doctor_id, include_cancelled=False
        )
        rows = build_day_schedule(day, windows, appointments, self._patient_names())
        return windows, rows, describe_day(rows, windows, day)

    # -- doctor list ----------------------------------------------------------
    def _refresh_doctors(self) -> None:
        children = self.doctor_list.get_children()
        if children:
            self.doctor_list.delete(*children)
        doctors = self._registry.list_doctors()
        for doctor in doctors:
            self.doctor_list.insert(
                "", "end", iid=doctor.person_id, values=(doctor.name, "")
            )
        if not doctors:
            self._selected_doctor_id = None
            self._refresh_windows()
            self.status_label.configure(text="Register a doctor before setting hours.")
            return
        self._refresh_doctor_statuses()
        self.doctor_list.selection_set(doctors[0].person_id)
        self._doctor_selected()

    def _refresh_doctor_statuses(self) -> None:
        for doctor in self._registry.list_doctors():
            if not self.doctor_list.exists(doctor.person_id):
                continue
            try:
                _windows, _rows, (kind, text, _appts, _open) = self._doctor_day(
                    doctor.person_id, self._day
                )
            except (ValueError, StorageError):
                kind, text = "off", "Unavailable"
            self.doctor_list.item(
                doctor.person_id,
                values=(doctor.name, text),
                tags=({"open": "open", "booked": "booked"}.get(kind, "off"),),
            )

    def _doctor_selected(self, _event=None) -> None:
        selection = self.doctor_list.selection()
        if not selection:
            return
        self._selected_doctor_id = selection[0]
        self._refresh_windows()

    # -- day navigation ---------------------------------------------------------
    def _shift_day(self, delta: int) -> None:
        self._set_day(self._day + timedelta(days=delta))

    def _set_day(self, day: date) -> None:
        self._day = day
        self._refresh_schedule()

    def _date_submitted(self, _event=None) -> None:
        try:
            day = date.fromisoformat(self.date_entry.get().strip())
        except ValueError:
            messagebox.showerror(
                "Availability", "Enter a valid date in YYYY-MM-DD format.", parent=self
            )
            return
        self._set_day(day)

    # -- the day view -------------------------------------------------------------
    def _refresh_schedule(self) -> None:
        self.date_entry.delete(0, "end")
        self.date_entry.insert(0, self._day.isoformat())
        self._refresh_doctor_statuses()
        self._refresh_week_strip()

        children = self.schedule_list.get_children()
        if children:
            self.schedule_list.delete(*children)
        doctor_id = self._selected_doctor_id
        if doctor_id is None:
            self.doctor_title.configure(text="")
            self.doctor_subtitle.configure(text="")
            self.day_banner.configure(text="Select a doctor to see their day.", style="BannerOff.TLabel")
            return
        try:
            doctor = self._registry.get_doctor(doctor_id)
            windows, rows, (kind, _text, appointments, open_count) = self._doctor_day(
                doctor_id, self._day
            )
        except (ValueError, StorageError) as error:
            messagebox.showerror("Availability", str(error), parent=self)
            return

        self.doctor_title.configure(text=doctor.name)
        self.doctor_subtitle.configure(
            text="{}  |  Nurse: {}".format(doctor.specialty, doctor.assigned_nurse.name)
        )
        day_text = "{:%A, %B %d}".format(self._day)
        plural = "" if appointments == 1 else "s"
        if kind == "booked" and self._day >= date.today():
            banner = "{} is fully booked on {} ({} appointment{}).".format(
                doctor.name, day_text, appointments, plural)
            style = "BannerBooked.TLabel"
        elif kind == "off" and not windows:
            banner = "{} has no working hours set, so no times can be booked.".format(doctor.name)
            if appointments:
                banner += " {} appointment{} already on this day.".format(appointments, plural)
            style = "BannerOff.TLabel"
        elif self._day < date.today():
            banner = "{} is in the past. {} appointment{} {} scheduled.".format(
                day_text, appointments, plural, "was" if appointments == 1 else "were")
            style = "BannerOff.TLabel"
        elif kind == "off":
            banner = "{} has no more open times on {} ({} appointment{}).".format(
                doctor.name, day_text, appointments, plural)
            style = "BannerOff.TLabel"
        else:
            banner = "{} appointment{} booked, {} time slot{} still open on {}.".format(
                appointments, plural, open_count, "" if open_count == 1 else "s", day_text)
            style = "BannerOpen.TLabel" if appointments == 0 else "BannerOff.TLabel"
        self.day_banner.configure(text=banner, style=style)

        for index, row in enumerate(rows):
            state = row["state"]
            if state == "open":
                status, tag = "Open", "open"
                detail = "Available to book" if self._day >= date.today() else "Past"
            elif state == "booked":
                status, tag = "Booked", "booked"
                detail = "{} ({})".format(row["patient_name"], row["patient_id"])
            else:
                status, tag = "Booked (outside hours)", "booked"
                detail = "{} ({})".format(row["patient_name"], row["patient_id"])
            self.schedule_list.insert(
                "", "end", iid="slot-{}".format(index),
                values=("{:%H:%M} - {:%H:%M}".format(row["start"], row["end"]), status, detail),
                tags=(tag,),
            )

    def _refresh_week_strip(self) -> None:
        week_start = self._day - timedelta(days=self._day.weekday())
        doctor_id = self._selected_doctor_id
        for offset, button in enumerate(self._day_buttons):
            day = week_start + timedelta(days=offset)
            caption = ""
            if doctor_id is not None:
                try:
                    _w, _rows, (kind, _t, appointments, _open) = self._doctor_day(doctor_id, day)
                    caption = (
                        "Full" if kind == "booked"
                        else "Off" if kind == "off" and appointments == 0
                        else "{} booked".format(appointments) if appointments
                        else "Free"
                    )
                except (ValueError, StorageError):
                    caption = ""
            button.configure(
                text="{:%a}\n{:%d %b}\n{}".format(day, day, caption),
                style="DaySel.TButton" if day == self._day else "Day.TButton",
                command=lambda d=day: self._set_day(d),
            )

    # -- working hours (unchanged behavior) -----------------------------------------
    def _refresh_windows(self) -> None:
        self.status_label.configure(text="")
        children = self.window_list.get_children()
        if children:
            self.window_list.delete(*children)
        if self._selected_doctor_id is None:
            self._refresh_schedule()
            return
        try:
            windows = self._service.get_availability(self._selected_doctor_id)
        except (ValueError, StorageError) as error:
            messagebox.showerror("Availability", str(error), parent=self)
            return
        for index, window in enumerate(windows):
            self.window_list.insert(
                "", "end", iid=str(index),
                values=(window.start.strftime("%H:%M"), window.end.strftime("%H:%M")),
            )
        if not windows:
            self.status_label.configure(text="No working hours are set for this doctor.")
        self._refresh_schedule()

    def add_window(self) -> None:
        if self._selected_doctor_id is None:
            messagebox.showerror("Availability", "Select a doctor first.", parent=self)
            return
        try:
            self._service.add_availability_window(
                self._selected_doctor_id,
                self.start_entry.get(),
                self.end_entry.get(),
            )
        except (ValueError, StorageError) as error:
            messagebox.showerror("Availability not saved", str(error), parent=self)
            return
        self.start_entry.delete(0, "end")
        self.end_entry.delete(0, "end")
        self._refresh_windows()
        self.status_label.configure(text="Doctor availability saved.")

    def remove_window(self) -> None:
        if self._selected_doctor_id is None:
            messagebox.showerror("Availability", "Select a doctor first.", parent=self)
            return
        selection = self.window_list.selection()
        if not selection:
            messagebox.showerror(
                "Availability", "Select a working-hour window to remove.", parent=self
            )
            return
        try:
            self._service.remove_availability_window(
                self._selected_doctor_id, int(selection[0])
            )
        except (ValueError, StorageError) as error:
            messagebox.showerror("Availability not saved", str(error), parent=self)
            return
        self._refresh_windows()
        self.status_label.configure(text="Doctor availability saved.")


# ---------------------------------------------------------------------------
# Visit records & prescriptions
# ---------------------------------------------------------------------------
class VisitRecordsScreen(ttk.Frame):
    """Find a visit by patient, doctor, or nurse; edit its summary and prescriptions."""

    ANY_PATIENT = "All patients"
    ANY_DOCTOR = "All doctors"
    ANY_NURSE = "All nurses"
    WHEN_CHOICES = ("Any date", "Today", "Upcoming", "Past")

    def __init__(self, master, on_navigate, records_service, registry=None) -> None:
        super().__init__(master, padding=(28, 22))
        self._records = records_service
        self._registry = registry if registry is not None else getattr(records_service, "registry", None)
        self._visits: List[dict] = []
        self._visits_by_id: Dict[str, dict] = {}
        self._patient_ids: Dict[str, str] = {}
        self._doctor_ids: Dict[str, str] = {}
        self._nurse_ids: Dict[str, str] = {}
        self._selected_appointment_id: Optional[str] = None
        self._selected_prescription_id: Optional[str] = None

        theme.screen_header(
            self, "Records & Prescriptions",
            "Search by name, ID, or medication, or filter by patient, doctor, nurse, and date. Then open a visit to review or update it.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        self._build_filters()

        body = ttk.Frame(self)
        body.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(14, 0))
        body.columnconfigure(0, weight=6, uniform="records")
        body.columnconfigure(1, weight=5, uniform="records")
        body.rowconfigure(0, weight=1)
        self._build_results(body)
        self._build_detail(body)

        self.status_label = ttk.Label(self, text="Changes are saved automatically.", style="Status.TLabel")
        self.status_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(10, 0))
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)
        self._fill_filter_choices()
        self.refresh_appointments()

    # -- layout -----------------------------------------------------------------
    def _build_filters(self) -> None:
        bar = ttk.Frame(self, style="Card.TFrame", padding=(16, 12))
        bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        for column, weight in enumerate((3, 3, 2, 2, 2)):
            bar.columnconfigure(column, weight=weight, uniform="filters")

        ttk.Label(bar, text="Search", style="CardField.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.search_entry = ttk.Entry(bar, width=1)
        self.search_entry.grid(row=1, column=0, sticky="ew", padx=(0, 10), pady=(4, 0))
        self.search_entry.bind("<KeyRelease>", self._apply_filters)

        self.patient_filter = self._filter_box(bar, "Patient", 1, width=21)
        self.doctor_filter = self._filter_box(bar, "Doctor", 2, width=17)
        self.nurse_filter = self._filter_box(bar, "Nurse", 3, width=17)
        self.when_filter = self._filter_box(bar, "When", 4, width=8)
        self.when_filter["values"] = self.WHEN_CHOICES
        self.when_filter.set(self.WHEN_CHOICES[0])
        ttk.Button(bar, text="Clear", command=self.clear_filters).grid(
            row=1, column=5, sticky="e", pady=(4, 0)
        )

    def _filter_box(self, parent, text, column, width=None):
        ttk.Label(parent, text=text, style="CardField.TLabel").grid(
            row=0, column=column, sticky="w"
        )
        box = ttk.Combobox(parent, state="readonly", width=1)
        box.grid(row=1, column=column, sticky="ew", padx=(0, 10), pady=(4, 0))
        box.bind("<<ComboboxSelected>>", self._apply_filters)
        return box

    def _build_results(self, body) -> None:
        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(left)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        visits_tab = ttk.Frame(self.notebook, padding=(0, 10, 0, 0))
        self.notebook.add(visits_tab, text="Visits")
        visits_tab.columnconfigure(0, weight=1)
        visits_tab.rowconfigure(1, weight=1)
        self.count_label = ttk.Label(visits_tab, text="", style="Muted.TLabel")
        self.count_label.grid(row=0, column=0, sticky="w", pady=(0, 6))
        visits_frame, self.visit_table = theme.make_table(
            visits_tab,
            (("when", "Date & time", 125, "w"), ("patient", "Patient", 110, "w"),
             ("doctor", "Doctor", 95, "w"), ("nurse", "Nurse", 95, "w"),
             ("rx", "Rx", 36, "center")),
            height=12,
        )
        visits_frame.grid(row=1, column=0, sticky="nsew")
        self.visit_table.bind("<<TreeviewSelect>>", self._visit_selected)
        ttk.Label(
            visits_tab, text="Grey rows have no summary or prescriptions yet.",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

        rx_tab = ttk.Frame(self.notebook, padding=(0, 10, 0, 0))
        self.notebook.add(rx_tab, text="All prescriptions")
        rx_tab.columnconfigure(0, weight=1)
        rx_tab.rowconfigure(1, weight=1)
        top = ttk.Frame(rx_tab)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.rx_count_label = ttk.Label(top, text="", style="Muted.TLabel")
        self.rx_count_label.pack(side="left")
        self.active_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            top, text="Active only", variable=self.active_only,
            command=self._fill_prescription_tab,
        ).pack(side="right")
        rx_frame, self.rx_table = theme.make_table(
            rx_tab,
            (("medication", "Medication", 100, "w"), ("dosage", "Dosage", 72, "w"),
             ("frequency", "Frequency", 90, "w"), ("status", "Status", 65, "w"),
             ("patient", "Patient", 100, "w"), ("doctor", "Doctor", 80, "w")),
            height=12,
        )
        rx_frame.grid(row=1, column=0, sticky="nsew")
        self.rx_table.bind("<Double-1>", self._open_prescription_visit)
        self.rx_table.bind("<Return>", self._open_prescription_visit)
        ttk.Label(
            rx_tab, text="Double-click a prescription to open its visit.", style="Muted.TLabel"
        ).grid(row=2, column=0, sticky="w", pady=(6, 0))

    def _build_detail(self, body) -> None:
        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(12, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        head = ttk.Frame(right, style="Card.TFrame", padding=(16, 12))
        head.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.detail_title = ttk.Label(head, text="No visit selected", style="CardTitle.TLabel")
        self.detail_title.pack(anchor="w")
        self.appointment_details = ttk.Label(
            head, text="Select a visit from the list to view its record.",
            style="CardMuted.TLabel", wraplength=480, justify="left",
        )
        self.appointment_details.pack(anchor="w", pady=(2, 0))

        self.detail_notebook = ttk.Notebook(right)
        self.detail_notebook.grid(row=1, column=0, sticky="nsew")

        summary_panel = ttk.Frame(self.detail_notebook, padding=(0, 12, 0, 0))
        self.detail_notebook.add(summary_panel, text="Visit summary")
        summary_panel.columnconfigure(0, weight=1)
        summary_panel.rowconfigure(0, weight=1)
        self.summary_text = tk.Text(summary_panel, height=8, wrap="word")
        theme.style_text(self.summary_text)
        summary_scrollbar = ttk.Scrollbar(
            summary_panel, orient="vertical", command=self.summary_text.yview
        )
        self.summary_text.configure(yscrollcommand=summary_scrollbar.set)
        self.summary_text.grid(row=0, column=0, sticky="nsew")
        summary_scrollbar.grid(row=0, column=1, sticky="ns")
        ttk.Button(
            summary_panel, text="Save summary", style="Primary.TButton", command=self.save_summary
        ).grid(row=1, column=0, columnspan=2, sticky="e", pady=(10, 0))

        prescription_panel = ttk.Frame(self.detail_notebook, padding=(0, 12, 0, 0))
        self.detail_notebook.add(prescription_panel, text="Prescriptions")
        prescription_panel.columnconfigure(0, weight=1)
        prescription_panel.columnconfigure(1, weight=1)
        prescription_panel.rowconfigure(0, weight=1)
        self.prescription_list = ttk.Treeview(
            prescription_panel,
            columns=("medication", "dosage", "frequency", "duration", "status"),
            show="headings", height=4, selectmode="browse",
        )
        for column, heading, width in (
            ("medication", "Medication", 110), ("dosage", "Dosage", 75),
            ("frequency", "Frequency", 95), ("duration", "Days", 50), ("status", "Status", 85),
        ):
            self.prescription_list.heading(column, text=heading, anchor="w")
            self.prescription_list.column(column, width=width, minwidth=40, anchor="w")
        self.prescription_list.grid(row=0, column=0, columnspan=2, sticky="nsew")
        self.prescription_list.bind("<<TreeviewSelect>>", self._prescription_selected)
        theme.style_tree(self.prescription_list)

        self._prescription_fields = {}
        layout = (
            ("medication", "Medication", 1, 0, 1), ("dosage", "Dosage", 1, 1, 1),
            ("frequency", "Frequency", 3, 0, 1), ("duration_days", "Duration (days)", 3, 1, 1),
            ("instructions", "Instructions", 5, 0, 2),
        )
        for key, label, row, column, span in layout:
            ttk.Label(prescription_panel, text=label, style="Clinic.Field.TLabel").grid(
                row=row, column=column, sticky="w", pady=(8, 0),
                padx=(0 if column == 0 else 8, 0),
            )
            entry = ttk.Entry(prescription_panel)
            entry.grid(
                row=row + 1, column=column, columnspan=span, sticky="ew", pady=(2, 0),
                padx=(0 if column == 0 else 8, 0),
            )
            self._prescription_fields[key] = entry

        buttons = ttk.Frame(prescription_panel)
        buttons.grid(row=7, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="New", command=self.new_prescription).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(buttons, text="Discontinue", command=self.discontinue_prescription).pack(
            side="left", padx=(0, 8)
        )
        ttk.Button(
            buttons, text="Save prescription", style="Primary.TButton",
            command=self.save_prescription,
        ).pack(side="left")

    # -- filters --------------------------------------------------------------------
    def _fill_filter_choices(self) -> None:
        registry = self._registry
        patients = registry.list_patients() if registry else []
        doctors = registry.list_doctors() if registry else []
        nurses = registry.list_nurses() if registry else []
        self._patient_ids = {_label(p): p.person_id for p in patients}
        self._doctor_ids = {_label(d): d.person_id for d in doctors}
        self._nurse_ids = {_label(n): n.person_id for n in nurses}
        for box, any_label, ids in (
            (self.patient_filter, self.ANY_PATIENT, self._patient_ids),
            (self.doctor_filter, self.ANY_DOCTOR, self._doctor_ids),
            (self.nurse_filter, self.ANY_NURSE, self._nurse_ids),
        ):
            box["values"] = (any_label,) + tuple(ids)
            box.set(any_label)

    def clear_filters(self) -> None:
        self.search_entry.delete(0, "end")
        self.patient_filter.set(self.ANY_PATIENT)
        self.doctor_filter.set(self.ANY_DOCTOR)
        self.nurse_filter.set(self.ANY_NURSE)
        self.when_filter.set(self.WHEN_CHOICES[0])
        self._apply_filters()

    def _shown_visits(self) -> List[dict]:
        return filter_visits(
            self._visits,
            text=self.search_entry.get(),
            patient_id=self._patient_ids.get(self.patient_filter.get()),
            doctor_id=self._doctor_ids.get(self.doctor_filter.get()),
            nurse_id=self._nurse_ids.get(self.nurse_filter.get()),
            when=self.when_filter.get() or self.WHEN_CHOICES[0],
        )

    def _apply_filters(self, _event=None) -> None:
        shown = self._shown_visits()
        children = self.visit_table.get_children()
        if children:
            self.visit_table.delete(*children)
        for visit in shown:
            self.visit_table.insert(
                "", "end", iid=visit["appointment_id"],
                values=self._visit_row(visit), tags=self._visit_tags(visit),
            )
        if self._selected_appointment_id and self.visit_table.exists(self._selected_appointment_id):
            self.visit_table.selection_set(self._selected_appointment_id)
        total = len(self._visits)
        if total == 0:
            self.count_label.configure(text="No booked appointments yet.")
        elif not shown:
            self.count_label.configure(text="No visits match these filters (0 of {}).".format(total))
        else:
            self.count_label.configure(text="Showing {} of {} visits".format(len(shown), total))
        self._fill_prescription_tab()

    @staticmethod
    def _visit_row(visit: dict):
        return (
            "{:%Y-%m-%d %H:%M}".format(visit["starts_at"]),
            visit["patient_name"], visit["doctor_name"], visit["nurse_name"],
            len(visit["prescriptions"]),
        )

    @staticmethod
    def _visit_tags(visit: dict):
        return () if (visit["summary"] or visit["prescriptions"]) else ("muted",)

    def _fill_prescription_tab(self) -> None:
        children = self.rx_table.get_children()
        if children:
            self.rx_table.delete(*children)
        active_only = self.active_only.get()
        count = 0
        for visit in self._shown_visits():
            for rx in visit["prescriptions"]:
                if active_only and rx["status"] != "active":
                    continue
                count += 1
                self.rx_table.insert(
                    "", "end", iid="{}|{}".format(visit["appointment_id"], rx["prescription_id"]),
                    values=(
                        rx["medication"], rx["dosage"], rx["frequency"],
                        rx["status"].title(), visit["patient_name"], visit["doctor_name"],
                    ),
                    tags=("muted",) if rx["status"] != "active" else (),
                )
        self.rx_count_label.configure(
            text="{} prescription{}".format(count, "" if count == 1 else "s")
        )

    # -- loading ----------------------------------------------------------------------
    def refresh_appointments(self) -> None:
        self._visits = []
        for appointment in self._records.list_recordable_appointments():
            try:
                self._visits.append(self._records.get_visit_summary(appointment.appointment_id))
            except (ValueError, StorageError):
                continue
        self._visits.sort(key=lambda v: v["starts_at"], reverse=True)
        self._visits_by_id = {v["appointment_id"]: v for v in self._visits}
        self._apply_filters()
        if not self._visits:
            self._selected_appointment_id = None
            self._clear_visit()
            self.appointment_details.configure(
                text="No booked appointments are available for visit records."
            )
            self.status_label.configure(text="")
            return
        first = self.visit_table.get_children()
        if first:
            self.visit_table.selection_set(first[0])
            self._load_visit(first[0])

    def _visit_selected(self, _event=None) -> None:
        selection = self.visit_table.selection()
        if not selection or selection[0] == self._selected_appointment_id:
            return
        self._load_visit(selection[0])

    def _open_prescription_visit(self, _event=None) -> None:
        selection = self.rx_table.selection()
        if not selection:
            return
        appointment_id, prescription_id = selection[0].split("|", 1)
        if self.visit_table.exists(appointment_id):
            self.visit_table.selection_set(appointment_id)
            self.visit_table.see(appointment_id)
        self._load_visit(appointment_id, prescription_id)
        self.notebook.select(0)
        self.detail_notebook.select(1)

    def _load_visit(self, appointment_id: str, prescription_id: Optional[str] = None) -> None:
        try:
            visit = self._records.get_visit_summary(appointment_id)
        except (ValueError, StorageError) as error:
            messagebox.showerror("Visit record", str(error), parent=self)
            return

        self._selected_appointment_id = appointment_id
        self._selected_prescription_id = None
        self.detail_title.configure(text="{} ({})".format(visit["patient_name"], visit["patient_id"]))
        self.appointment_details.configure(
            text=(
                "{starts_at:%A, %B %d, %Y at %H:%M}\n"
                "Doctor: {doctor_name} ({doctor_id})   Nurse: {nurse_name} ({nurse_id})\n"
                "Status: {status}"
            ).format(**visit)
        )
        self.summary_text.delete("1.0", "end")
        self.summary_text.insert("1.0", visit["summary"])
        self.prescription_list.delete(*self.prescription_list.get_children())
        for index, item in enumerate(visit["prescriptions"]):
            self.prescription_list.insert(
                "", "end", iid=item["prescription_id"],
                values=(item["medication"], item["dosage"], item["frequency"],
                        item["duration_days"], item["status"].title()),
                tags=("odd",) if index % 2 else (),
            )
        self.new_prescription(clear_status=False)
        if prescription_id and self.prescription_list.exists(prescription_id):
            self.prescription_list.selection_set(prescription_id)
            self.prescription_list.focus(prescription_id)
            self._prescription_selected()
        self._store_visit(visit)

    def _store_visit(self, visit: dict) -> None:
        """Keep the cached list (and its tables) in step with a just-loaded visit."""
        appointment_id = visit["appointment_id"]
        self._visits_by_id[appointment_id] = visit
        for index, cached in enumerate(self._visits):
            if cached["appointment_id"] == appointment_id:
                self._visits[index] = visit
        if self.visit_table.exists(appointment_id):
            self.visit_table.item(
                appointment_id, values=self._visit_row(visit), tags=self._visit_tags(visit)
            )
        self._fill_prescription_tab()

    # -- editing (behavior unchanged) ---------------------------------------------------
    def save_summary(self) -> None:
        if self._selected_appointment_id is None:
            messagebox.showerror("Visit record", "Select an appointment first.", parent=self)
            return
        try:
            self._records.update_summary(
                self._selected_appointment_id,
                self.summary_text.get("1.0", "end-1c"),
            )
        except (ValueError, StorageError) as error:
            messagebox.showerror("Summary not saved", str(error), parent=self)
            return
        try:
            self._store_visit(
                self._records.get_visit_summary(self._selected_appointment_id)
            )
        except (ValueError, StorageError):
            pass
        self.status_label.configure(text="Visit summary saved.")

    def new_prescription(self, clear_status: bool = True) -> None:
        self._selected_prescription_id = None
        self.prescription_list.selection_remove(
            *self.prescription_list.selection()
        )
        for field in self._prescription_fields.values():
            field.delete(0, "end")
        if clear_status:
            self.status_label.configure(text="Enter details for a new prescription.")

    def _prescription_selected(self, _event=None) -> None:
        selected = self.prescription_list.selection()
        if not selected:
            return
        prescription_id = selected[0]
        if _event is not None and prescription_id == self._selected_prescription_id:
            return  # a delayed event for a selection that is already loaded
        self._selected_prescription_id = prescription_id
        try:
            prescription = self._records.get_visit_summary(
                self._selected_appointment_id
            )["prescriptions"]
            item = next(
                value
                for value in prescription
                if value["prescription_id"] == prescription_id
            )
        except (StopIteration, ValueError, StorageError) as error:
            messagebox.showerror("Prescription", str(error), parent=self)
            return
        for key in ("medication", "dosage", "frequency", "duration_days", "instructions"):
            field = self._prescription_fields[key]
            field.delete(0, "end")
            field.insert(0, str(item[key]))
        self.status_label.configure(text="Editing selected prescription.")

    def save_prescription(self) -> None:
        if self._selected_appointment_id is None:
            messagebox.showerror("Prescription", "Select an appointment first.", parent=self)
            return
        values = {
            key: field.get().strip()
            for key, field in self._prescription_fields.items()
        }
        try:
            if self._selected_prescription_id is None:
                prescription = self._records.add_prescription(
                    self._selected_appointment_id,
                    values["medication"],
                    values["dosage"],
                    values["frequency"],
                    values["duration_days"],
                    values["instructions"],
                )
            else:
                prescription = self._records.update_prescription(
                    self._selected_appointment_id,
                    self._selected_prescription_id,
                    **values,
                )
        except (ValueError, StorageError) as error:
            messagebox.showerror("Prescription not saved", str(error), parent=self)
            return
        self._load_visit(
            self._selected_appointment_id,
            prescription.prescription_id,
        )
        self.status_label.configure(text="Prescription saved.")

    def discontinue_prescription(self) -> None:
        if self._selected_appointment_id is None or self._selected_prescription_id is None:
            messagebox.showerror(
                "Prescription", "Select a prescription to discontinue.", parent=self
            )
            return
        if not messagebox.askyesno(
            "Discontinue prescription",
            "Mark this prescription as discontinued? It will stay in the record.",
            parent=self,
        ):
            return
        try:
            self._records.discontinue_prescription(
                self._selected_appointment_id, self._selected_prescription_id
            )
        except (ValueError, StorageError) as error:
            messagebox.showerror("Prescription not changed", str(error), parent=self)
            return
        self._load_visit(self._selected_appointment_id, self._selected_prescription_id)
        self.status_label.configure(text="Prescription discontinued.")

    def _clear_visit(self) -> None:
        self._selected_prescription_id = None
        self.detail_title.configure(text="No visit selected")
        self.appointment_details.configure(text="")
        self.summary_text.delete("1.0", "end")
        self.prescription_list.delete(*self.prescription_list.get_children())
        self.new_prescription(clear_status=False)


# ---------------------------------------------------------------------------
# Application shell
# ---------------------------------------------------------------------------
class ClinicApp:
    def __init__(
        self,
        root: tk.Tk,
        screen_factories: Optional[Mapping[str, ScreenFactory]] = None,
        stats_provider: Optional[Callable[[], dict]] = None,
    ) -> None:
        self.root = root
        self.root.title("Medical Clinic Appointment System")
        self.root.geometry("1280x800")
        self.root.minsize(1040, 660)
        theme.configure_styles(root)
        self._stats_provider = stats_provider

        self._nav: Dict[str, tuple] = {}
        self._build_sidebar()
        self.container = ttk.Frame(root)
        self.container.pack(side="left", fill="both", expand=True)

        self._screen_factories: Dict[str, ScreenFactory] = {
            "home": lambda parent, navigate: HomeScreen(
                parent, navigate, stats_provider=self._stats_provider
            ),
            "scheduling": lambda parent, navigate: SchedulingScreen(
                parent, navigate
            ),
        }
        if screen_factories:
            if "home" in screen_factories:
                raise ValueError("The home route is reserved.")
            self._screen_factories.update(screen_factories)
        self._current_screen = None
        self.show_screen("home")

    def _build_sidebar(self) -> None:
        sidebar = tk.Frame(self.root, background=theme.SIDEBAR, width=250)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        brand = tk.Frame(sidebar, background=theme.SIDEBAR)
        brand.pack(fill="x", padx=20, pady=(26, 24))
        ttk.Label(brand, text="Medical Clinic", style="Brand.TLabel").pack(anchor="w")
        ttk.Label(brand, text="Appointment system", style="BrandSub.TLabel").pack(anchor="w")

        for route, label in NAV_ITEMS:
            row = tk.Frame(sidebar, background=theme.SIDEBAR)
            row.pack(fill="x", pady=1)
            indicator = tk.Frame(row, background=theme.SIDEBAR, width=4)
            indicator.pack(side="left", fill="y")
            button = ttk.Button(
                row, text=label, style="Sidebar.TButton", cursor="hand2",
                command=lambda r=route: self.show_screen(r),
            )
            button.pack(side="left", fill="x", expand=True)
            self._nav[route] = (indicator, button)

        ttk.Label(
            sidebar, text="Changes are saved automatically.", style="BrandSub.TLabel"
        ).pack(side="bottom", anchor="w", padx=20, pady=18)

    def _highlight(self, active: str) -> None:
        for route, (indicator, button) in self._nav.items():
            is_active = route == active
            indicator.configure(background=theme.ACCENT if is_active else theme.SIDEBAR)
            button.configure(style="SidebarActive.TButton" if is_active else "Sidebar.TButton")

    def register_screen(self, name: str, factory: ScreenFactory) -> None:
        if name == "home":
            raise ValueError("The home route is reserved.")
        self._screen_factories[name] = factory

    def show_screen(self, name: str) -> None:
        if self._current_screen is not None:
            self._current_screen.destroy()

        factory = self._screen_factories.get(name)
        if factory is None:
            screen = ttk.Frame(self.container, padding=32)
            theme.screen_header(
                screen, "Not connected yet", "This section has not been set up."
            ).pack(anchor="w")
            ttk.Button(
                screen, text="Back to dashboard", command=lambda: self.show_screen("home")
            ).pack(anchor="w", pady=16)
            self._current_screen = screen
        else:
            self._current_screen = factory(self.container, self.show_screen)

        self._current_screen.pack(fill="both", expand=True)
        self._highlight(name)
