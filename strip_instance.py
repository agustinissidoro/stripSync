import time
import micropython
import urandom
from post_process import PostProcessor
from color_provider import ColorProvider
from transition_manager import TransitionManager
from spatial_engine import SpatialEngine

class StripInstance:
    def __init__(self, name, count, start_index):
        self.name = name
        self.count = count
        self.start_index = start_index

        self.colors = ColorProvider()
        self.tx = TransitionManager(count)
        self.engine = SpatialEngine(count)
        self.fx = PostProcessor()
        self.fx.fade_ms = 0
        self.fx.brightness = 1.0
        self.fx.set_jitter(0)

        self.c_mode = 0
        self.color_mode = "gradient"
        self.pattern_counts = None
        self.s_mode = 0
        self.active_points = [(0, 0, 0)]
        # Speed is a time period in ms for one tick step (lower = faster).
        self.speed = 10
        self.arg = 5
        self.is_running = True
        self.dirty = True
        self._buf_target = [(0, 0, 0)] * count
        self._buf_smooth = [(0, 0, 0)] * count
        self._buf_frame = [(0, 0, 0)] * count
        self._last_ms = time.ticks_ms()
        self._timed_end_ms = None
        self._timed_restore_method = None
        self._timed_prev_state = None

        self.staging = {
            "color": None, "mode": None, "direction": None,
            "fade": None, "speed": None, "load_time": None,
            "color_mode": None, "pattern": None
        }

    def _resolve_c_mode(self):
        if not self.active_points or len(self.active_points) <= 1:
            return 0
        if self.color_mode == "blocks":
            return 2
        if self.color_mode == "pattern":
            return 3
        # Default to gradient for multi-color
        return 1

    def _set_color_mode(self, mode, pattern=None):
        if mode in ("simple", "gradient", "blocks", "pattern"):
            self.color_mode = mode
        if pattern is not None:
            self.pattern_counts = pattern
    def set_property(self, msg_type, val, live=False):
        if live:
            # LIVE MODE: Precise sequential updates
            if msg_type == "SET_FADE":
                # Apply immediately so the NEXT color command knows the duration
                self.tx.fade_ms = val
                self.fx.fade_ms = val
                self.dirty = True
            elif msg_type == "SET_BRIGHT":
                self.fx.brightness = val
                self.dirty = True
            elif msg_type == "SET_JITTER":
                self.fx.set_jitter(val)
                self.dirty = True
            elif msg_type == "SET_COLOR":
                # Trigger transition using the current self.tx.fade_ms
                self.active_points = val
                self.c_mode = self._resolve_c_mode()
                self.tx.start_transition()
                self.dirty = True
            elif msg_type == "SET_C_MODE":
                mode, pattern = val
                self._set_color_mode(mode, pattern)
                self.c_mode = self._resolve_c_mode()
                self.dirty = True
            elif msg_type == "SET_S_MODE":
                self.s_mode = val
                if val == 5: self.engine.loading_start_ms = time.ticks_ms()
                self.dirty = True
            elif msg_type == "SET_DIR":
                self.engine.direction = val
                self.dirty = True
            elif msg_type == "SET_SPEED":
                self.speed = val
                self.dirty = True
            elif msg_type == "SET_LOAD_TIME":
                self.engine.loading_target_ms = val
                self.engine.loading_start_ms = time.ticks_ms()
                self.dirty = True
        else:
            # STAGED MODE: Save for apply()
            if msg_type == "SET_COLOR": self.staging["color"] = val
            elif msg_type == "SET_C_MODE":
                mode, pattern = val
                self.staging["color_mode"] = mode
                if pattern is not None:
                    self.staging["pattern"] = pattern
            elif msg_type == "SET_S_MODE": self.staging["mode"] = val
            elif msg_type == "SET_DIR": self.staging["direction"] = val
            elif msg_type == "SET_FADE": self.staging["fade"] = val
            elif msg_type == "SET_SPEED": self.staging["speed"] = val
            elif msg_type == "SET_LOAD_TIME": self.staging["load_time"] = val
            elif msg_type == "SET_BRIGHT": self.fx.stage_brightness(val)
            elif msg_type == "SET_JITTER": self.fx.stage_jitter(val)

    def apply(self, duration_ms=None, restore_method="last"):
        prev_state = None
        if duration_ms is not None and duration_ms > 0:
            prev_state = self._snapshot_state()

        # 0. Apply color mode before color so multi-color uses the right mode
        if self.staging["color_mode"] is not None:
            self._set_color_mode(self.staging["color_mode"], self.staging["pattern"])
            self.staging["color_mode"] = None
            self.staging["pattern"] = None
            self.c_mode = self._resolve_c_mode()
            self.dirty = True
        elif self.staging["pattern"] is not None and self.color_mode == "pattern":
            self.pattern_counts = self.staging["pattern"]
            self.staging["pattern"] = None
            self.c_mode = self._resolve_c_mode()
            self.dirty = True

        # 1. Update Fade Timing FIRST so tx knows the duration before transition starts
        if self.staging["fade"] is not None:
            self.tx.fade_ms = self.staging["fade"]
            self.fx.fade_ms = self.staging["fade"]
            self.staging["fade"] = None
            self.dirty = True
            
        # 2. Commit Color and snapshot for the LERP
        if self.staging["color"] is not None:
            new_colors = self.staging["color"]

            # Trigger transition if color changed OR if we want to force a re-fade
            self.active_points = new_colors
            self.c_mode = self._resolve_c_mode()
            self.tx.start_transition()

            self.staging["color"] = None
            self.dirty = True

        # 3. Handle remaining properties
        if self.staging["mode"] is not None:
            self.s_mode = self.staging["mode"]
            self.staging["mode"] = None
            self.dirty = True
        if self.staging["direction"] is not None:
            self.engine.direction = self.staging["direction"]
            self.staging["direction"] = None
            self.dirty = True
        if self.staging["speed"] is not None:
            self.speed = self.staging["speed"]
            self.staging["speed"] = None
            self.dirty = True
        
        if self.staging["load_time"] is not None:
            self.engine.loading_target_ms = self.staging["load_time"]
            self.engine.loading_start_ms = time.ticks_ms()
            self.staging["load_time"] = None
            self.dirty = True
        elif self.s_mode == 5:
            # Persistent reset for progress bar if mode is just activated
            self.engine.loading_start_ms = time.ticks_ms()
            self.dirty = True

        # Apply any staged global FX for this strip
        self.fx.apply()

        if duration_ms is not None and duration_ms > 0:
            self._timed_prev_state = prev_state
            self._timed_restore_method = restore_method if restore_method in ("off", "last") else "last"
            self._timed_end_ms = time.ticks_add(time.ticks_ms(), duration_ms)
        else:
            self._timed_end_ms = None
            self._timed_prev_state = None
            self._timed_restore_method = None

    def _snapshot_state(self):
        return {
            "c_mode": self.c_mode,
            "color_mode": self.color_mode,
            "pattern_counts": None if self.pattern_counts is None else list(self.pattern_counts),
            "s_mode": self.s_mode,
            "active_points": list(self.active_points),
            "speed": self.speed,
            "fade": self.tx.fade_ms,
            "direction": self.engine.direction,
            "brightness": self.fx.brightness,
            "jitter": self.fx.jitter,
            "load_time": self.engine.loading_target_ms,
        }

    def _apply_state(self, state):
        self.tx.fade_ms = state["fade"]
        self.fx.fade_ms = state["fade"]

        self.active_points = list(state["active_points"])
        self.color_mode = state.get("color_mode", self.color_mode)
        self.pattern_counts = state.get("pattern_counts", self.pattern_counts)
        self.c_mode = self._resolve_c_mode()
        self.tx.start_transition()

        self.s_mode = state["s_mode"]
        self.speed = state["speed"]
        self.engine.direction = state["direction"]
        self.engine.loading_target_ms = state["load_time"]
        if self.s_mode == 5:
            self.engine.loading_start_ms = time.ticks_ms()

        self.fx.brightness = state["brightness"]
        self.fx.set_jitter(state["jitter"])
        self.dirty = True

    def _apply_off(self):
        self.active_points = [(0, 0, 0)]
        self.c_mode = 0
        self.s_mode = 0
        self.tx.start_transition()
        self.fx.brightness = 0.0
        self.fx.set_jitter(0)
        self.dirty = True

    def check_timeout(self, now_ms):
        if self._timed_end_ms is None:
            return False
        if time.ticks_diff(now_ms, self._timed_end_ms) >= 0:
            if self._timed_restore_method == "last" and self._timed_prev_state:
                self._apply_state(self._timed_prev_state)
            else:
                self._apply_off()
            self._timed_end_ms = None
            self._timed_prev_state = None
            self._timed_restore_method = None
            return True
        return False

    def is_animating(self):
        if self.tx.active_fade_ms > 0.0:
            return True
        if self.s_mode == 0:
            return False
        if self.s_mode in (3, 5):
            return True
        return self.speed > 0

    def needs_render(self):
        if self.dirty:
            return True
        if self.is_animating():
            return True
        if self.fx.is_animating():
            return True
        return self.fx.jitter > 0

    @micropython.native
    def render(self, hardware_buffer):
        now = time.ticks_ms()
        dt_ms = time.ticks_diff(now, self._last_ms)
        if dt_ms < 0:
            dt_ms = 0
        self._last_ms = now

        start = self.start_index
        count = self.count

        if not self.is_running:
            black = (0, 0, 0)
            for i in range(count):
                hardware_buffer[start + i] = black
            return

        # 1. Get base colors from provider
        target_paint = self.colors.fill_colors(
            self.c_mode,
            self.active_points,
            count,
            self.speed,
            self._buf_target,
            dt_ms,
            self.pattern_counts,
        )
        
        # 2. Apply Fade (Linear Interpolation)
        smooth_paint = self.tx.apply(target_paint, self._buf_smooth)
        
        # 3. Apply Spatial Engine (Motion/Effects)
        frame = self.engine.apply(self.s_mode, smooth_paint, self.speed, self.arg, self._buf_frame, dt_ms)

        # 4. Write to the shared hardware buffer
        b_int = self.fx.update()
        jitter = self.fx.jitter
        if jitter == 0 and b_int >= 256:
            for i in range(count):
                hardware_buffer[start + i] = frame[i]
            return

        j = jitter
        if j < 0:
            j = 0

        if j == 0:
            for i in range(count):
                r, g, b = frame[i]
                hardware_buffer[start + i] = ((r * b_int) >> 8, (g * b_int) >> 8, (b * b_int) >> 8)
            return

        for i in range(count):
            r, g, b = frame[i]
            delta = (urandom.getrandbits(16) % (2 * j + 1)) - j
            r = 0 if r + delta < 0 else (255 if r + delta > 255 else r + delta)
            g = 0 if g + delta < 0 else (255 if g + delta > 255 else g + delta)
            b = 0 if b + delta < 0 else (255 if b + delta > 255 else b + delta)
            hardware_buffer[start + i] = ((r * b_int) >> 8, (g * b_int) >> 8, (b * b_int) >> 8)
