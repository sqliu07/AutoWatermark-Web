import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import media.video as video
from errors import WatermarkError


def metadata(**stream_fields):
    return {
        "streams": [{"width": 64, "height": 48, **stream_fields}],
        "format": {"duration": "0.2"},
    }


def mock_probe(monkeypatch, payload):
    calls = []
    monkeypatch.setattr(video.shutil, "which", lambda name: "/usr/bin/" + name)

    def run(command, **kwargs):
        calls.append(command)
        assert kwargs["timeout"] == 30
        return SimpleNamespace(stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr(video.subprocess, "run", run)
    return calls


def test_encode_probes_metadata_once_and_keeps_input_restrictions(tmp_path, monkeypatch):
    calls = []
    output = tmp_path / "output.mp4"
    monkeypatch.setattr(video.shutil, "which", lambda name: "/usr/bin/" + name)

    def run(command, **kwargs):
        calls.append(command)
        if Path(command[0]).name == "ffprobe":
            assert kwargs["timeout"] == 30
            return SimpleNamespace(stdout=json.dumps(metadata(side_data_list=[{"rotation": 90}])), stderr="")
        output.write_bytes(b"video")
        assert kwargs["timeout"] == 120
        return SimpleNamespace(stdout=b"", stderr=b"")

    monkeypatch.setattr(video.subprocess, "run", run)
    video._apply_watermark_to_video(tmp_path / "input.mp4", tmp_path / "overlay.png",
                                    output, (8, 8, 72, 56), (80, 64))
    probes = [call for call in calls if Path(call[0]).name == "ffprobe"]
    assert len(probes) == 1
    probe = probes[0]
    for option, value in (("-f", "mov"), ("-protocol_whitelist", "file"),
                          ("-enable_drefs", "0"), ("-use_absolute_path", "0"),
                          ("-max_streams", "8"), ("-threads", "2"),
                          ("-select_streams", "v:0"), ("-of", "json")):
        assert probe[probe.index(option) + 1] == value
    encoder = calls[-1]
    assert "transpose=2" in encoder[encoder.index("-filter_complex") + 1]
    assert output.read_bytes() == b"video"


@pytest.mark.parametrize("payload", [None, [], {}, {"streams": []},
    {"streams": [None]}, {"streams": [{}, {}]},
    metadata(width=True), metadata(height="48.5"),
    metadata(tags=[]), metadata(side_data_list="invalid"),
    metadata(side_data_list=[None]), metadata(side_data_list=[{"rotation": "nan"}]),
    metadata(side_data_list=[{"rotation": True}]), metadata(tags={"rotate": {}}),
    {"streams": [{"width": 64, "height": 48}], "format": []},
])
def test_malformed_probe_metadata_fails_before_encoding(monkeypatch, payload):
    calls = mock_probe(monkeypatch, payload)
    with pytest.raises((ValueError, RuntimeError)):
        video._probe_video(Path("/tmp/input.mp4"))
    assert len(calls) == 1


@pytest.mark.parametrize("size", [(60000, 100), (0, 64), (6400, 6400)])
def test_probe_rejects_oversized_or_invalid_dimensions(monkeypatch, size):
    mock_probe(monkeypatch, metadata(width=size[0], height=size[1]))
    with pytest.raises(WatermarkError):
        video._probe_video(Path("/tmp/input.mp4"))


@pytest.mark.parametrize("duration", ["31", "0", "-1", "nan", "inf", "N/A", None, True])
def test_probe_rejects_invalid_duration(monkeypatch, duration):
    payload = metadata()
    payload["format"]["duration"] = duration
    mock_probe(monkeypatch, payload)
    with pytest.raises(ValueError):
        video._probe_video(Path("/tmp/input.mp4"))


@pytest.mark.parametrize("stream_fields,expected", [
    ({"tags": {"rotate": "270"}, "side_data_list": [{"rotation": 90}]}, 90),
    ({"tags": {"rotate": "90"}}, 270),
    ({"side_data_list": [{"rotation": -90}]}, 270),
    ({}, None),
])
def test_single_probe_preserves_rotation_conventions(monkeypatch, stream_fields, expected):
    mock_probe(monkeypatch, metadata(**stream_fields))
    result = video._probe_video(Path("/tmp/input.mp4"))
    assert result.width == 64
    assert result.height == 48
    assert result.duration == 0.2
    assert result.rotation == expected


def test_probe_rejects_oversized_json_before_parsing(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(video.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(stdout=" " * 65537, stderr=""))
    with pytest.raises(ValueError, match="metadata"):
        video._probe_video(Path("/tmp/input.mp4"))
