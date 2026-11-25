from score import score_record


def make_record(command: str, task: dict) -> dict:
    return {
        "status": "ok",
        "model_command": command,
        "parse_error": None,
        "reasoning_leak": False,
        "output_format": "api_json",
        "expected_command": task["expected_command"],
    }


def test_exact_command_passes():
    task = {
        "expected_command": "glab issue list --closed",
        "required_flags": ["--closed"],
        "forbidden_patterns": ["--state"],
    }
    checks = score_record(make_record("glab issue list --closed", task), task)
    assert checks["pass"] is True
    assert checks["error_type"] is None


def test_hallucinated_flag_is_invalid_flag():
    task = {
        "expected_command": "glab issue list",
        "required_flags": [],
        "forbidden_patterns": ["--state"],
    }
    checks = score_record(make_record("glab issue list --state open", task), task)
    assert checks["pass"] is False
    assert checks["error_type"] == "invalid_flag"
    assert "--state" in checks["diff"]["forbidden"]


def test_missing_required_flag_is_reported():
    task = {
        "expected_command": "glab ci status --branch main",
        "required_flags": ["--branch main"],
        "forbidden_patterns": [],
    }
    checks = score_record(make_record("glab ci status", task), task)
    assert checks["error_type"] == "missing_required_flag"
    assert checks["diff"]["missing"] == ["--branch main"]
