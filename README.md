LED Manager (Pico / Pico W)

This firmware drives one or more NeoPixel strips on a Raspberry Pi Pico or Pico W.
Strips are segmented into named blocks that you can target over serial commands.

Config (config.json)
The config is a JSON object with optional global keys and one or more pin blocks.

Optional global keys:
- STATUS_PIN: Heartbeat LED pin. Use "LED" on Pico W, or a GPIO number/"GPIOxx".
- RESET_BUTTON: GPIO pin for a physical reset button (active LOW, internal pull-up).

Pin blocks (required):
- Each top-level key is the GPIO pin driving a physical LED strip.
- Each value is a dictionary of named blocks mapped to [start, end] indices.
- Indices are local to that physical strip.

Example:
{
  "STATUS_PIN": "LED",
  "RESET_BUTTON": "GPIO15",
  "GPIO28": {
    "front": [0, 22],
    "back": [23, 46]
  },
  "GPIO2": {
    "left": [0, 10]
  }
}

Notes:
- Strip names must be unique across all pins.
- If STATUS_PIN is omitted, it defaults to GPIO25 (Pico) / "LED" is preferred for Pico W.
- RESET_BUTTON is optional; if set, press to GND to reboot the board.

Commands and Behaviors
Commands are read from stdin (USB serial). Each command must end with a semicolon (;).
Multiple commands can be sent in one line, separated by semicolons.
Commands are case-insensitive but are lowercased internally.

Targeting
- You can prefix a command with a strip name or "all".
- Example: "front color 255 0 0;" or "all brightness 0.5;"

Live mode
- "live 1;" enables LIVE mode (immediate apply).
- "live 0;" disables LIVE mode (staged changes, apply with "apply;").

Commands (control)
- start;        Resume rendering (all strips).
- stop;         Stop rendering and clear all LEDs.
- reset;        Reinitialize config and hardware (soft reset of system state).
- apply;        Apply staged changes (when live mode is off).
  apply N METHOD; Apply staged changes for N ms, then restore.
                 METHOD: "off" (brightness to 0) or "last" (previous state).
                 If METHOD is omitted, "last" is used.
- ping;         No-op (useful for link testing).
- test N;       Lights LED index N (local index) on any strip that has it; stops animation.

Commands (properties)
- color R G B [R G B ...];
  Sets color points. Multiple triplets enable multi-color mode.
- color_mode MODE [PATTERN...];
  Sets color rendering mode: simple, gradient, blocks, pattern.
  For pattern, provide one count per color (e.g., "color_mode pattern 3 2 5;").
- brightness V; Sets brightness (float, e.g., 0.0 to 1.0).
- mode N;       Sets spatial mode.
- speed N;      Sets animation speed (int).
- fade N;       Sets fade time in ms.
- jitter N;     Sets jitter amount (int).
- direction D;  Sets direction ("right", "left", "pingpong").
- load_time N;  Sets loading/progress bar duration in ms.

Behavior details
- With live mode OFF, property commands are staged and only take effect after "apply;".
- With live mode ON, property commands take effect immediately.
- "stop;" turns off LEDs and halts rendering until "start;".
- "reset;" rebuilds all strip instances and re-reads config.json.
- Heartbeat LED toggles every 500 ms.
 - "apply N METHOD;" overrides any previous timed apply on the same strip.

Modes and Arguments
Color behavior
- color with 1 RGB triplet: solid fill across the strip.
- color with multiple triplets: uses current color_mode (defaults to gradient).

Color modes (color_mode)
- simple: solid color only (used automatically when only 1 color is set).
- gradient: interpolate between colors across the strip.
- blocks: split the strip into equal blocks per color (no interpolation).
- pattern: repeat the provided per-color counts across the strip.

Spatial modes (mode N)
- 0: Static (no motion) - shows the current colors as-is.
- 1: Single moving pixel (uses current colors buffer).
- 2: Blink full buffer (on/off). Uses internal arg (default 5) as duty.
- 3: Random sparkle (density = internal arg, default 5).
- 4: Rotate buffer (scrolls colors across the strip).
- 5: Loading/progress bar (uses load_time for duration).

Arguments
- brightness V: float 0.0-1.0 or int 0-255 (both accepted).
- speed N: time in ms per tick step (lower = faster); 0 stops animation.
- fade N: color transition time in ms.
- jitter N: per-pixel random jitter (0 = off).
- direction D: "right", "left", or "pingpong" (anything else acts as pingpong).
- load_time N: loading bar duration in ms (mode 5 only).

Hardware reset button
If RESET_BUTTON is set, the board reboots when the button is held LOW for ~50 ms.
This resets I/O and forces USB serial to re-enumerate.
