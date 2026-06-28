import json

import pytest

from content_factory.mission_control.approvals import ApprovalStore


def test_approval_state_writes_local_json(tmp_path):
    store = ApprovalStore(tmp_path)

    approval = store.write("job-abc123", "approved", "Ready for human export.")

    path = tmp_path / "approvals" / "job-abc123.json"
    assert path.is_file()
    assert json.loads(path.read_text(encoding="utf-8")) == approval
    assert approval["job_id"] == "job-abc123"
    assert approval["state"] == "approved"
    assert approval["updated_at"].endswith("+00:00")


def test_approval_state_can_be_updated(tmp_path):
    store = ApprovalStore(tmp_path)
    store.write("job-abc123", "rejected", "Wrong hook")

    updated = store.write("job-abc123", "needs_revision", "Try a clearer hook")

    assert store.read("job-abc123") == updated
    assert updated["state"] == "needs_revision"


def test_missing_approval_defaults_to_pending_without_writing(tmp_path):
    store = ApprovalStore(tmp_path)

    approval = store.read("new-job")

    assert approval["state"] == "pending"
    assert not (tmp_path / "approvals").exists()


@pytest.mark.parametrize("job_id", ["../escape", "..", "nested/job", "nested\\job"])
def test_approval_path_traversal_is_rejected(tmp_path, job_id):
    store = ApprovalStore(tmp_path)

    with pytest.raises(ValueError, match="invalid job_id"):
        store.write(job_id, "approved")

    assert not (tmp_path.parent / "escape.json").exists()


def test_unknown_approval_state_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="invalid approval state"):
        ApprovalStore(tmp_path).write("job-abc123", "publish")
