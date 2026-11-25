from common import normalize_command, parse_model_output, tokenize


def test_normalize_command_expands_short_flags_and_equals_form():
    assert tokenize("glab issue list -R group/project --assignee=@me") == [
        "glab",
        "issue",
        "list",
        "--repo",
        "group/project",
        "--assignee",
        "@me",
    ]
    assert normalize_command("glab issue list -R group/project") == "glab issue list --repo group/project"


def test_parse_api_tool_call_arguments():
    response = {
        "message": {
            "content": None,
            "tool_calls": [
                {"function": {"arguments": '{"command": "glab issue list --closed"}'}}
            ],
        }
    }
    parsed = parse_model_output(response)
    assert parsed["command"] == "glab issue list --closed"
    assert parsed["output_format"] == "api_json"
    assert parsed["parse_error"] is None


def test_parse_native_xml_tool_call():
    response = {
        "message": {
            "content": (
                "<tool_call><function=run_glab_command>"
                "<parameter=command>glab mr list --merged</parameter>"
                "</function></tool_call>"
            ),
            "tool_calls": [],
        }
    }
    parsed = parse_model_output(response)
    assert parsed["command"] == "glab mr list --merged"
    assert parsed["output_format"] == "xml"
    assert parsed["parse_error"] is None


def test_plain_text_is_not_a_valid_tool_call():
    response = {"message": {"content": "<think>reasoning</think>glab issue list", "tool_calls": []}}
    parsed = parse_model_output(response)
    assert parsed["parse_error"] == "no_tool_call"
    assert parsed["reasoning_leak"] is True
    assert parsed["visible_text"] == "glab issue list"
