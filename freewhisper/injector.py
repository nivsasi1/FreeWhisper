import time

import keyboard
import pyperclip


def paste_text(text: str, delay_ms: int = 150):
    """Inject text into the focused window via clipboard + Ctrl+V.

    Clipboard-paste (not simulated typing) is required for Hebrew/RTL text.
    Restores the previous clipboard afterwards.
    """
    if not text:
        return
    try:
        previous = pyperclip.paste()
    except pyperclip.PyperclipException:
        previous = None
    pyperclip.copy(text)
    time.sleep(delay_ms / 1000)
    keyboard.send("ctrl+v")
    time.sleep(delay_ms / 1000)
    if previous is not None:
        pyperclip.copy(previous)
