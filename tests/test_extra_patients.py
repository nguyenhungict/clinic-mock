"""Extra canonical patients loaded from MOCK_EXTRA_PATIENTS_FILE."""

from __future__ import annotations

import json

from clinic_mock.config import settings
from clinic_mock.store import CANONICAL_TENANT, db, seed_default

EXTRA = [
    {
        "id": "pt_9001",
        "display_name": "T. V. B.",
        "phone": "0900000001",
        "dob": "2000-01-31",
        "verify": {"full_name": "Trần Văn B", "dob": "2000-01-31"},
    }
]

SLOT = {
    "slot_id": "slot_x9002",
    "clinic_id": "cl_vinmec",
    "start_time": "2026-10-15T10:30:00+07:00",
    "end_time": "2026-10-15T11:00:00+07:00",
    "provider_id": "pr_vinmec_1",
}


def test_extra_patients_seeded_from_file(tmp_path, monkeypatch):
    f = tmp_path / "patients.json"
    f.write_text(json.dumps(EXTRA, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(settings.mock_auth, "EXTRA_PATIENTS_FILE", str(f))
    seed_default()
    p = db.patients["pt_9001"]
    assert p.tenant_id == CANONICAL_TENANT
    assert p.verify.full_name == "Trần Văn B"


def test_missing_extra_patients_file_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(
        settings.mock_auth, "EXTRA_PATIENTS_FILE", str(tmp_path / "missing.json")
    )
    seed_default()
    assert "pt_3391" in db.patients
    assert "pt_9001" not in db.patients


def test_extra_slots_and_appointments_seeded_from_file(tmp_path, monkeypatch, client):
    appt = {
        "appointment_id": "apt_09001",
        "slot_id": "slot_x9001",
        "provider_id": "pr_vinmec_1",
        "status": "SCHEDULED",
        "clinic_id": "cl_vinmec",
        "starts_at": "2026-10-15T08:00:00+07:00",
        "ends_at": "2026-10-15T08:30:00+07:00",
        "department": "Nội tổng quát",
        "patient_id": "pt_9001",
        "attempt_count": 0,
        "version": 1,
    }
    f = tmp_path / "extra.json"
    f.write_text(
        json.dumps(
            {"patients": EXTRA, "slots": [SLOT], "appointments": [appt]},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(settings.mock_auth, "EXTRA_PATIENTS_FILE", str(f))
    seed_default()
    r = client.get(
        "/v1/appointments/apt_09001", headers={"Authorization": "Bearer sk_test_a"}
    )
    assert r.status_code == 200
    assert r.json()["patient"]["patient_id"] == "pt_9001"
    assert db.slots["slot_x9002"].tenant_id == CANONICAL_TENANT
