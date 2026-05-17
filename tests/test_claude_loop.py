"""Validate TOOL_DEFS match the real tools.py function signatures."""

import inspect

from src import tools
from src.claude_loop import TOOL_DEFS, TOOL_IMPLS


def _params(fn) -> dict[str, inspect.Parameter]:
    return dict(inspect.signature(fn).parameters)


def test_tool_def_names_match_tools_module():
    expected = {
        "lookup_user",
        "match_lawyers",
        "connect_to_lawyer",
        "research_and_email",
        "end_call",
        "escalate_to_human",
        "route_to_public_defender",
    }
    defined = {td["name"] for td in TOOL_DEFS}
    assert defined == expected


def test_tool_impls_dispatch_to_real_functions():
    assert TOOL_IMPLS["lookup_user"] is tools.lookup_user
    assert TOOL_IMPLS["match_lawyers"] is tools.match_lawyers
    assert TOOL_IMPLS["connect_to_lawyer"] is tools.connect_to_lawyer
    assert TOOL_IMPLS["research_and_email"] is tools.research_and_email
    assert TOOL_IMPLS["end_call"] is tools.end_call
    assert TOOL_IMPLS["escalate_to_human"] is tools.escalate_to_human
    assert TOOL_IMPLS["route_to_public_defender"] is tools.route_to_public_defender


def test_end_call_schema_matches_signature():
    td = next(td for td in TOOL_DEFS if td["name"] == "end_call")
    schema_props = set(td["input_schema"]["properties"].keys())
    fn_params = set(_params(tools.end_call).keys())
    assert schema_props == fn_params
    required = set(td["input_schema"]["required"])
    assert required == fn_params


def test_research_and_email_schema_matches_signature():
    td = next(td for td in TOOL_DEFS if td["name"] == "research_and_email")
    schema_props = set(td["input_schema"]["properties"].keys())
    fn_params = set(_params(tools.research_and_email).keys())
    assert schema_props == fn_params
    required = set(td["input_schema"]["required"])
    assert required == fn_params


def test_lookup_user_schema_matches_signature():
    td = next(td for td in TOOL_DEFS if td["name"] == "lookup_user")
    schema_props = set(td["input_schema"]["properties"].keys())
    fn_params = set(_params(tools.lookup_user).keys())
    assert schema_props == fn_params
    # lookup_user has all optional params
    assert "required" not in td["input_schema"] or td["input_schema"]["required"] == []


def test_match_lawyers_schema_matches_signature():
    td = next(td for td in TOOL_DEFS if td["name"] == "match_lawyers")
    schema_props = set(td["input_schema"]["properties"].keys())
    fn_params = set(_params(tools.match_lawyers).keys())
    assert schema_props == fn_params
    # jurisdiction_county is Optional in the Python signature; everything else required
    required = set(td["input_schema"]["required"])
    assert required == {"user_id", "jurisdiction_state", "practice_area", "urgency"}


def test_connect_to_lawyer_schema_matches_signature():
    td = next(td for td in TOOL_DEFS if td["name"] == "connect_to_lawyer")
    schema_props = set(td["input_schema"]["properties"].keys())
    fn_params = set(_params(tools.connect_to_lawyer).keys())
    assert schema_props == fn_params
    required = set(td["input_schema"]["required"])
    assert required == fn_params


def test_escalate_to_human_schema_matches_signature():
    td = next(td for td in TOOL_DEFS if td["name"] == "escalate_to_human")
    schema_props = set(td["input_schema"]["properties"].keys())
    fn_params = set(_params(tools.escalate_to_human).keys())
    assert schema_props == fn_params
    required = set(td["input_schema"]["required"])
    assert required == fn_params


def test_route_to_public_defender_schema_matches_signature():
    td = next(td for td in TOOL_DEFS if td["name"] == "route_to_public_defender")
    schema_props = set(td["input_schema"]["properties"].keys())
    fn_params = set(_params(tools.route_to_public_defender).keys())
    assert schema_props == fn_params
    required = set(td["input_schema"]["required"])
    assert required == fn_params


def test_match_lawyers_urgency_is_enum():
    td = next(td for td in TOOL_DEFS if td["name"] == "match_lawyers")
    urgency = td["input_schema"]["properties"]["urgency"]
    assert urgency.get("enum") == ["urgent", "non_urgent"]


def test_all_tool_def_properties_have_types():
    for td in TOOL_DEFS:
        for prop_name, prop in td["input_schema"]["properties"].items():
            assert "type" in prop, f"{td['name']}.{prop_name} missing type"
