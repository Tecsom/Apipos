"""Unit tests for the standard service response envelope {status, data, message}."""
from src.utils.response import error_response, success_response

ENVELOPE_KEYS = {"status", "data", "message"}


def test_success_response_defaults_exact_shape():
    response = success_response()
    assert set(response) == ENVELOPE_KEYS
    assert response == {"status": "success", "data": None, "message": ""}
    assert isinstance(response["message"], str)


def test_success_response_with_values_keeps_them_unchanged():
    payload = {"printers": ["A", "B"]}
    response = success_response(payload, "ok")
    assert set(response) == ENVELOPE_KEYS
    assert response["status"] == "success"
    assert response["data"] is payload
    assert response["message"] == "ok"


def test_error_response_defaults_data_to_none():
    response = error_response("No printer selected.")
    assert set(response) == ENVELOPE_KEYS
    assert response == {"status": "error", "data": None, "message": "No printer selected."}


def test_error_response_with_data_keeps_message_first_signature():
    response = error_response("Printer 'X' not found.", {"available": ["TestPrinter"]})
    assert set(response) == ENVELOPE_KEYS
    assert response["status"] == "error"
    assert response["message"] == "Printer 'X' not found."
    assert response["data"] == {"available": ["TestPrinter"]}
    assert isinstance(response["data"]["available"], list)


def test_responses_are_independent_dicts():
    first = success_response()
    first["data"] = "mutated"
    assert success_response()["data"] is None
    assert error_response("e") is not error_response("e")
