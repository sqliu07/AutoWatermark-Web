from pathlib import Path
from types import SimpleNamespace
import json

import media.motion_photo as motion_module
import media.video as video_module


def test_get_video_wh_accepts_trailing_separator(monkeypatch):
    monkeypatch.setattr(video_module.shutil, "which", lambda _: "/usr/local/bin/ffprobe")

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="1008x1344x\n", stderr="")

    monkeypatch.setattr(video_module.subprocess, "run", fake_run)

    assert video_module._get_video_wh(Path("/tmp/fake.mp4")) == (1008, 1344)


def test_get_video_rotation_prefers_side_data(monkeypatch):
    monkeypatch.setattr(video_module.shutil, "which", lambda _: "/usr/local/bin/ffprobe")

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

    monkeypatch.setattr(video_module.subprocess, "run", fake_run)

    assert video_module._get_video_rotation(Path("/tmp/fake.mp4")) == 90


def test_get_video_rotation_converts_legacy_rotate_tag(monkeypatch):
    monkeypatch.setattr(video_module.shutil, "which", lambda _: "/usr/local/bin/ffprobe")

    payload = {
        "streams": [
            {
                "tags": {"rotate": "90"},
            }
        ]
    }

    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(video_module.subprocess, "run", fake_run)

    assert video_module._get_video_rotation(Path("/tmp/fake.mp4")) == 270


def test_find_motion_video_start_with_offset_attr(tmp_path):
    fake_mp4 = (
        b"\x00\x00\x00\x18ftypisom"
        b"\x00\x00\x02\x00isomiso2"
    )
    xmp = (
        b'<x:xmpmeta xmlns:x="adobe:ns:meta/">'
        b'<rdf:Description GCamera:MotionPhotoOffset="%d" />'
        b"</x:xmpmeta>" % len(fake_mp4)
    )
    fake_jpeg = b"\xff\xd8" + xmp + b"\xff\xd9"
    motion_file = tmp_path / "motion.jpg"
    motion_file.write_bytes(fake_jpeg + fake_mp4)

    start = motion_module.find_motion_video_start(motion_file)
    assert start == len(fake_jpeg)


def test_find_motion_video_start_returns_none_for_non_motion(tmp_path):
    non_motion = tmp_path / "plain.jpg"
    non_motion.write_bytes(b"\xff\xd8hello\xff\xd9")

    assert motion_module.find_motion_video_start(non_motion) is None
