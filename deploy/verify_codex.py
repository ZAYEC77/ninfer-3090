#!/usr/bin/env python3
"""Exercise real Codex/NInfer tool calls in a disposable server directory."""
import json
from pathlib import Path
import secrets
import subprocess
import tempfile

binary = str(Path.home() / ".local/bin/codex")
with tempfile.TemporaryDirectory(prefix="codex-ninfer-smoke-") as tmp:
    marker = "CODEX_NINFER_" + secrets.token_hex(6)
    Path(tmp, "probe.txt").write_text(marker + "\n")
    prompt = (
        "Use a shell command to read probe.txt in the current directory. "
        "Then use apply_patch to create result.txt containing exactly the same "
        "single line as probe.txt. Do not change any other file. "
        "Finally reply with only the exact content of probe.txt. "
        "This is a connection, shell, and apply_patch smoke test. "
        "Do not delegate or spawn agents. If a command fails, stop immediately "
        "and report its exact error without retrying."
    )
    cmd = [binary, "exec", "--strict-config", "--skip-git-repo-check", "--ephemeral",
           "--sandbox", "workspace-write", "--json", "-C", tmp, prompt]
    print("Starting disposable Codex/NInfer tool test", flush=True)
    p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True,
                       text=True, timeout=180)
    events = []
    for line in p.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    checks = {
        "exit_zero": p.returncode == 0,
        "turn_completed": any(e.get("type") == "turn.completed" for e in events),
        "shell_succeeded": any(e.get("item", {}).get("type") == "command_execution"
                               and e["item"].get("exit_code") == 0 for e in events),
        "patch_succeeded": any(e.get("item", {}).get("type") == "file_change"
                               and e["item"].get("status") == "completed" for e in events),
        "exact_file_content": Path(tmp, "result.txt").is_file()
                              and Path(tmp, "result.txt").read_text() == marker + "\n",
        "exact_answer": any(e.get("item", {}).get("type") == "agent_message"
                            and e["item"].get("text", "").strip() == marker for e in events),
    }
    print(p.stderr[-3000:])
    print(p.stdout[-16000:])
    print(json.dumps(checks))
    if not all(checks.values()):
        raise SystemExit(1)
