"""Smoke tests: the builder is importable and the fake backend intercepts I/O."""
from src.services import escpos_service
from src.services.print_job_builder import PrintJobBuilder


def test_print_job_builder_empty_job_returns_non_empty_bytes():
    data = PrintJobBuilder(48).to_bytes()
    assert isinstance(data, bytes)
    assert len(data) > 0


def test_list_printers_with_fake_backend_returns_fake_printers(fake_backend):
    assert escpos_service.list_printers() == ["TestPrinter"]
