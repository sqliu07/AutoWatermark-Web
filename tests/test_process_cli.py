import pytest

import process as process_module
from errors import WatermarkError, WatermarkErrorCode


def test_process_cli_reports_watermark_error(monkeypatch):
    messages = []

    class DummyLogger:
        def error(self, message):
            messages.append(message)

    def fake_process_image(*_args, **_kwargs):
        raise WatermarkError(WatermarkErrorCode.MISSING_EXIF_DATA)

    monkeypatch.setattr(process_module, "logger", DummyLogger())
    monkeypatch.setattr(process_module, "process_image", fake_process_image)
    monkeypatch.setattr(process_module.sys, "argv", ["process.py", "photo.jpg", "en", "1", "85"])

    with pytest.raises(SystemExit) as exc_info:
        process_module.main()

    assert exc_info.value.code == 1
    assert messages == ["This image does not contain valid exif data!"]
