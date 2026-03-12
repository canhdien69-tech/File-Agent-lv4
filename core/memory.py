# ==============================================================================
#  SUNNY AI v5.0 — core/memory.py
#  Long-term semantic memory: FAISS + sentence-transformers.
#  Fallback: JSON nếu thiếu thư viện.
# ==============================================================================
import os, json, datetime
from core.config import FILES, MEMORY_LIMIT, VECTOR_TOP_K

try:
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer
    HAS_VECTOR = True
except ImportError:
    HAS_VECTOR = False


def _write_log(msg: str):
    try:
        with open(FILES["LOG"], "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


class VectorMemory:
    EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
    DIM         = 384

    def __init__(self):
        self.enabled  = HAS_VECTOR
        self.embedder = None
        self.index    = None
        self.metadata : list[dict] = []

        if self.enabled:
            try:
                self.embedder = SentenceTransformer(self.EMBED_MODEL)
                self._load_index()
                _write_log(f"VectorMemory: FAISS ready. Entries: {self.index.ntotal}")
            except Exception as e:
                _write_log(f"VectorMemory init failed: {e} — JSON fallback.")
                self.enabled = False

        if not self.enabled:
            _write_log("VectorMemory: running in JSON-only mode.")

    # ── Index I/O ─────────────────────────────────────────────
    def _load_index(self):
        idx_path  = FILES["VECTOR_INDEX"]
        meta_path = FILES["VECTOR_META"]
        if os.path.exists(idx_path) and os.path.exists(meta_path):
            self.index = faiss.read_index(idx_path)
            with open(meta_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)
        else:
            self.index    = faiss.IndexFlatIP(self.DIM)
            self.metadata = []

    def _save_index(self):
        try:
            faiss.write_index(self.index, FILES["VECTOR_INDEX"])
            tmp = FILES["VECTOR_META"] + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
            os.replace(tmp, FILES["VECTOR_META"])
        except Exception as e:
            _write_log(f"VectorMemory._save_index: {e}")

    # ── JSON backup ───────────────────────────────────────────
    def _save_json(self, entry: dict):
        try:
            mem = []
            mp  = FILES["MEMORY"]
            if os.path.exists(mp):
                with open(mp, "r", encoding="utf-8") as f:
                    mem = json.load(f)
            mem = (mem + [entry])[-MEMORY_LIMIT:]
            tmp = mp + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(mem, f, ensure_ascii=False, indent=2)
            os.replace(tmp, mp)
        except Exception:
            pass

    def get_recent_json(self, n: int = 6) -> list[dict]:
        try:
            with open(FILES["MEMORY"], "r", encoding="utf-8") as f:
                return json.load(f)[-n:]
        except Exception:
            return []

    # ── Core API ──────────────────────────────────────────────
    def add(self, user_msg: str, ai_resp: str):
        entry = {
            "user": user_msg,
            "ai"  : ai_resp[:500],
            "t"   : str(datetime.datetime.now()),
        }
        if self.enabled:
            try:
                vec = self.embedder.encode(
                    [user_msg], normalize_embeddings=True
                ).astype("float32")
                self.index.add(vec)
                self.metadata.append(entry)
                # FIX (GPT): Pruning vector index — không để phình mãi
                self._prune()
                self._save_index()
            except Exception as e:
                _write_log(f"VectorMemory.add: {e}")
        self._save_json(entry)

    def _prune(self):
        """Giữ tối đa MEMORY_LIMIT entries — xóa entries cũ nhất."""
        if self.index.ntotal <= MEMORY_LIMIT:
            return
        try:
            # Lấy tất cả vectors hiện tại
            all_vecs = self.index.reconstruct_n(0, self.index.ntotal)
            # Chỉ giữ MEMORY_LIMIT entries mới nhất
            keep_vecs = all_vecs[-MEMORY_LIMIT:]
            self.metadata  = self.metadata[-MEMORY_LIMIT:]
            # Rebuild index với entries được giữ lại
            self.index = faiss.IndexFlatIP(self.DIM)
            self.index.add(keep_vecs)
            _write_log(f"VectorMemory pruned → {self.index.ntotal} entries")
        except Exception as e:
            _write_log(f"VectorMemory._prune: {e}")

    def search(self, query: str, top_k: int = VECTOR_TOP_K) -> list[dict]:
        if not self.enabled or self.index.ntotal == 0:
            return []
        try:
            vec = self.embedder.encode(
                [query], normalize_embeddings=True
            ).astype("float32")
            k = min(top_k, self.index.ntotal)
            scores, indices = self.index.search(vec, k)
            return [
                self.metadata[i]
                for s, i in zip(scores[0], indices[0])
                if i >= 0 and s > 0.3
            ]
        except Exception as e:
            _write_log(f"VectorMemory.search: {e}")
            return []

    def format_context(self, results: list[dict]) -> str:
        if not results:
            return ""
        lines = ["[Relevant past context:]"]
        for r in results:
            lines += [f"  Q: {r['user'][:100]}", f"  A: {r['ai'][:150]}"]
        return "\n".join(lines)

    def stats(self) -> dict:
        n_json = len(self.get_recent_json(999))
        return {
            "vector_enabled": self.enabled,
            "vector_entries": self.index.ntotal if self.enabled else 0,
            "json_entries"  : n_json,
        }


class ConversationManager:
    MAX_TURNS = 6

    def __init__(self):
        self._h: list[dict] = []

    def add(self, role: str, content: str):
        self._h.append({"role": role, "content": content})
        if len(self._h) > self.MAX_TURNS * 2:
            self._h = self._h[-(self.MAX_TURNS * 2):]

    def get(self) -> list[dict]:
        return list(self._h)

    def clear(self):
        self._h.clear()
