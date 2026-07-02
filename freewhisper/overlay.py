"""Always-on-top floating widget — atelier dark-ink pill with flowing waves.

Recording visual: three overlapping sine curves that physically roll across
the panel (Siri-style), amplitude driven by your voice, plus a ring that
pulses out of the mic button. The live transcript sits in its own inset box
under the controls.

Crucial Windows detail: the window gets WS_EX_NOACTIVATE, so clicking its
buttons NEVER steals focus from the text field you're dictating into.
Runs in the main thread; worker-thread state is read via a 60ms poll.
"""

import collections
import ctypes
import math

TRANS = "#010203"
INK = "#2b2440"
INSET = "#221c33"          # live-transcript box, a shade darker than the panel
EDGE = "#5b2d8e"
EDGE_DIM = "#453a63"
GRIP = "#8a7fa8"
LIVE_FG = "#d6cfea"
X_FG = "#c9899a"
PILL_BG = "#3a3153"
MIC_COLORS = {"idle": "#5b2d8e", "rec": "#d64545", "busy": "#e8a33d", "cmd": "#4a7fd0"}
WAVE_MAIN = {"rec": "#e46a6a", "cmd": "#7aa5e8", "busy": "#e8a33d", "idle": GRIP}

W_REC, H_REC = 380, 108
W_IDLE, H_IDLE = 252, 56
PILL_R = 26
WAVE_X0 = 252


def _rrect_pts(x1, y1, x2, y2, r):
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]


def _blend(c1: str, c2: str, f: float) -> str:
    f = max(0.0, min(1.0, f))
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(a, b))


def _no_activate(tk_window):
    """WS_EX_NOACTIVATE + TOOLWINDOW: clickable but never takes focus, no alt-tab entry."""
    tk_window.update_idletasks()
    hwnd = ctypes.windll.user32.GetParent(tk_window.winfo_id()) or tk_window.winfo_id()
    GWL_EXSTYLE = -20
    style = ctypes.windll.user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE)
    ctypes.windll.user32.SetWindowLongPtrW(hwnd, GWL_EXSTYLE,
                                           style | 0x08000000 | 0x00000080)


class Overlay:
    def __init__(self, get_state, get_language, get_level, get_live_text,
                 on_record, on_command, on_cycle_language, on_copy_last,
                 get_history, on_quit):
        import tkinter as tk
        self.tk = tk

        self.get_state = get_state
        self.get_language = get_language
        self.get_level = get_level
        self.get_live_text = get_live_text
        self.get_history = get_history
        self.on_copy_last = on_copy_last
        self.width = float(W_IDLE)
        self.height = float(H_IDLE)
        self._amp = 0.0
        self._t = 0.0
        self._pulse = 0.0
        self._flash = 0
        self._hist_win = None

        root = tk.Tk()
        self.root = root
        root.title("FreeWhisper")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.attributes("-transparentcolor", TRANS)
        root.attributes("-alpha", 0.97)
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{W_REC}x{H_REC}+{sw - W_REC - 40}+{sh - H_REC - 120}")

        c = tk.Canvas(root, width=W_REC, height=H_REC, bg=TRANS, highlightthickness=0)
        c.pack()
        self.canvas = c

        self.bg = c.create_polygon(_rrect_pts(1, 1, W_IDLE, H_IDLE - 1, PILL_R),
                                   smooth=True, fill=INK, outline=EDGE, width=2)
        y = H_IDLE // 2
        self.grip = c.create_text(16, y, text="⠿", fill=GRIP, font=("Segoe UI", 12))

        mx = 48
        self.mic_center = (mx, y)
        self.mic_circle = c.create_oval(mx - 15, y - 15, mx + 15, y + 15,
                                        fill=MIC_COLORS["idle"], outline="", tags="mic")
        # clean minimal mic: capsule head, cradle arc, stem, base
        c.create_oval(mx - 4, y - 10, mx + 4, y + 1, fill="white", outline="", tags="mic")
        c.create_arc(mx - 8, y - 8, mx + 8, y + 6, start=180, extent=180,
                     style="arc", outline="white", width=2, tags="mic")
        c.create_line(mx, y + 6, mx, y + 10, fill="white", width=2,
                      capstyle="round", tags="mic")
        c.create_line(mx - 4, y + 10, mx + 4, y + 10, fill="white", width=2,
                      capstyle="round", tags="mic")

        c.create_text(78, y, text="⚡", fill="#e8c96a", font=("Segoe UI", 13), tags="cmd")
        c.create_polygon(_rrect_pts(94, 14, 148, H_IDLE - 14, 12), smooth=True,
                         fill=PILL_BG, outline="", tags="lang")
        self.lang_text = c.create_text(121, y, text="", fill="white",
                                       font=("Segoe UI", 10, "bold"), tags="lang")
        self.copy_btn = c.create_text(166, y, text="📋", font=("Segoe UI", 12), tags="copy")
        c.create_text(196, y, text="🕘", font=("Segoe UI", 12), tags="hist")
        c.create_text(226, y, text="✕", fill=X_FG, font=("Segoe UI", 12, "bold"), tags="x")

        # live transcript inset box (visible only while expanded and speaking)
        self.live_box = c.create_polygon(
            _rrect_pts(14, 62, W_REC - 14, H_REC - 8, 12), smooth=True,
            fill=INSET, outline=EDGE_DIM, width=1, state="hidden")
        self.live = c.create_text(W_REC - 26, (62 + H_REC - 8) / 2, text="",
                                  fill=LIVE_FG, anchor="e", font=("Segoe UI", 10),
                                  width=W_REC - 52, state="hidden")

        c.tag_bind("mic", "<Button-1>", lambda e: on_record())
        c.tag_bind("cmd", "<Button-1>", lambda e: on_command())
        c.tag_bind("lang", "<Button-1>", lambda e: on_cycle_language())
        c.tag_bind("copy", "<Button-1>", lambda e: self._copy_clicked())
        c.tag_bind("hist", "<Button-1>", lambda e: self._toggle_history())
        c.tag_bind("x", "<Button-1>", lambda e: on_quit())
        for t in ("mic", "cmd", "lang", "copy", "hist", "x"):
            c.tag_bind(t, "<Enter>", lambda e: c.config(cursor="hand2"))
            c.tag_bind(t, "<Leave>", lambda e: c.config(cursor=""))
        for item in (self.bg, self.grip):
            c.tag_bind(item, "<ButtonPress-1>", self._press)
            c.tag_bind(item, "<B1-Motion>", self._drag)

        self._drag_off = (0, 0)
        _no_activate(root)
        self._poll()

    # --- interactions ---------------------------------------------------------

    def _press(self, e):
        self._drag_off = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _drag(self, e):
        dx, dy = self._drag_off
        self.root.geometry(f"+{e.x_root - dx}+{e.y_root - dy}")
        if self._hist_win is not None:
            self._place_history()

    def _copy_clicked(self):
        if self.on_copy_last():
            self._flash = 8  # brief ✔ = copied

    def _toggle_history(self):
        if self._hist_win is not None:
            self._close_history()
            return
        tk = self.tk
        win = tk.Toplevel(self.root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.0)
        win.configure(bg=INK, highlightbackground=EDGE, highlightthickness=2)
        items = self.get_history()
        if not items:
            tk.Label(win, text="עדיין אין היסטוריה", bg=INK, fg=GRIP,
                     font=("Segoe UI", 10), padx=14, pady=10).pack()
        for entry in list(items)[:8]:
            shown = entry if len(entry) <= 46 else entry[:45] + "…"
            row = tk.Label(win, text=shown, bg=INK, fg="#e6e0f5", anchor="e",
                           justify="right", font=("Segoe UI", 10), padx=12, pady=5,
                           width=44, cursor="hand2")
            row.pack(fill="x")
            row.bind("<Button-1>", lambda e, full=entry: self._copy_history(full, e.widget))
            row.bind("<Enter>", lambda e: e.widget.config(bg=PILL_BG))
            row.bind("<Leave>", lambda e: e.widget.config(bg=INK))
        self._hist_win = win
        _no_activate(win)
        self._place_history()
        self._fade_in(win, 0.0)

    def _copy_history(self, text, widget):
        from .injector import copy_text
        copy_text(text)
        widget.config(fg="#7be08a")
        widget.after(600, lambda: widget.config(fg="#e6e0f5"))

    def _place_history(self):
        win = self._hist_win
        win.update_idletasks()
        x = self.root.winfo_x() + W_REC - win.winfo_reqwidth()
        y = self.root.winfo_y() - win.winfo_reqheight() - 8
        win.geometry(f"+{x}+{max(0, y)}")

    def _close_history(self):
        if self._hist_win is not None:
            self._hist_win.destroy()
            self._hist_win = None

    def _fade_in(self, win, alpha):
        if self._hist_win is not win:
            return
        alpha = min(0.97, alpha + 0.12)
        win.attributes("-alpha", alpha)
        if alpha < 0.97:
            win.after(20, lambda: self._fade_in(win, alpha))

    # --- render loop ----------------------------------------------------------

    def _draw_waves(self, state):
        """Three rolling sine curves, edge-tapered — a wave that looks like a wave."""
        c = self.canvas
        x0, x1 = WAVE_X0, self.width - 16
        span = x1 - x0
        if span < 40:
            return
        cy = H_IDLE / 2
        main = WAVE_MAIN.get(state, WAVE_MAIN["idle"])
        base = 2.5 + self._amp * 15
        for amp_f, cycles, speed, color in (
                (1.00, 2.2, 1.6, main),
                (0.62, 3.1, -2.3, _blend(main, INK, 0.45)),
                (0.38, 4.0, 3.0, _blend(main, INK, 0.68))):
            pts, x = [], x0
            step = max(3, int(span // 34))
            while x <= x1:
                u = (x - x0) / span
                yy = cy + math.sin(u * cycles * 2 * math.pi + self._t * speed) \
                    * base * amp_f * math.sin(math.pi * u)
                pts += [x, yy]
                x += step
            if len(pts) >= 8:
                c.create_line(*pts, fill=color, width=2.4, smooth=True,
                              capstyle="round", tags="wave")

    def _draw_pulse(self, state):
        """A ring that swells out of the mic button while recording."""
        if state not in ("rec", "cmd"):
            self._pulse = 0.0
            return
        self._pulse = (self._pulse + 0.055 + self._amp * 0.06) % 1.0
        mx, my = self.mic_center
        r = 16 + self._pulse * 11
        color = _blend(MIC_COLORS[state], INK, 0.25 + self._pulse * 0.75)
        self.canvas.create_oval(mx - r, my - r, mx + r, my + r,
                                outline=color, width=2, tags="wave")
        self.canvas.tag_lower("wave", "mic")

    def _poll(self):
        state = self.get_state()
        c = self.canvas
        active = state in ("rec", "busy", "cmd")
        self._t += 0.22

        target = min(1.0, self.get_level() / 0.05) ** 0.7 if state in ("rec", "cmd") else 0.0
        self._amp += (target - self._amp) * (0.45 if target > self._amp else 0.12)

        c.itemconfig(self.mic_circle, fill=MIC_COLORS.get(state, MIC_COLORS["idle"]))
        c.itemconfig(self.lang_text, text=self.get_language().upper()[:4])
        if self._flash > 0:
            self._flash -= 1
            c.itemconfig(self.copy_btn, text="✔" if self._flash else "📋")

        # eased expand/collapse; the WINDOW itself grows/shrinks too, otherwise
        # Windows leaves stale purple ghosts in the transparent area after collapse
        tw = W_REC if active else W_IDLE
        th = H_REC - 2 if active else H_IDLE
        if abs(self.width - tw) > 0.5 or abs(self.height - th) > 0.5:
            if active:  # expand the window up-front so the growing pill has room
                self.root.geometry(f"{W_REC}x{H_REC}")
            self.width += (tw - self.width) * 0.3
            self.height += (th - self.height) * 0.3
            c.coords(self.bg, *_rrect_pts(1, 1, self.width, self.height - 1, PILL_R))
        elif not active and self.root.winfo_width() != W_IDLE:
            self.root.geometry(f"{W_IDLE}x{H_IDLE}")  # crop away the ghost area

        c.delete("wave")
        if self.width > WAVE_X0 + 40:
            self._draw_waves(state)
            self._draw_pulse(state)

        live = self.get_live_text() if active else ""
        shown = "normal" if (self.height > H_REC - 20 and live) else "hidden"
        # keep it to one visual line inside the box
        c.itemconfig(self.live, text=live[-60:], state=shown)
        c.itemconfigure(self.live_box, state=shown)

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
