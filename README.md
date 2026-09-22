LED Manager (Pico / Pico W)

MicroPython firmware that drives one or more NeoPixel strips from a Raspberry Pi
Pico or Pico W. Each physical strip is segmented into named blocks that can be
targeted independently over USB serial.

The board is overclocked to 250 MHz at boot (main.py).


Files
- main.py              Boot, config load, hardware init, main render loop.
- comm_handler.py      Serial command parser (text mode).
- pixel_map.py         Binary frame receiver (pixel map / DMX).
- strip_instance.py    Per-strip state, staging, apply, render pipeline.
- color_provider.py    Color fill modes (solid/gradient/blocks/pattern).
- spatial_engine.py    Spatial/motion modes.
- transition_manager.py Color fading (LERP).
- post_process.py      Brightness and jitter.
- status.py            Heartbeat LED and hardware reset button.
- wipe.py              Destructive utility — see "Utilities" at the end.


Config (config.json)

A JSON object with optional global keys and one or more pin blocks.

Optional global keys
- STATUS_PIN    Heartbeat LED pin. "LED" (Pico W onboard), a GPIO number, or
                "GPIOxx". Default: "LED", which falls back to GPIO25 if the
                "LED" alias is unavailable.
- RESET_BUTTON  GPIO pin for a physical reset button. Default: none (disabled).

Pin blocks
- Every other top-level key is a GPIO pin driving one physical LED strip.
  Accepted forms: "GPIO28", "28", or the number 28.
- Each value is an object mapping a block name to [start, end] LED indices.
- Indices are inclusive and local to that physical strip.
- The physical strip length is derived from the highest end index on that pin
  (max end + 1). Index gaps are allowed but still consume LEDs.

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

Notes
- Strip names must be unique across all pins.
- Strip names must be lowercase. Incoming serial commands are lowercased before
  parsing, so an uppercase name in config.json can never be targeted.
- Avoid naming a strip after a command keyword (color, mode, apply, config, ...).
- If config.json is missing or unreadable, the firmware falls back to
  {"strip1": [0, 46]} on GPIO28.
- Legacy flat format is still accepted: a top-level object of name -> [start, end]
  with no pin keys is mapped onto GPIO28.
- An unparseable pin key falls back to GPIO28.


Serial interface

Commands are read from stdin (USB serial). Framing rules:
- Every command must end with a semicolon (;).
- Multiple commands may be sent on one line: "color 255 0 0; speed 50;"
- Input is lowercased and whitespace-trimmed before parsing.
- Text after the last semicolon stays buffered until its terminator arrives.
- Malformed commands are silently ignored.


Targeting

Prefix a command with a strip name to target one block, or with "all" (or no
prefix at all) to target every block.

  front color 255 0 0;
  all brightness 0.5;
  brightness 0.5;          same as "all brightness 0.5;"

The commands live, macro, test, flashall, config and save are global — any target prefix
on them is ignored.


Live mode vs staged mode

- live 1;   LIVE mode. Property commands take effect immediately.
- live 0;   STAGED mode (default at boot). Property commands are buffered and
            only take effect when you send "apply;".

Live mode is a global setting, not per-strip.

In LIVE mode, "fade N;" applies immediately, so the next color command uses the
new fade duration. Brightness changes also fade using the current fade value.


Commands (control)

- start;          Resume rendering on all strips.
- stop;           Halt rendering and clear all LEDs to black.
- reset;          Rebuild all strip instances and re-initialize hardware from the
                  current runtime config. This does NOT re-read config.json —
                  after boot the in-memory config is the source of truth.
- apply;          Commit staged changes (STAGED mode only).
- apply N METHOD; Commit staged changes for N ms, then revert.
                  METHOD "last" (default): restore the state captured just
                  before this apply ran.
                  METHOD "off": go black with brightness 0 (does not restore).
                  A new timed apply replaces any pending one on the same strip.
- ping;           Echoes the line "ping" back over serial. Useful for link tests.
- test;           Flashes the on-board status LED fast (10 Hz) for 3 seconds,
                  then returns it to the normal 1 Hz status blink. Echoes the
                  line "test". Nothing else is touched: the strips keep
                  rendering and no state changes, so it is safe to send at any
                  time as a connection check.
- test N;         Lights physical LED index N white (255,255,255) on every pin
                  long enough to have it, and clears the rest of that pin.
                  N is a raw hardware index on the pin, not a strip-local index.
                  This halts rendering — send "start;" to resume.
- flashall;       Blinks every declared pixel on every pin white at 2 Hz for
                  3 seconds, then restores the previous picture and resumes
                  rendering on its own. Echoes the line "flashall".
- flashall N;     Same, for N milliseconds. A non-integer or N <= 0 falls back
                  to 3000.
                  flashall is global: a target prefix is ignored, it always
                  covers every pin. It writes straight to the hardware and
                  pauses rendering while it runs, so no strip property, staged
                  value or timed apply is touched — but any "pixels" override
                  is released, so overridden strips repaint from the pipeline
                  when the flash ends. A "reset;" or "config" re-init cancels a
                  flash in progress.


Commands (runtime config)

These mutate the in-memory config and immediately re-initialize the hardware.
Nothing is written to flash until you send "save;".

- config PINNAME STRIPNAME LOW-HIGH [STRIPNAME LOW-HIGH ...];
    Defines all strips on PINNAME in a single message, replacing that pin's
    previous mapping entirely. One pin per message.
    Ranges are written LOW-HIGH with a hyphen and no spaces.
    Example: config GPIO28 front 0-22 back 23-46;

- config PINNAME remove;
    Removes that pin's strip handler entirely.
    Example: config GPIO28 remove;

- config clearall;
    Wipes the whole runtime config — every pin, every strip, and the STATUS_PIN
    and RESET_BUTTON entries. No strips remain until you configure some.

- save;
    Writes the current runtime config to config.json. Prints "Config saved." on
    success or "Save failed: <error>" on failure.

STATUS_PIN and RESET_BUTTON can only be set by editing config.json; there is no
serial command to change them.


Commands (properties)

- color R G B [R G B ...];
    Sets the color points. One triplet is a solid fill; multiple triplets engage
    the current color mode. Values must come in complete triplets.
- color_mode MODE [COUNT ...];
    MODE is simple, gradient, blocks or pattern.
    For pattern, supply one repeat count per color: color_mode pattern 3 2 5;
- brightness V;   0.0-1.0 as a float, or 0-255 as an integer.
- mode N;         Spatial mode (see below).
- speed N;        Milliseconds per animation tick. Lower is faster; 0 freezes motion.
- fade N;         Color transition time in ms. 0 snaps instantly.
- jitter N;       Per-pixel random brightness jitter in the range [-N, +N]. 0 is off.
- direction D;    right, left or pingpong. Any other value behaves as pingpong.
- load_time N;    Duration of the loading bar (spatial mode 5) in ms.


Direct pixel writes

- pixels R G B [R G B ...];
    Writes raw RGB values straight to the hardware, bypassing the whole render
    pipeline. The value count must be a non-zero multiple of 3.

    With a strip target, pixels are written from that strip's start index and
    clamped to its length: "front pixels 255 0 0 0 255 0;"
    With "all" (or no prefix), pixels are written from physical index 0 on every
    pin and clamped to each pin's length.

    Affected strips stop being rendered by the animation pipeline until the next
    property command or "apply;" on that strip releases the override.


Binary macro modes

- macro 0;   Text mode (default).
- macro 1;   Binary pixel map mode.
- macro 2;   Binary DMX mode.

While macro mode is 1 or 2 the text parser is bypassed entirely — no text
command is read, including "macro 0;". The only way back to text mode is the
binary exit frame below (or a hardware reset). On exit the firmware prints
"Binary mode: exited".

All frames start with the magic byte 0xAD.

Pixel map frame (macro 1)
  [0xAD] [pin_idx] [n_lo] [n_hi] [R G B] x n
  pin_idx  index into the pin list sorted by ascending GPIO number (0 = first).
  n        16-bit little-endian pixel count.
  Pixels are written from physical index 0 on that pin and clamped to its length.

DMX frame (macro 2)
  [0xAD] [universe] [0x00] [0x00] [512 channel bytes]
  universe maps to pin_idx the same way (universe 0 = first pin).
  Channels map as pixel[i] = (ch[i*3], ch[i*3+1], ch[i*3+2]), 170 pixels total.

Exit frame (both modes)
  [0xAD] [0xFF] [0x00] [0x00]

Frames with a zero or oversized payload are discarded and the parser re-syncs on
the next magic byte.


Color modes (color_mode)

- simple    Solid color. Used automatically whenever only one color is set,
            regardless of the configured color mode.
- gradient  Interpolate between consecutive color points across the strip.
            Default at boot.
- blocks    Split the strip into equal blocks, one per color, no interpolation.
            Leftover pixels go to the last color.
- pattern   Repeat the supplied per-color counts across the strip. If the number
            of counts does not match the number of colors, this falls back to
            blocks.


Spatial modes (mode N)

- 0  Static. Shows the color buffer as-is. Default at boot.
- 1  Single moving pixel, taking its color from the buffer at that position.
- 2  Blink the whole buffer on and off.
- 3  Random sparkle.
- 4  Rotate the buffer across the strip.
- 5  Loading bar, filling over load_time ms. Direction sets the origin: right
     fills from the first pixel, left from the last, pingpong from the center.
     Once full it stays full — re-send "mode 5;" or "load_time N;" to restart.

Modes 1, 4 and 5 follow the direction setting. Modes 2 and 3 use a fixed
internal argument of 5 (blink duty out of 10, sparkle density out of 256); there
is no serial command to change it.


Defaults at boot

  color        0 0 0 (black)     color_mode   gradient
  mode         0 (static)        direction    right
  speed        10 ms             fade         0 ms
  brightness   1.0               jitter       0
  load_time    1000 ms           live mode    off (staged)
  macro mode   0 (text)          rendering    running


Serial output

The firmware prints on stdout, so a host-side parser should tolerate these lines:
- "--- LedManager: System Initializing ---", "Mapped: GPIOxx -> name",
  "System Ready." on every boot and re-initialization.
- "Set (target): PROPERTY -> value" after each property command in STAGED mode.
  LIVE mode is silent.
- "COMM: Live Mode ON|OFF" and "COMM: Macro Mode N" on mode changes.
- "ping" in response to "ping;".
- "test" in response to "test;".
- "flashall" in response to "flashall;".
- "Config saved." or "Save failed: <error>" after "save;".
- "Binary mode: exited" when leaving a macro mode.
- "MAIN LOOP EXCEPTION: <error>" plus a traceback if the loop throws; the loop
  backs off 200 ms and continues.


Status LED and reset button

The heartbeat LED on STATUS_PIN toggles every 1000 ms. The "LED" alias is driven
active-low; a numbered GPIO is driven active-high.

If RESET_BUTTON is set, the pin is configured as an input with an internal
pull-up and the board reboots when it is held to GND for ~50 ms. This resets I/O
and forces USB serial to re-enumerate.


Boot behavior

Each physical strip flashes dim white (50,50,50) for 100 ms and then goes black
as it is initialized. Seeing that flash confirms the pin and length were picked
up from the config.


Utilities

wipe.py deletes every file and folder on the board's filesystem, including the
firmware itself. It runs on import — there is no function to call and no
confirmation prompt. Do not copy it to the board unless that is exactly what you
want.
