# splash.py
"""
Server splash screen — smooth video + audio.

Files expected in the project folder:
    splash.mp4        — the video
    splash_audio.mp3  — the audio track (already extracted, just place it here)

Dependencies:
    pip install opencv-python pillow pygame

Do NOT run this file directly. Run server.py instead.
"""

import tkinter as tk
from PIL import Image, ImageTk
import cv2
import threading
import os
import time
import pygame
import ffmpeg

# ── Resolve all paths relative to THIS file's directory ───────────────────────
_HERE        = os.path.dirname(os.path.abspath(__file__))
SPLASH_VIDEO = os.path.join(_HERE, "splash.mp4")
SPLASH_AUDIO = os.path.join(_HERE, "splash_audio.mp3")


class SplashScreen:
    def __init__(self, on_done):
        self.on_done  = on_done
        self.running  = True
        self._photo   = None   # GC protection for current PhotoImage
        self._img_id  = None   # single canvas image item (no stacking)

        self.root = tk.Tk()
        self.root.title("Parental Control — Server")
        self.root.configure(bg="black")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)

        # Disable window close button during splash
        self.root.protocol("WM_DELETE_WINDOW", lambda: None)

        # ESC only — no click-to-skip
        self.root.bind("<Escape>", self._finish)

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        if os.path.exists(SPLASH_VIDEO):
            threading.Thread(target=self._play_video, daemon=True).start()
        else:
            self._show_static_splash()

    # ── Audio ─────────────────────────────────────────────────────────────────
    def _start_audio(self):
        """
        Play splash_audio.mp3 using pygame.
        Called from the video thread just before the first frame is shown
        so audio and video stay in sync.
        """
        if not os.path.exists(SPLASH_AUDIO):
            print("[Splash] splash_audio.mp3 not found — playing silently.")
            return

        try:
            import pygame
            # Use a fresh mixer init every time with standard settings
            pygame.mixer.quit()          # ensure clean state
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
            pygame.mixer.music.load(SPLASH_AUDIO)
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.play()
            print("[Splash] Audio started.")
        except ImportError:
            print("[Splash] pygame not installed — no audio.  Run: pip install pygame")
        except Exception as e:
            print(f"[Splash] Audio error: {e}")

    def _stop_audio(self):
        try:
            import pygame
            pygame.mixer.music.stop()
            pygame.mixer.quit()
        except Exception:
            pass

    # ── Video playback ────────────────────────────────────────────────────────
    def _play_video(self):
        cap = cv2.VideoCapture(SPLASH_VIDEO)
        if not cap.isOpened():
            print("[Splash] Cannot open splash.mp4")
            self.root.after(0, self._finish)
            return

        fps            = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_duration = 1.0 / fps   # target seconds per frame

        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        first_frame = True

        while self.running:
            t0 = time.perf_counter()

            ret, frame = cap.read()
            if not ret:
                break   # video ended

            # Start audio exactly when the first frame is ready
            # so they are in sync from frame 0
            if first_frame:
                self._start_audio()
                first_frame = False

            # Resize frame to fullscreen, convert BGR→RGB
            frame_resized = cv2.resize(frame, (sw, sh),
                                       interpolation=cv2.INTER_LINEAR)
            rgb = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(image=Image.fromarray(rgb))

            # Push to main thread — uses itemconfig so only ONE canvas item exists
            self.root.after(0, self._update_frame, photo)

            # Sleep for the remaining frame time to match video FPS exactly
            elapsed = time.perf_counter() - t0
            remaining = frame_duration - elapsed
            if remaining > 0:
                time.sleep(remaining)

        cap.release()
        self._stop_audio()

        if self.running:
            self.root.after(0, self._finish)

    def _update_frame(self, photo):
        """Replace the canvas image in-place — no stacking, no black flicker."""
        self._photo = photo          # prevent garbage collection
        if self._img_id is None:
            self._img_id = self.canvas.create_image(0, 0, anchor="nw",
                                                     image=photo)
        else:
            self.canvas.itemconfig(self._img_id, image=photo)

    # ── Static fallback (no splash.mp4 found) ────────────────────────────────
    def _show_static_splash(self):
        print("[Splash] splash.mp4 not found — showing static splash.")
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        # Gradient background
        steps = 60
        for i in range(steps):
            rv = i / steps
            r = int(5  + rv * 8)
            g = int(8  + rv * 16)
            b = int(25 + rv * 55)
            self.canvas.create_rectangle(
                0, int(sh * i / steps), sw, int(sh * (i + 1) / steps),
                fill=f"#{r:02x}{g:02x}{b:02x}", outline=""
            )

        # Diagonal scan-lines
        for i in range(-sh, sw, 60):
            self.canvas.create_line(i, 0, i + sh, sh, fill="#0d2040", width=1)

        # Glow rings
        cx, cy = sw // 2, sh // 2 - 80
        for radius in range(200, 50, -10):
            alpha = int(120 * (1 - radius / 220))
            b_val = min(alpha * 3, 255)
            self.canvas.create_oval(
                cx - radius, cy - radius, cx + radius, cy + radius,
                fill=f"#00{min(alpha, 60):02x}{b_val:02x}", outline=""
            )

        self.canvas.create_text(cx, cy, text="🛡",
                                 font=("Segoe UI Emoji", 80), fill="#00d4ff")
        self.canvas.create_text(sw // 2, sh // 2 + 60,
                                 text="PARENTAL CONTROL",
                                 font=("Courier New", 46, "bold"), fill="#ffffff")
        self.canvas.create_text(sw // 2, sh // 2 + 118,
                                 text="SERVER CONSOLE",
                                 font=("Courier New", 20), fill="#00d4ff")
        self.canvas.create_text(sw // 2, sh // 2 + 158,
                                 text="v2.0  •  Encrypted  •  Secure",
                                 font=("Courier New", 11), fill="#334466")

        # Progress bar
        bx1, by = sw // 2 - 220, sh // 2 + 200
        self.canvas.create_rectangle(bx1, by, bx1 + 440, by + 12,
                                      fill="#0d2040", outline="#1a3a6a")
        self._bar_id = self.canvas.create_rectangle(bx1, by, bx1, by + 12,
                                                     fill="#00d4ff", outline="")
        self._bx1, self._bx2, self._by1, self._by2 = bx1, bx1 + 440, by, by + 12
        self._bar_w = 0
        self._animate_bar()

        self.canvas.create_text(sw // 2, sh - 36,
                                 text="Press ESC to skip",
                                 font=("Courier New", 10), fill="#1e3050")

        self.root.after(5000, self._finish)

    def _animate_bar(self):
        if not self.running:
            return
        total = self._bx2 - self._bx1
        self._bar_w = min(self._bar_w + 1.8, total)
        self.canvas.coords(self._bar_id,
                           self._bx1, self._by1,
                           self._bx1 + self._bar_w, self._by2)
        if self._bar_w < total:
            self.root.after(18, self._animate_bar)

    # ── Finish ────────────────────────────────────────────────────────────────
    def _finish(self, event=None):
        if not self.running:
            return
        self.running = False
        self._stop_audio()
        try:
            self.root.destroy()
        except Exception:
            pass
        self.on_done()

    def run(self):
        self.root.mainloop()