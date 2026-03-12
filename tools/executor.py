# ==============================================================================
#  SUNNY AI v5.0 — tools/executor.py
#  python_exec: chạy Python code an toàn (sandbox)
#  shell_run:   chạy shell command an toàn (whitelist)
# ==============================================================================
import subprocess, sys, io, contextlib, datetime
from core.sandbox import Sandbox


def python_exec(code: str) -> str:
    """
    Chạy Python code trong môi trường hạn chế.
    Chặn os.system, subprocess, ghi file, eval, exec, socket, requests.
    """
    if not code or not code.strip():
        return "[Error]: Empty code."

    ok, reason = Sandbox.check_code(code)
    if not ok:
        return f"[Blocked]: {reason}"

    # Capture stdout/stderr
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    # Namespace an toàn — không có builtins nguy hiểm
    import math, datetime, random
    safe_globals = {
        "__builtins__": {
            "print": print,
            "range": range,
            "len": len,
            "int": int,
            "float": float,
            "str": str,
            "list": list,
            "dict": dict,
            "tuple": tuple,
            "set": set,
            "bool": bool,
            "abs": abs,
            "round": round,
            "min": min,
            "max": max,
            "sum": sum,
            "sorted": sorted,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "isinstance": isinstance,
            "type": type,
            "repr": repr,
        },
        "math": math,
        "datetime": datetime,
        "random": random,
    }

    try:
        with contextlib.redirect_stdout(stdout_buf), \
             contextlib.redirect_stderr(stderr_buf):
            exec(compile(code, "<sunny_exec>", "exec"), safe_globals)

        output = stdout_buf.getvalue()
        errors = stderr_buf.getvalue()

        result = ""
        if output:
            result += f"[Output]:\n{output.strip()}"
        if errors:
            result += f"\n[Stderr]:\n{errors.strip()}"
        return result.strip() or "[OK]: Code ran, no output."

    except Exception as e:
        return f"[Error]: {type(e).__name__}: {e}"


def shell_run(cmd: str) -> str:
    """
    Chạy shell command với whitelist an toàn.
    Chỉ cho phép lệnh đọc: dir, ls, echo, pip list...
    """
    if not cmd or not cmd.strip():
        return "[Error]: Empty command."

    ok, reason = Sandbox.check_shell(cmd)
    if not ok:
        return f"[Blocked]: {reason}"

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=10,
            encoding="utf-8",
            errors="replace",
        )
        output = result.stdout.strip()
        errors = result.stderr.strip()

        if output:
            return f"[Shell output]:\n{output}"
        if errors:
            return f"[Shell error]:\n{errors}"
        return "[OK]: Command ran, no output."

    except subprocess.TimeoutExpired:
        return "[Error]: Command timed out (10s limit)."
    except Exception as e:
        return f"[Error]: {e}"
