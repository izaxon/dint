from __future__ import annotations

from dint.engines import ClaudeEngine, CodexEngine, parse_claude_line, parse_codex_line


def test_cli_argv_resume() -> None:
    claude = ClaudeEngine(binary="claude")
    assert "--resume" not in claude.argv("hi", ".", None)
    assert claude.argv("hi", ".", "ses-1")[-3:-1] == ["--resume", "ses-1"]
    codex = CodexEngine(binary="codex")
    assert "resume" not in codex.argv("hi", r"C:\proj", None)
    assert codex.argv("hi", r"C:\proj", "thr_1")[:4] == ["codex", "exec", "resume", "thr_1"]


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
