# FreeWhisper

**Free, private, local voice dictation for Windows — speak Hebrew or English anywhere, get clean AI-polished text at your cursor. No cloud, no subscription, no audio ever leaves your machine.**

Think Wispr Flow, but running 100% on your own GPU. Tap a hotkey in any app, talk, go quiet — and a locally-run Whisper model transcribes you while a local LLM strips the filler words, fixes punctuation, and even applies your spoken self-corrections ("on Tuesday... no wait, Wednesday" comes out as just Wednesday). Hebrew support is first-class, not an afterthought: it uses the [ivrit.ai](https://huggingface.co/ivrit-ai) Whisper fine-tune (state of the art for Hebrew STT) and pastes via the clipboard because simulated typing mangles RTL text.

## Demo

<!-- demo GIF goes here: record yourself dictating in Hebrew + English -->
*Demo coming soon.*

## Features

- **Tap-to-dictate anywhere** — `Ctrl+Shift+Space` in any app; recording auto-stops after ~2s of silence (RMS watchdog) or on a second tap
- **Bilingual with per-dictation auto-detect** — a cheap language-ID pass picks Hebrew or English, then a single full decode runs on the right model
- **LLM cleanup that fails open** — filler removal, punctuation, spoken self-corrections, list formatting; if Ollama is down, the raw transcript is pasted instead of losing your words
- **Live typing** — a low-beam partial transcript streams into the field as you speak, then gets erased and replaced by the final clean version
- **Command mode** — select text anywhere, `Ctrl+Shift+C`, speak an instruction ("translate to English", "תקצר את זה") and the result replaces it
- **Spoken intents, detected in code** — "delete everything / תמחק הכל" cancels, "write this in English / תכתוב באנגלית" switches output language; routed by regex, never trusted to the LLM
- **Floating overlay widget** — always-on-top pill with a voice-reactive waveform, live transcript, history, and a `WS_EX_NOACTIVATE` window style so clicking it never steals focus from the field you're dictating into
- **Personal dictionary** — your names/terms bias both Whisper (initial prompt) and the LLM prompt
- **Output guard** — a script filter blocks CJK/Cyrillic/Arabic leakage (small local models love sneaking those in) and falls back to the raw transcript
- **Quality-of-life** — tray icon, start/stop sound cues, multi-monitor widget placement, single-instance lock, `--check` environment doctor, `--test-mic` calibration

## How it works

```
hotkey → record (sounddevice, 16 kHz) → faster-whisper on GPU → Ollama cleanup → Ctrl+V paste
```

- **STT**: [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2) with one lazily-loaded, pre-warmed model per language — Hebrew: `ivrit-ai/whisper-large-v3-turbo-ct2`, English: `deepdml/faster-whisper-large-v3-turbo-ct2`
- **Auto language**: the multilingual model does a cheap encode-only language ID on the first ~15s, then exactly one full beam-search pass runs on the winning model (the Hebrew fine-tune gave up language detection, so it can't go first)
- **Cleanup**: a local LLM via [Ollama](https://ollama.com)'s `/api/chat` (default `gemma3:12b` — best Hebrew quality; `qwen2.5:7b` is faster), with few-shot examples and `keep_alive: -1` so the model stays warm between dictations
- **Injection**: clipboard-save → `Ctrl+V` → optional restore (`keyboard` + `pyperclip`) — the only method that reliably survives Hebrew/RTL
- **UI**: a tkinter overlay polled at 60 ms from worker threads; Win32 calls via `ctypes` for the no-focus-steal window style and monitor placement

## Requirements

- Windows 10/11
- Python 3.12+ (built on 3.14)
- An NVIDIA GPU is strongly recommended (CUDA runtime installed as pip wheels — no CUDA Toolkit needed); CPU fallback works with `device: cpu`, `compute_type: int8`
- [Ollama](https://ollama.com) for the cleanup step (optional — `llm.enabled: false` pastes raw transcripts)

## Install & run

```powershell
git clone https://github.com/nivsasi1/FreeWhisper
cd FreeWhisper
winget install Ollama.Ollama   # if you don't have it
.\setup.ps1                    # venv, deps, CUDA wheels, ollama pull, desktop + startup shortcuts
```

Then verify and launch:

```powershell
.venv\Scripts\python -m freewhisper --check   # mic / CUDA / Ollama sanity check
.venv\Scripts\python -m freewhisper
```

The two Whisper models (~1.6 GB each) download from Hugging Face on first use. `setup.ps1` also creates a startup shortcut, so FreeWhisper runs windowless at login (logs go to `freewhisper.log`).

All settings — hotkeys, silence threshold, models, LLM, personal dictionary, mic device, widget — live in [`config.yaml`](config.yaml), which is fully commented.

| Action | How |
|---|---|
| Dictate | `Ctrl+Shift+Space` or the mic button |
| Stop | go quiet (~2s) or tap again |
| Command on selection | `Ctrl+Shift+C`, then speak |
| Cycle AUTO → HE → EN | `Ctrl+Alt+L` or the language pill |
| History / copy last | widget buttons |

## Development

```powershell
.venv\Scripts\python -m pytest                 # smoke tests (config, prompts, intent regexes)
.venv\Scripts\python -m freewhisper --test-mic # record 3s, print level + transcript
```

## Tech stack

Python · faster-whisper (CTranslate2, CUDA) · Ollama · sounddevice · tkinter + Win32 (ctypes) · keyboard / pyperclip / pystray · pytest
