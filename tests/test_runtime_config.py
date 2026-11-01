import logging
from concurrent.futures import ThreadPoolExecutor
from logging.handlers import RotatingFileHandler

import logging_utils


def test_logger_rotates_and_keeps_console_without_duplicates(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(logging_utils, '_LOG_DIR', str(tmp_path))
    monkeypatch.setattr(logging_utils, '_LOG_FILE', str(tmp_path / 'app.log'))
    logger = logging_utils.get_logger('runtime-config-test')
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            configured = list(pool.map(lambda _: logging_utils.get_logger('runtime-config-test'), range(32)))
        assert all(item is logger for item in configured)
        files = [h for h in logger.handlers if isinstance(h, RotatingFileHandler)]
        consoles = [h for h in logger.handlers if isinstance(h, logging.StreamHandler)
                    and not isinstance(h, logging.FileHandler)]
        assert len(files) == len(consoles) == 1
        assert files[0].maxBytes > 0 and files[0].backupCount > 0
        files[0].maxBytes = 80
        logger.info('first message ' + 'a' * 80)
        logger.info('second message')
        assert 'second message' in capsys.readouterr().out
        assert (tmp_path / 'app.log.1').exists()
    finally:
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
            handler.close()
