# ==============================================================================
#  SUNNY AI v5.0 — tools/scanner.py
#  Folder junk scanner + temp dir cleaner.
# ==============================================================================
import os, shutil
from core.sandbox import Sandbox

JUNK_EXTS  = {".tmp", ".log", ".bak", ".old", ".cache"}
MAX_FILES  = 5000
MAX_DEPTH  = 5


def _get_temp_dir() -> str:
    return os.environ.get("TEMP") or os.environ.get("TMPDIR") or "/tmp"


def scan_folder(path: str) -> str:
    """Scan folder tùy chọn — tìm file rác theo extension."""
    ok, result = Sandbox.check_folder(path)
    if not ok:
        return f"[Blocked]: {result}"

    resolved   = result
    report     = []
    total_size = 0
    root_depth = resolved.rstrip(os.sep).count(os.sep)

    try:
        for root, dirs, files in os.walk(resolved):
            if root.count(os.sep) - root_depth >= MAX_DEPTH:
                dirs.clear()
            for fn in files:
                if len(report) >= MAX_FILES:
                    break
                if os.path.splitext(fn)[1].lower() in JUNK_EXTS:
                    fp = os.path.join(root, fn)
                    try:
                        total_size += os.path.getsize(fp)
                        report.append(fp)
                    except OSError:
                        pass

        if not report:
            return "✅ No junk files found."
        note = f" (stopped at {MAX_FILES})" if len(report) >= MAX_FILES else ""
        return f"🗑️ {len(report)} junk files ({total_size/1024/1024:.2f} MB){note}."

    except Exception as e:
        return f"[SCAN ERROR]: {e}"


def scan_temp() -> str:
    """Scan thư mục TEMP của hệ thống — báo cáo dung lượng rác."""
    tmp = _get_temp_dir()
    try:
        total = 0
        count = 0
        for fn in os.listdir(tmp):
            fp = os.path.join(tmp, fn)
            try:
                if os.path.isfile(fp) or os.path.islink(fp):
                    total += os.path.getsize(fp)
                    count += 1
                elif os.path.isdir(fp):
                    for root, dirs, files in os.walk(fp):
                        for f in files:
                            try: total += os.path.getsize(os.path.join(root, f))
                            except OSError: pass
                    count += 1
            except OSError:
                pass
        return f"🗑️ Temp dir: {tmp}\n   {count} items — {total/1024/1024:.2f} MB rác."
    except Exception as e:
        return f"[SCAN_TEMP ERROR]: {e}"


def delete_temp() -> str:
    """Xóa toàn bộ nội dung thư mục TEMP hệ thống."""
    tmp = _get_temp_dir()
    deleted = 0
    failed  = 0
    try:
        for fn in os.listdir(tmp):
            fp = os.path.join(tmp, fn)
            try:
                if os.path.isfile(fp) or os.path.islink(fp):
                    os.unlink(fp)
                elif os.path.isdir(fp):
                    shutil.rmtree(fp)
                deleted += 1
            except Exception:
                failed += 1
        return f"✅ Đã dọn {deleted} mục trong {tmp}." + (f" ({failed} bị bỏ qua)" if failed else "")
    except Exception as e:
        return f"[DELETE_TEMP ERROR]: {e}"

