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
