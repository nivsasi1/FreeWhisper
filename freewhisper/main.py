import argparse
import os
import sys
import threading
import time
import traceback
from pathlib import Path

from . import config as config_mod
from .cleaner import Cleaner
from .injector import paste_text
from .recorder import Recorder, rms
from .transcriber import Transcriber

LOG_PATH = Path(__file__).resolve().parent.parent / "freewhisper.log"


def _setup_windowless_logging():
    # under pythonw there is no console; send prints to a log file instead
    if sys.stdout is None or sys.stderr is None:
        log = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.language = cfg.language
        self.recorder = Recorder(cfg.input_device)
        self.transcriber = Transcriber(cfg)
        self.cleaner = Cleaner(cfg)
        self.busy = threading.Lock()
        self.state = "idle"  # idle | rec | busy (drives overlay color)
        self._overlay = None
        self._tray = None

    # --- record / transcribe -------------------------------------------------

    def start_recording(self):
        if self.recorder.recording:
            return
        try:
            self.recorder.start()
            self.state = "rec"
            print(f"[rec] ● recording ({self.language}) — stops after "
                  f"{self.cfg.silence_seconds:.0f}s of silence")
            threading.Thread(target=self._watchdog, daemon=True).start()
        except Exception as e:
            print(f"[rec] mic error: {e}")

    def stop_recording(self):
        if not self.recorder.recording:
            return
        audio = self.recorder.stop()
        print(f"[rec] ■ {audio.size / 16000:.1f}s captured, level={rms(audio):.4f}")
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def toggle_recording(self):
        if self.recorder.recording:
            self.stop_recording()
        else:
            self.start_recording()

    def _watchdog(self):
        """Auto-stop when the user goes quiet, or at the hard cap."""
        started = time.time()
        last_voice = started
        while self.recorder.recording:
            time.sleep(0.1)
            now = time.time()
            if self.recorder.recent_rms(0.3) > self.cfg.silence_threshold:
                last_voice = now
            if now - last_voice >= self.cfg.silence_seconds and now - started > 1.0:
                print("[rec] silence — auto-stop")
                self.stop_recording()
                return
            if now - started >= self.cfg.max_record_s:
                print("[rec] max length — auto-stop")
                self.stop_recording()
                return

    def _process(self, audio):
        with self.busy:
            self.state = "busy"
            try:
                text = self.transcriber.transcribe(audio, self.language)
                if not text:
                    print("[stt] (nothing recognized — was the mic level near 0?)")
                    return
                print(f"[stt] {text}")
                cleaned = self.cleaner.clean(text)
                if cleaned != text:
                    print(f"[llm] {cleaned}")
                paste_text(cleaned, self.cfg.paste_delay_ms)
            except Exception:
                traceback.print_exc()
            finally:
                self.state = "idle"

    def toggle_language(self, *_):
        self.language = "en" if self.language == "he" else "he"
        print(f"[cfg] language → {self.language}")

    # --- lifecycle ------------------------------------------------------------

    def quit(self, *_):
        print("[app] quitting")
        try:
            import keyboard
            keyboard.unhook_all()
        except Exception:
            pass
        if self._tray is not None:
            try:
                self._tray.stop()
            except Exception:
                pass
        if self._overlay is not None:
            self._overlay.close()
        threading.Timer(0.5, lambda: os._exit(0)).start()

    def _start_tray(self):
        try:
            import pystray
            from PIL import Image, ImageDraw

            img = Image.new("RGB", (64, 64), "#5b2d8e")
            d = ImageDraw.Draw(img)
            d.ellipse((16, 8, 48, 40), fill="white")
            d.rectangle((28, 40, 36, 54), fill="white")
            menu = pystray.Menu(
                pystray.MenuItem(lambda item: f"Language: {self.language} (toggle)", self.toggle_language),
                pystray.MenuItem("Quit", self.quit),
            )
            self._tray = pystray.Icon("FreeWhisper", img, "FreeWhisper", menu)
            self._tray.run_detached()
        except Exception as e:
            print(f"[tray] unavailable ({e})")

    def run(self):
        import keyboard

        keyboard.add_hotkey(self.cfg.hotkey, self.toggle_recording)
        keyboard.add_hotkey(self.cfg.language_toggle_hotkey, self.toggle_language)
        self._start_tray()

        if self.cfg.llm.enabled:
            if self.cleaner.available():
                # pre-warm: first Ollama call loads ~5GB into VRAM (can take ~1 min)
                threading.Thread(target=self.cleaner.clean, args=("hi",), daemon=True).start()
            else:
                print("[llm] WARNING: Ollama not reachable — will paste raw transcripts until it is")

        print(f"FreeWhisper ready. Tap {self.cfg.hotkey} (or the mic button) to dictate "
              f"({self.language}); it stops on its own when you stop talking. "
              f"✕ on the widget quits.")

        if self.cfg.overlay:
            try:
                from .overlay import Overlay
                self._overlay = Overlay(
                    get_state=lambda: self.state,
                    get_language=lambda: self.language,
                    get_level=lambda: self.recorder.recent_rms(0.08) if self.recorder.recording else 0.0,
                    on_record=self.toggle_recording,
                    on_toggle_language=self.toggle_language,
                    on_quit=self.quit,
                )
                self._overlay.run()   # blocks; Ctrl+C lands here and falls through
                self.quit()
                return
            except Exception as e:
                print(f"[overlay] unavailable ({e}); running headless")
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            self.quit()


# --- diagnostics ---------------------------------------------------------------

def check(cfg):
    """Doctor mode: verify environment without loading models."""
    ok = True
    print(f"config       : language={cfg.language}, hotkey={cfg.hotkey}")
    print(f"stt models   : he={cfg.models['he']}\n               en={cfg.models['en']}")

    import sounddevice as sd
    try:
        dev = sd.query_devices(kind="input")
        print(f"microphone   : OK (default: {dev['name']})")
    except Exception as e:
        ok = False
        print(f"microphone   : FAIL ({e})")
    inputs = [f"    [{i}] {d['name']}" for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
    print("input devices (set `input_device: N` in config.yaml to override):")
    print("\n".join(inputs[:10]))

    try:
        import ctranslate2
        n = ctranslate2.get_cuda_device_count()
        print(f"cuda         : {n} device(s)" + ("" if n else " — will run on CPU (int8)"))
    except Exception as e:
        ok = False
        print(f"ctranslate2  : FAIL ({e})")

    cleaner = Cleaner(cfg)
    if cleaner.available():
        print(f"ollama       : OK at {cfg.llm.url} (model: {cfg.llm.model})")
    else:
        print(f"ollama       : not reachable at {cfg.llm.url} — install/start it, then `ollama pull {cfg.llm.model}`")

    print("check        :", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def test_mic(cfg, seconds: float = 3.0):
    """Record N seconds from the configured mic and run STT once."""
    app = App(cfg)
    print(f"[mic-test] recording {seconds:.0f}s — speak now...")
    app.recorder.start()
    time.sleep(seconds)
    audio = app.recorder.stop()
    level = rms(audio)
    print(f"[mic-test] captured {audio.size / 16000:.1f}s, level={level:.4f} "
          f"({'OK' if level > 0.001 else 'SILENT — wrong device or muted mic?'})")
    text = app.transcriber.transcribe(audio, cfg.language)
    print(f"[mic-test] transcript: {text or '(empty)'}")
    return 0


def _single_instance_lock():
    # hold a localhost port for the process lifetime; second launch exits quietly
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 47814))
        return s
    except OSError:
        print("[app] FreeWhisper is already running — exiting")
        sys.exit(0)


def main():
    _setup_windowless_logging()
    parser = argparse.ArgumentParser(prog="freewhisper", description="Local push-to-talk AI dictation")
    parser.add_argument("--check", action="store_true", help="verify environment and exit")
    parser.add_argument("--test-mic", action="store_true", help="record 3s, print level + transcript")
    args = parser.parse_args()

    cfg = config_mod.load()
    if args.check:
        sys.exit(check(cfg))
    if args.test_mic:
        sys.exit(test_mic(cfg))
    _lock = _single_instance_lock()
    App(cfg).run()


if __name__ == "__main__":
    main()
