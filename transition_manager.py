import time
import micropython

class TransitionManager:
    def __init__(self, count):
        self.count = count
        self.fade_ms = 0 
        
        # PRE-ALLOCATION: Store current values as ints (0-255)
        self.cur_r = [0] * count
        self.cur_g = [0] * count
        self.cur_b = [0] * count
        
        self.start_r = [0] * count
        self.start_g = [0] * count
        self.start_b = [0] * count
        self.start_time = time.ticks_ms()
        self.active_fade_ms = 0

    def start_transition(self):
        """Captures the current state as the starting point for the new fade."""
        self.start_time = time.ticks_ms()
        self.active_fade_ms = int(self.fade_ms)
        
        # VITAL: Snapshot current actual values (even mid-fade) as the new starting point
        for i in range(self.count):
            self.start_r[i] = self.cur_r[i]
            self.start_g[i] = self.cur_g[i]
            self.start_b[i] = self.cur_b[i]
        
        # No logging here to keep runtime quiet

    @micropython.native
    def apply(self, target_buffer, out_buffer):
        _fade = self.active_fade_ms
        
        # If no fade is active, snap immediately to target
        if _fade <= 0:
            for i in range(self.count):
                r, g, b = target_buffer[i]
                self.cur_r[i], self.cur_g[i], self.cur_b[i] = r, g, b
                out_buffer[i] = (r, g, b)
            return out_buffer

        elapsed = time.ticks_diff(time.ticks_ms(), self.start_time)
        
        # Handle Completion
        if elapsed >= _fade:
            self.active_fade_ms = 0
            for i in range(self.count):
                r, g, b = target_buffer[i]
                self.cur_r[i], self.cur_g[i], self.cur_b[i] = r, g, b
                out_buffer[i] = (r, g, b)
            return out_buffer
        
        if elapsed < 0:
            elapsed = 0

        # LERP: Start + (Target - Start) * Progress
        # We update cur_r/g/b so the NEXT transition knows where we left off
        for i in range(self.count):
            tr, tg, tb = target_buffer[i]
            
            sr = self.start_r[i]
            sg = self.start_g[i]
            sb = self.start_b[i]

            nr = sr + ((tr - sr) * elapsed) // _fade
            ng = sg + ((tg - sg) * elapsed) // _fade
            nb = sb + ((tb - sb) * elapsed) // _fade
            
            self.cur_r[i], self.cur_g[i], self.cur_b[i] = nr, ng, nb
            out_buffer[i] = (nr, ng, nb)

        return out_buffer
