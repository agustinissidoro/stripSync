import machine, neopixel, time, json, gc, sys
import micropython
from comm_handler import CommHandler
from strip_instance import StripInstance
from status import StatusBlinker, ResetButton
from pixel_map import PixelMapReceiver

# Set frequency immediately before any I/O initialization
machine.freq(250000000)
#print(f'Running at {machine.freq()} Hz')

# Configuration
DEFAULT_STRIP_PIN = 28
DEFAULT_STATUS_PIN = "LED"
DEFAULT_RESET_BUTTON_PIN = None

# Globals
strips = {}
strip_groups = {}
physical_strips = {}
strip_to_pin = {}
comm = None
pxr = None
_runtime_config = None  # live config dict; loaded from file once, mutated by 'config' command
TOTAL_LEDS = 0
TOTAL_LEDS_BY_PIN = {}
is_running = True
status = None
reset_button = None

def _parse_pin_key(pin_key):
    if isinstance(pin_key, int):
        return pin_key
    if isinstance(pin_key, str):
        if pin_key.upper() == "LED":
            return "LED"
        if pin_key.startswith("GPIO"):
            try:
                return int(pin_key[4:])
            except:
                return DEFAULT_STRIP_PIN
        try:
            return int(pin_key)
        except:
            return DEFAULT_STRIP_PIN
    return DEFAULT_STRIP_PIN

def initialize_system():
    global strips, strip_groups, physical_strips, strip_to_pin, TOTAL_LEDS, TOTAL_LEDS_BY_PIN, comm, pxr, is_running, status, reset_button, _runtime_config
    print("\n--- LedManager: System Initializing ---")

    # Load from file only on first boot; afterwards _runtime_config is the source of truth
    if _runtime_config is None:
        try:
            with open('config.json', 'r') as f:
                _runtime_config = json.load(f)
        except:
            _runtime_config = {"strip1": [0, 46]}

    # Work on a shallow copy so STATUS_PIN / RESET_BUTTON deletions don't mutate _runtime_config
    strip_config = dict(_runtime_config)

    # Optional status pin (blink LED) and reset button
    status_pin = DEFAULT_STATUS_PIN
    reset_pin = DEFAULT_RESET_BUTTON_PIN
    if isinstance(strip_config, dict) and "STATUS_PIN" in strip_config:
        status_pin = strip_config["STATUS_PIN"]
        del strip_config["STATUS_PIN"]
    if isinstance(strip_config, dict) and "RESET_BUTTON" in strip_config:
        reset_pin = strip_config["RESET_BUTTON"]
        del strip_config["RESET_BUTTON"]

    # Support new config format: { "GPIO28": { "front": [0, 22], ... }, "GPIO15": {...} }
    if strip_config and isinstance(next(iter(strip_config.values())), dict):
        pin_config = strip_config
    else:
        pin_config = {DEFAULT_STRIP_PIN: strip_config}

    # Rebuild Instances + Hardware
    strips = {}
    strip_groups = {}
    physical_strips = {}
    TOTAL_LEDS_BY_PIN = {}
    TOTAL_LEDS = 0

    for pin_key, blocks in pin_config.items():
        pin_num = _parse_pin_key(pin_key)
        if not isinstance(blocks, dict):
            continue

        max_idx = 0
        for bounds in blocks.values():
            if bounds[1] > max_idx: max_idx = bounds[1]
        total_leds = max_idx + 1
        TOTAL_LEDS_BY_PIN[pin_num] = total_leds
        if total_leds > TOTAL_LEDS: TOTAL_LEDS = total_leds

        # Hardware Init with RESTORED BLINK
        physical_strips[pin_num] = neopixel.NeoPixel(machine.Pin(pin_num), total_leds)
        hw = physical_strips[pin_num]
        hw.fill((50, 50, 50))
        hw.write()
        time.sleep(0.1)
        hw.fill((0, 0, 0))
        hw.write()

        strip_groups[pin_num] = []
        for name, bounds in blocks.items():
            count = (bounds[1] - bounds[0]) + 1
            strips[name] = StripInstance(name, count, bounds[0])
            strip_groups[pin_num].append(strips[name])
            print(f"Mapped: GPIO{pin_num} -> {name}")
    
    # Build reverse map: strip_name -> pin_num (used for PIXELS command routing)
    strip_to_pin = {}
    for pin_num, group in strip_groups.items():
        for s in group:
            strip_to_pin[s.name] = pin_num

    comm = CommHandler(strip_names=list(strips.keys()))
    pxr = PixelMapReceiver(physical_strips, sorted(physical_strips.keys()))
    status = StatusBlinker(status_pin, interval_ms=1000)
    reset_button = ResetButton(reset_pin, hold_ms=50, active_low=True)
    is_running = True
    gc.collect()
    print("System Ready.")

initialize_system()
_strips_vals = strips.values()

while True:
    try:
        if status:
            status.update()
        if reset_button and reset_button.update():
            machine.reset()

        # --- MACRO MODE BRANCH ---
        macro = comm.macro_mode
        if macro > 0:
            # Binary mode: pixel map (1) or DMX (2)
            # Bypass the entire render pipeline — raw bytes go straight to hardware.
            pxr.update(macro)
            if pxr.exit_requested:
                pxr.exit_requested = False
                comm.macro_mode = 0
                print("Binary mode: exited")
            continue

        # --- TEXT MODE (macro 0) — original flow, unchanged ---
        packets = comm.update()
        frame_dirty = False
        render_all = False

        if packets:
            for packet in packets:
                target, msg_type, val, is_live = packet[:4]

                # --- COMMAND HANDLING ---
                if msg_type == "CMD":
                    if val == "RESET":
                        initialize_system()
                        _strips_vals = strips.values()
                        frame_dirty = True
                        render_all = True
                        continue
                    elif val == "PING":
                        pass
                    elif val == "START":
                        is_running = True
                        render_all = True
                        for s in _strips_vals:
                            s.dirty = True
                    elif val == "STOP":
                        is_running = False
                        for hw in physical_strips.values():
                            hw.fill((0, 0, 0))
                            hw.write()
                        frame_dirty = False
                        render_all = False
                    elif val == "APPLY":
                        targets = _strips_vals if target == "all" else [strips[target]]
                        duration_ms = packet[4] if len(packet) > 4 else None
                        restore_method = packet[5] if len(packet) > 5 else "last"
                        for s in targets:
                            s.apply(duration_ms, restore_method)
                        frame_dirty = True
                        render_all = True
                    elif val == "SAVE":
                        try:
                            with open('config.json', 'w') as f:
                                json.dump(_runtime_config, f)
                            print("Config saved.")
                        except Exception as e:
                            print("Save failed:", e)
                elif msg_type == "CMD_CONFIG":
                    # config GPIO28 strip1 0 46 — update runtime config and re-init
                    pin_key, name, start, end = val
                    if pin_key not in _runtime_config or not isinstance(_runtime_config[pin_key], dict):
                        _runtime_config[pin_key] = {}
                    _runtime_config[pin_key][name] = [start, end]
                    initialize_system()
                    _strips_vals = strips.values()
                    frame_dirty = True
                    render_all = True
                    continue
                elif msg_type == "CMD_TEST":
                    idx = val
                    is_running = False
                    for pin_num, hw in physical_strips.items():
                        total = TOTAL_LEDS_BY_PIN[pin_num]
                        if idx < 0 or idx >= total:
                            continue
                        hw.fill((0, 0, 0))
                        hw[idx] = (255, 255, 255)
                        hw.write()
                    frame_dirty = False
                    render_all = False

                elif msg_type == "PIXELS":
                    # Direct pixel write — bypasses all pipeline stages (text-mode pixel mapping).
                    # Sets pixel_override on targeted strips so the render pipeline doesn't clobber us.
                    nums = val
                    n_px = len(nums) // 3
                    if target == "all":
                        for pin_num, hw in physical_strips.items():
                            n = min(n_px, TOTAL_LEDS_BY_PIN[pin_num])
                            for i in range(n):
                                j = i * 3
                                hw[i] = (nums[j], nums[j + 1], nums[j + 2])
                            hw.write()
                        for s in _strips_vals:
                            s.pixel_override = True
                    else:
                        s = strips.get(target)
                        if s:
                            pin_num = strip_to_pin.get(target)
                            hw = physical_strips.get(pin_num)
                            if hw:
                                n = min(n_px, s.count)
                                off = s.start_index
                                for i in range(n):
                                    j = i * 3
                                    hw[off + i] = (nums[j], nums[j + 1], nums[j + 2])
                                hw.write()
                            s.pixel_override = True
                    frame_dirty = False

                # --- STRIP PROPERTY ROUTING ---
                else:
                    targets = _strips_vals if target == "all" else [strips[target]]
                    for s in targets:
                        s.set_property(msg_type, val, live=is_live)
                    frame_dirty = True

        # Timed apply expiration
        now_ms = time.ticks_ms()
        for s in _strips_vals:
            if s.check_timeout(now_ms):
                frame_dirty = True
                render_all = True

        # Standard Animation Render
        if is_running:
            for pin_num, group in strip_groups.items():
                did_render = False
                hw = physical_strips[pin_num]
                for s in group:
                    if render_all or s.needs_render():
                        s.render(hw)
                        if not s.needs_render():
                            s.dirty = False
                        did_render = True

                if did_render:
                    hw.write()

        time.sleep_ms(1)
    except Exception as e:
        print("MAIN LOOP EXCEPTION:", e)
        try:
            sys.print_exception(e)
        except:
            pass
        time.sleep_ms(200)
