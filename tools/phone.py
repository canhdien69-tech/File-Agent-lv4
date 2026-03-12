# ==============================================================================
#  SUNNY AI v5.0 — tools/phone.py
#  ADB phone control.
# ==============================================================================
import uuid
from core.config import ENABLE_PHONE


def phone_control(cmd: str) -> str:
    if not ENABLE_PHONE:
        return "[Blocked]: Phone control disabled by policy."
    try:
        import subprocess

        def run(args: list) -> str:
            return subprocess.check_output(
                ["adb"] + args, timeout=5
            ).decode().strip()

        cl = cmd.lower()
        if "pin" in cl or "battery" in cl:
            res = run(["shell", "dumpsys", "battery"])
            lvl = [x.split(":")[1].strip() for x in res.split("\n") if "level" in x]
            return f"Battery: {lvl[0]}%" if lvl else "Cannot read battery."

        elif "screenshot" in cl or "chup" in cl or "cap" in cl:
            fn = f"cap_{uuid.uuid4().hex[:4]}.png"
            run(["shell", "screencap", "-p", f"/sdcard/{fn}"])
            run(["pull", f"/sdcard/{fn}", "."])
            run(["shell", "rm", f"/sdcard/{fn}"])
            return f"Screenshot saved: {fn}"

        elif "home" in cl:
            run(["shell", "input", "keyevent", "3"])
            return "Home button pressed."

        elif "back" in cl:
            run(["shell", "input", "keyevent", "4"])
            return "Back button pressed."

        return f"Unknown command: {cmd}"

    except FileNotFoundError:
        return "[ADB ERROR]: adb not found. Install Android SDK Platform Tools."
    except Exception as e:
        return f"[ADB ERROR]: {e}"
