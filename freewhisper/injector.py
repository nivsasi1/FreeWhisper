import time

import keyboard
import pyperclip


def paste_text(text: str, delay_ms: int = 150, restore_clipboard: bool = False):
    """Inject text into the focused window via clipboard + Ctrl+V.

    Clipboard-paste (not simulated typing) is required for Hebrew/RTL text.
    By default the result STAYS in the clipboard: restoring the old clipboard
    too early races slow apps — they read it after the restore and paste the
    old content instead. With restore_clipboard=True we wait a full second
    before restoring, which is safe for all but the slowest apps.
    """
    if not text:
        return
    previous = None
    if restore_clipboard:
        try:
            previous = pyperclip.paste()
        except pyperclip.PyperclipException:
            pass
    pyperclip.copy(text)
    time.sleep(delay_ms / 1000)
    keyboard.send("ctrl+v")
    if restore_clipboard and previous is not None:
        time.sleep(1.0)
        pyperclip.copy(previous)


def copy_text(text: str):
    """Just put text on the clipboard (for the copy button / history)."""
    pyperclip.copy(text)


def type_text(text: str):
    """Type unicode text into the focused field (used for live partials)."""
    if text:
        keyboard.write(text)


def send_backspaces(n: int):
    for i in range(n):
        keyboard.send("backspace")
        if i % 40 == 39:
            time.sleep(0.02)  # let slow apps keep up on long erases


def grab_selection(delay_ms: int = 150) -> str:
    """Copy whatever is selected in the focused app and return it.

    Uses the Ctrl+C trick. Two timing traps handled here:
    - if this was triggered by a hotkey, the user's physical Ctrl/Alt/Shift are
      still held — sending Ctrl+C then reaches the app as Ctrl+Alt+C. Wait for
      release first.
    - slow apps write the clipboard late — poll for the change instead of a
      fixed sleep.
    Returns "" when nothing is selected.
    """
    try:
        previous = pyperclip.paste()
    except pyperclip.PyperclipException:
        previous = ""
    marker = "\x00__freewhisper__\x00"
    pyperclip.copy(marker)

    deadline = time.time() + 1.0
    while time.time() < deadline and any(
            keyboard.is_pressed(k) for k in ("ctrl", "alt", "shift")):
        time.sleep(0.03)
    keyboard.send("ctrl+c")

    grabbed = marker
    deadline = time.time() + 1.0
    while time.time() < deadline:
        time.sleep(0.05)
        try:
            grabbed = pyperclip.paste()
        except pyperclip.PyperclipException:
            continue
        if grabbed != marker:
            break
    pyperclip.copy(previous)
    return "" if grabbed == marker else grabbed
