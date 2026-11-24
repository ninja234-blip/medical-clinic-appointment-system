"""Patient and staff management screen."""

import tkinter as tk
from tkinter import messagebox, ttk

import theme
from models import NurseAdministrator
from storage import StorageError


class PatientsStaffScreen(ttk.Frame):
    """Stage 1 screen for registering, listing, and updating patients."""

    def __init__(self, master, on_navigate, clinic_service):
        super().__init__(master, padding=(28, 22))
        self._service = clinic_service
        self._selected_patient_id = None

        theme.screen_header(
            self, "Patients & Staff",
            "Register patients and staff, assign nurses, and record nursing and administrative duties.",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))

        self.notebook = ttk.Notebook(self)
        notebook = self.notebook
        notebook.grid(row=1, column=0, columnspan=2, sticky="nsew")
        tab = ttk.Frame(notebook, padding=(12, 12))
        notebook.add(tab, text="Patients")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(3, weight=1)

        ttk.Label(tab, text="Name", style="Clinic.Field.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 8)
        )
        self.name_entry = ttk.Entry(tab)
        self.name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(tab, text="Phone", style="Clinic.Field.TLabel").grid(
            row=1, column=0, sticky="w", padx=(0, 12), pady=(0, 12)
        )
        self.phone_entry = ttk.Entry(tab)
        self.phone_entry.grid(row=1, column=1, sticky="ew", pady=(0, 12))

        buttons = ttk.Frame(tab)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(0, 12))
        self.register_button = ttk.Button(
            buttons,
            text="Register Patient",
            style="Primary.TButton",
            command=self.register_patient,
        )
        self.register_button.pack(side="left", padx=(0, 8))
        self.update_button = ttk.Button(
            buttons,
            text="Update Selected Patient",
            command=self.update_selected_patient,
            state="disabled",
        )
        self.update_button.pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Clear", command=self.clear).pack(side="left")

        table_frame = ttk.Frame(tab)
        table_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        self.patient_table = ttk.Treeview(
            table_frame,
            columns=("patient_id", "name", "phone"),
            show="headings",
            height=10,
            selectmode="browse",
        )
        self.patient_table.heading("patient_id", text="Patient ID")
        self.patient_table.heading("name", text="Name")
        self.patient_table.heading("phone", text="Phone")
        self.patient_table.column("patient_id", width=100, anchor="center")
        self.patient_table.column("name", width=220, anchor="w")
        self.patient_table.column("phone", width=160, anchor="w")
        self.patient_table.grid(row=0, column=0, sticky="nsew")
        self.patient_table.bind("<<TreeviewSelect>>", self._patient_selected)

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.patient_table.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.patient_table.configure(yscrollcommand=scrollbar.set)

        self.status_label = ttk.Label(tab, text="", style="Status.TLabel")
        self.status_label.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.refresh_patients()
        self._build_staff_tab(notebook)
        self._build_duties_tab(notebook)
        notebook.bind("<<NotebookTabChanged>>", self._notebook_tab_changed)

    def _build_staff_tab(self, notebook) -> None:
        """Create staff registration, tables, and nurse reassignment controls."""
        staff_tab = ttk.Frame(notebook, padding=(12, 12))
        notebook.add(staff_tab, text="Staff")
        staff_tab.columnconfigure(0, weight=1)
        staff_tab.rowconfigure(1, weight=1)

        form = ttk.Frame(staff_tab)
        form.grid(row=0, column=0, sticky="ew")
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Name", style="Clinic.Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 8))
        self.staff_name_entry = ttk.Entry(form)
        self.staff_name_entry.grid(row=0, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="Role", style="Clinic.Field.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 12), pady=(0, 8))
        self.staff_role_choice = ttk.Combobox(form, values=("Nurse", "Doctor", "Administrator", "NurseAdministrator"), state="readonly")
        self.staff_role_choice.current(0)
        self.staff_role_choice.grid(row=1, column=1, sticky="ew", pady=(0, 8))
        self.staff_role_choice.bind("<<ComboboxSelected>>", self._staff_role_selected)

        ttk.Label(form, text="Specialty", style="Clinic.Field.TLabel").grid(row=2, column=0, sticky="w", padx=(0, 12), pady=(0, 8))
        self.staff_specialty_entry = ttk.Entry(form, state="disabled")
        self.staff_specialty_entry.grid(row=2, column=1, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="Assigned Nurse", style="Clinic.Field.TLabel").grid(row=3, column=0, sticky="w", padx=(0, 12), pady=(0, 8))
        self.staff_nurse_choice = ttk.Combobox(form, state="disabled")
        self.staff_nurse_choice.grid(row=3, column=1, sticky="ew", pady=(0, 8))

        staff_buttons = ttk.Frame(form)
        staff_buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(4, 10))
        ttk.Button(staff_buttons, text="Register Staff", style="Primary.TButton", command=self.register_staff).pack(side="left", padx=(0, 8))
        ttk.Button(staff_buttons, text="Clear", command=self.clear_staff).pack(side="left")

        tables = ttk.Frame(staff_tab)
        tables.grid(row=1, column=0, sticky="nsew")
        tables.columnconfigure(0, weight=1)
        tables.columnconfigure(1, weight=1)
        tables.rowconfigure(0, weight=1)

        staff_table_frame = ttk.LabelFrame(tables, text="Staff", padding=8)
        staff_table_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        staff_table_frame.columnconfigure(0, weight=1)
        staff_table_frame.rowconfigure(0, weight=1)
        self.staff_table = ttk.Treeview(staff_table_frame, columns=("id", "name", "role"), show="headings", height=7, selectmode="browse")
        for column, heading, width in (("id", "ID", 90), ("name", "Name", 150), ("role", "Role", 150)):
            self.staff_table.heading(column, text=heading)
            self.staff_table.column(column, width=width, anchor="w")
        self.staff_table.grid(row=0, column=0, sticky="nsew")
        staff_scroll = ttk.Scrollbar(staff_table_frame, orient="vertical", command=self.staff_table.yview)
        staff_scroll.grid(row=0, column=1, sticky="ns")
        staff_xscroll = ttk.Scrollbar(
            staff_table_frame, orient="horizontal", command=self.staff_table.xview
        )
        staff_xscroll.grid(row=1, column=0, sticky="ew")
        self.staff_table.configure(
            yscrollcommand=staff_scroll.set,
            xscrollcommand=staff_xscroll.set,
        )

        doctor_frame = ttk.LabelFrame(tables, text="Doctors", padding=8)
        doctor_frame.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        doctor_frame.columnconfigure(0, weight=1)
        doctor_frame.rowconfigure(0, weight=1)
        self.doctor_table = ttk.Treeview(doctor_frame, columns=("doctor_id", "doctor_name", "specialty", "nurse_id", "nurse_name"), show="headings", height=7, selectmode="browse")
        for column, heading, width in (("doctor_id", "Doctor ID", 90), ("doctor_name", "Name", 130), ("specialty", "Specialty", 110), ("nurse_id", "Assigned Nurse ID", 120), ("nurse_name", "Assigned Nurse Name", 150)):
            self.doctor_table.heading(column, text=heading)
            self.doctor_table.column(column, width=width, anchor="w")
        self.doctor_table.grid(row=0, column=0, sticky="nsew")
        doctor_scroll = ttk.Scrollbar(doctor_frame, orient="vertical", command=self.doctor_table.yview)
        doctor_scroll.grid(row=0, column=1, sticky="ns")
        doctor_xscroll = ttk.Scrollbar(
            doctor_frame, orient="horizontal", command=self.doctor_table.xview
        )
        doctor_xscroll.grid(row=1, column=0, sticky="ew")
        self.doctor_table.configure(
            yscrollcommand=doctor_scroll.set,
            xscrollcommand=doctor_xscroll.set,
        )
        self.doctor_table.bind("<<TreeviewSelect>>", self._doctor_selected)

        reassignment = ttk.Frame(staff_tab)
        reassignment.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        reassignment.columnconfigure(1, weight=1)
        ttk.Label(reassignment, text="Reassign Nurse", style="Clinic.Field.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.reassignment_nurse_choice = ttk.Combobox(reassignment, state="readonly")
        self.reassignment_nurse_choice.grid(row=0, column=1, sticky="ew")
        self.reassignment_nurse_choice.bind("<<ComboboxSelected>>", self._update_assign_button)
        self.assign_nurse_button = ttk.Button(reassignment, text="Assign Nurse", style="Primary.TButton", command=self.assign_nurse, state="disabled")
        self.assign_nurse_button.grid(row=0, column=2, padx=(12, 0))

        self.staff_status_label = ttk.Label(staff_tab, text="", style="Status.TLabel")
        self.staff_status_label.grid(row=3, column=0, sticky="w", pady=(10, 0))

        self._nurse_ids = {}
        self._reassignment_nurse_ids = {}
        self._selected_doctor_id = None
        self.refresh_staff()

    def _build_duties_tab(self, notebook) -> None:
        """Create nursing and administrative duty controls."""
        duties_tab = ttk.Frame(notebook, padding=(12, 12))
        notebook.add(duties_tab, text="Staff Duties")
        duties_tab.columnconfigure(0, weight=1)
        duties_tab.rowconfigure(1, weight=1)

        selection = ttk.Frame(duties_tab)
        selection.grid(row=0, column=0, sticky="ew")
        selection.columnconfigure(1, weight=1)
        ttk.Label(selection, text="Patient", style="Clinic.Field.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 12), pady=(0, 8)
        )
        self.duty_patient_choice = ttk.Combobox(selection, state="readonly")
        self.duty_patient_choice.grid(row=0, column=1, sticky="ew", pady=(0, 8))
        self.duty_patient_choice.bind("<<ComboboxSelected>>", self._duty_patient_selected)
        self.duty_phone_label = ttk.Label(selection, text="Current phone: ")
        self.duty_phone_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))

        body = ttk.Frame(duties_tab)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        nursing = ttk.LabelFrame(body, text="Nursing duty", padding=10)
        nursing.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        nursing.columnconfigure(0, weight=1)
        nursing.rowconfigure(3, weight=1)
        ttk.Label(nursing, text="Nurse", style="Clinic.Field.TLabel").grid(row=0, column=0, sticky="w")
        self.duty_nurse_choice = ttk.Combobox(nursing, state="readonly")
        self.duty_nurse_choice.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(nursing, text="Care note").grid(row=2, column=0, sticky="w")
        self.care_note_text = tk.Text(nursing, height=4, wrap="word")
        theme.style_text(self.care_note_text)
        self.care_note_text.grid(row=3, column=0, sticky="nsew", pady=(4, 8))
        ttk.Button(nursing, text="Add Care Note", style="Primary.TButton", command=self.add_care_note).grid(row=4, column=0, sticky="e")

        existing_notes = ttk.LabelFrame(nursing, text="Existing care notes", padding=6)
        existing_notes.grid(row=5, column=0, sticky="nsew", pady=(10, 0))
        existing_notes.columnconfigure(0, weight=1)
        existing_notes.rowconfigure(0, weight=1)
        self.care_notes_text = tk.Text(existing_notes, height=7, wrap="word", state="disabled")
        theme.style_text(self.care_notes_text)
        care_notes_scroll = ttk.Scrollbar(existing_notes, orient="vertical", command=self.care_notes_text.yview)
        self.care_notes_text.configure(yscrollcommand=care_notes_scroll.set)
        self.care_notes_text.grid(row=0, column=0, sticky="nsew")
        care_notes_scroll.grid(row=0, column=1, sticky="ns")

        administration = ttk.LabelFrame(body, text="Administrative duty", padding=10)
        administration.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        administration.columnconfigure(0, weight=1)
        ttk.Label(administration, text="Administrator", style="Clinic.Field.TLabel").grid(row=0, column=0, sticky="w")
        self.duty_administrator_choice = ttk.Combobox(administration, state="readonly")
        self.duty_administrator_choice.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        ttk.Label(administration, text="New Phone", style="Clinic.Field.TLabel").grid(row=2, column=0, sticky="w")
        self.new_phone_entry = ttk.Entry(administration)
        self.new_phone_entry.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(administration, text="Update Contact", style="Primary.TButton", command=self.update_duty_contact).grid(row=4, column=0, sticky="e")

        self.duty_status_label = ttk.Label(duties_tab, text="", style="Status.TLabel")
        self.duty_status_label.grid(row=2, column=0, sticky="w", pady=(10, 0))
        self._duty_patient_ids = {}
        self._duty_nurse_ids = {}
        self._duty_administrator_ids = {}
        self._selected_duty_patient_id = None
        self.refresh_duties()

    def _notebook_tab_changed(self, event) -> None:
        """Refresh duties dropdowns when Staff Duties becomes active."""
        notebook = event.widget
        try:
            if notebook.tab(notebook.select(), "text") == "Staff Duties":
                self.refresh_duties()
        except tk.TclError:
            return

    def refresh_duties(self) -> None:
        """Refresh duty dropdowns while preserving valid selections by ID."""
        old_patient_id = self._selected_duty_patient_id
        patients = self._service.registry.list_patients()
        patient_labels = tuple(f"{patient.name} [{patient.person_id}]" for patient in patients)
        self._duty_patient_ids = {
            f"{patient.name} [{patient.person_id}]": patient.person_id
            for patient in patients
        }
        self.duty_patient_choice["values"] = patient_labels

        patient_ids = {patient.person_id for patient in patients}
        if old_patient_id not in patient_ids:
            old_patient_id = None
        if old_patient_id is None:
            self.duty_patient_choice.set("")
            self._selected_duty_patient_id = None
            self.duty_phone_label.configure(text="Current phone: ")
            self._replace_care_notes([])
        else:
            label = next((label for label, patient_id in self._duty_patient_ids.items() if patient_id == old_patient_id), "")
            self.duty_patient_choice.set(label)
            self._selected_duty_patient_id = old_patient_id

        old_nurse_id = self._duty_nurse_ids.get(self.duty_nurse_choice.get())
        nurses = self._service.registry.list_nurses()
        nurse_labels = tuple(f"{nurse.name} [{nurse.person_id}]" for nurse in nurses)
        self._duty_nurse_ids = {
            f"{nurse.name} [{nurse.person_id}]": nurse.person_id
            for nurse in nurses
        }
        self.duty_nurse_choice["values"] = nurse_labels
        nurse_ids = {nurse.person_id for nurse in nurses}
        if old_nurse_id in nurse_ids:
            nurse_label = next((label for label, nurse_id in self._duty_nurse_ids.items() if nurse_id == old_nurse_id), "")
            self.duty_nurse_choice.set(nurse_label)
        else:
            self.duty_nurse_choice.set("")

        old_administrator_id = self._duty_administrator_ids.get(self.duty_administrator_choice.get())
        administrators = self._service.registry.list_administrators()
        administrator_labels = tuple(f"{administrator.name} [{administrator.person_id}]"
                                     for administrator in administrators)
        self._duty_administrator_ids = {
            f"{administrator.name} [{administrator.person_id}]": administrator.person_id
            for administrator in administrators
        }
        self.duty_administrator_choice["values"] = administrator_labels
        administrator_ids = {administrator.person_id for administrator in administrators}
        if old_administrator_id in administrator_ids:
            administrator_label = next((label for label, administrator_id in self._duty_administrator_ids.items() if administrator_id == old_administrator_id), "")
            self.duty_administrator_choice.set(administrator_label)
        else:
            self.duty_administrator_choice.set("")

        if old_patient_id is not None:
            self._load_duty_patient(old_patient_id)

    def _duty_patient_selected(self, _event=None) -> None:
        """Switch the active patient and clear pending duty inputs."""
        patient_id = self._duty_patient_ids.get(self.duty_patient_choice.get())
        self.care_note_text.delete("1.0", "end")
        self.new_phone_entry.delete(0, "end")
        self.duty_status_label.configure(text="")
        self._selected_duty_patient_id = patient_id
        if patient_id is None:
            self.duty_phone_label.configure(text="Current phone: ")
            self._replace_care_notes([])
            return
        self._load_duty_patient(patient_id)

    def _load_duty_patient(self, patient_id) -> None:
        """Load the selected patient's phone and care notes."""
        patient = self._service.registry.get_patient(patient_id)
        self.duty_phone_label.configure(text=f"Current phone: {patient.phone}")
        self._replace_care_notes(patient.care_notes)

    def _replace_care_notes(self, notes) -> None:
        """Replace the read-only care-notes text area."""
        self.care_notes_text.configure(state="normal")
        self.care_notes_text.delete("1.0", "end")
        for index, note in enumerate(notes):
            if index:
                self.care_notes_text.insert("end", "\n")
            self.care_notes_text.insert("end", note)
        self.care_notes_text.configure(state="disabled")

    def add_care_note(self) -> None:
        """Add a nursing note through the shared ClinicService."""
        self.duty_status_label.configure(text="")
        patient_id = self._selected_duty_patient_id
        nurse_id = self._duty_nurse_ids.get(self.duty_nurse_choice.get())
        note = self.care_note_text.get("1.0", "end-1c")
        if patient_id is None:
            messagebox.showerror("Care note", "Select a patient first.", parent=self)
            return
        if nurse_id is None:
            messagebox.showerror("Care note", "Select a nurse first.", parent=self)
            return
        try:
            self._service.add_care_note(nurse_id, patient_id, note)
        except (ValueError, StorageError) as error:
            messagebox.showerror("Care note not saved", str(error), parent=self)
            return
        self.care_note_text.delete("1.0", "end")
        self._load_duty_patient(patient_id)
        self.duty_status_label.configure(text="Care note added successfully.")

    def update_duty_contact(self) -> None:
        """Update patient phone through an administrator."""
        self.duty_status_label.configure(text="")
        patient_id = self._selected_duty_patient_id
        administrator_id = self._duty_administrator_ids.get(self.duty_administrator_choice.get())
        phone = self.new_phone_entry.get()
        if patient_id is None:
            messagebox.showerror("Patient contact", "Select a patient first.", parent=self)
            return
        if administrator_id is None:
            messagebox.showerror("Patient contact", "Select an administrator first.", parent=self)
            return
        try:
            self._service.update_patient_contact_as_administrator(administrator_id, patient_id, phone)
        except (ValueError, StorageError) as error:
            messagebox.showerror("Contact not updated", str(error), parent=self)
            return

        self.new_phone_entry.delete(0, "end")
        self._load_duty_patient(patient_id)
        self.refresh_patients()
        if self.patient_table.selection():
            self.patient_table.selection_remove(*self.patient_table.selection())
        self._selected_patient_id = None
        self.register_button.configure(state="normal")
        self.update_button.configure(state="disabled")
        self.name_entry.delete(0, "end")
        self.phone_entry.delete(0, "end")
        self.duty_status_label.configure(text="Patient contact updated successfully.")

    def _staff_role_selected(self, _event=None) -> None:
        """Enable Doctor-only fields only when a Doctor is selected and nurses exist."""
        is_doctor = self.staff_role_choice.get() == "Doctor"
        self.staff_specialty_entry.configure(
            state="normal" if is_doctor else "disabled"
        )
        self.staff_nurse_choice.configure(
            state="readonly"
            if is_doctor and getattr(self, "_nurse_ids", {})
            else "disabled"
        )

    def refresh_staff(self) -> None:
        """Refresh staff, nurse dropdowns, and doctor records from the registry."""
        nurses = self._service.registry.list_nurses()
        nurse_labels = tuple(f"{nurse.name} [{nurse.person_id}]" for nurse in nurses)
        self._nurse_ids = {
            f"{nurse.name} [{nurse.person_id}]": nurse.person_id
            for nurse in nurses
        }
        self._reassignment_nurse_ids = dict(self._nurse_ids)
        self.staff_nurse_choice["values"] = nurse_labels
        self.reassignment_nurse_choice["values"] = nurse_labels
        self.staff_nurse_choice.set("")
        self.reassignment_nurse_choice.set("")

        if not nurses:
            self.staff_status_label.configure(
                text="Register a nurse first before registering a doctor."
            )
        elif self.staff_status_label.cget("text") == "Register a nurse first before registering a doctor.":
            self.staff_status_label.configure(text="")
        self._staff_role_selected()

        for table in (self.staff_table, self.doctor_table):
            children = table.get_children()
            if children:
                table.delete(*children)

        seen_dual_role = set()
        staff_entries = []
        for nurse in self._service.registry.list_nurses():
            if isinstance(nurse, NurseAdministrator):
                staff_entries.append((nurse, "NurseAdministrator"))
                seen_dual_role.add(id(nurse))
            else:
                staff_entries.append((nurse, "Nurse"))
        for administrator in self._service.registry.list_administrators():
            if id(administrator) not in seen_dual_role:
                staff_entries.append((administrator, "Administrator"))

        for index, (staff, role) in enumerate(staff_entries):
            self.staff_table.insert(
                "", "end", iid=f"staff-{index}",
                values=(staff.person_id, staff.name, role),
            )

        self._doctor_row_ids = {}
        for index, doctor in enumerate(self._service.registry.list_doctors()):
            row_id = f"doctor-{index}-{doctor.person_id}"
            self._doctor_row_ids[row_id] = doctor.person_id
            self.doctor_table.insert(
                "", "end", iid=row_id,
                values=(
                    doctor.person_id,
                    doctor.name,
                    doctor.specialty,
                    doctor.assigned_nurse.person_id,
                    doctor.assigned_nurse.name,
                ),
            )

        self._selected_doctor_id = None
        self.assign_nurse_button.configure(state="disabled")

    def register_staff(self) -> None:
        """Dispatch registration to the role-specific service method."""
        role = self.staff_role_choice.get()
        name = self.staff_name_entry.get()
        self.staff_status_label.configure(text="")
        try:
            if not role or role not in ("Nurse", "Administrator", "NurseAdministrator", "Doctor"):
                raise ValueError("Select a supported staff role.")
            if role == "Nurse":
                self._service.register_nurse(name)
            elif role == "Administrator":
                self._service.register_administrator(name)
            elif role == "NurseAdministrator":
                self._service.register_nurse_administrator(name)
            elif role == "Doctor":
                if not self._service.registry.list_nurses():
                    raise ValueError("A nurse must be registered before registering a doctor.")
                nurse_id = self._nurse_ids.get(self.staff_nurse_choice.get())
                if nurse_id is None:
                    raise ValueError("Select an assigned nurse before registering the doctor.")
                self._service.register_doctor(name, self.staff_specialty_entry.get(), nurse_id)
        except (ValueError, StorageError) as error:
            messagebox.showerror("Staff not registered", str(error), parent=self)
            return

        self.clear_staff(clear_status=False)
        self.refresh_staff()
        self.staff_status_label.configure(text="Staff registered successfully.")

    def clear_staff(self, clear_status=True) -> None:
        """Clear staff form fields and selections."""
        self.staff_name_entry.delete(0, "end")
        self.staff_specialty_entry.configure(state="normal")
        self.staff_specialty_entry.delete(0, "end")
        self.staff_role_choice.current(0)
        self.staff_nurse_choice.set("")
        self.staff_specialty_entry.configure(state="disabled")
        self.staff_nurse_choice.configure(state="disabled")
        if clear_status:
            self.staff_status_label.configure(text="")

    def _doctor_selected(self, _event=None) -> None:
        """Remember the selected doctor and update reassignment availability."""
        selection = self.doctor_table.selection()
        self._selected_doctor_id = (
            self._doctor_row_ids.get(selection[0]) if selection else None
        )
        self._update_assign_button()

    def _update_assign_button(self, _event=None) -> None:
        """Enable assignment only with a selected doctor and nurse."""
        valid = (
            self._selected_doctor_id is not None
            and self.reassignment_nurse_choice.get() in self._reassignment_nurse_ids
        )
        self.assign_nurse_button.configure(state="normal" if valid else "disabled")

    def assign_nurse(self) -> None:
        """Reassign a nurse through the shared ClinicService."""
        self.staff_status_label.configure(text="")
        nurse_id = self._reassignment_nurse_ids.get(
            self.reassignment_nurse_choice.get()
        )
        if self._selected_doctor_id is None or nurse_id is None:
            return
        try:
            self._service.assign_nurse(self._selected_doctor_id, nurse_id)
        except (ValueError, StorageError) as error:
            messagebox.showerror("Nurse not assigned", str(error), parent=self)
            return
        self.refresh_staff()
        self.staff_status_label.configure(text="Nurse reassigned successfully.")

    def refresh_patients(self) -> None:
        """Reload rows from the shared PeopleRegistry."""
        children = self.patient_table.get_children()
        if children:
            self.patient_table.delete(*children)
        for patient in self._service.registry.list_patients():
            self.patient_table.insert(
                "",
                "end",
                iid=patient.person_id,
                values=(patient.person_id, patient.name, patient.phone),
            )

    def register_patient(self) -> None:
        """Register through ClinicService, which generates the patient ID."""
        self.status_label.configure(text="")
        if self._selected_patient_id is not None:
            return
        try:
            self._service.register_patient(self.name_entry.get(), self.phone_entry.get())
        except (ValueError, StorageError) as error:
            messagebox.showerror("Patient not registered", str(error), parent=self)
            return
        self.refresh_patients()
        self.clear()
        self.status_label.configure(text="Patient registered successfully.")

    def _patient_selected(self, _event=None) -> None:
        """Populate the form and remember the selected patient ID."""
        selection = self.patient_table.selection()
        if not selection:
            return
        patient_id = selection[0]
        patient = self._service.registry.get_patient(patient_id)
        self._selected_patient_id = patient_id
        self.name_entry.delete(0, "end")
        self.name_entry.insert(0, patient.name)
        self.phone_entry.delete(0, "end")
        self.phone_entry.insert(0, patient.phone)
        self.register_button.configure(state="disabled")
        self.update_button.configure(state="normal")

    def update_selected_patient(self) -> None:
        """Update the selected record through ClinicService."""
        self.status_label.configure(text="")
        if self._selected_patient_id is None:
            return
        try:
            self._service.update_patient(
                self._selected_patient_id,
                self.name_entry.get(),
                self.phone_entry.get(),
            )
        except (ValueError, StorageError) as error:
            messagebox.showerror("Patient not updated", str(error), parent=self)
            return
        self.refresh_patients()
        self.clear()
        self.status_label.configure(text="Patient updated successfully.")

    def clear(self) -> None:
        """Clear fields, table selection, and update state."""
        self.name_entry.delete(0, "end")
        self.phone_entry.delete(0, "end")
        selection = self.patient_table.selection()
        if selection:
            self.patient_table.selection_remove(*selection)
        self._selected_patient_id = None
        self.register_button.configure(state="normal")
        self.update_button.configure(state="disabled")
        self.status_label.configure(text="")
