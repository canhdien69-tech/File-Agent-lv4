# ==============================================================================
#  SUNNY AI v5.0 — core/brain.py
#  SunnyBrain: LLM inference, tool calling, planning, streaming.
# ==============================================================================
import gc, re, json, threading, datetime
import torch, psutil
from core.config import (
    PERSONA_NAME, DEVICE, MODEL_NAME,
    MAX_SEQ_LENGTH, MAX_NEW_TOKENS, MAX_RESPONSE_LEN,
    TOOL_SCHEMA, PLAN_MAX_STEPS, FILES
)
from core.planner import parse_json_obj, parse_json_arr, _validate_plan


def _write_log(msg: str):
    try:
        with open(FILES["LOG"], "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


class SunnyBrain:
    INFERENCE_TIMEOUT = 120
    LOCK_TIMEOUT      = 130

    # ── System prompts ────────────────────────────────────────
    SYSTEM = f"""Bạn là {PERSONA_NAME} — trợ lý AI thông minh, thân thiện, đáng tin.
PHONG CÁCH: Xưng "em", gọi người dùng là "bạn". Thân thiện nhưng chuyên nghiệp.
NGUYÊN TẮC:
- Dùng dữ liệu thực tế từ tool khi có. Không bịa đặt.
- Nếu không chắc → nói thật.
- Trả lời súc tích. Đề xuất bước tiếp theo nếu hữu ích."""

    TOOL_SYSTEM = f"""Bạn là {PERSONA_NAME} — AI agent. Quyết định tool cần dùng.
{TOOL_SCHEMA}"""

    PLAN_SYSTEM = f"""Bạn là {PERSONA_NAME} — AI planner. Tạo kế hoạch thực hiện yêu cầu.
Output ONLY JSON array (tối đa {PLAN_MAX_STEPS} bước):
[{{"step":1,"action":"web_search","input":"...","reason":"..."}}]
Valid actions: web_search, visit_url, read_file, scan_folder, phone_control, read_diary, python_exec, shell_run, none
Output ONLY JSON array. No markdown, no explanation."""

    REPLAN_SYSTEM = f"""Bạn là {PERSONA_NAME} — AI replanner. Bước vừa rồi thất bại.
Tạo kế hoạch thay thế. Output ONLY JSON array.
Valid actions: web_search, visit_url, read_file, scan_folder, phone_control, read_diary, python_exec, shell_run, none"""

    REACT_SYSTEM = f"""Bạn là {PERSONA_NAME} — AI agent thông minh.
Dựa vào scratchpad bên dưới, quyết định bước tiếp theo.
Output ONLY JSON:
{{"thought": "...", "action": "web_search|visit_url|read_file|scan_folder|phone_control|read_diary|python_exec|shell_run|finish", "input": "..."}}
Nếu đã đủ thông tin để trả lời → action = "finish", input = "".
Output ONLY JSON. No markdown."""

    CRITIC_SYSTEM = """Đánh giá kết quả vừa thu được.
Câu hỏi: Kết quả này đã đủ để trả lời yêu cầu của người dùng chưa?
Output ONLY: YES hoặc NO."""

    REPORT_SYSTEM = """Chuyên gia phân tích dữ liệu.
Viết báo cáo gồm:
1. 📌 TÓM TẮT (3 dòng)
2. 📊 SỐ LIỆU QUAN TRỌNG
3. ⚠️ RỦI RO (nếu có)
4. 💡 ĐỀ XUẤT
Ngắn gọn, đi thẳng vào vấn đề."""

    def __init__(self, model, tokenizer):
        self.model        = model
        self.tokenizer    = tokenizer
        self._lock        = threading.Lock()

    # ── Helpers ───────────────────────────────────────────────
    def _guard(self, ids: torch.Tensor) -> torch.Tensor:
        max_in = MAX_SEQ_LENGTH - MAX_NEW_TOKENS - 50
        if ids.shape[-1] > max_in:
            _write_log(f"CONTEXT_TRIM: {ids.shape[-1]}→{max_in}")
            ids = ids[:, -max_in:]
        return ids

    def _sanitize(self, text: str) -> str:
        return re.sub(r'<\|im_(start|end)\|>', '', text)

    def _build(self, system: str, user: str,
               extra: str = "", history: list = None) -> str:
        safe_user  = self._sanitize(user)
        safe_extra = self._sanitize(extra)
        data = f"\n\n[Tool data]:\n{safe_extra[:2000]}" if safe_extra.strip() else ""
        
        # Tự động nhận diện cấu trúc não bộ (Llama 3 hay Hermes ChatML)
        path = getattr(self.model.config, "_name_or_path", MODEL_NAME).lower()
        
        if "hermes" in path or "chatml" in path:
            # Dành cho não Hermes 8B
            p = f"<|im_start|>system\n{system}{data}<|im_end|>\n"
            for t in (history or []):
                p += f"<|im_start|>{t['role']}\n{self._sanitize(t['content'])}<|im_end|>\n"
            p += f"<|im_start|>user\n{safe_user}<|im_end|>\n<|im_start|>assistant\n"
            return p
        else:
            # Dành cho não Llama 3.2 3B
            p = f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system}{data}<|eot_id|>"
            for t in (history or []):
                p += f"<|start_header_id|>{t['role']}<|end_header_id|>\n\n{self._sanitize(t['content'])}<|eot_id|>"
            p += f"<|start_header_id|>user<|end_header_id|>\n\n{safe_user}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
            return p

    def _encode(self, prompt: str):
        ids = self.tokenizer([prompt], return_tensors="pt").to(DEVICE)["input_ids"]
        ids = self._guard(ids)
        return ids, ids.shape[-1]

    # ── Safe generate ─────────────────────────────────────────
    def _gen(self, ids: torch.Tensor, max_tok: int, il: int) -> str:
        res, err = [None], [None]

        def _infer():
            acquired = self._lock.acquire(timeout=self.LOCK_TIMEOUT)
            if not acquired:
                err[0] = "[Lock timeout]: Previous inference still holding lock."; return
            try:
                with torch.no_grad():
                    out = self.model.generate(
                        input_ids=ids, max_new_tokens=max_tok,
                        use_cache=True, do_sample=False,
                        pad_token_id=self.tokenizer.eos_token_id,
                    )
                res[0] = self.tokenizer.decode(
                    out[0][il:], skip_special_tokens=True
                ).strip()
            except torch.cuda.OutOfMemoryError:
                if "8b" in MODEL_NAME.lower():
                    err[0] = "VRAM full. Close other apps."
                    torch.cuda.empty_cache(); gc.collect()
                else:
                    torch.cuda.empty_cache(); gc.collect()
                    cpu = ids.to("cpu"); il2 = cpu.shape[-1]
                    self.model.to("cpu")
                    try:
                        with torch.no_grad():
                            out2 = self.model.generate(
                                input_ids=cpu,
                                max_new_tokens=min(max_tok, 100),
                                use_cache=True, do_sample=False,
                                pad_token_id=self.tokenizer.eos_token_id,
                            )
                        res[0] = self.tokenizer.decode(
                            out2[0][il2:], skip_special_tokens=True
                        ).strip()
                    except Exception as e2:
                        err[0] = f"OOM+CPU failed: {e2}"
                    finally:
                        self.model.to(DEVICE)
            except Exception as e:
                err[0] = str(e)
            finally:
                if acquired:
                    self._lock.release()
                gc.collect()
                if DEVICE == "cuda":
                    try:
                        used = torch.cuda.memory_reserved()
                        total = torch.cuda.get_device_properties(0).total_memory
                        if used / total > 0.75:
                            torch.cuda.empty_cache()
                    except Exception:
                        pass

        t = threading.Thread(target=_infer, daemon=True)
        t.start(); t.join(timeout=self.INFERENCE_TIMEOUT)
        if t.is_alive():
            err[0] = "[Timeout]: Inference exceeded 120s. Please retry."
            _write_log("INFERENCE_TIMEOUT: daemon thread left running.")
            gc.collect()
            if DEVICE == "cuda":
                try: torch.cuda.empty_cache()
                except Exception: pass
        if err[0]:
            _write_log(f"INFERENCE_ERROR: {err[0]}")
            return f"[Error]: {err[0]}"
        return res[0] or ""

    # ── LLM Tool Decision ─────────────────────────────────────
    def decide_tool(self, msg: str, history: list = None) -> dict:
        p   = self._build(self.TOOL_SYSTEM, msg, history=history)
        ids, il = self._encode(p)
        raw = self._gen(ids, 150, il)
        obj = parse_json_obj(raw)
        from core.planner import _get_dispatch
        if obj and "tool" in obj and obj["tool"] in _get_dispatch():
            return obj
        _write_log(f"TOOL_PARSE_FAIL: {raw[:80]}")
        return {"tool": "none", "input": ""}

    # ── Planning ──────────────────────────────────────────────
    def make_plan(self, msg: str, history: list = None,
                  context: str = "") -> list[dict]:
        p   = self._build(self.PLAN_SYSTEM, msg, context, history)
        ids, il = self._encode(p)
        raw = self._gen(ids, 400, il)
        arr = parse_json_arr(raw)
        if arr:
            return _validate_plan(arr)
        _write_log(f"PLAN_PARSE_FAIL: {raw[:100]}")
        return [{"step": 1, "action": "none", "input": "", "reason": "fallback"}]

    def replan(self, msg: str, failed_step: dict,
               error: str, history: list = None) -> list[dict]:
        context = (f"Original goal: {msg}\n"
                   f"Failed: {failed_step['action']}({failed_step['input']})\n"
                   f"Error: {error}\nSuggest alternative approach.")
        p   = self._build(self.REPLAN_SYSTEM, context, history=history)
        ids, il = self._encode(p)
        raw = self._gen(ids, 300, il)
        arr = parse_json_arr(raw)
        if arr:
            return _validate_plan(arr)
        return [{"step": 1, "action": "none", "input": "", "reason": "replan_failed"}]

    # ── Streaming answer ──────────────────────────────────────
    def think_stream(self, msg: str, tool_data: str = "",
                     history: list = None, memory_ctx: str = ""):
        from transformers import TextIteratorStreamer
        stat     = f"[Thời gian hiện tại: {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')} | CPU {psutil.cpu_percent(interval=0.1):.0f}% | RAM {psutil.virtual_memory().percent:.0f}%]"
        full_sys = self.SYSTEM + "\n" + stat
        if memory_ctx:
            full_sys += f"\n\n{memory_ctx}"
        prompt   = self._build(full_sys, msg, tool_data, history)
        ids, _   = self._encode(prompt)
        streamer = TextIteratorStreamer(
            self.tokenizer, skip_prompt=True, skip_special_tokens=True
        )

        def run():
            acquired = self._lock.acquire(timeout=self.LOCK_TIMEOUT)
            if not acquired:
                _write_log("STREAM_LOCK_TIMEOUT: previous inference holding lock.")
                try: streamer.text_queue.put(streamer.stop_signal)
                except Exception: pass
                return
            try:
                self.model.generate(
                    input_ids=ids, streamer=streamer,
                    max_new_tokens=MAX_NEW_TOKENS, use_cache=True,
                    pad_token_id=self.tokenizer.eos_token_id,
                )
            except Exception as e:
                _write_log(f"STREAM_ERROR: {e}")
                try: streamer.text_queue.put(streamer.stop_signal)
                except Exception: pass
            finally:
                self._lock.release()
                gc.collect()
                if DEVICE == "cuda":
                    try: torch.cuda.empty_cache()
                    except Exception: pass

        threading.Thread(target=run, daemon=True).start()
        return streamer

    # ── Report ────────────────────────────────────────────────
    def generate_report(self, data: str, fname: str) -> str:
        prompt = self._build(self.REPORT_SYSTEM, f'Data from "{fname}":\n\n{data}\n\n➡️ Write report:')
        ids, _ = self._encode(prompt)
        return self._gen(ids, min(MAX_NEW_TOKENS * 2, 600), ids.shape[-1])

    # ── ReAct Loop (Level 4) ──────────────────────────────────
    def react_loop(self, msg: str, history: list = None,
                   status_cb=None) -> str:
        from core.planner import _get_dispatch
        dispatch        = _get_dispatch()
        scratchpad      = ""
        MAX_STEPS       = PLAN_MAX_STEPS
        last_action     = None
        last_inp        = None
        same_action_count = 0

        for step in range(1, MAX_STEPS + 1):
            # Think
            react_input = f"User goal: {msg}\n\nScratchpad:\n{scratchpad}" if scratchpad else f"User goal: {msg}"
            p   = self._build(self.REACT_SYSTEM, react_input, history=history)
            ids, il = self._encode(p)
            raw = self._gen(ids, 200, il)

            thought_obj = None
            try:
                thought_obj = json.loads(raw)
            except Exception:
                from core.planner import parse_json_obj
                thought_obj = parse_json_obj(raw)

            if not thought_obj:
                _write_log(f"REACT_PARSE_FAIL step={step}: {raw[:80]}")
                scratchpad += f"\nThought: [parse error]\nObservation: could not parse action\n"
                continue

            thought = thought_obj.get("thought", "")
            action  = thought_obj.get("action", "finish")
            inp     = thought_obj.get("input", "")

            if action == "finish" or action not in dispatch:
                _write_log(f"REACT_FINISH step={step}")
                break

            # ── Repeated action guard ─────────────────────────
            if action == last_action and inp == last_inp:
                same_action_count += 1
                if same_action_count >= 2:
                    _write_log(f"REACT_LOOP_GUARD: same action×{same_action_count} — breaking")
                    scratchpad += f"\nNote: Repeated action detected, stopping loop.\n"
                    break
            else:
                same_action_count = 0
            last_action = action
            last_inp    = inp

            # Run tool
            result = ""
            try:
                fn = dispatch.get(action)
                result = fn(inp) if fn else "[Error]: unknown tool"
            except Exception as e:
                result = f"[Error]: {e}"

            # Failure memory — ghi lỗi vào scratchpad để không lặp lại
            is_fail = (not result or result.startswith("[Error]")
                       or result.startswith("[Blocked]"))
            if is_fail:
                _write_log(f"REACT_TOOL_FAIL step={step} {action}: {result[:80]}")
                scratchpad += (f"\nThought: {thought}\nAction: {action}({inp})"
                               f"\nObservation: FAILED — {result}. Try a different approach.\n")
                continue

            # Update scratchpad
            scratchpad += (f"\nThought: {thought}\nAction: {action}({inp})"
                           f"\nObservation: {result[:500]}\n")

            # Critic check
            critic_prompt = self._build(
                self.CRITIC_SYSTEM,
                f"User goal: {msg}\nLast observation: {result[:300]}"
            )
            ids2, il2 = self._encode(critic_prompt)
            verdict = self._gen(ids2, 10, il2).strip().upper()
            _write_log(f"REACT_CRITIC step={step}: {verdict}")
            if "YES" in verdict:
                break

        return scratchpad.strip()

    # ── Persist ───────────────────────────────────────────────
    def save(self, user_msg: str, ai_resp: str, vmem):
        ai_resp = ai_resp[:MAX_RESPONSE_LEN]
        vmem.add(user_msg, ai_resp)
        try:
            with open(FILES["DIARY"], "a", encoding="utf-8") as f:
                f.write(f"[{datetime.datetime.now()}]\nU: {user_msg}\nA: {ai_resp}\n---\n")
        except Exception:
            pass
        try:
            with open(FILES["AUDIT"], "a", encoding="utf-8") as f:
                f.write(json.dumps(
                    {"t": str(datetime.datetime.now()), "q": user_msg, "a": ai_resp},
                    ensure_ascii=False
                ) + "\n")
        except Exception:
            pass

