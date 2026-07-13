from __future__ import annotations

from pathlib import Path


def build_restricted_pi_rpc_command(
    *,
    binary: str,
    session_dir: Path,
    extension_path: Path,
    provider: str,
    model: str,
    thinking: str,
    continue_session: bool = False,
    trust_generated_context: bool = False,
) -> list[str]:
    """Build the common, extension-only Pi RPC command for application agents."""

    command = [binary, "--mode", "rpc", "--session-dir", str(session_dir)]
    if continue_session:
        command.append("--continue")
    command.extend(
        [
            "--extension",
            str(extension_path),
            "--no-builtin-tools",
            "--no-extensions",
            "--no-skills",
            "--no-prompt-templates",
            "--no-themes",
        ]
    )
    if trust_generated_context:
        command.append("--approve")
    else:
        command.extend(["--no-approve", "--no-context-files"])
    command.extend(["--provider", provider, "--model", model, "--thinking", thinking])
    return command
