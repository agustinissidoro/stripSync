import sys
import uselect

class CommHandler:
    def __init__(self, strip_names=[]):
        self.poll = uselect.poll()
        self.poll.register(sys.stdin, uselect.POLLIN)
        self.buffer = ""
        self.strip_names = strip_names
        self.live_mode = False
        self.macro_mode = 0  # 0=text, 1=pixel_map binary, 2=DMX binary

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

        if parts[0] == "macro":
            try:
                mode = int(parts[1]) if len(parts) > 1 else 0
                self.macro_mode = max(0, min(2, mode))
                print("COMM: Macro Mode", self.macro_mode)
            except:
                pass
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
        if cmd in ["start", "stop", "reset", "save"]:
            return (target, "CMD", cmd.upper(), False)

        if cmd == "config":
            # config clearall               — wipe entire runtime config
            # config GPIO28 remove          — remove a pin's strip handler entirely
            # config GPIO28 strip1 0-46 [strip2 47-90 ...]  — (re)define all strips on a pin
            #   (one message covers one pin; sending it again replaces that pin's whole mapping)
            try:
                if len(payload) < 2:
                    return None
                if payload[1] == "clearall":
                    return (target, "CMD_CONFIG_CLEARALL", None, False)

                pin = payload[1].upper()  # e.g. "GPIO28"

                if len(payload) == 3 and payload[2] == "remove":
                    return (target, "CMD_CONFIG_REMOVE", pin, False)

                rest = payload[2:]
                if len(rest) < 2 or len(rest) % 2 != 0:
                    return None
                blocks = {}
                for i in range(0, len(rest), 2):
                    name = rest[i]
                    rng = rest[i + 1]
                    if '-' not in rng:
                        return None
                    lo_str, hi_str = rng.split('-', 1)
                    blocks[name] = [int(lo_str), int(hi_str)]
                if not blocks:
                    return None
                return (target, "CMD_CONFIG", (pin, blocks), False)
            except:
                return None

        prop_map = {
            "color": "SET_COLOR", "brightness": "SET_BRIGHT",
            "mode": "SET_S_MODE", "speed": "SET_SPEED",
            "fade": "SET_FADE", "jitter": "SET_JITTER",
            "direction": "SET_DIR", "load_time": "SET_LOAD_TIME"
        }

        if cmd == "test":
            # "test;" alone -> flash the on-board status LED for 3s (link check).
            # "test N;"     -> light physical LED index N on every pin.
            if len(payload) < 2:
                return (target, "CMD_TEST", None, False)
            try:
                val = int(payload[1])
                return (target, "CMD_TEST", val, False)
            except:
                return None

        if cmd == "flashall":
            # "flashall;" / "flashall N;" -> blink every declared pixel on every
            # pin for N ms (default 3000). Always global: target prefix ignored.
            duration_ms = 3000
            if len(payload) > 1:
                try:
                    duration_ms = int(payload[1])
                except:
                    duration_ms = 3000
            if duration_ms <= 0:
                duration_ms = 3000
            return ("all", "CMD_FLASH_ALL", duration_ms, False)

        if cmd == "pixels":
            try:
                nums = [int(x) for x in payload[1:]]
                if len(nums) % 3 != 0 or len(nums) == 0:
                    return None
                return (target, "PIXELS", nums, True)  # always applied live, bypasses pipeline
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
