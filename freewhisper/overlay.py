"""Always-on-top floating widget with a live voice waveform.

Idle: compact rounded pill (grip / mic / HE-EN / ✕).
Recording: the pill smoothly expands and shows bars dancing with your voice.

Runs in the main thread (tkinter requirement); worker-thread state is read
via a 60ms poll. The window background uses -transparentcolor, so the rounded
corners are truly transparent and click-through.
"""

import collections

TRANS = "#010203"        # rendered fully transparent + click-through
INK = "#2b2440"
EDGE = "#5b2d8e"
COLORS = {"idle": "#5b2d8e", "rec": "#d64545", "busy": "#e8a33d"}
WAVE_COLOR = {"rec": "#e46a6a", "busy": "#e8a33d", "idle": "#8a7fa8"}

H = 56
W_IDLE = 168
W_REC = 320
MIC = (52, H // 2)       # mic button center
WAVE_X0 = 170            # waveform area start
BAR_STEP = 6
MAXLEVEL = 0.06          # mic RMS mapped to full bar height


def _rrect_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


class Overlay:
    def __init__(self, get_state, get_language, get_level, on_record, on_toggle_language, on_quit):
        import tkinter as tk

        self.get_state = get_state
        self.get_language = get_language
        self.get_level = get_level
        self.levels = collections.deque([0.0] * 24, maxlen=24)
        self.width = float(W_IDLE)

        self.root = tk.Tk()
        self.root.title("FreeWhisper")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-transparentcolor", TRANS)
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{W_REC}x{H}+{sw - W_REC - 40}+{sh - H - 130}")

        c = tk.Canvas(self.root, width=W_REC, height=H, bg=TRANS, highlightthickness=0)
        c.pack()
        self.canvas = c

        self.bg = c.create_polygon(_rrect_pts(1, 1, W_IDLE, H - 1, 26),
                                   smooth=True, fill=INK, outline=EDGE, width=2)
        self.grip = c.create_text(16, H // 2, text="⠿", fill="#8a7fa8",
                                  font=("Segoe UI", 12))

        mx, my = MIC
        self.mic_circle = c.create_oval(mx - 16, my - 16, mx + 16, my + 16,
                                        fill=COLORS["idle"], outline="", tags="mic")
        c.create_oval(mx - 5, my - 11, mx + 5, my + 2, fill="white", outline="", tags="mic")
        c.create_rectangle(mx - 2, my + 2, mx + 2, my + 8, fill="white", outline="", tags="mic")
        c.create_line(mx - 7, my + 9, mx + 7, my + 9, fill="white", width=2, tags="mic")

        self.lang_pill = c.create_polygon(_rrect_pts(80, 14, 122, H - 14, 12),
                                          smooth=True, fill="#3a3153", outline="", tags="lang")
        self.lang_text = c.create_text(101, H // 2, text=self.get_language().upper(),
                                       fill="white", font=("Segoe UI", 11, "bold"), tags="lang")
        self.x_btn = c.create_text(144, H // 2, text="✕", fill="#c9899a",
                                   font=("Segoe UI", 12, "bold"), tags="x")

        c.tag_bind("mic", "<Button-1>", lambda e: on_record())
        c.tag_bind("lang", "<Button-1>", lambda e: on_toggle_language())
        c.tag_bind("x", "<Button-1>", lambda e: on_quit())
        for cursor_tag in ("mic", "lang", "x"):
            c.tag_bind(cursor_tag, "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind(cursor_tag, "<Leave>", lambda e: c.config(cursor=""))

        # drag anywhere on the pill background or grip
        for item in (self.bg, self.grip):
            c.tag_bind(item, "<ButtonPress-1>", self._press)
            c.tag_bind(item, "<B1-Motion>", self._drag)

        self._drag_off = (0, 0)
        self._poll()

    def _press(self, e):
        self._drag_off = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag(self, e):
        dx, dy = self._drag_off
        self.root.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")

    def _poll(self):
        state = self.get_state()
        c = self.canvas
        c.itemconfig(self.mic_circle, fill=COLORS.get(state, COLORS["idle"]))
        c.itemconfig(self.lang_text, text=self.get_language().upper())

        # feed the waveform: live mic level while recording, decay otherwise
        if state == "rec":
            self.levels.append(self.get_level())
        elif state == "busy":
            self.levels.append(self.levels[-1] * 0.75)
        else:
            self.levels.append(0.0)

        # smooth expand/collapse
        target = W_REC if state in ("rec", "busy") else W_IDLE
        if abs(self.width - target) > 1:
            self.width += (target - self.width) * 0.35
            c.coords(self.bg, *_rrect_pts(1, 1, self.width, H - 1, 26))

        c.delete("wave")
        if self.width > WAVE_X0 + 20:
            color = WAVE_COLOR.get(state, WAVE_COLOR["idle"])
            n = int((self.width - WAVE_X0 - 12) // BAR_STEP)
            shown = list(self.levels)[-n:] if n > 0 else []
            for i, lvl in enumerate(shown):
                x = WAVE_X0 + i * BAR_STEP
                h = 2 + min(1.0, lvl / MAXLEVEL) ** 0.5 * 18
                c.create_line(x, H / 2 - h, x, H / 2 + h, fill=color, width=3,
                              capstyle="round", tags="wave")

        self.root.after(60, self._poll)

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            pass

    def close(self):
        try:
            self.root.after(0, self.root.destroy)
        except Exception:
            pass
