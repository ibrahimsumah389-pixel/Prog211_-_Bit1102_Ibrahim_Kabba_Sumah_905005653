"""Patient Record System (PRS) - single-file version.

PROG211 Object-Oriented Programming 1 - Health domain.
Everything (classes, registry and menu program) is in this one file,
so it runs on its own with no extra folders or packages.

Run with:  python "Patient Record System.py"
"""

from __future__ import annotations

import csv
import re
import sys
from datetime import date
from pathlib import Path
from typing import (Callable, Dict, Iterator, NamedTuple, Optional, Tuple,
                    TypeVar, Union)



# =========================================================================== #
# PART 1: CLASSES (Patient, HealthWorker, Visit, VitalSigns)
# =========================================================================== #

DateInput = Union[date, str]  # a date object or text in YYYY-MM-DD format
Number = Union[int, float, str]  # numbers may arrive as text typed by a user

# Reference data is stored in tuples because it must never change while the
# program runs (immutable).
DISTRICTS: Tuple[str, ...] = (
    "Bo", "Bombali", "Bonthe", "Falaba", "Kailahun", "Kambia", "Karene",
    "Kenema", "Koinadugu", "Kono", "Moyamba", "Port Loko", "Pujehun",
    "Tonkolili", "Western Area Rural", "Western Area Urban",
)
SEXES: Tuple[str, ...] = ("Female", "Male", "Prefer not to say")
VISIT_TYPES: Tuple[str, ...] = (
    "Outpatient", "Follow-up", "Antenatal", "Immunisation", "Emergency",
)
DIAGNOSES: Tuple[str, ...] = (
    "Malaria", "Typhoid", "Respiratory infection", "Diarrhoeal disease",
    "Hypertension", "Diabetes", "Malnutrition", "Injury", "Routine check",
    "Other",
)
CHRONIC_CONDITIONS: Tuple[str, ...] = ("Hypertension", "Diabetes")
WORKER_ROLES: Tuple[str, ...] = (
    "Doctor", "Nurse", "Midwife", "Community Health Officer",
)
FIRST_VALID_DATE = date(2000, 1, 1)


def check_range(value: Number, name: str, low: float, high: float) -> float:
    """Convert ``value`` to a number and check it lies between low and high."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be a number.") from None
    if not low <= number <= high:
        raise ValueError(f"{name} must be between {low:g} and {high:g}.")
    return number


def match_option(value: str, options: Tuple[str, ...]) -> Optional[str]:
    """Return the option that matches ``value`` (ignoring case and extra
    spaces), or None. Used for districts, diagnoses, roles and so on."""
    cleaned = " ".join((value or "").split()).lower()
    for option in options:
        if option.lower() == cleaned:
            return option
    return None


# --------------------------------------------------------------------------- #
# Immutable records (tuples)
# --------------------------------------------------------------------------- #
class VitalSigns(NamedTuple):
    """Measurements taken at a visit. Blood pressure is optional because it is
    not measured at every visit (for example, infant immunisations)."""

    temperature_c: float
    weight_kg: float
    systolic: Optional[int] = None
    diastolic: Optional[int] = None

    def has_fever(self) -> bool:
        """A temperature of 38.0 °C or higher is recorded as a fever."""
        return self.temperature_c >= 38.0

    def bp_category(self) -> str:
        """Blood pressure category based on the American Heart Association
        adult ranges. Returns 'Not measured' if BP was not taken."""
        if self.systolic is None or self.diastolic is None:
            return "Not measured"
        s, d = self.systolic, self.diastolic
        if s > 180 or d > 120:
            return "Hypertensive crisis"
        if s >= 140 or d >= 90:
            return "High (stage 2)"
        if s >= 130 or d >= 80:
            return "High (stage 1)"
        if s >= 120:
            return "Elevated"
        return "Normal"

    def summary(self) -> str:
        """One readable line describing the vital signs."""
        bp = (
            f"{self.systolic}/{self.diastolic} mmHg - {self.bp_category()}"
            if self.systolic is not None and self.diastolic is not None
            else "BP not measured"
        )
        fever = " FEVER" if self.has_fever() else ""
        return f"{self.temperature_c:.1f} C{fever} | {self.weight_kg:g} kg | {bp}"


class Visit(NamedTuple):
    """One visit to a health facility. Immutable: once a visit is saved it
    cannot be edited, which protects the integrity of the medical record."""

    visit_date: date
    visit_type: str
    diagnosis: str
    vitals: VitalSigns
    worker_id: str


# --------------------------------------------------------------------------- #
# Patient
# --------------------------------------------------------------------------- #
class Patient:
    """A patient, identified by a pseudonymous code instead of a name."""

    ID_PREFIX = "PAT"
    MAX_AGE = 120
    _next_number = 1  # class attribute shared by every Patient object

    def __init__(self, age: Number, sex: str, district: str) -> None:
        clean_age = Patient.validate_age(age)
        clean_sex = Patient.normalise_sex(sex)
        if clean_sex is None:
            raise ValueError("Sex must be Female, Male or Prefer not to say (F/M/P).")
        clean_district = match_option(district, DISTRICTS)
        if clean_district is None:
            raise ValueError(f"Unknown district: '{district}'.")

        # The ID is only created after every check has passed.
        self.patient_id: str = Patient.generate_id()
        self.age: int = clean_age
        self.sex: str = clean_sex
        self.district: str = clean_district
        self._visits: Tuple[Visit, ...] = ()

    # ---- class methods ---------------------------------------------------- #
    @classmethod
    def generate_id(cls) -> str:
        """Create the next unique patient code, e.g. PAT-0001."""
        new_id = f"{cls.ID_PREFIX}-{cls._next_number:04d}"
        cls._next_number += 1
        return new_id

    @classmethod
    def reset_counter(cls) -> None:
        """Restart ID numbering (used by the automated tests)."""
        cls._next_number = 1

    @classmethod
    def from_tuple(cls, data: Tuple[Number, str, str]) -> "Patient":
        """Alternative constructor: build a Patient from (age, sex, district)."""
        age, sex, district = data
        return cls(age, sex, district)

    # ---- static methods --------------------------------------------------- #
    @staticmethod
    def validate_age(value: Number) -> int:
        """Check that an age is a whole number of years between 0 and 120."""
        text = str(value).strip()
        if not re.fullmatch(r"\d{1,3}", text):
            raise ValueError("Age must be a whole number of years, e.g. 34.")
        age = int(text)
        if age > Patient.MAX_AGE:
            raise ValueError(f"Age must be between 0 and {Patient.MAX_AGE}.")
        return age

    @staticmethod
    def normalise_sex(value: str) -> Optional[str]:
        """Accept full words or the shortcuts F, M and P."""
        shortcuts = {"f": "Female", "m": "Male", "p": "Prefer not to say"}
        cleaned = (value or "").strip().lower()
        return shortcuts.get(cleaned) or match_option(cleaned, SEXES)

    @staticmethod
    def age_group(age: int) -> str:
        """Standard public-health age bands used in reports."""
        if age < 5:
            return "0-4"
        if age < 15:
            return "5-14"
        if age < 25:
            return "15-24"
        if age < 45:
            return "25-44"
        if age < 65:
            return "45-64"
        return "65+"

    # ---- instance methods ------------------------------------------------- #
    @property
    def visits(self) -> Tuple[Visit, ...]:
        """All visits, oldest first (read-only tuple)."""
        return self._visits

    def add_visit(self, visit: Visit) -> None:
        """Add a visit to this patient's history, keeping date order.

        Normally called by ``HealthWorker.record_visit``, which validates the
        visit details first.
        """
        if not isinstance(visit, Visit):
            raise TypeError("visit must be a Visit record.")
        self._visits = tuple(sorted(self._visits + (visit,), key=lambda v: v.visit_date))

    def visit_count(self) -> int:
        """Number of recorded visits."""
        return len(self._visits)

    def latest_visit(self) -> Optional[Visit]:
        """The most recent visit, or None if the patient has no visits."""
        return self._visits[-1] if self._visits else None

    def has_condition(self, diagnosis: str) -> bool:
        """True if the diagnosis appears in any visit."""
        wanted = match_option(diagnosis, DIAGNOSES)
        return any(v.diagnosis == wanted for v in self._visits)

    def needs_follow_up(self) -> Tuple[str, ...]:
        """Reasons this patient should be followed up (empty if none).

        Based on the latest visit: fever, stage 2 or crisis blood pressure,
        or any chronic condition on record.
        """
        latest = self.latest_visit()
        if latest is None:
            return ()
        reasons: Tuple[str, ...] = ()
        if latest.vitals.has_fever():
            reasons += (f"fever ({latest.vitals.temperature_c:.1f} C)",)
        if latest.vitals.bp_category() in ("High (stage 2)", "Hypertensive crisis"):
            reasons += (f"blood pressure {latest.vitals.bp_category().lower()}",)
        reasons += tuple(
            f"chronic condition: {c}" for c in CHRONIC_CONDITIONS if self.has_condition(c)
        )
        return reasons

    def update_record(
        self, age: Optional[Number] = None, district: Optional[str] = None
    ) -> None:
        """Update age and/or district. All checks run before anything changes."""
        new_age = Patient.validate_age(age) if age is not None else self.age
        new_district = self.district
        if district is not None:
            matched = match_option(district, DISTRICTS)
            if matched is None:
                raise ValueError(f"Unknown district: '{district}'.")
            new_district = matched
        self.age, self.district = new_age, new_district

    def display_info(self, include_visits: bool = True) -> str:
        """Return a readable summary of the patient and their visit history."""
        lines: Tuple[str, ...] = (
            f"Patient {self.patient_id} | Age {self.age} ({Patient.age_group(self.age)})"
            f" | {self.sex} | {self.district} | Visits: {self.visit_count()}",
        )
        if include_visits:
            if not self._visits:
                lines += ("   No visits recorded yet.",)
            for v in self._visits:
                lines += (
                    f"   {v.visit_date.isoformat()} {v.visit_type:<12} {v.diagnosis:<22}"
                    f" by {v.worker_id}",
                    f"      Vitals: {v.vitals.summary()}",
                )
        return "\n".join(lines)

    def __repr__(self) -> str:
        return (
            f"Patient(patient_id={self.patient_id!r}, age={self.age!r}, "
            f"sex={self.sex!r}, district={self.district!r})"
        )


# --------------------------------------------------------------------------- #
# HealthWorker
# --------------------------------------------------------------------------- #
class HealthWorker:
    """A health worker who records patient visits, identified by staff code."""

    ID_PREFIX = "HW"
    _next_number = 1

    def __init__(self, role: str, district: str) -> None:
        clean_role = match_option(role, WORKER_ROLES)
        if clean_role is None:
            raise ValueError(f"Role must be one of: {', '.join(WORKER_ROLES)}.")
        clean_district = match_option(district, DISTRICTS)
        if clean_district is None:
            raise ValueError(f"Unknown district: '{district}'.")

        self.worker_id: str = HealthWorker.generate_id()
        self.role: str = clean_role
        self.district: str = clean_district
        self.visits_recorded: int = 0

    # ---- class methods ---------------------------------------------------- #
    @classmethod
    def generate_id(cls) -> str:
        """Create the next unique staff code, e.g. HW-0001."""
        new_id = f"{cls.ID_PREFIX}-{cls._next_number:04d}"
        cls._next_number += 1
        return new_id

    @classmethod
    def reset_counter(cls) -> None:
        """Restart ID numbering (used by the automated tests)."""
        cls._next_number = 1

    @classmethod
    def roles(cls) -> str:
        """The supported roles as one readable line."""
        return ", ".join(WORKER_ROLES)

    # ---- static methods --------------------------------------------------- #
    @staticmethod
    def parse_date(value: DateInput) -> date:
        """Turn 'YYYY-MM-DD' text (or a date) into a date, rejecting dates in
        the future or before the year 2000."""
        if isinstance(value, date):
            visit_date = value
        else:
            try:
                visit_date = date.fromisoformat(str(value).strip())
            except ValueError:
                raise ValueError("Date must be in YYYY-MM-DD format, e.g. 2026-03-15.") from None
        if not FIRST_VALID_DATE <= visit_date <= date.today():
            raise ValueError("Date cannot be in the future or before 2000-01-01.")
        return visit_date

    @staticmethod
    def build_vitals(
        temperature_c: Number,
        weight_kg: Number,
        systolic: Optional[Number] = None,
        diastolic: Optional[Number] = None,
    ) -> VitalSigns:
        """Validate measurements and return a VitalSigns record.

        Blood pressure is optional: leave both values as None (or empty text)
        if it was not measured.
        """
        temperature = round(check_range(temperature_c, "Temperature (C)", 30, 45), 1)
        weight = round(check_range(weight_kg, "Weight (kg)", 0.5, 300), 1)
        sys_bp, dia_bp = HealthWorker.check_blood_pressure(systolic, diastolic)
        return VitalSigns(temperature, weight, sys_bp, dia_bp)

    @staticmethod
    def check_blood_pressure(
        systolic: Optional[Number], diastolic: Optional[Number]
    ) -> Tuple[Optional[int], Optional[int]]:
        """Validate a blood pressure pair. Returns (None, None) if not measured."""
        blank = (None, "")
        if systolic in blank and diastolic in blank:
            return None, None
        if systolic in blank or diastolic in blank:
            raise ValueError("Enter both systolic and diastolic blood pressure, or neither.")
        sys_bp = check_range(systolic, "Systolic BP", 50, 260)  # type: ignore[arg-type]
        dia_bp = check_range(diastolic, "Diastolic BP", 30, 160)  # type: ignore[arg-type]
        if not sys_bp.is_integer() or not dia_bp.is_integer():
            raise ValueError("Blood pressure must be whole numbers, e.g. 120/80.")
        if sys_bp <= dia_bp:
            raise ValueError("Systolic BP (top number) must be higher than diastolic.")
        return int(sys_bp), int(dia_bp)

    @staticmethod
    def parse_blood_pressure(text: str) -> Tuple[Optional[int], Optional[int]]:
        """Read blood pressure typed as '120/80'. Empty text means not measured."""
        cleaned = (text or "").replace(" ", "")
        if not cleaned:
            return None, None
        parts = cleaned.split("/")
        if len(parts) != 2:
            raise ValueError("Type blood pressure as two numbers, e.g. 120/80.")
        return HealthWorker.check_blood_pressure(parts[0], parts[1])

    # ---- instance methods ------------------------------------------------- #
    def record_visit(
        self,
        patient: Patient,
        visit_date: DateInput,
        visit_type: str,
        diagnosis: str,
        vitals: VitalSigns,
    ) -> Visit:
        """Validate and save a visit to the patient's record.

        This is the main interaction between the two classes: the health
        worker creates the Visit and the Patient object stores it.
        """
        if not isinstance(patient, Patient):
            raise TypeError("patient must be a Patient object.")
        if not isinstance(vitals, VitalSigns):
            raise TypeError("vitals must be a VitalSigns record.")
        clean_date = HealthWorker.parse_date(visit_date)
        clean_type = match_option(visit_type, VISIT_TYPES)
        if clean_type is None:
            raise ValueError(f"Visit type must be one of: {', '.join(VISIT_TYPES)}.")
        clean_diagnosis = match_option(diagnosis, DIAGNOSES)
        if clean_diagnosis is None:
            raise ValueError(f"Diagnosis must be one of: {', '.join(DIAGNOSES)}.")
        if clean_type == "Antenatal" and patient.sex == "Male":
            raise ValueError("An antenatal visit cannot be recorded for a male patient.")

        visit = Visit(clean_date, clean_type, clean_diagnosis, vitals, self.worker_id)
        patient.add_visit(visit)
        self.visits_recorded += 1
        return visit

    def display_info(self) -> str:
        """Return a readable summary of the health worker."""
        return (
            f"Health worker {self.worker_id} | {self.role} | {self.district} | "
            f"Visits recorded: {self.visits_recorded}"
        )

    def __repr__(self) -> str:
        return (
            f"HealthWorker(worker_id={self.worker_id!r}, role={self.role!r}, "
            f"district={self.district!r})"
        )


# =========================================================================== #
# PART 2: PATIENT REGISTRY (dictionary storage)
# =========================================================================== #

CountRow = Tuple[str, int]                      # (label, number of visits)
FollowUpRow = Tuple[Patient, Tuple[str, ...]]   # (patient, reasons)


class PatientRegistry:
    """Stores patients and health workers in dictionaries keyed by their IDs."""

    # Privacy rule for shared statistics: any count below this number is
    # replaced by "<5" so that rare cases cannot point to one individual.
    MIN_CELL_COUNT = 5
    EXPORT_COLUMNS: Tuple[str, ...] = ("district", "diagnosis", "visits")

    def __init__(self) -> None:
        self._patients: Dict[str, Patient] = {}
        self._workers: Dict[str, HealthWorker] = {}

    # ---- adding records --------------------------------------------------- #
    def add_patient(self, patient: Patient) -> Patient:
        """Store a patient under its patient_id."""
        if not isinstance(patient, Patient):
            raise TypeError("Only Patient objects can be added as patients.")
        if patient.patient_id in self._patients:
            raise ValueError(f"Patient {patient.patient_id} is already registered.")
        self._patients[patient.patient_id] = patient
        return patient

    def add_worker(self, worker: HealthWorker) -> HealthWorker:
        """Store a health worker under its worker_id."""
        if not isinstance(worker, HealthWorker):
            raise TypeError("Only HealthWorker objects can be added as workers.")
        if worker.worker_id in self._workers:
            raise ValueError(f"Health worker {worker.worker_id} is already registered.")
        self._workers[worker.worker_id] = worker
        return worker

    # ---- looking records up ----------------------------------------------- #
    def get_patient(self, patient_id: str) -> Optional[Patient]:
        """Return the patient with this code (case-insensitive), or None."""
        return self._patients.get((patient_id or "").strip().upper())

    def get_worker(self, worker_id: str) -> Optional[HealthWorker]:
        """Return the health worker with this code (case-insensitive), or None."""
        return self._workers.get((worker_id or "").strip().upper())

    def patients(self) -> Tuple[Patient, ...]:
        """All patients, in the order they were registered."""
        return tuple(self._patients.values())

    def workers(self) -> Tuple[HealthWorker, ...]:
        """All health workers, in the order they were registered."""
        return tuple(self._workers.values())

    def __len__(self) -> int:
        return len(self._patients)

    def __contains__(self, record_id: object) -> bool:
        return isinstance(record_id, str) and (
            record_id.upper() in self._patients or record_id.upper() in self._workers
        )

    def __iter__(self) -> Iterator[Patient]:
        """Looping over the registry loops over its patients."""
        return iter(self._patients.values())

    def all_visits(self) -> Tuple[Tuple[Patient, Visit], ...]:
        """Every visit in the registry, paired with its patient."""
        return tuple((p, v) for p in self._patients.values() for v in p.visits)

    # ---- displaying records ----------------------------------------------- #
    def display_patients(self, include_visits: bool = True) -> str:
        """All patients as readable text."""
        if not self._patients:
            return "No patients registered yet."
        separator = "\n\n" if include_visits else "\n"
        return separator.join(p.display_info(include_visits) for p in self._patients.values())

    def display_workers(self) -> str:
        """All health workers as readable text."""
        if not self._workers:
            return "No health workers registered yet."
        return "\n".join(w.display_info() for w in self._workers.values())

    # ---- analysis --------------------------------------------------------- #
    def diagnosis_summary(self) -> Tuple[CountRow, ...]:
        """Number of visits for each diagnosis, most common first."""
        counts: Dict[str, int] = {}
        for _, visit in self.all_visits():
            counts[visit.diagnosis] = counts.get(visit.diagnosis, 0) + 1
        return tuple(sorted(counts.items(), key=lambda row: (-row[1], row[0])))

    def district_diagnosis_counts(self) -> Tuple[Tuple[str, str, int], ...]:
        """Visits counted by (district, diagnosis), sorted alphabetically."""
        counts: Dict[Tuple[str, str], int] = {}
        for patient, visit in self.all_visits():
            key = (patient.district, visit.diagnosis)
            counts[key] = counts.get(key, 0) + 1
        return tuple((d, dx, n) for (d, dx), n in sorted(counts.items()))

    def follow_up_list(self) -> Tuple[FollowUpRow, ...]:
        """Patients whose latest visit or history means they need follow-up."""
        return tuple(
            (patient, reasons)
            for patient in self._patients.values()
            if (reasons := patient.needs_follow_up())
        )

    def patients_with(self, diagnosis: str) -> Tuple[Patient, ...]:
        """All patients who have ever had the given diagnosis."""
        if match_option(diagnosis, DIAGNOSES) is None:
            raise ValueError(f"Unknown diagnosis '{diagnosis}'.")
        return tuple(p for p in self._patients.values() if p.has_condition(diagnosis))

    @staticmethod
    def format_counts(rows: Tuple[CountRow, ...], label: str = "Diagnosis") -> str:
        """Turn (label, count) rows into an aligned text table."""
        if not rows:
            return "No visits recorded yet."
        total = sum(count for _, count in rows)
        header = f"{label:<24}{'Visits':>8}{'Share':>9}"
        body = tuple(
            f"{name:<24}{count:>8}{count / total:>9.0%}" for name, count in rows
        )
        footer = f"{'Total':<24}{total:>8}"
        divider = "-" * len(header)
        return "\n".join((header, divider) + body + (divider, footer))

    # ---- anonymised statistics export (DPG: extracting data safely) ------- #
    def export_statistics(self, path: Union[str, Path]) -> Tuple[int, int]:
        """Write visit counts by district and diagnosis to a CSV file.

        No patient codes, ages, sexes or dates are exported. Counts below
        MIN_CELL_COUNT are written as "<5" (small-number suppression), a
        standard public-health method for preventing re-identification.

        Returns (rows written, rows suppressed).
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        rows_written = suppressed = 0
        with target.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(PatientRegistry.EXPORT_COLUMNS)
            for district, diagnosis, count in self.district_diagnosis_counts():
                if count < PatientRegistry.MIN_CELL_COUNT:
                    writer.writerow((district, diagnosis, f"<{PatientRegistry.MIN_CELL_COUNT}"))
                    suppressed += 1
                else:
                    writer.writerow((district, diagnosis, count))
                rows_written += 1
        return rows_written, suppressed

    # ---- alternative constructor ------------------------------------------ #
    @classmethod
    def with_sample_data(cls) -> "PatientRegistry":
        """Create a registry pre-filled with invented demonstration data.

        Every record is fictional and represents no real person.
        """
        registry = cls()
        workers = tuple(
            registry.add_worker(HealthWorker(role, district))
            for role, district in (
                ("Nurse", "Bo"),
                ("Doctor", "Kenema"),
                ("Community Health Officer", "Port Loko"),
            )
        )
        patient_data: Tuple[Tuple[int, str, str], ...] = (
            (34, "F", "Bo"), (6, "M", "Bo"), (58, "M", "Bo"), (25, "F", "Bo"),
            (2, "F", "Bo"), (41, "M", "Kenema"), (67, "F", "Kenema"),
            (19, "F", "Port Loko"), (45, "M", "Port Loko"), (12, "M", "Bo"),
        )
        patients = tuple(registry.add_patient(Patient.from_tuple(d)) for d in patient_data)

        # (patient, worker, date, visit type, diagnosis, temp, weight, sys, dia)
        visits = (
            (0, 0, "2026-03-02", "Outpatient", "Malaria", 38.9, 62, 118, 76),
            (0, 0, "2026-03-16", "Follow-up", "Routine check", 36.8, 62, 116, 75),
            (1, 0, "2026-04-10", "Outpatient", "Malaria", 39.2, 21, None, None),
            (2, 0, "2026-01-20", "Outpatient", "Hypertension", 36.9, 81, 158, 96),
            (2, 0, "2026-04-22", "Follow-up", "Hypertension", 36.7, 80, 146, 92),
            (3, 0, "2026-05-05", "Antenatal", "Routine check", 36.6, 64, 112, 70),
            (3, 0, "2026-06-18", "Outpatient", "Malaria", 38.4, 65, 110, 72),
            (4, 0, "2026-02-14", "Immunisation", "Routine check", 36.9, 11.5, None, None),
            (4, 0, "2026-07-01", "Emergency", "Malaria", 39.6, 11.8, None, None),
            (9, 0, "2026-08-11", "Outpatient", "Malaria", 38.6, 38, None, None),
            (5, 1, "2026-02-03", "Outpatient", "Typhoid", 38.7, 74, 128, 82),
            (5, 1, "2026-02-17", "Follow-up", "Typhoid", 37.0, 73, 124, 80),
            (6, 1, "2026-03-09", "Outpatient", "Diabetes", 36.8, 70, 134, 84),
            (6, 1, "2026-06-09", "Follow-up", "Diabetes", 36.7, 69, 132, 82),
            (7, 2, "2026-04-01", "Antenatal", "Routine check", 36.7, 58, 108, 68),
            (7, 2, "2026-05-28", "Outpatient", "Respiratory infection", 37.9, 59, 110, 70),
            (8, 2, "2026-07-15", "Outpatient", "Diarrhoeal disease", 37.4, 77, 122, 78),
            (8, 2, "2026-09-02", "Emergency", "Injury", 36.9, 77, 136, 86),
        )
        for p, w, when, kind, dx, temp, weight, sys_bp, dia_bp in visits:
            vitals = HealthWorker.build_vitals(temp, weight, sys_bp, dia_bp)
            workers[w].record_visit(patients[p], when, kind, dx, vitals)
        return registry


# --------------------------------------------------------------------------- #
# Simple functions to add and display records (Task 2)
# --------------------------------------------------------------------------- #
def add_record(registry: PatientRegistry, record: Union[Patient, HealthWorker]) -> str:
    """Add a Patient or HealthWorker to the registry's dictionary; return its ID."""
    if isinstance(record, Patient):
        return registry.add_patient(record).patient_id
    if isinstance(record, HealthWorker):
        return registry.add_worker(record).worker_id
    raise TypeError("Record must be a Patient or a HealthWorker.")


def display_records(registry: PatientRegistry) -> None:
    """Loop through the dictionaries and print every worker and patient."""
    print("=== Health Workers ===")
    print(registry.display_workers())
    print()
    print("=== Patients and Visit History ===")
    print(registry.display_patients())



# =========================================================================== #
# PART 3: MENU PROGRAM
# =========================================================================== #

APP_TITLE = "PATIENT RECORD SYSTEM (PRS) - Sierra Leone"
EXPORT_FILE = "health_statistics.csv"
T = TypeVar("T")

MENU: Tuple[Tuple[str, str], ...] = (
    ("1", "Register a patient"),
    ("2", "Register a health worker"),
    ("3", "Record a visit"),
    ("4", "View all records"),
    ("5", "View one patient's history"),
    ("6", "Patients needing follow-up"),
    ("7", "Diagnosis summary"),
    ("8", "Export anonymised statistics (CSV)"),
    ("9", "Load sample data"),
    ("0", "Exit"),
)


class UserExit(Exception):
    """Raised when the user closes input (Ctrl+D / Ctrl+Z) or presses Ctrl+C."""


# --------------------------------------------------------------------------- #
# Input helpers
# --------------------------------------------------------------------------- #
def ask(prompt: str) -> str:
    """Read one line of input, turning Ctrl+C / end-of-input into UserExit."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise UserExit from None


def ask_until_valid(prompt: str, convert: Callable[[str], T], attempts: int = 3) -> Optional[T]:
    """Ask repeatedly until ``convert`` accepts the answer.

    Returns the converted value, or None after too many invalid attempts so
    the user is never trapped in a loop.
    """
    for attempt in range(1, attempts + 1):
        answer = ask(prompt)
        try:
            return convert(answer)
        except ValueError as error:
            remaining = attempts - attempt
            hint = f" ({remaining} attempt(s) left)" if remaining else ""
            print(f"  Error: {error}{hint}")
    print("  Too many invalid attempts. Returning to the main menu.")
    return None


def choose_from(options: Tuple[str, ...], name: str) -> Callable[[str], str]:
    """Build a converter that accepts an option by name or by its number."""

    def convert(text: str) -> str:
        if text.isdigit() and 1 <= int(text) <= len(options):
            return options[int(text) - 1]
        matched = match_option(text, options)
        if matched is None:
            raise ValueError(f"{name} not recognised. Type its number or its name.")
        return matched

    return convert


def show_options(options: Tuple[str, ...]) -> None:
    """Print options numbered from 1, three per line."""
    cells = tuple(f"{i:>2}. {option}" for i, option in enumerate(options, start=1))
    for start in range(0, len(cells), 3):
        print("   " + "".join(f"{cell:<28}" for cell in cells[start:start + 3]).rstrip())


def show_heading(title: str) -> None:
    print()
    print(title)
    print("-" * len(title))


# --------------------------------------------------------------------------- #
# Menu actions
# --------------------------------------------------------------------------- #
def register_patient(registry: PatientRegistry) -> None:
    show_heading("Register a patient")
    print("Privacy notice: no names, phone numbers or ID numbers are collected.")
    print("Keep the patient code shown at the end in the clinic's own register.")
    age = ask_until_valid("Age in years: ", Patient.validate_age)
    if age is None:
        return

    def to_sex(text: str) -> str:
        sex = Patient.normalise_sex(text)
        if sex is None:
            raise ValueError("Type F (Female), M (Male) or P (Prefer not to say).")
        return sex

    sex = ask_until_valid("Sex (F / M / P = prefer not to say): ", to_sex)
    if sex is None:
        return
    show_options(DISTRICTS)
    district = ask_until_valid("District (number or name): ", choose_from(DISTRICTS, "District"))
    if district is None:
        return
    patient = Patient(age, sex, district)
    add_record(registry, patient)
    print(f"Success: patient registered with code {patient.patient_id}.")


def register_worker(registry: PatientRegistry) -> None:
    show_heading("Register a health worker")
    show_options(WORKER_ROLES)
    role = ask_until_valid("Role (number or name): ", choose_from(WORKER_ROLES, "Role"))
    if role is None:
        return
    show_options(DISTRICTS)
    district = ask_until_valid("Facility district (number or name): ", choose_from(DISTRICTS, "District"))
    if district is None:
        return
    worker = HealthWorker(role, district)
    add_record(registry, worker)
    print(f"Success: health worker registered with staff code {worker.worker_id}.")


def record_visit(registry: PatientRegistry) -> None:
    show_heading("Record a visit")
    if not registry.workers() or not registry.patients():
        print("Please register at least one health worker (option 2) and one patient (option 1).")
        return

    def to_worker(text: str) -> HealthWorker:
        worker = registry.get_worker(text)
        if worker is None:
            raise ValueError("No health worker with that code (example: HW-0001).")
        return worker

    def to_patient(text: str) -> Patient:
        patient = registry.get_patient(text)
        if patient is None:
            raise ValueError("No patient with that code (example: PAT-0001).")
        return patient

    def to_date(text: str) -> date:
        return date.today() if not text else HealthWorker.parse_date(text)

    worker = ask_until_valid("Your staff code: ", to_worker)
    if worker is None:
        return
    patient = ask_until_valid("Patient code: ", to_patient)
    if patient is None:
        return
    visit_date = ask_until_valid("Visit date YYYY-MM-DD (press Enter for today): ", to_date)
    if visit_date is None:
        return
    show_options(VISIT_TYPES)
    visit_type = ask_until_valid("Visit type (number or name): ", choose_from(VISIT_TYPES, "Visit type"))
    if visit_type is None:
        return
    show_options(DIAGNOSES)
    diagnosis = ask_until_valid("Diagnosis (number or name): ", choose_from(DIAGNOSES, "Diagnosis"))
    if diagnosis is None:
        return
    temperature = ask_until_valid(
        "Temperature in C (e.g. 37.2): ", lambda t: check_range(t, "Temperature (C)", 30, 45)
    )
    if temperature is None:
        return
    weight = ask_until_valid(
        "Weight in kg (e.g. 64.5): ", lambda w: check_range(w, "Weight (kg)", 0.5, 300)
    )
    if weight is None:
        return
    bp = ask_until_valid(
        "Blood pressure e.g. 120/80 (press Enter if not measured): ",
        HealthWorker.parse_blood_pressure,
    )
    if bp is None:
        return
    try:
        vitals = HealthWorker.build_vitals(temperature, weight, bp[0], bp[1])
        visit = worker.record_visit(patient, visit_date, visit_type, diagnosis, vitals)
    except ValueError as error:
        print(f"  Error: {error} The visit was not saved.")
        return
    print(f"Success: {visit.visit_type} visit on {visit.visit_date.isoformat()} saved "
          f"for {patient.patient_id}.")
    print(f"Vitals: {visit.vitals.summary()}")
    reasons = patient.needs_follow_up()
    if reasons:
        print("Follow-up recommended: " + "; ".join(reasons) + ".")


def view_one_patient(registry: PatientRegistry) -> None:
    show_heading("View one patient's history")
    patient = registry.get_patient(ask("Patient code: "))
    if patient is None:
        print("No patient with that code.")
        return
    print(patient.display_info())
    reasons = patient.needs_follow_up()
    print("Follow-up: " + ("; ".join(reasons) if reasons else "none needed"))


def follow_up(registry: PatientRegistry) -> None:
    show_heading("Patients needing follow-up")
    rows = registry.follow_up_list()
    if not rows:
        print("No patients currently need follow-up.")
        return
    for patient, reasons in rows:
        print(f"{patient.patient_id} ({patient.district}): " + "; ".join(reasons))
    print(f"Total: {len(rows)} patient(s).")


def diagnosis_summary(registry: PatientRegistry) -> None:
    show_heading("Diagnosis summary (all visits)")
    print(PatientRegistry.format_counts(registry.diagnosis_summary()))


def export_statistics(registry: PatientRegistry) -> None:
    show_heading("Export anonymised statistics")
    try:
        rows, suppressed = registry.export_statistics(EXPORT_FILE)
    except OSError as error:
        print(f"  Error: could not write the file ({error}).")
        return
    print(f"Success: {rows} row(s) of visit counts written to '{EXPORT_FILE}'.")
    print(f"For privacy, {suppressed} small count(s) were shown as "
          f"'<{PatientRegistry.MIN_CELL_COUNT}' and no patient codes were exported.")


def load_sample(registry: PatientRegistry) -> PatientRegistry:
    show_heading("Load sample data")
    if registry.patients() or registry.workers():
        answer = ask("This replaces the current data. Continue? (y/n): ").lower()
        if answer not in ("y", "yes"):
            print("Cancelled. Your data has not changed.")
            return registry
    Patient.reset_counter()
    HealthWorker.reset_counter()
    sample = PatientRegistry.with_sample_data()
    print(f"Loaded {len(sample.workers())} health workers, {len(sample)} patients and "
          f"{len(sample.all_visits())} visits (all fictional).")
    return sample


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #
def print_menu() -> None:
    print()
    print("=" * len(APP_TITLE))
    print(APP_TITLE)
    print("=" * len(APP_TITLE))
    for key, label in MENU:
        print(f"  {key}. {label}")


def run() -> int:
    registry = PatientRegistry()
    print("Welcome! Type the number of an option and press Enter.")
    try:
        while True:
            print_menu()
            choice = ask("Choose an option (0-9): ")
            if choice == "1":
                register_patient(registry)
            elif choice == "2":
                register_worker(registry)
            elif choice == "3":
                record_visit(registry)
            elif choice == "4":
                show_heading("All records")
                display_records(registry)
            elif choice == "5":
                view_one_patient(registry)
            elif choice == "6":
                follow_up(registry)
            elif choice == "7":
                diagnosis_summary(registry)
            elif choice == "8":
                export_statistics(registry)
            elif choice == "9":
                registry = load_sample(registry)
            elif choice == "0":
                print("Goodbye. Thank you for using PRS.")
                return 0
            else:
                print("  Error: please type a number from 0 to 9.")
    except UserExit:
        print("\nInput closed. Goodbye.")
        return 0


if __name__ == "__main__":
    sys.exit(run())