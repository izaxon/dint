from __future__ import annotations

from dint.engines.claude import parse_claude_line
from dint.engines.codex import parse_codex_line


def test_claude_resume_session_and_tools() -> None:
    events = []
    events += parse_claude_line(
        '{"type":"system","subtype":"init","session_id":"ses-1"}'
    )
    events += parse_claude_line(
        '{"type":"assistant","session_id":"ses-1","message":{"content":['
        '{"type":"tool_use","name":"Read","input":{"file_path":"a.py"}},'
        '{"type":"text","text":"Looks good"}]}}'
    )
    events += parse_claude_line(
        '{"type":"result","subtype":"success","session_id":"ses-1","result":"Looks good"}'
    )
    kinds = [e.type for e in events]
    assert "ses-1" in {e.session_id for e in events}
    assert "tool" in kinds
    assert any(e.type == "text" and e.text == "Looks good" for e in events)
    assert kinds[-1] == "done"


def test_codex_thread_id_and_followup_shape() -> None:
    started = parse_codex_line('{"type":"thread.started","thread_id":"thr_abc"}')
    assert started[0].session_id == "thr_abc"
    text = parse_codex_line(
        '{"type":"item.completed","item":{"type":"agent_message","text":"plan ready"}}'
    )
    assert text[0].type == "text"
    assert text[0].text == "plan ready"
    tool = parse_codex_line(
        '{"type":"item.completed","item":{"type":"command_execution","command":"ls"}}'
    )
    assert tool[0].type == "tool"
    done = parse_codex_line('{"type":"turn.completed"}')
    assert done[0].type == "done"
