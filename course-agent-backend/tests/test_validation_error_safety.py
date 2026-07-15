from app.utils.json_safety import json_safe


def test_validation_errors_never_expose_raw_binary_payloads():
    value = {
        "input": b"username=student&password=secret",
        "ctx": {"error": ValueError("invalid body")},
    }

    result = json_safe(value)

    assert result["input"] == "<binary payload: 32 bytes>"
    assert result["ctx"]["error"] == "invalid body"
