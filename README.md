# 🎙️ FreeWhisper

**Local, free, private voice dictation for Windows — a Wispr Flow clone that runs 100% on your own machine.**

Tap a hotkey anywhere, speak in **Hebrew or English**, stop talking — and clean,
AI-polished text appears at your cursor. No cloud, no subscription, no audio ever leaving your PC.

- **STT**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) on the GPU —
  Hebrew via the [ivrit.ai](https://huggingface.co/ivrit-ai) fine-tune (state of the art for Hebrew),
  English via stock Whisper large-v3-turbo
- **Cleanup**: a local LLM through [Ollama](https://ollama.com) (`qwen2.5:7b`) removes filler words
  (אה, אמ, um, uh), fixes punctuation, applies spoken self-corrections ("ביום שלישי, לא רגע, רביעי" → רביעי)
- **UI**: a small always-on-top floating pill with a live waveform that dances with your voice

## How it works

```
tap Ctrl+Shift+Space (or click the mic)
        │
        ▼
🎤 record until you go quiet for ~2s        (sounddevice, RMS silence watchdog)
        │
        ▼
📝 faster-whisper transcribes on the GPU    (HE: ivrit.ai turbo / EN: large-v3-turbo)
        │
        ▼
🤖 Ollama LLM cleans the transcript         (fillers, punctuation, corrections, lists)
        │
        ▼
📋 pasted at your cursor via clipboard      (Ctrl+V — the only method that survives Hebrew/RTL)
```

## Using it

| Action | How |
|---|---|
| Start dictating | **Ctrl+Shift+Space** or click the 🎤 mic on the widget |
| Stop | just stop talking (~2s), or tap the hotkey again |
| Command mode (⚡) | select text anywhere → **Ctrl+Shift+C** → speak an instruction ("translate to English", "תקצר את זה") — the result replaces/pastes |
| Theme | `theme:` in config (**light** / atelier / glass / neon) or cycle live from the tray menu |
| Language | **Ctrl+Alt+L** or the pill cycles **AUTO → HE → EN** (auto detects per dictation) |
| Copy last result | 📋 on the widget (turns ✔) |
| History | 🕘 opens the last dictations — click a row to copy it |
| Move the widget | drag it by the ⠿ grip |
| Quit completely | **✕** on the widget, or tray icon → Quit |

While you talk the widget expands: waveform bars dance with your voice and a **live transcript**
streams underneath. Colors: 🟣 idle · 🔴 dictating · 🔵 command · 🟠 processing.

**Live typing** (`live_typing: true`): the draft is typed straight into the field you're
dictating into as you speak, then erased and replaced with the clean LLM version at the end —
just don't move the cursor mid-dictation.

**Spoken commands inside a dictation**: end with "תמחק הכל" / "delete everything, never mind"
to cancel (nothing is pasted); say "תכתוב את זה באנגלית" / "write this in English" to switch
the output language. Output is locked to Hebrew/English only — both at the Whisper
language-detection level and in the LLM prompt.

The widget window is set `WS_EX_NOACTIVATE`, so clicking its buttons never steals focus —
your cursor stays in the text field and the paste lands there.

FreeWhisper starts automatically at login (shortcut in `shell:startup`) and runs windowless —
logs go to `freewhisper.log`. A desktop shortcut launches it manually; a single-instance
lock (port 47814) makes double-launching harmless.

## Setup (fresh machine)

```powershell
# 1. dependencies
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt

# 2. Ollama + the cleanup model
winget install Ollama.Ollama
ollama pull qwen2.5:7b

# 3. sanity check (mic / CUDA / Ollama), then run
.venv\Scripts\python -m freewhisper --check
.venv\Scripts\python -m freewhisper
```

The two Whisper models (~1.6 GB each) download from Hugging Face on first use.
GPU inference needs the NVIDIA runtime wheels — already in `requirements.txt` scope via
`pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` (the app adds their DLLs to the search path itself).

## Configuration — `config.yaml`

| Key | What it does |
|---|---|
| `hotkey` | dictation hotkey (default `ctrl+shift+space`; `ctrl+alt+space` is taken by Claude Desktop) |
| `language` | startup language, `he` / `en` |
| `silence_seconds` | how much quiet ends a dictation (default 2) |
| `silence_threshold` | mic level that counts as "talking" — calibrate with `--test-mic` |
| `models` | per-language faster-whisper model ids |
| `llm.model` | Ollama model for cleanup; `llm.enabled: false` pastes raw transcripts |
| `dictionary` | your names/terms — biases both Whisper and the LLM (e.g. לב התחביב) |
| `input_device` | mic index from `--check` (null = system default) |
| `overlay` | show the floating widget |

## Troubleshooting

- **Nothing pastes** → run `.venv\Scripts\python -m freewhisper --test-mic` *while speaking*.
  `SILENT` means wrong mic — pick an index from `--check` into `input_device`.
- **`cublas64_12.dll not found`** → `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` in the venv.
- **Cuts you off mid-sentence** → lower `silence_threshold`; **never stops** → raise it.
- **Slow cleanup** → switch `llm.model` to `qwen2.5:3b` (`ollama pull qwen2.5:3b`).
- Background instance logs: `freewhisper.log` in the project root.

## Project layout

```
freewhisper/
  main.py         app orchestration: hotkeys, watchdog, tray, lifecycle, --check/--test-mic
  overlay.py      tkinter floating pill + live waveform (poll-based, thread-safe)
  recorder.py     16kHz mic capture with sample-rate fallback + RMS helpers
  transcriber.py  faster-whisper wrapper (per-language models, CUDA DLL bootstrap)
  cleaner.py      Ollama post-processing (fails open — raw text is never lost)
  injector.py     clipboard-save → paste → clipboard-restore
config.yaml       all user settings
tests/            pytest smoke tests
```

## Dev

```powershell
.venv\Scripts\python -m pytest        # tests
.venv\Scripts\python -m freewhisper --check     # environment doctor
```

Built 2026 · Python 3.14 · tested on Windows 11, RTX 5070 Ti.
