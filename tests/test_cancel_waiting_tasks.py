from pathlib import Path
import time

import pytest


@pytest.mark.parametrize("status", ["needs_logo", "needs_options"])
def test_cancelling_waiting_task_releases_capacity_and_uploaded_copy(app, client, status):
    path = Path(app.config["UPLOAD_FOLDER"]) / "waiting.jpg"
    path.write_bytes(b"uploaded copy")
    state = app.extensions["state"]
    state.create_task("waiting", {"status": status, "filepath": str(path)})
    response = client.post("/api/tasks/waiting/cancel")
    assert response.status_code == 200
    assert state.get_task("waiting")["status"] == "cancelled"
    assert state.count_tasks_by_status("needs_logo", "needs_options") == 0
    assert not path.exists()
    assert client.post("/api/tasks/waiting/cancel").status_code == 200
    assert state.cleanup_old_tasks(time.time() + 7200) == 1


@pytest.mark.parametrize("status", ["queued", "processing", "succeeded", "failed"])
def test_cancel_does_not_interrupt_or_delete_other_task_states(app, client, status):
    path = Path(app.config["UPLOAD_FOLDER"]) / "active.jpg"
    path.write_bytes(b"photo")
    state = app.extensions["state"]
    state.create_task("active", {"status": status, "filepath": str(path)})
    assert client.post("/api/tasks/active/cancel").status_code == 409
    assert state.get_task("active")["status"] == status
    assert path.exists()


def test_cancel_cannot_unlink_outside_uploads_or_database(app, client, tmp_path):
    state = app.extensions["state"]
    outside = tmp_path / "private.jpg"
    outside.write_bytes(b"private")
    for task_id, path in [("outside", outside), ("database", Path(app.config["STATE_DB_PATH"]))]:
        state.create_task(task_id, {"status": "needs_logo", "filepath": str(path)})
        assert client.post(f"/api/tasks/{task_id}/cancel").status_code == 200
        assert path.exists()
    assert outside.read_bytes() == b"private"
    assert client.post("/api/tasks/unknown/cancel").status_code == 404


def test_status_restores_media_choices_after_a_lost_confirmation_response(app, client):
    state = app.extensions["state"]
    state.create_task("recover-options", {
        "status": "needs_options", "features": {"is_hdr": True, "is_motion": False},
        "preserve_hdr": False, "preserve_motion": True,
    })
    response = client.get("/api/status/recover-options")
    assert response.status_code == 200
    assert response.json["features"] == {"is_hdr": True, "is_motion": False}
    assert response.json["preserve_hdr"] is False
    assert response.json["preserve_motion"] is True
