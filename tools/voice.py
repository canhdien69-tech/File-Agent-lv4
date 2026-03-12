# ==============================================================================
#  SUNNY AI v5.0 — tools/voice.py
#  AudioMouth: TTS (edge_tts + pygame)
#  AudioEar  : STT (speech_recognition)
# ==============================================================================
import os, re, uuid, threading, queue, datetime
from core.config import FILES

# ── Optional imports ──────────────────────────────────────────
try:
    import edge_tts, pygame, asyncio
    HAS_TTS = True
except ImportError:
    HAS_TTS = False

try:
    import speech_recognition as sr
    HAS_MIC = True
except ImportError:
    HAS_MIC = False


def _write_log(msg: str):
    try:
        with open(FILES["LOG"], "a", encoding="utf-8") as f:
            f.write(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        pass


# ==============================================================================
# TTS — Sunny nói ra loa
# ==============================================================================
class AudioMouth:
    VOICE = "vi-VN-HoaiMyNeural"
    RATE  = "+15%"

    def __init__(self):
        self.enabled = HAS_TTS
        self._q      = queue.Queue()

        if self.enabled:
            try:
                pygame.mixer.init()
            except Exception as e:
                _write_log(f"AudioMouth: pygame init failed: {e}")
                self.enabled = False

        if self.enabled:
            threading.Thread(target=self._worker, daemon=True).start()
            _write_log("AudioMouth: TTS ready.")
        else:
            _write_log("AudioMouth: edge_tts/pygame not found — TTS disabled.")

    def speak(self, text: str):
        """Đưa text vào hàng đợi TTS. Non-blocking."""
        if not self.enabled:
            return
        # Strip markdown / URLs / special chars
        clean = re.sub(r'http\S+', '', text)
        clean = re.sub(r'[#*<>@|{}\[\]`]', '', clean).strip()
        if len(clean) >= 2:
            self._q.put(clean)

    def _worker(self):
        """Worker thread: đọc queue và phát âm thanh tuần tự."""
        while True:
            text = self._q.get()
            try:
                fn   = f"tts_{uuid.uuid4().hex[:6]}.mp3"
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(
                    edge_tts.Communicate(
                        text[:500], self.VOICE, rate=self.RATE
                    ).save(fn)
                )
                loop.close()

                if os.path.exists(fn):
                    pygame.mixer.music.load(fn)
                    pygame.mixer.music.play()
                    import time
                    while pygame.mixer.music.get_busy():
                        time.sleep(0.05)
                    pygame.mixer.music.unload()
                    os.remove(fn)

            except Exception as e:
                _write_log(f"AudioMouth._worker: {e}")
                # Dọn file nếu còn sót
                try:
                    if os.path.exists(fn): os.remove(fn)
                except Exception:
                    pass
            finally:
                self._q.task_done()

    @property
    def is_available(self) -> bool:
        return self.enabled

    def status(self) -> str:
        return "TTS: ready" if self.enabled else "TTS: disabled (install edge-tts pygame)"


# ==============================================================================
# STT — Nhận giọng nói từ mic
# ==============================================================================
class AudioEar:
    LANGUAGE    = "vi-VN"
    TIMEOUT     = 4       # giây chờ bắt đầu nói
    PHRASE_LIMIT = 8      # giây tối đa 1 câu

    def __init__(self, callback):
        """
        callback(event_type: str, data: str)
        event_type: 'USER_VOICE' | 'SYSTEM'
        """
        self.enabled      = HAS_MIC
        self.callback     = callback
        self.is_listening = False

        if self.enabled:
            self.recognizer = sr.Recognizer()
            _write_log("AudioEar: STT ready.")
        else:
            _write_log("AudioEar: SpeechRecognition not found — STT disabled.")

    def listen_once(self):
        """Lắng nghe một câu. Non-blocking — chạy trong thread riêng."""
        if not self.enabled:
            self.callback("SYSTEM", "❌ STT disabled. Install: pip install SpeechRecognition")
            return
        if self.is_listening:
            self.callback("SYSTEM", "⏳ Already listening...")
            return
        threading.Thread(target=self._thread, daemon=True).start()

    def _thread(self):
        self.is_listening = True
        try:
            with sr.Microphone() as src:
                self.callback("SYSTEM", "👂 Listening... (nói đi)")
                self.recognizer.adjust_for_ambient_noise(src, duration=0.5)
                audio = self.recognizer.listen(
                    src,
                    timeout=self.TIMEOUT,
                    phrase_time_limit=self.PHRASE_LIMIT,
                )
                text = self.recognizer.recognize_google(audio, language=self.LANGUAGE)
                self.callback("USER_VOICE", text)

        except sr.WaitTimeoutError:
            self.callback("SYSTEM", "⏰ Không nghe thấy gì. Thử lại?")
        except sr.UnknownValueError:
            self.callback("SYSTEM", "❓ Không nhận ra giọng nói. Nói rõ hơn?")
        except sr.RequestError as e:
            self.callback("SYSTEM", f"❌ Google STT error: {e}")
        except Exception as e:
            _write_log(f"AudioEar._thread: {e}")
            self.callback("SYSTEM", f"❌ STT error: {e}")
        finally:
            self.is_listening = False

    @property
    def is_available(self) -> bool:
        return self.enabled

    def status(self) -> str:
        return "STT: ready" if self.enabled else "STT: disabled (install SpeechRecognition)"
