import math

class ColorProvider:
    def __init__(self):
        self.tick = 0

    def _lerp_color(self, c1, c2, t):
        """Linearly interpolates between color c1 and c2 by factor t (0.0 to 1.0)."""
        return (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t)
        )

    def fill_colors(self, mode, color_data, count, speed_ms, out, dt_ms, pattern_counts=None):
        """
        Fills 'out' with per-LED (R,G,B) tuples. Returns out.
        color_data is expected to be a list of (R,G,B) tuples
        for modes that support multiple points.
        """
        if speed_ms and speed_ms > 0 and dt_ms > 0:
            self.tick += dt_ms / speed_ms

        if not color_data:
            color_data = ((0, 0, 0),)

        # Mode 0: Solid (Uses first color in list)
        if mode == 0:
            c = color_data[0]
            for i in range(count):
                out[i] = c
            return out

        # Mode 1: Multi-Point Gradient
        elif mode == 1:
            if len(color_data) < 2:
                c = color_data[0]
                for i in range(count):
                    out[i] = c
                return out

            num_segments = len(color_data) - 1

            # Stable segment mapping: segment = floor(i * num_segments / count)
            # local_t = fractional part of (i * num_segments / count)
            for i in range(count):
                x = (i * num_segments) / count  # 0..num_segments
                segment = int(x)
                if segment >= num_segments:
                    segment = num_segments - 1
                    local_t = 1.0
                else:
                    local_t = x - segment

                out[i] = self._lerp_color(color_data[segment], color_data[segment + 1], local_t)

            return out

        # Mode 2: Blocks (no interpolation, equal segments)
        elif mode == 2:
            n = len(color_data)
            if n == 0:
                c = (0, 0, 0)
                for i in range(count):
                    out[i] = c
                return out
            block_len = count // n
            if block_len <= 0:
                for i in range(count):
                    idx = i if i < n else (n - 1)
                    out[i] = color_data[idx]
                return out
            for i in range(count):
                idx = i // block_len
                if idx >= n:
                    idx = n - 1
                out[i] = color_data[idx]
            return out

        # Mode 3: Pattern (repeat counts per color)
        elif mode == 3:
            n = len(color_data)
            if n == 0:
                c = (0, 0, 0)
                for i in range(count):
                    out[i] = c
                return out
            if not pattern_counts or len(pattern_counts) != n:
                # Fallback to blocks
                block_len = count // n
                if block_len <= 0:
                    for i in range(count):
                        idx = i if i < n else (n - 1)
                        out[i] = color_data[idx]
                    return out
                for i in range(count):
                    idx = i // block_len
                    if idx >= n:
                        idx = n - 1
                    out[i] = color_data[idx]
                return out
            counts = [c if c > 0 else 0 for c in pattern_counts]
            total = 0
            for c in counts:
                total += c
            if total <= 0:
                c = color_data[0]
                for i in range(count):
                    out[i] = c
                return out
            # Build prefix sums for lookup
            prefix = []
            running = 0
            for c in counts:
                running += c
                prefix.append(running)
            for i in range(count):
                pos = i % total
                idx = 0
                while idx < n and pos >= prefix[idx]:
                    idx += 1
                if idx >= n:
                    idx = n - 1
                out[i] = color_data[idx]
            return out

        c = color_data[0]
        for i in range(count):
            out[i] = c
        return out
