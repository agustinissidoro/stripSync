from machine import Pin
import time

def _parse_pin_entry(pin_entry):
    if pin_entry is None:
        return None
    if isinstance(pin_entry, int):
        return pin_entry
    if isinstance(pin_entry, str):
        v = pin_entry.strip().upper()
        if not v:
            return None
        if v == "LED":
            return "LED"
        if v.startswith("GPIO"):
            try:
                return int(v[4:])
            except:
                return None
        try:
            return int(v)
        except:
            return None
    return None

class StatusBlinker:
    def __init__(self, pin_entry="LED", interval_ms=1000, active_low=None):
        self.interval_ms = interval_ms
        self.last_toggle = time.ticks_ms()
        self.state = False
        self.led, self.active_low = self._init_pin(pin_entry, active_low)
        self._set(False)

    def _init_pin(self, pin_entry, active_low):
        pin = _parse_pin_entry(pin_entry)
        # Prefer Pico W "LED" alias, fall back to GPIO25 if needed
        if pin == "LED":
            if active_low is None:
                active_low = True
            try:
                return Pin("LED", Pin.OUT), active_low
            except:
                try:
                    return Pin(25, Pin.OUT), active_low
                except:
                    return None, active_low if active_low is not None else False
        if active_low is None:
            active_low = False
        try:
            return Pin(pin, Pin.OUT), active_low
        except:
            return None, active_low

    def _set(self, state):
        if self.led:
            out = not state if self.active_low else state
            self.led.value(1 if out else 0)

    def update(self):
        if time.ticks_diff(time.ticks_ms(), self.last_toggle) >= self.interval_ms:
            self.state = not self.state
            self._set(self.state)
            self.last_toggle = time.ticks_ms()

class ResetButton:
    def __init__(self, pin_entry=None, hold_ms=50, active_low=True):
        self.hold_ms = hold_ms
        self.active_low = active_low
        self.pin = self._init_pin(pin_entry)
        self.last_val = 1 if active_low else 0
        self.last_change_ms = time.ticks_ms()
        self.triggered = False

    def _init_pin(self, pin_entry):
        pin = _parse_pin_entry(pin_entry)
        if pin is None:
            return None
        pull = Pin.PULL_UP if self.active_low else Pin.PULL_DOWN
        try:
            return Pin(pin, Pin.IN, pull)
        except:
            try:
                return Pin(pin, Pin.IN)
            except:
                return None

    def update(self):
        if not self.pin:
            return False
        val = self.pin.value()
        if val != self.last_val:
            self.last_val = val
            self.last_change_ms = time.ticks_ms()
            self.triggered = False
            return False

        pressed = (val == 0) if self.active_low else (val == 1)
        if pressed and not self.triggered:
            if time.ticks_diff(time.ticks_ms(), self.last_change_ms) >= self.hold_ms:
                self.triggered = True
                return True
        return False
