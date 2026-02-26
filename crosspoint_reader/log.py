import os
import sys
import time
import traceback
from contextlib import suppress


_LOG = []
_MAX_LINES = 500
_LOG_FILE = None


def _get_log_file_path():
    """Get the path to the persistent log file in Calibre config directory."""
    global _LOG_FILE
    if _LOG_FILE is not None:
        return _LOG_FILE

    with suppress(Exception):
        from calibre.utils.config import config_dir
        log_dir = os.path.join(config_dir, 'logs')
        os.makedirs(log_dir, exist_ok=True)
        _LOG_FILE = os.path.join(log_dir, 'crosspoint_reader.log')
        return _LOG_FILE
    return None


def add_log(message):
    """Add a log message with timestamp."""
    timestamp = time.strftime('%H:%M:%S')
    line = f'[{timestamp}] {message}'
    _LOG.append(line)
    if len(_LOG) > _MAX_LINES:
        _LOG[:len(_LOG) - _MAX_LINES] = []

    # Also write to persistent log file
    log_path = _get_log_file_path()
    if log_path:
        with suppress(Exception):
            with open(log_path, 'a', encoding='utf-8') as f:
                f.write(line + '\n')


def add_error(message, exc=None):
    """Add an error log message with optional traceback."""
    if exc:
        tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
        tb = ''.join(tb_lines).strip()
        add_log(f'ERROR: {message}')
        for line in tb.split('\n'):
            if line.strip():
                add_log(f'  {line}')
    else:
        add_log(f'ERROR: {message}')

    # Also log to Calibre's log if available
    with suppress(Exception):
        from calibre.utils.logging import default_log
        default_log.error(f'[CrossPoint] {message}')


def add_warning(message):
    """Add a warning log message."""
    add_log(f'WARNING: {message}')

    # Also log to Calibre's log if available
    with suppress(Exception):
        from calibre.utils.logging import default_log
        default_log.warning(f'[CrossPoint] {message}')


def add_debug(message):
    """Add a debug log message."""
    add_log(f'DEBUG: {message}')


def add_info(message):
    """Add an info log message."""
    add_log(f'INFO: {message}')


def get_log_text():
    """Get all log lines as a single string."""
    return '\n'.join(_LOG)


def clear_log():
    """Clear all log entries."""
    global _LOG
    _LOG = []


def get_log_file_path():
    """Get the path to the persistent log file, if available."""
    return _get_log_file_path()
