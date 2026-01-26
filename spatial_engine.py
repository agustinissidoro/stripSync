import math
import urandom
import time

class SpatialEngine:
    def __init__(self, count):
        self.count = count
        self.tick = 0
        self.direction = "right"
        self.loading_start_ms = time.ticks_ms()
        self.loading_target_ms = 1000  # Default 1s
        self.output = [(0, 0, 0)] * count
        self.black = (0, 0, 0)

    def apply(self, mode, colors, speed_ms, arg, out_buffer, dt_ms):
        if speed_ms and speed_ms > 0 and dt_ms > 0:
            self.tick += dt_ms / speed_ms

        # Ensure colors is a per-LED buffer of length count
        if not colors:
            colors = self.output
            for i in range(self.count):
                colors[i] = self.black
        if len(colors) != self.count:
            # safe fallback (repeat or crop)
            if len(colors) == 1:
                c = colors[0]
                for i in range(self.count):
                    out_buffer[i] = c
                colors = out_buffer
            else:
                for i in range(self.count):
                    out_buffer[i] = colors[i] if i < len(colors) else self.black
                colors = out_buffer

        # --- Universal Motion Calculation ---
        t = self.tick * 10
        if self.direction == "right":
            pos = int(t) % self.count
        elif self.direction == "left":
            pos = (self.count - 1) - (int(t) % self.count)
        else:  # pingpong
            pos = int(t) % (self.count * 2)
            if pos >= self.count:
                pos = (self.count * 2 - 1) - pos

        # --- Spatial Modes ---
        if mode == 0:
            for i in range(self.count):
                out_buffer[i] = colors[i]
            return out_buffer

        # Mode 1: single moving pixel from the *current per-LED buffer*
        elif mode == 1:
            for i in range(self.count):
                out_buffer[i] = self.black
            out_buffer[pos] = colors[pos]
            return out_buffer

        # Mode 2: blink full buffer
        elif mode == 2:
            is_on = (int(self.tick * 5) % 10) < (arg if arg > 0 else 5)
            if is_on:
                for i in range(self.count):
                    out_buffer[i] = colors[i]
            else:
                for i in range(self.count):
                    out_buffer[i] = self.black
            return out_buffer

        # Mode 3: random sparkle (density = arg)
        elif mode == 3:
            for i in range(self.count):
                if (urandom.getrandbits(8) & 0xFF) < arg:
                    out_buffer[i] = colors[i]
                else:
                    out_buffer[i] = self.black
            return out_buffer

        # Mode 4: rotate buffer
        elif mode == 4:
            for i in range(self.count):
                out_buffer[i] = colors[(i + pos) % self.count]
            return out_buffer

        # Mode 5: Exact Loading Bar
        elif mode == 5:
            elapsed = time.ticks_diff(time.ticks_ms(), self.loading_start_ms)
            progress = min(1.0, elapsed / self.loading_target_ms)
            fill_limit = int(progress * self.count)

            for i in range(self.count):
                out_buffer[i] = self.black

            if self.direction == "right":
                for i in range(fill_limit):
                    out_buffer[i] = colors[i]
            elif self.direction == "left":
                for i in range(self.count - fill_limit, self.count):
                    out_buffer[i] = colors[i]
            else:  # pingpong (fills from center)
                mid = self.count // 2
                half_fill = int(progress * mid)
                for i in range(mid - half_fill, mid + half_fill):
                    if 0 <= i < self.count:
                        out_buffer[i] = colors[i]
            return out_buffer

        for i in range(self.count):
            out_buffer[i] = colors[i]
        return out_buffer
