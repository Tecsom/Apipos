"""Unit tests for the app log (src/app_log.py)."""
import _thread
import io
import logging
import os
import sys
import threading

import pytest

from src import app_log


@pytest.fixture
def log_file(tmp_path, monkeypatch):
    """Point app_log at a temp file and undo what setup_logging touches."""
    path = tmp_path / "logs" / "apipos.log"
    monkeypatch.setattr(app_log, "LOG_FILE", str(path))
    monkeypatch.setattr(app_log, "_configured", False)
    monkeypatch.setattr(app_log, "_crash_file", None)
    # pytest arms faulthandler itself; atexit hooks would outlive the test.
    monkeypatch.setattr(app_log.faulthandler, "enable", lambda **kwargs: None)
    monkeypatch.setattr(app_log.atexit, "register", lambda func: func)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    monkeypatch.setattr(logging, "raiseExceptions", logging.raiseExceptions)
    loggers = [logging.getLogger(n) for n in ("", "stdout", "stderr", "werkzeug")]
    saved = [(lg, list(lg.handlers), lg.level, lg.propagate) for lg in loggers]
    yield path
    for lg, handlers, level, propagate in saved:
        for handler in lg.handlers:
            if handler not in handlers:
                handler.close()
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate = propagate
    if app_log._crash_file is not None:
        app_log._crash_file.close()


def _read(path):
    return path.read_text(encoding="utf-8")


def _console(monkeypatch):
    """Install fresh in-memory stdout / stderr and return (stdout, stderr).

    pytest's own capture re-points sys.stdout / sys.stderr when the test body
    starts, discarding what a fixture patched during setup; patching here,
    inside the body, is the only way to know what the "original" streams are.
    """
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    return out, err


def _default_thread_excepthook():
    """The stock threading.excepthook (threading.__excepthook__ is 3.10+)."""
    return getattr(threading, "__excepthook__", None) or _thread._excepthook


def _capturing_logger(name):
    """A private INFO logger whose formatted messages land in a list."""
    records = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    logger = logging.getLogger(name)
    logger.handlers[:] = [ListHandler()]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    return logger, records


# ---------------------------------------------------------------------------
# setup_logging
# ---------------------------------------------------------------------------

def test_setup_logging_returns_path_and_writes_startup_line(log_file):
    result = app_log.setup_logging()

    assert result == str(log_file)
    assert log_file.parent.is_dir()
    text = _read(log_file)
    assert "iniciando" in text
    assert app_log.APP_VERSION in text


def test_setup_logging_second_call_returns_same_and_adds_no_handlers(log_file):
    first = app_log.setup_logging()
    handlers = list(logging.getLogger().handlers)

    second = app_log.setup_logging()

    assert second == first == str(log_file)
    assert logging.getLogger().handlers == handlers
    assert _read(log_file).count("iniciando") == 1


def test_setup_logging_routes_logging_records_to_the_file(log_file):
    app_log.setup_logging()

    app_log.log.info("registro de prueba")

    assert "INFO" in _read(log_file)
    assert "apipos: registro de prueba" in _read(log_file)


def test_setup_logging_print_goes_to_log_and_is_echoed_to_console(log_file, monkeypatch):
    original_out, _ = _console(monkeypatch)

    app_log.setup_logging()
    print("hola ñ")

    assert "stdout: hola ñ" in _read(log_file)
    assert "hola ñ" in original_out.getvalue()


def test_setup_logging_stderr_write_is_logged_as_warning(log_file, monkeypatch):
    _, original_err = _console(monkeypatch)

    app_log.setup_logging()
    sys.stderr.write("algo salio mal\n")

    assert "WARNING" in _read(log_file)
    assert "stderr: algo salio mal" in _read(log_file)
    assert "algo salio mal" in original_err.getvalue()


def test_setup_logging_without_console_print_reaches_the_log(log_file, monkeypatch):
    # The windowed PyInstaller build on Windows has no stdout / stderr at all.
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)

    app_log.setup_logging()
    print("sin consola")

    assert "stdout: sin consola" in _read(log_file)


def test_setup_logging_thread_exception_traceback_reaches_the_log(log_file, monkeypatch):
    # pytest replaces threading.excepthook; restore the default (writes to stderr).
    monkeypatch.setattr(threading, "excepthook", _default_thread_excepthook())
    _console(monkeypatch)
    app_log.setup_logging()

    def boom():
        raise ValueError("boom-hilo")

    thread = threading.Thread(target=boom, name="boom-thread")
    thread.start()
    thread.join()

    text = _read(log_file)
    assert "Exception in thread" in text
    assert "ValueError: boom-hilo" in text


def test_setup_logging_big_previous_log_is_rotated_to_dot_one(log_file):
    log_file.parent.mkdir(parents=True)
    log_file.write_bytes(b"x" * (app_log.LOG_MAX_BYTES + 1))

    app_log.setup_logging()

    rotated = log_file.with_name("apipos.log.1")
    assert rotated.stat().st_size == app_log.LOG_MAX_BYTES + 1
    assert log_file.stat().st_size < 10_000
    assert "iniciando" in _read(log_file)


def test_setup_logging_small_previous_log_is_kept_and_appended(log_file):
    log_file.parent.mkdir(parents=True)
    log_file.write_text("linea previa\n", encoding="utf-8")

    app_log.setup_logging()

    assert not log_file.with_name("apipos.log.1").exists()
    text = _read(log_file)
    assert text.startswith("linea previa\n")
    assert "iniciando" in text


def test_setup_logging_unwritable_folder_returns_none_and_keeps_streams(log_file, monkeypatch):
    # The "folder" is a plain file, so it cannot be created.
    log_file.parent.write_text("not a folder", encoding="utf-8")
    original_out, original_err = _console(monkeypatch)

    assert app_log.setup_logging() is None

    assert sys.stdout is original_out
    assert sys.stderr is original_err


def test_setup_logging_sets_werkzeug_to_warning(log_file):
    app_log.setup_logging()

    assert logging.getLogger("werkzeug").level == logging.WARNING


def test_setup_logging_werkzeug_request_lines_are_not_logged(log_file):
    app_log.setup_logging()

    logging.getLogger("werkzeug").info('127.0.0.1 - - "GET /health HTTP/1.1" 200 -')

    assert '"GET /health' not in _read(log_file)


def test_setup_logging_enables_faulthandler_on_the_log_file(log_file, monkeypatch):
    calls = []
    monkeypatch.setattr(app_log.faulthandler, "enable", lambda **kwargs: calls.append(kwargs))

    app_log.setup_logging()

    assert len(calls) == 1
    assert calls[0]["file"].name == str(log_file)


def test_setup_logging_registers_an_atexit_line_that_logs_the_exit(log_file, monkeypatch):
    registered = []
    monkeypatch.setattr(app_log.atexit, "register", lambda func: registered.append(func))

    app_log.setup_logging()
    assert len(registered) == 1
    registered[0]()

    assert "terminó" in _read(log_file)


# ---------------------------------------------------------------------------
# _LogStream
# ---------------------------------------------------------------------------

def test_log_stream_buffers_partial_lines_until_newline():
    logger, records = _capturing_logger("test_log_stream_partial")
    stream = app_log._LogStream(logger, logging.INFO, None)

    stream.write("media ")
    assert records == []
    stream.write("linea\notra\n")

    assert records == ["media linea", "otra"]


def test_log_stream_skips_blank_lines_and_survives_a_broken_echo():
    class BrokenEcho:
        def write(self, text):
            raise OSError("consola rota")

        def flush(self):
            raise OSError("consola rota")

    logger, records = _capturing_logger("test_log_stream_blank")
    stream = app_log._LogStream(logger, logging.INFO, BrokenEcho())

    assert stream.write("\n   \nuna\n") == len("\n   \nuna\n")
    stream.flush()

    assert records == ["una"]
    assert stream.encoding == "utf-8"
    assert stream.writable() is True



# ---------------------------------------------------------------------------
# open_log_folder
# ---------------------------------------------------------------------------

def test_open_log_folder_win32_calls_startfile_with_the_folder(log_file, monkeypatch):
    calls = []
    monkeypatch.setattr(app_log.sys, "platform", "win32")
    monkeypatch.setattr(os, "startfile", lambda folder: calls.append(folder), raising=False)

    app_log.open_log_folder()

    assert calls == [str(log_file.parent)]
    assert log_file.parent.is_dir()


def test_open_log_folder_darwin_calls_open(log_file, monkeypatch):
    calls = []
    monkeypatch.setattr(app_log.sys, "platform", "darwin")
    monkeypatch.setattr(app_log.subprocess, "Popen", lambda args: calls.append(args))

    app_log.open_log_folder()

    assert calls == [["open", str(log_file.parent)]]


def test_open_log_folder_linux_calls_xdg_open(log_file, monkeypatch):
    calls = []
    monkeypatch.setattr(app_log.sys, "platform", "linux")
    monkeypatch.setattr(app_log.subprocess, "Popen", lambda args: calls.append(args))

    app_log.open_log_folder()

    assert calls == [["xdg-open", str(log_file.parent)]]
