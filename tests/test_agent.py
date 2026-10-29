import json

import pytest

from structural_engine import engineering_agent as ea
from structural_engine.dxf_structural_inference import analyze_dxf_structure
from structural_engine.engineering_agent import (
    EngineeringAgent,
    EngineeringTool,
    build_engineering_tools,
)

SCHEMA = {"type": "object", "properties": {}, "additionalProperties": False}


def call(name):
    return {
        "message": {"content": "", "tool_calls": [{"function": {"name": name, "arguments": {}}}]}
    }


def final(text="done"):
    return {"message": {"content": text}}


class FakeClient:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def chat_response(self, model, messages, image_bytes=None, tools=None, options=None, **_):
        self.calls.append(
            {"messages": [dict(m) for m in messages], "options": options, "tools": tools}
        )
        return self.script.pop(0)


def tool(name, payload=None):
    return EngineeringTool(name, "d", SCHEMA, lambda args: dict(payload or {"tool_status": "OK"}))


def test_tool_then_final_answer():
    client = FakeClient(call("a"), final("ok"))
    res = EngineeringAgent(client=client).run("m", [{"role": "user", "content": "hi"}], [tool("a")])
    assert res.stopped_reason == "MODEL_FINAL_RESPONSE" and res.final_text == "ok"
    assert set(res.tool_results) == {"a"} and res.trace[0]["status"] == "OK"


def test_repeated_and_unknown_tools_are_blocked():
    client = FakeClient(call("a"), call("a"), call("ghost"), final())
    res = EngineeringAgent(client=client).run("m", [], [tool("a")])
    statuses = [t["status"] for t in res.trace]
    assert statuses == ["OK", "BLOCKED", "BLOCKED"]


def test_tool_budget_is_enforced():
    client = FakeClient(call("a"), call("b"), call("c"), final())
    res = EngineeringAgent(client=client, max_tool_calls=2).run(
        "m", [], [tool("a"), tool("b"), tool("c")]
    )
    assert [t["status"] for t in res.trace] == ["OK", "OK", "BLOCKED"]


def test_huge_tool_results_are_truncated_before_reaching_the_model():
    client = FakeClient(call("big"), final())
    EngineeringAgent(client=client).run(
        "m", [], [tool("big", {"tool_status": "OK", "blob": "x" * 20000})]
    )
    sent = [m for m in client.calls[1]["messages"] if m.get("role") == "tool"][0]["content"]
    assert len(sent) <= ea.TOOL_RESULT_CHAR_LIMIT + 50
    assert json.loads(sent)["truncated"] is True


def test_small_results_pass_through_untouched():
    client = FakeClient(call("a"), final())
    EngineeringAgent(client=client).run("m", [], [tool("a", {"tool_status": "OK", "n": 3})])
    sent = [m for m in client.calls[1]["messages"] if m.get("role") == "tool"][0]["content"]
    assert json.loads(sent) == {"tool_status": "OK", "n": 3}


def test_context_window_is_configurable(monkeypatch):
    monkeypatch.delenv("STRUCTURAL_STUDIO_NUM_CTX", raising=False)
    assert ea._model_options()["num_ctx"] == ea.DEFAULT_NUM_CTX
    monkeypatch.setenv("STRUCTURAL_STUDIO_NUM_CTX", "8192")
    assert ea._model_options()["num_ctx"] == 8192
    monkeypatch.setenv("STRUCTURAL_STUDIO_NUM_CTX", "garbage")
    assert ea._model_options()["num_ctx"] == ea.DEFAULT_NUM_CTX
    monkeypatch.setenv("STRUCTURAL_STUDIO_NUM_CTX", "10")
    assert ea._model_options()["num_ctx"] == 2048  # never below a usable minimum


def test_time_budget_stops_the_loop(monkeypatch):
    ticks = iter([0.0, 0.0, 1000.0])  # deadline set, round 1 allowed, round 2 past the deadline
    monkeypatch.setattr(ea.time, "monotonic", lambda: next(ticks, 1000.0))
    client = FakeClient(call("a"), final("summary"))
    res = EngineeringAgent(client=client, max_seconds=5).run("m", [], [tool("a")])
    assert res.stopped_reason == "TIME_BUDGET" and res.final_text == "summary"
    assert len(client.calls) == 2  # one tool round + the closing summary, not 7 rounds


def test_recommendation_reports_observed_evidence(sample_dxf_bytes):
    analysis = analyze_dxf_structure(sample_dxf_bytes, "s.dxf")
    tools = {t.name: t for t in build_engineering_tools({"dxf_structural_analysis": analysis}, {})}
    res = tools["recommend_structural_system_from_reviewed_dxf"].execute({})

    # still not a decision: the drawing cannot prove a structural system
    assert res["system_id"] == "insufficient_data" and res["automatic_analysis_allowed"] is False
    ev = res["evidence"]
    assert ev["included_entities_by_role"]["column"] == 5
    assert ev["column_entities_as_loose_lines"] == 2
    assert ev["column_entities_with_closed_outline"] >= 3
    ids = {x["system_id"] for x in res["system_indicators"]}
    assert ids == {"rc_beam_slab", "rc_flat_plate", "rc_shear_wall", "load_bearing_walls"}
    flat = [x for x in res["system_indicators"] if x["system_id"] == "rc_flat_plate"][0]
    assert "لا يثبت" in flat["observed"]  # absence of beams is explicitly not proof


def test_recommendation_changes_with_the_drawing(make_dxf, sample_dxf_bytes):
    def only_walls(doc, msp):
        doc.layers.add("wall 25cm")
        for i in range(3):
            msp.add_lwpolyline(
                [(0, i * 3000), (5000, i * 3000), (5000, i * 3000 + 250)],
                close=True,
                dxfattribs={"layer": "wall 25cm"},
            )

    a_walls = analyze_dxf_structure(make_dxf(only_walls), "w.dxf")
    a_cols = analyze_dxf_structure(sample_dxf_bytes, "s.dxf")
    rec = lambda a: {
        t.name: t for t in build_engineering_tools({"dxf_structural_analysis": a}, {})
    }["recommend_structural_system_from_reviewed_dxf"].execute({})["evidence"][
        "included_entities_by_role"
    ]
    assert rec(a_walls) == {"wall": 3}
    assert rec(a_cols).get("wall") is None and rec(a_cols)["column"] == 5
