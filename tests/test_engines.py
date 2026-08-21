from __future__ import annotations

from dint.engines import (
    ClaudeEngine,
    CodexEngine,
    CopilotEngine,
    GrokEngine,
    parse_claude_line,
    parse_codex_line,
    parse_copilot_line,
    parse_grok_line,
)


def test_cli_argv_resume() -> None:
    claude = ClaudeEngine(binary="claude")
    assert "--resume" not in claude.argv("hi", ".", None)
    assert claude.argv("hi", ".", "ses-1")[-3:-1] == ["--resume", "ses-1"]
    codex = CodexEngine(binary="codex")
    assert "resume" not in codex.argv("hi", r"C:\proj", None)
    assert codex.argv("hi", r"C:\proj", "thr_1")[:4] == ["codex", "exec", "resume", "thr_1"]
    grok = GrokEngine(binary="grok")
    g = grok.argv("hi", r"C:\proj", None)
    assert g[:1] == ["grok"] and "-p" in g and "streaming-json" in g
    assert "--resume" not in g
    resumed = grok.argv("hi", r"C:\proj", "ses-g")
    assert resumed[-2:] == ["--resume", "ses-g"]
    copilot = CopilotEngine(binary="copilot")
    c = copilot.argv("hi", r"C:\proj", None)
    assert "-p" in c and "--output-format" in c and "json" in c
    assert not any(a.startswith("--resume") for a in c)
    assert "--resume=ses-c" in copilot.argv("hi", r"C:\proj", "ses-c")


def test_claude_resume_session_and_tools() -> None:
    events = parse_claude_line('{"type":"system","subtype":"init","session_id":"ses-1"}')
    events += parse_claude_line(
        '{"type":"assistant","session_id":"ses-1","message":{"content":['
        '{"type":"tool_use","name":"Read","input":{"file_path":"a.py"}},'
        '{"type":"text","text":"Looks good"}]}}'
    )
    events += parse_claude_line(
        '{"type":"result","subtype":"success","session_id":"ses-1","result":"Looks good"}'
    )
    assert events[0].type == "session" and events[0].session_id == "ses-1"
    assert any(e.type == "tool" for e in events)
    assert any(e.type == "text" and e.text == "Looks good" for e in events)
    assert events[-1].type == "done"


def test_codex_thread_id_and_followup_shape() -> None:
    started = parse_codex_line('{"type":"thread.started","thread_id":"thr_abc"}')
    assert started[0].type == "session" and started[0].session_id == "thr_abc"
    text = parse_codex_line(
        '{"type":"item.completed","item":{"type":"agent_message","text":"plan ready"}}'
    )
    assert text[0].type == "text" and text[0].text == "plan ready"
    tool = parse_codex_line(
        '{"type":"item.completed","item":{"type":"command_execution","command":"ls"}}'
    )
    assert tool[0].type == "tool"
    assert parse_codex_line('{"type":"turn.completed"}')[0].type == "done"


def test_copilot_session_and_tools() -> None:
    events = parse_copilot_line(
        '{"type":"assistant.message","sessionId":"cp-1","data":{"content":"hello world","toolRequests":[{"name":"view"}]}}'
    )
    events += parse_copilot_line(
        '{"type":"tool.execution_start","data":{"toolName":"view"},"sessionId":"cp-1"}'
    )
    events += parse_copilot_line(
        '{"type":"result","sessionId":"cp-1","exitCode":0}'
    )
    assert any(e.type == "text" and "hello" in e.text for e in events)
    assert any(e.type == "tool" for e in events)
    assert events[-1].type == "done" and events[-1].session_id == "cp-1"


def test_grok_native_streaming_json() -> None:
    events = parse_grok_line('{"type":"thought","data":"hmm"}')
    events += parse_grok_line('{"type":"text","data":"Hej"}')
    events += parse_grok_line('{"type":"text","data":"!"}')
    events += parse_grok_line('{"type":"tool_call","toolName":"read_file","title":"Read"}')
    events += parse_grok_line('{"type":"end","sessionId":"abc123","stopReason":"end_turn"}')
    assert not any(e.type == "text" and e.text == "hmm" for e in events)
    assert [e.text for e in events if e.type == "text"] == ["Hej", "!"]
    assert any(e.type == "tool" and e.tool == "read_file" for e in events)
    assert events[-1].type == "done" and events[-1].session_id == "abc123"
