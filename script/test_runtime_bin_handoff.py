#!/usr/bin/env python3
"""Run the runtime-bin bootstrap blocks without the terminal protocol/UI."""

import os
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path


BOOTSTRAP = Path(__file__).resolve().parents[1] / "app/assets/bundled/bootstrap"
MARKER = "# System profiles can discard the runtime commands inherited from the container entrypoint."


def check_shell(shell, root):
    executable = shutil.which(shell)
    if executable is None:
        raise RuntimeError(f"{shell} is required")
    filename = {"bash": "bash_body.sh", "zsh": "zsh_body.sh", "fish": "fish.sh"}[shell]
    block = (BOOTSTRAP / filename).read_text().split(MARKER, 1)[1].split("\n\n", 1)[0]
    runtime = str(root / "runtime [bin]")
    profile_path = f"{root}/customer:{root}/system:/usr/bin:/bin"
    command_shim = """
command() {
    if [[ "$*" == "-p uname -s" ]]; then
        printf '%s\\n' "$TEST_KERNEL"
    else
        builtin command "$@"
    fi
}
"""
    scenarios = [
        ("profile reset", runtime, profile_path, "Linux", f"{runtime}:{profile_path}"),
        (
            "duplicate entries",
            runtime,
            f"{runtime}:{profile_path}:{runtime}",
            "Linux",
            f"{runtime}:{profile_path}",
        ),
        ("unset", None, profile_path, "Linux", profile_path),
        ("missing directory", str(root / "missing"), profile_path, "Linux", profile_path),
        ("relative directory", "runtime [bin]", profile_path, "Linux", profile_path),
        ("non-Linux", runtime, profile_path, "Darwin", profile_path),
    ]
    for label, directory, initial_path, kernel, expected in scenarios:
        environment = os.environ.copy()
        environment.pop("WARP_RUNTIME_BIN", None)
        environment["TEST_KERNEL"] = kernel
        if directory is not None:
            environment["WARP_RUNTIME_BIN"] = directory
        profile = root / f"profile.{shell}"
        if shell == "fish":
            profile.write_text(f"set -gx PATH {shlex.quote(initial_path)}\n")
            setup = ""
            report = 'printf "%s\\n" (string join : $PATH); ffmpeg'
        else:
            profile.write_text(f"export PATH={shlex.quote(initial_path)}\n")
            setup = command_shim
            report = 'printf "%s\\n" "$PATH"; ffmpeg'
        script = f"{setup}\nsource {shlex.quote(str(profile))}\n{block}\n{block}\n{report}"
        result = subprocess.run(
            [executable, "-c", script],
            env=environment,
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
        selected_tool = "runtime" if expected.startswith(runtime + ":") else "customer"
        assert result.stdout.splitlines() == [expected, selected_tool], (
            f"{shell}: {label}: {result.stdout!r}\n{result.stderr}"
        )
        print(f"PASS {shell}: {label}")


def main():
    with tempfile.TemporaryDirectory(prefix="warp-runtime-bin-") as directory:
        root = Path(directory)
        for name in ("runtime [bin]", "customer", "system"):
            (root / name).mkdir()
        for name, result in (("runtime [bin]", "runtime"), ("customer", "customer")):
            tool = root / name / "ffmpeg"
            tool.write_text(f"#!/bin/sh\nprintf '{result}\\n'\n")
            tool.chmod(0o755)
        uname = root / "system" / "uname"
        uname.write_text('#!/bin/sh\nprintf "%s\\n" "$TEST_KERNEL"\n')
        uname.chmod(0o755)
        for shell in ("bash", "zsh", "fish"):
            check_shell(shell, root)


if __name__ == "__main__":
    main()
