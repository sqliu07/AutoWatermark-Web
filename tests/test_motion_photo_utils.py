from pathlib import Path
from types import SimpleNamespace
import json

import core.motion_photo_utils as motion_utils


def test_get_video_wh_accepts_trailing_separator(monkeypatch):
    monkeypatch.setattr(motion_utils.shutil, "which", lambda _: "/usr/local/bin/ffprobe")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="1008x1344x\n", stderr="")

    monkeypatch.setattr(motion_utils.subprocess, "run", fake_run)

    assert motion_utils._get_video_wh(Path("/tmp/fake.mp4")) == (1008, 1344)


def test_get_video_rotation_prefers_side_data(monkeypatch):
    monkeypatch.setattr(motion_utils.shutil, "which", lambda _: "/usr/local/bin/ffprobe")

    payload = {
        "streams": [
            {
                "tags": {"rotate": "270"},
                "side_data_list": [{"rotation": 90}],
            }
        ]
    }

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(motion_utils.subprocess, "run", fake_run)

    assert motion_utils._get_video_rotation(Path("/tmp/fake.mp4")) == 90


def test_get_video_rotation_converts_legacy_rotate_tag(monkeypatch):
    monkeypatch.setattr(motion_utils.shutil, "which", lambda _: "/usr/local/bin/ffprobe")

    payload = {
        "streams": [
            {
                "tags": {"rotate": "90"},
            }
        ]
    }

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(motion_utils.subprocess, "run", fake_run)

    assert motion_utils._get_video_rotation(Path("/tmp/fake.mp4")) == 270
