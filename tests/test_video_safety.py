import json
import shutil
import subprocess
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import pytest
from PIL import Image

import media.video as video
from errors import WatermarkError


def test_probes_restrict_formats_protocols_and_external_tracks(monkeypatch):
    commands = []
    monkeypatch.setattr(video.shutil, "which", lambda _: "/usr/bin/ffprobe")

    def run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(stdout=json.dumps({"streams": [{"width": 64, "height": 64}]}), stderr="")

    monkeypatch.setattr(video.subprocess, "run", run)
    assert video._get_video_wh(Path("/tmp/input.mp4")) == (64, 64)
    assert video._get_video_rotation(Path("/tmp/input.mp4")) is None
    for command in commands:
        for option, value in (("-f", "mov"), ("-protocol_whitelist", "file"),
                              ("-enable_drefs", "0"), ("-use_absolute_path", "0")):
            assert command[command.index(option) + 1] == value


def test_probe_rejects_oversized_video_before_encoding(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(video.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(stdout=json.dumps({"streams": [{"width": 60000, "height": 100}]}), stderr=""))
    with pytest.raises(WatermarkError):
        video._get_video_wh(Path("/tmp/input.mp4"))


@pytest.mark.parametrize("duration", ["31", "nan", "inf", "-1", "N/A"])
def test_invalid_or_long_video_duration_is_rejected(monkeypatch, duration):
    monkeypatch.setattr(video.shutil, "which", lambda _: "/usr/bin/ffprobe")
    monkeypatch.setattr(video.subprocess, "run", lambda *args, **kwargs:
                        SimpleNamespace(stdout=json.dumps({"streams": [{}], "format": {"duration": duration}}), stderr=""))
    with pytest.raises(ValueError):
        video._get_video_duration(Path("/tmp/input.mp4"))


def test_video_canvas_is_bounded_before_encoder_runs(monkeypatch):
    monkeypatch.setattr(video.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video, "_probe_video", lambda _: video._VideoMetadata(6000, 6000, 1, 0))

    def run(*args, **kwargs):
        pytest.fail("encoder started before expanded-canvas validation")

    monkeypatch.setattr(video.subprocess, "run", run)
    with pytest.raises(WatermarkError):
        video._apply_watermark_to_video(Path("input.mp4"), Path("overlay.png"),
                                        Path("out.mp4"), (0, 0, 1000, 1000), (2000, 2000))


def test_encoder_inputs_and_output_are_bounded(tmp_path, monkeypatch):
    commands = []
    monkeypatch.setattr(video.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video, "_probe_video", lambda _: video._VideoMetadata(64, 64, 1, 0))
    output = tmp_path / "out.mp4"

    def run(command, **kwargs):
        commands.append(command)
        output.write_bytes(b"result")
        assert kwargs["timeout"] == 120

    monkeypatch.setattr(video.subprocess, "run", run)
    video._apply_watermark_to_video(tmp_path / "input.mp4", tmp_path / "overlay.png",
                                    output, (8, 8, 72, 72), (80, 80))
    command = commands[0]
    first_input = command.index("-i")
    second_input = command.index("-i", first_input + 1)
    assert command[command.index("-f") + 1] == "mov"
    assert command[command.index("-f", first_input) + 1] == "image2"
    assert command[command.index("-pattern_type") + 1] == "none"
    assert command[command.index("-c:v", first_input) + 1] == "png"
    assert command[:first_input].count("file") == 1
    assert command[first_input:second_input].count("file") == 1
    assert command[command.index("-filter_complex_threads") + 1] == "2"
    assert command[command.index("-t", second_input) + 1] == "30"
    assert command[command.index("-fs") + 1] == str(video.MAX_VIDEO_OUTPUT_BYTES)
    assert command[command.index("-map", command.index("-map") + 1) + 1] == "0:a:0?"


@pytest.mark.parametrize("failure", ["timeout", "size"])
def test_encoder_removes_incomplete_or_oversized_output(tmp_path, monkeypatch, failure):
    monkeypatch.setattr(video.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    monkeypatch.setattr(video, "_probe_video", lambda _: video._VideoMetadata(64, 64, 1, 0))
    monkeypatch.setattr(video, "MAX_VIDEO_OUTPUT_BYTES", 8)
    output = tmp_path / "out.mp4"

    def run(command, **kwargs):
        output.write_bytes(b"12345678")
        if failure == "timeout":
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(video.subprocess, "run", run)
    with pytest.raises((subprocess.TimeoutExpired, ValueError)):
        video._apply_watermark_to_video(tmp_path / "input.mp4", tmp_path / "overlay.png",
                                        output, (8, 8, 72, 72), (80, 80))
    assert not output.exists()


@pytest.fixture
def real_video(tmp_path):
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("ffmpeg and ffprobe are required")
    path = tmp_path / "input.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-f", "lavfi", "-i",
                    "color=c=blue:s=64x64:d=0.2:r=10", "-c:v", "libx264", "-threads", "1",
                    "-pix_fmt", "yuv420p", str(path)], check=True, capture_output=True, timeout=10)
    return path


def test_real_motion_video_still_encodes(real_video, tmp_path):
    overlay = tmp_path / "overlay.png"
    with Image.new("RGBA", (80, 80), (255, 255, 255, 40)) as image:
        image.save(overlay)
    output = tmp_path / "output.mp4"
    video._apply_watermark_to_video(real_video, overlay, output, (8, 8, 72, 72), (80, 80))
    assert video._get_video_wh(output) == (80, 80)
    assert 0 < video._get_video_duration(output) < 1


@pytest.mark.parametrize("manifest", ["hls", "dash", "concat"])
def test_real_probe_rejects_manifests_without_fetching(real_video, tmp_path, manifest):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(real_video.read_bytes())

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    remote = f"http://127.0.0.1:{server.server_port}/private.mp4"
    local = real_video.as_uri()
    if manifest == "hls":
        content = f"#EXTM3U\n#ftyp\n#EXT-X-TARGETDURATION:1\n#EXTINF:1,\n{remote}\n#EXTINF:1,\n{local}\n#EXT-X-ENDLIST\n"
    elif manifest == "dash":
        # This MPD passes the historical `ftyp in first 64KiB` heuristic and
        # makes unrestricted ffprobe fetch the loopback URL even with .mp4.
        content = f'''<?xml version="1.0"?><MPD xmlns="urn:mpeg:dash:schema:mpd:2011"
            profiles="urn:mpeg:dash:profile:isoff-on-demand:2011" type="static"
            mediaPresentationDuration="PT1S" minBufferTime="PT1S"><!--ftyp-->
            <Period><AdaptationSet mimeType="video/mp4"><Representation id="1"
            bandwidth="1000" codecs="avc1.64001e"><BaseURL>{remote}</BaseURL>
            <SegmentBase indexRange="0-0"><Initialization range="0-0"/></SegmentBase>
            </Representation></AdaptationSet></Period></MPD>'''
    else:
        content = f"ffconcat version 1.0\n#ftyp\nfile '{remote}'\nfile '{local}'\n"
    path = tmp_path / "malicious.mp4"
    path.write_text(content)
    try:
        with pytest.raises(RuntimeError, match="ffprobe failed"):
            video._get_video_wh(path)
        assert requests == []
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)


def test_real_probe_rejects_manifest_referencing_local_media(real_video, tmp_path):
    path = tmp_path / "local-manifest.mp4"
    path.write_text(f"ffconcat version 1.0\n#ftyp\nfile '{real_video.name}'\n")
    with pytest.raises(RuntimeError, match="ffprobe failed"):
        video._get_video_wh(path)
