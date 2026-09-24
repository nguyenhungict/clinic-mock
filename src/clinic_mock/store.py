"""In-memory store with snapshot/restore for test isolation.

Single global `db` instance; snapshot copies are deep via model_dump.

Canonical contract fixtures (Listing 3/4 ids: apt_00417, pt_3391, slot_91d2,
slot_77aa, cl_vinmec) are seeded once under the sentinel tenant `t_canonical`
and visible to every caller via `_visible_tenants()`. Per-tenant fixtures
keep the existing suffix trick so isolation tests still see distinct rows.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from clinic_mock.auth import derive_tenant_id
from clinic_mock.schemas import (
    Appointment,
    Patient,
    PatientRef,
    PatientVerify,
    Slot,
)


# Tenant id under which contract canonical fixtures live. Read by the route
# helpers to widen the tenant filter — see _visible_tenants() in routes.py.
CANONICAL_TENANT = "t_canonical"


def now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class Store:
    def __init__(self) -> None:
        self.patients: dict[str, Patient] = {}
        self.slots: dict[str, Slot] = {}
        self.appointments: dict[str, Appointment] = {}
        self.snapshots: dict[str, dict] = {}
        self.system_clock_offset_sec: int = 0

    def now(self) -> datetime:
        return datetime.now(UTC).fromtimestamp(
            datetime.now(UTC).timestamp() + self.system_clock_offset_sec,
            tz=UTC,
        )

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    def reset(self) -> None:
        self.__init__()

    def snapshot(self) -> str:
        sid = self.new_id("snap")
        self.snapshots[sid] = {
            "patients": {k: v.model_dump() for k, v in self.patients.items()},
            "slots": {k: v.model_dump() for k, v in self.slots.items()},
            "appointments": {k: v.model_dump() for k, v in self.appointments.items()},
            "system_clock_offset_sec": self.system_clock_offset_sec,
        }
        return sid

    def restore(self, sid: str) -> None:
        snap = self.snapshots.get(sid)
        if snap is None:
            from clinic_mock.errors import not_found

            raise not_found(f"snapshot {sid}")
        self.patients = {k: Patient(**v) for k, v in snap["patients"].items()}
        self.slots = {k: Slot(**v) for k, v in snap["slots"].items()}
        self.appointments = {
            k: Appointment(**v) for k, v in snap["appointments"].items()
        }
        self.system_clock_offset_sec = snap["system_clock_offset_sec"]

    def dump(self) -> dict:
        return {
            "patients": [p.model_dump() for p in self.patients.values()],
            "slots": [s.model_dump() for s in self.slots.values()],
            "appointments": [a.model_dump() for a in self.appointments.values()],
        }


db = Store()


# ----- seed fixtures -----

CLINICS = [
    {"id": "c_001", "name": "Phòng khám Đa khoa Trung tâm"},
    {"id": "c_002", "name": "Phòng khám Đa khoa Cầu Giấy"},
    {"id": "cl_vinmec", "name": "Vinmec Times City"},
]

PROVIDERS = [
    {"id": "pr_456", "name": "Bác sĩ Nguyễn Văn An", "clinic_id": "c_001"},
    {"id": "pr_789", "name": "Bác sĩ Trần Thị Bình", "clinic_id": "c_002"},
    {"id": "pr_vinmec_1", "name": "Bác sĩ Phạm Thị Cúc", "clinic_id": "cl_vinmec"},
]

# Per-tenant fixtures — each row is replicated once per registered key, with
# the row id suffixed by a short tenant hash so the copies stay unique in the
# store while the row content is identical across callers.
PATIENT_FIXTURES = [
    {
        "id": "p_12345",
        "display_name": "Mai N.",
        "phone": "0912345678",
        "dob": "1985-04-12",
        "verify": {"full_name": "Nguyễn Thị Mai", "dob": "1985-04-12"},
    },
    {
        "id": "p_67890",
        "display_name": "Nam T.",
        "phone": "0987654321",
        "dob": "1972-11-03",
        "verify": {"full_name": "Trần Văn Nam", "dob": "1972-11-03"},
    },
]

SLOT_FIXTURES = [
    {
        "slot_id": "s_987",
        "clinic_id": "c_001",
        "start_time": "2026-09-15T09:00:00Z",
        "end_time": "2026-09-15T09:30:00Z",
        "provider_id": "pr_456",
    },
    {
        "slot_id": "s_988",
        "clinic_id": "c_001",
        "start_time": "2026-09-15T09:30:00Z",
        "end_time": "2026-09-15T10:00:00Z",
        "provider_id": "pr_456",
    },
    {
        "slot_id": "s_1024",
        "clinic_id": "c_002",
        "start_time": "2026-09-15T11:00:00Z",
        "end_time": "2026-09-15T11:30:00Z",
        "provider_id": "pr_789",
    },
]

# Canonical contract fixtures — Listing 3/4. Seeded once under t_canonical
# and visible to all tenants. apt_00417 consumes slot_77aa (NOT in db.slots).
CANONICAL_PATIENT_FIXTURES = [
    {
        "id": "pt_3391",
        "display_name": "N. V. A.",
        "phone": "0912345600",
        "dob": "1978-03-14",
        "verify": {"full_name": "Nguyễn Văn A", "dob": "1978-03-14"},
    },
    # Demo records (mentor cho phép thêm ngoài Nguyễn Văn A, 24-09-2026): hồ sơ thường, không edge case.
    {
        "id": "pt_3401",
        "display_name": "T. T. B.",
        "phone": "0901234501",
        "dob": "1990-06-21",
        "verify": {"full_name": "Trần Thị Bình", "dob": "1990-06-21"},
    },
    {
        "id": "pt_3402",
        "display_name": "L. V. C.",
        "phone": "0901234502",
        "dob": "1965-01-09",
        "verify": {"full_name": "Lê Văn Cường", "dob": "1965-01-09"},
    },
    {
        "id": "pt_3403",
        "display_name": "P. T. D.",
        "phone": "0901234503",
        "dob": "1988-12-02",
        "verify": {"full_name": "Phạm Thị Dung", "dob": "1988-12-02"},
    },
    {
        "id": "pt_3404",
        "display_name": "H. M. Đ.",
        "phone": "0901234504",
        "dob": "1975-07-30",
        "verify": {"full_name": "Hoàng Minh Đức", "dob": "1975-07-30"},
    },
    {
        "id": "pt_3405",
        "display_name": "V. T. H.",
        "phone": "0901234505",
        "dob": "1995-03-17",
        "verify": {"full_name": "Vũ Thị Hoa", "dob": "1995-03-17"},
    },
    {
        "id": "pt_3406",
        "display_name": "Đ. Q. H.",
        "phone": "0901234506",
        "dob": "1982-09-05",
        "verify": {"full_name": "Đặng Quốc Hùng", "dob": "1982-09-05"},
    },
    {
        "id": "pt_3407",
        "display_name": "B. T. L.",
        "phone": "0901234507",
        "dob": "1970-11-23",
        "verify": {"full_name": "Bùi Thị Lan", "dob": "1970-11-23"},
    },
    {
        "id": "pt_3408",
        "display_name": "Đ. V. L.",
        "phone": "0901234508",
        "dob": "1999-02-14",
        "verify": {"full_name": "Đỗ Văn Long", "dob": "1999-02-14"},
    },
    {
        "id": "pt_3409",
        "display_name": "N. T. M.",
        "phone": "0901234509",
        "dob": "1986-05-08",
        "verify": {"full_name": "Ngô Thị Minh", "dob": "1986-05-08"},
    },
    {
        "id": "pt_3410",
        "display_name": "D. T. P.",
        "phone": "0901234510",
        "dob": "1960-10-01",
        "verify": {"full_name": "Dương Thanh Phong", "dob": "1960-10-01"},
    },
]

CANONICAL_SLOT_FIXTURES = [
    # Listing 4 — the open slot the bot will pick during reschedule.
    {
        "slot_id": "slot_91d2",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-14T15:00:00+07:00",
        "end_time": "2026-10-14T15:30:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    # Demo slot trống, sau slot_91d2 theo cả thứ tự lẫn giờ để slot_91d2 vẫn được đề xuất đầu tiên.
    {
        "slot_id": "slot_b501",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-15T10:30:00+07:00",
        "end_time": "2026-10-15T11:00:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b502",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-15T15:30:00+07:00",
        "end_time": "2026-10-15T16:00:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b503",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-16T09:00:00+07:00",
        "end_time": "2026-10-16T09:30:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b504",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-16T14:00:00+07:00",
        "end_time": "2026-10-16T14:30:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b505",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-19T10:00:00+07:00",
        "end_time": "2026-10-19T10:30:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b506",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-19T15:30:00+07:00",
        "end_time": "2026-10-19T16:00:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b507",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-20T08:00:00+07:00",
        "end_time": "2026-10-20T08:30:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b508",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-20T14:00:00+07:00",
        "end_time": "2026-10-20T14:30:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b509",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-21T09:00:00+07:00",
        "end_time": "2026-10-21T09:30:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
    {
        "slot_id": "slot_b510",
        "clinic_id": "cl_vinmec",
        "start_time": "2026-10-21T15:00:00+07:00",
        "end_time": "2026-10-21T15:30:00+07:00",
        "provider_id": "pr_vinmec_1",
    },
]

CANONICAL_APPOINTMENT_FIXTURES = [
    # Listing 3 — apt_00417 occupies slot_77aa (which is NOT seeded in
    # db.slots). Listing 4's reschedule flow releases slot_77aa back.
    {
        "appointment_id": "apt_00417",
        "slot_id": "slot_77aa",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-14T15:30:00+07:00",
        "ends_at": "2026-10-14T16:00:00+07:00",
        "department": "Nội tổng quát",
        "patient_id": "pt_3391",
        "attempt_count": 0,
        "version": 3,
    },
    # Demo lịch hẹn: mỗi bệnh nhân demo một lịch SCHEDULED, chiếm slot riêng không nằm trong db.slots.
    {
        "appointment_id": "apt_00418",
        "slot_id": "slot_a418",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-15T08:00:00+07:00",
        "ends_at": "2026-10-15T08:30:00+07:00",
        "department": "Nội tổng quát",
        "patient_id": "pt_3401",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00419",
        "slot_id": "slot_a419",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-15T09:30:00+07:00",
        "ends_at": "2026-10-15T10:00:00+07:00",
        "department": "Tim mạch",
        "patient_id": "pt_3402",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00420",
        "slot_id": "slot_a420",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-15T14:00:00+07:00",
        "ends_at": "2026-10-15T14:30:00+07:00",
        "department": "Sản phụ khoa",
        "patient_id": "pt_3403",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00421",
        "slot_id": "slot_a421",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-16T08:30:00+07:00",
        "ends_at": "2026-10-16T09:00:00+07:00",
        "department": "Tiêu hóa",
        "patient_id": "pt_3404",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00422",
        "slot_id": "slot_a422",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-16T10:00:00+07:00",
        "ends_at": "2026-10-16T10:30:00+07:00",
        "department": "Da liễu",
        "patient_id": "pt_3405",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00423",
        "slot_id": "slot_a423",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-16T15:00:00+07:00",
        "ends_at": "2026-10-16T15:30:00+07:00",
        "department": "Cơ xương khớp",
        "patient_id": "pt_3406",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00424",
        "slot_id": "slot_a424",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-19T08:00:00+07:00",
        "ends_at": "2026-10-19T08:30:00+07:00",
        "department": "Mắt",
        "patient_id": "pt_3407",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00425",
        "slot_id": "slot_a425",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-19T09:00:00+07:00",
        "ends_at": "2026-10-19T09:30:00+07:00",
        "department": "Tai Mũi Họng",
        "patient_id": "pt_3408",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00426",
        "slot_id": "slot_a426",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-19T14:30:00+07:00",
        "ends_at": "2026-10-19T15:00:00+07:00",
        "department": "Răng Hàm Mặt",
        "patient_id": "pt_3409",
        "attempt_count": 0,
        "version": 1,
    },
    {
        "appointment_id": "apt_00427",
        "slot_id": "slot_a427",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-20T09:00:00+07:00",
        "ends_at": "2026-10-20T09:30:00+07:00",
        "department": "Thần kinh",
        "patient_id": "pt_3410",
        "attempt_count": 0,
        "version": 1,
    },
]


def _seed_tenants() -> list[str]:
    """Resolve the isolation scopes used by the seed fixtures.

    Parses `MOCK_API_KEYS` directly in env order — the registry is a set
    and would lose insertion order. Falls back to a single derived scope
    if the env is empty so the mock stays usable with zero env tweaks.
    """
    from clinic_mock.config import settings

    raw = settings.mock_auth.API_KEYS
    keys: list[str] = []
    for entry in raw.split(","):
        e = entry.strip()
        if not e:
            continue
        if ":" in e:
            _, e = (p.strip() for p in e.split(":", 1))
        keys.append(e)
    if not keys:
        keys = ["sk_unset"]
    tenants = [derive_tenant_id(k) for k in keys]
    seen: set[str] = set()
    unique: list[str] = []
    for t in tenants:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


def _scope_suffix(tenant: str) -> str:
    """Short, stable suffix used to disambiguate per-scope fixture copies."""
    return tenant[-4:]


def _seed_canonical_patients() -> None:
    for f in CANONICAL_PATIENT_FIXTURES:
        db.patients[f["id"]] = Patient(
            patient_id=f["id"],
            tenant_id=CANONICAL_TENANT,
            display_name=f["display_name"],
            phone=f["phone"],
            dob=f["dob"],
            verify=PatientVerify(**f["verify"]),
        )


def _seed_canonical_slots() -> None:
    for f in CANONICAL_SLOT_FIXTURES:
        db.slots[f["slot_id"]] = Slot(
            slot_id=f["slot_id"],
            tenant_id=CANONICAL_TENANT,
            clinic_id=f["clinic_id"],
            start_time=f["start_time"],
            end_time=f["end_time"],
            provider_id=f["provider_id"],
        )


def _seed_canonical_appointments() -> None:
    for f in CANONICAL_APPOINTMENT_FIXTURES:
        patient = db.patients[f["patient_id"]]
        appt = Appointment(
            appointment_id=f["appointment_id"],
            tenant_id=CANONICAL_TENANT,
            slot_id=f["slot_id"],
            provider_id=f["provider_id"],
            status=f["status"],
            clinic_id=f["clinic_id"],
            starts_at=f["starts_at"],
            ends_at=f["ends_at"],
            department=f["department"],
            patient=PatientRef(
                patient_id=patient.patient_id,
                display_name=patient.display_name,
                verify=patient.verify,
            ),
            attempt_count=f["attempt_count"],
            version=f["version"],
        )
        db.appointments[f["appointment_id"]] = appt


def seed_default() -> None:
    """Populate db with the canonical mock fixtures (idempotent: reset first).

    Canonical contract fixtures seed once under `t_canonical` and are visible
    to every tenant. Per-tenant fixtures replicate per registered key with a
    short tenant hash suffix.
    """
    db.reset()
    db.system_clock_offset_sec = 0
    tenants = _seed_tenants()

    _seed_canonical_patients()
    _seed_canonical_slots()
    _seed_canonical_appointments()

    for tenant in tenants:
        suffix = _scope_suffix(tenant)
        for f in PATIENT_FIXTURES:
            pid = f"{f['id']}_{suffix}"
            db.patients[pid] = Patient(
                patient_id=pid,
                tenant_id=tenant,
                display_name=f["display_name"],
                phone=f["phone"],
                dob=f["dob"],
                verify=PatientVerify(**f["verify"]),
            )
        for f in SLOT_FIXTURES:
            sid = f"{f['slot_id']}_{suffix}"
            db.slots[sid] = Slot(
                slot_id=sid,
                tenant_id=tenant,
                clinic_id=f["clinic_id"],
                start_time=f["start_time"],
                end_time=f["end_time"],
                provider_id=f["provider_id"],
            )
