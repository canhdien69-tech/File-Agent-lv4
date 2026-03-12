# ==============================================================================
#  SUNNY AI v5.0 — core/planner.py
#  Planning loop: Goal → Plan → Execute → Observe → Reply
#  Retry + Re-plan khi tool fail.
# ==============================================================================
import os, json, re, time, datetime
from core.config import FILES, PLAN_MAX_STEPS, PLAN_MAX_RETRIES

# ── Tool dispatch (import lazy để tránh circular) ─────────────
def _get_dispatch() -> dict:
    from tools.web      import web_search, visit_url
    from tools.reader   import read_file
    from tools.scanner  import scan_folder, scan_temp, delete_temp
    from tools.phone    import phone_control
    from tools.executor import python_exec, shell_run

    def read_diary(_: str = "") -> str:
        if not os.path.exists(FILES["DIARY"]):
            return "[DIARY]: Empty."
        with open(FILES["DIARY"], "r", encoding="utf-8") as f:
            return "[DIARY]:\n" + "".join(f.readlines()[-20:])

    return {
        "web_search"   : web_search,
        "visit_url"    : visit_url,
        "read_file"    : read_file,
        "scan_folder"  : scan_folder,
        "scan_temp"    : lambda _: scan_temp(),
        "delete_temp"  : lambda _: delete_temp(),
        "phone_control": phone_control,
        "read_diary"   : read_diary,
        "python_exec"  : python_exec,
        "shell_run"    : shell_run,
        "none"         : lambda _: "",
    }


def _write_log(msg: str):
    try:
        with open(FILES["LOG"], "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


# ── JSON parsers ──────────────────────────────────────────────
def parse_json_obj(raw: str) -> dict | None:
    """Tìm JSON object đầu tiên hợp lệ trong raw string."""
    depth = 0; start = None
    for i, ch in enumerate(raw):
        if ch == "{":
            if depth == 0: start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                try:
                    obj = json.loads(raw[start:i+1])
                    if isinstance(obj, dict): return obj
                except Exception:
                    pass
                start = None
    return None


def parse_json_arr(raw: str) -> list | None:
    """
    Balanced bracket parser — không dùng regex.
    Tìm tất cả JSON array hợp lệ, ưu tiên cái có dict bên trong.
    """
    results = []
    i = 0
    while i < len(raw):
        if raw[i] == "[":
            depth = 0
            for j in range(i, len(raw)):
                if raw[j] == "[": depth += 1
                elif raw[j] == "]":
                    depth -= 1
                    if depth == 0:
                        candidate = raw[i:j+1]
                        try:
                            arr = json.loads(candidate)
                            if isinstance(arr, list) and arr and isinstance(arr[0], dict):
                                results.append(arr)
                        except Exception:
                            pass
                        i = j + 1
                        break
            else:
                i += 1
        else:
            i += 1
    return results[0] if results else None


# ── Plan validator ────────────────────────────────────────────
def _validate_plan(raw_plan: list) -> list[dict]:
    dispatch = _get_dispatch()
    valid = []
    for s in raw_plan[:PLAN_MAX_STEPS]:
        if not isinstance(s, dict) or "action" not in s:
            continue
        action = s.get("action", "none")
        if action not in dispatch:
            action = "none"
        valid.append({
            "step"  : len(valid) + 1,
            "action": action,
            "input" : str(s.get("input", ""))[:500],
            "reason": s.get("reason", ""),
        })
    return valid or [{"step": 1, "action": "none", "input": "", "reason": "fallback"}]


# ── Executor ──────────────────────────────────────────────────
class PlanExecutor:
    def __init__(self, brain):
        self.brain    = brain
        self.dispatch = _get_dispatch()

    def run(self, plan: list[dict], original_msg: str,
            history: list = None, status_cb=None,
            use_react: bool = False) -> str:

        # ── Level 4: ReAct loop ───────────────────────────────
        if use_react:
            return self.brain.react_loop(original_msg, history, status_cb)

        # ── Level 3: Classic plan/execute ─────────────────────
        observations = []

        for step in plan:
            action = step["action"]
            inp    = step["input"]
            if action == "none":
                continue

            if status_cb:
                status_cb(f"⚙️ Step {step['step']}: {action}({inp[:50]})")

            last_error = None

            # ── Retry loop ────────────────────────────────────
            for attempt in range(1, PLAN_MAX_RETRIES + 1):
                fn = self.dispatch.get(action)
                if not fn:
                    last_error = f"Unknown tool: {action}"; break
                try:
                    result = fn(inp)
                    is_fail = (not result
                               or result.startswith("[Error]")
                               or result.startswith("[Blocked]")
                               or result.startswith("[Missing]"))
                    if not is_fail:
                        observations.append(f"[Step {step['step']} — {action}]:\n{result}")
                        last_error = None; break
                    else:
                        last_error = result
                        _write_log(f"STEP_FAIL attempt={attempt} {action}: {last_error[:80]}")
                        if attempt < PLAN_MAX_RETRIES:
                            time.sleep(1)
                except Exception as e:
                    last_error = str(e)
                    _write_log(f"STEP_EXCEPTION attempt={attempt}: {e}")
                    if attempt < PLAN_MAX_RETRIES:
                        time.sleep(1)

            # ── Replan nếu tất cả retry fail ─────────────────
            if last_error:
                _write_log(f"STEP_ALL_RETRIES_FAILED: {action} — {last_error[:80]}")
                if status_cb:
                    status_cb(f"⚠️ {action} failed. Replanning...")
                alt_plan = self.brain.replan(original_msg, step, last_error, history)
                for alt in alt_plan:
                    if alt["action"] == "none": continue
                    fn2 = self.dispatch.get(alt["action"])
                    if fn2:
                        try:
                            alt_result = fn2(alt["input"])
                            observations.append(
                                f"[Step {step['step']} REPLAN {alt['action']}]:\n{alt_result}"
                            )
                        except Exception as e2:
                            observations.append(
                                f"[Step {step['step']} REPLAN FAILED]: {e2}"
                            )

        return "\n\n".join(observations)
