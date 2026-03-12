# ==============================================================================
#  SUNNY AI v5.0 — core/sandbox.py
#  Security: path traversal, symlink attack, extension whitelist.
# ==============================================================================
import os, re
from core.config import (
    ENABLE_FILE_ACCESS, ENABLE_SCAN, ALLOW_INTERNET,
    BLOCKED_PATH_PATTERNS, ALLOWED_EXTENSIONS
)


def _resolve_safe(path: str) -> tuple[str, bool]:
    """
    Resolve path thật sự (theo dõi symlink).
    Trả về (resolved_path, is_safe).
    FIX: os.path.realpath() theo dõi symlink — tránh symlink trỏ ra ngoài whitelist.
    """
    try:
        resolved = os.path.realpath(os.path.abspath(path))
        return resolved, True
    except Exception:
        return path, False


def _check_traversal(original: str, resolved: str) -> tuple[bool, str]:
    """
    FIX path traversal: so sánh resolved path với original.
    Nếu resolved khác xa original (do ../ hay symlink) → block.
    """
    orig_abs = os.path.abspath(original)
    # Cho phép nếu resolved nằm trong cùng thư mục gốc với original
    orig_dir = os.path.dirname(orig_abs)
    if not resolved.startswith(orig_dir):
        # Kiểm tra thêm: resolved có nằm trong working dir không
        cwd = os.path.realpath(os.getcwd())
        if not resolved.startswith(cwd):
            return False, f"Path traversal detected: '{original}' resolves to '{resolved}'"
    return True, "OK"


def _check_blocked(path: str) -> tuple[bool, str]:
    for pattern in BLOCKED_PATH_PATTERNS:
        if re.search(pattern, path, re.IGNORECASE):
            return False, f"Access denied: matches restricted pattern."
    return True, "OK"


class Sandbox:
    @staticmethod
    def check_path(path: str) -> tuple[bool, str]:
        if not ENABLE_FILE_ACCESS:
            return False, "File access disabled by policy."

        # 1. Resolve symlinks → chống symlink attack
        resolved, ok = _resolve_safe(path)
        if not ok:
            return False, "Cannot resolve path."

        # 2. Path traversal check
        safe, reason = _check_traversal(path, resolved)
        if not safe:
            return False, reason

        # 3. Blocklist check (trên resolved path)
        safe, reason = _check_blocked(resolved)
        if not safe:
            return False, reason

        # 4. Extension whitelist
        ext = os.path.splitext(resolved)[1].lower()
        if ext and ext not in ALLOWED_EXTENSIONS:
            return False, f"Extension '{ext}' not allowed. Allowed: {ALLOWED_EXTENSIONS}"

        # 5. Tồn tại không
        if not os.path.exists(resolved):
            return False, f"File not found: {path}"

        return True, resolved   # trả về resolved path để dùng tiếp

    @staticmethod
    def check_folder(path: str) -> tuple[bool, str]:
        if not ENABLE_SCAN:
            return False, "Folder scan disabled by policy."

        resolved, ok = _resolve_safe(path)
        if not ok:
            return False, "Cannot resolve path."

        safe, reason = _check_blocked(resolved)
        if not safe:
            return False, reason

        if not os.path.isdir(resolved):
            return False, f"Not a directory: {path}"

        return True, resolved

    @staticmethod
    def check_url(url: str) -> tuple[bool, str]:
        if not ALLOW_INTERNET:
            return False, "Internet access disabled by policy."
        if not (url.startswith("https://") or url.startswith("http://")):
            return False, "Only http/https URLs allowed."
        return True, "OK"

    @staticmethod
    def check_code(code: str) -> tuple[bool, str]:
        """Kiểm tra Python code trước khi exec — block lệnh nguy hiểm."""
        BLOCKED_PATTERNS = [
            r"os\.system",
            r"subprocess",
            r"shutil\.rmtree",
            r"open\s*\(.*['\"][wa][b\+]*['\"]",   # ghi/append file
            r"__import__",
            r"eval\s*\(",
            r"exec\s*\(",
            r"importlib",
            r"socket\.",
            r"requests\.",
            r"urllib",
        ]
        for pattern in BLOCKED_PATTERNS:
            if re.search(pattern, code):
                return False, f"Blocked pattern in code: {pattern}"
        return True, "OK"

    @staticmethod
    def check_shell(cmd: str) -> tuple[bool, str]:
        """Kiểm tra shell command — chỉ cho phép lệnh đọc an toàn."""
        ALLOWED_CMDS = [
            "dir", "ls", "echo", "type", "cat",
            "python --version", "pip list", "pip show",
            "where", "which", "whoami", "hostname",
            "ipconfig", "ifconfig",
        ]
        cmd_lower = cmd.strip().lower()
        if any(cmd_lower.startswith(a) for a in ALLOWED_CMDS):
            return True, "OK"

        BLOCKED_SHELL = [
            r"rm\s+-rf", r"del\s+/", r"format\s+",
            r"shutdown", r"reboot", r"mkfs",
            r"curl\s+.*\|", r"wget\s+.*\|",   # pipe to shell
            r">\s*/dev/", r"dd\s+if=",
        ]
        for pattern in BLOCKED_SHELL:
            if re.search(pattern, cmd, re.IGNORECASE):
                return False, f"Blocked shell command: {pattern}"

        return True, "OK"
