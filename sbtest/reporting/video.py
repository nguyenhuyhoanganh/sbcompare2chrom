"""``--record``: one MP4 per test instead of a picture per step.

A background thread grabs the browser's windows (page, toolbar, bubbles, its dialogs) a few
times per second, draws the running case step at the bottom and a red frame on each
interaction for a moment (the same marks as the step pictures, ``sbtest.steps.mark``), and
pipes the frames to ffmpeg (``imageio-ffmpeg``) which writes H.264 - playable in the HTML report
and on Confluence. Windows only (it records the screen); recording never fails a test.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from sbtest import steps
from sbtest.utils import log

FPS = 5
WIDTH = 1280          # frames are scaled to this width (even height): small files, readable text
MARK_SECONDS = 1.5    # how long an interaction stays framed


class Recorder:
    def __init__(self, session, path: Path, fps: int = FPS, width: int = WIDTH) -> None:
        self.session, self.path, self.fps, self.width = session, Path(path), fps, width
        self.box = None                         # screen box of the browser windows
        self.size = None                        # video size, fixed by the first frame
        self.marks: list[tuple[float, dict]] = []
        self._viewport: dict = {}               # window box -> page viewport origin on screen
        self._stop = threading.Event()
        self._thread = None
        self._writer = None
        self.frames = 0

    # -- called on the test thread ---------------------------------------------------
    def start(self) -> "Recorder":
        import imageio_ffmpeg

        self.box = self.session.native.window_rect()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        first = self._frame()
        self.size = first.size
        self._writer = imageio_ffmpeg.write_frames(
            str(self.path), self.size, fps=self.fps, codec="libx264", quality=6, macro_block_size=2,
            pix_fmt_out="yuv420p", output_params=["-preset", "ultrafast"], ffmpeg_log_level="error")
        self._writer.send(None)
        self._writer.send(first.tobytes())
        self.frames = 1
        self._thread = threading.Thread(target=self._loop, name="sbtest-video", daemon=True)
        self._thread.start()
        return self

    def mark(self, m: dict) -> None:
        """An interaction (steps.mark) -> framed in the next frames, in screen coordinates."""
        screen = m.get("screen")
        if m.get("web") and self.box is not None:
            try:   # page viewport origin: one UIA lookup per window position
                if self.box not in self._viewport:
                    self._viewport[self.box] = self.session.native.viewport_origin()
                vx, vy = self._viewport[self.box]
                x, y, w, h, dpr = m["web"]
                screen = (vx + x * dpr, vy + y * dpr, vx + (x + w) * dpr, vy + (y + h) * dpr)
            except Exception:  # noqa: BLE001 - the frame is a help, not the test
                screen = None
        self.marks.append((time.monotonic(), {**m, "web": None, "screen": screen}))

    def stop(self) -> Path | None:
        """Finish the file; returns its path (None when nothing was recorded)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception as e:  # noqa: BLE001
                log.warning("video not finished: %s", e)
                return None
        return self.path if self.frames and self.path.exists() else None

    # -- background thread -------------------------------------------------------------
    def _loop(self) -> None:
        tick = 1 / self.fps
        next_t = time.monotonic() + tick
        last_box = time.monotonic()
        frame = None
        while not self._stop.is_set():
            try:
                if time.monotonic() - last_box > 1:   # windows open / close (dialogs, popups)
                    self.box, last_box = self.session.native.window_rect(), time.monotonic()
                frame = self._frame()
            except Exception as e:  # noqa: BLE001 - browser closing, desktop locked: keep the last frame
                log.debug("video frame skipped: %s", e)
            if frame is not None:
                # real time: when grabbing was slow, repeat the frame for the ticks it missed
                now = time.monotonic()
                repeat = 1 + max(0, int((now - next_t) / tick))
                for _ in range(repeat):
                    self._writer.send(frame.tobytes())
                    self.frames += 1
                next_t += tick * repeat
            self._stop.wait(max(0.0, next_t - time.monotonic()))

    def _frame(self):
        from PIL import Image, ImageDraw, ImageGrab

        from sbtest.reporting.evidence import _font, draw_marks

        img = ImageGrab.grab(bbox=self.box, all_screens=True).convert("RGB")
        now = time.monotonic()
        active = [m for t, m in self.marks if now - t < MARK_SECONDS]
        if active:
            numbered = len(self.marks) - len(active) + 1
            draw_marks(img, active, origin=self.box[:2], first=numbered)
        running = [s for s in steps.history() if s["status"] == "running"]
        if running:   # the case step being executed, at the bottom
            draw = ImageDraw.Draw(img)
            font = _font(max(14, img.width // 70))
            text = running[-1]["title"]
            tw, th = draw.textbbox((0, 0), text, font=font)[2:]
            draw.rectangle((0, img.height - th - 16, min(img.width, tw + 24), img.height), fill=(30, 30, 30))
            draw.text((12, img.height - th - 10), text, fill="white", font=font)
        w = self.width
        h = (img.height * w // img.width) // 2 * 2
        img = img.resize((w, h))
        if self.size and img.size != self.size:   # the windows box changed: keep the video size
            canvas = Image.new("RGB", self.size, (40, 40, 40))
            img.thumbnail(self.size)
            canvas.paste(img, (0, 0))
            img = canvas
        return img
