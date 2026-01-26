import sys
import uselect

class CommHandler:
    def __init__(self, strip_names=[]):
        self.poll = uselect.poll()
        self.poll.register(sys.stdin, uselect.POLLIN)
        self.buffer = ""
        self.strip_names = strip_names
        self.live_mode = False 

    def update(self):
        # 1. Batch Read: Check if data is waiting
        if self.poll.poll(0):
            # Read all available characters at once
            # We loop while data is pending to empty the hardware buffer
            incoming = ""
            while self.poll.poll(0):
                chunk = sys.stdin.read(1)
                if not chunk:
                    break
                if isinstance(chunk, bytes):
                    try:
                        chunk = chunk.decode()
                    except:
                        continue
                incoming += chunk
            
            # 2. Process the batch
            # This handles cases where multiple commands might arrive at once 
            # (e.g., "color 255 0 0; speed 50;")
            packets = []
            for char in incoming:
                if char == ';':
                    raw_cmd = self.buffer.strip().lower()
                    self.buffer = ""
                    # Return all parsed commands so batch lines work as expected
                    pkt = self._parse_one(raw_cmd)
                    if pkt is not None:
                        packets.append(pkt)
                else:
                    self.buffer += char
            
            return packets if packets else None
        return None

    def _parse_one(self, raw):
        parts = raw.split()
        if not parts: return None

        if parts[0] == "live" and len(parts) > 1:
            self.live_mode = (parts[1] == "1")
            print("COMM: Live Mode", "ON" if self.live_mode else "OFF")
            return None

        target = "all"
        payload = parts
        if parts[0] in self.strip_names or parts[0] == "all":
            target = parts[0]
            payload = parts[1:]
        
        if not payload: return None
        cmd = payload[0]

        if cmd == "ping":
            print("ping")
            return (target, "CMD", "PING", False)
        if cmd == "apply":
            duration_ms = None
            restore_method = "last"
            if len(payload) > 1:
                try:
                    duration_ms = int(payload[1])
                except:
                    duration_ms = None
            if len(payload) > 2:
                rm = payload[2].lower()
                if rm in ("off", "last"):
                    restore_method = rm
            return (target, "CMD", "APPLY", False, duration_ms, restore_method)
        if cmd == "color_mode":
            if len(payload) < 2:
                return None
            mode = payload[1].lower()
            pattern = None
            if mode == "pattern" and len(payload) > 2:
                try:
                    pattern = [int(x) for x in payload[2:]]
                except:
                    pattern = None
            return (target, "SET_C_MODE", (mode, pattern), self.live_mode)
        if cmd in ["start", "stop", "reset"]:
            return (target, "CMD", cmd.upper(), False)

        prop_map = {
            "color": "SET_COLOR", "brightness": "SET_BRIGHT",
            "mode": "SET_S_MODE", "speed": "SET_SPEED",
            "fade": "SET_FADE", "jitter": "SET_JITTER",
            "direction": "SET_DIR", "load_time": "SET_LOAD_TIME"
        }

        if cmd == "test":
            try:
                val = int(payload[1])
                return (target, "CMD_TEST", val, False)
            except:
                return None

        if cmd in prop_map:
            try:
                msg_type = prop_map[cmd]
                if cmd == "color":
                    nums = [int(x) for x in payload[1:]]
                    val = [tuple(nums[i:i+3]) for i in range(0, len(nums), 3)]
                elif cmd == "brightness":
                    val = float(payload[1])
                elif cmd == "direction":
                    val = payload[1]
                else:
                    val = int(payload[1])

                if not self.live_mode:
                    print(f"Set ({target}): {cmd.upper()} -> {val}")
                return (target, msg_type, val, self.live_mode)
            except:
                return None
        return None
