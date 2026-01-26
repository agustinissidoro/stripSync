import time
import urandom
import micropython

class PostProcessor:
    def __init__(self):
        self.active_b = 256  # Actual multiplier used in loop
        self.staged_b = 256  # Waiting for APPLY
        self.jitter = 0
        self.staged_jitter = 0
        self.fade_ms = 0
        self._b_start = 256
        self._b_target = 256
        self._b_start_time = time.ticks_ms()
        self._b_fade_ms = 0

    @property
    def brightness(self):
        return self.active_b / 256.0

    @brightness.setter
    def brightness(self, value):
        """Sets both immediately (for LIVE mode)."""
        self._start_brightness_fade(self._to_int(value), self.fade_ms)
        self.staged_b = self._b_target

    def set_brightness_live(self, value):
        """LIVE mode: apply immediately, ignoring fade_ms."""
        target_b = self._to_int(value)
        self.active_b = target_b
        self._b_start = target_b
        self._b_target = target_b
        self._b_fade_ms = 0
        self._b_start_time = time.ticks_ms()
        self.staged_b = target_b

    def stage_brightness(self, value):
        """Stages value for later (for STAGED mode)."""
        self.staged_b = self._to_int(value)
    
    def stage_jitter(self, value):
        self.staged_jitter = max(0, int(value))

    def set_jitter(self, value):
        self.jitter = max(0, int(value))
        self.staged_jitter = self.jitter

    def _to_int(self, value):
        # Convert 0-255 or 0.0-1.0 to 0-256
        if value > 1.0: return max(0, min(256, int(value)))
        return max(0, min(256, int(value * 256)))

    def apply(self):
        """Commits the staged brightness to the active calculation."""
        self._start_brightness_fade(self.staged_b, self.fade_ms)
        self.jitter = self.staged_jitter

    def _start_brightness_fade(self, target_b, fade_ms):
        if fade_ms <= 0:
            self.active_b = target_b
            self._b_start = target_b
            self._b_target = target_b
            self._b_fade_ms = 0
            self._b_start_time = time.ticks_ms()
            return
        self._b_start = self.active_b
        self._b_target = target_b
        self._b_fade_ms = float(fade_ms)
        self._b_start_time = time.ticks_ms()

    def is_animating(self):
        return self._b_fade_ms > 0

    def update(self):
        if self._b_fade_ms > 0:
            elapsed = time.ticks_diff(time.ticks_ms(), self._b_start_time)
            progress = elapsed / self._b_fade_ms
            if progress >= 1.0:
                self.active_b = self._b_target
                self._b_fade_ms = 0
            elif progress > 0.0:
                self.active_b = int(self._b_start + (self._b_target - self._b_start) * progress)
        return self.active_b

    @micropython.native
    def process(self, buffer):
        b_int = self.update()

        if b_int >= 256 and self.jitter == 0:
            return
        
        j = self.jitter

        for i in range(len(buffer)):
            r, g, b = buffer[i]
            if j > 0:
                # Per-pixel random jitter in range [-j, +j]
                delta = (urandom.getrandbits(16) % (2 * j + 1)) - j
                r = 0 if r + delta < 0 else (255 if r + delta > 255 else r + delta)
                g = 0 if g + delta < 0 else (255 if g + delta > 255 else g + delta)
                b = 0 if b + delta < 0 else (255 if b + delta > 255 else b + delta)

            # Bit-shift division (Value * Multiplier) / 256
            buffer[i] = ((r * b_int) >> 8, (g * b_int) >> 8, (b * b_int) >> 8)
