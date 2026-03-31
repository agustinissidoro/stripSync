import os
import sys
import uselect
import micropython

class PixelMapReceiver:
    """
    Binary frame receiver for pixel mapping (macro 1) and DMX (macro 2).
    Bypasses the entire render pipeline — writes raw RGB directly to neopixel hardware.

    Pixel Map Protocol (macro 1):
      [0xAD] [pin_idx: 1B] [n_pixels_lo: 1B] [n_pixels_hi: 1B] [R G B × n_pixels]
      pin_idx: index into the sorted pin list from config (0 = first pin)
      n_pixels: 16-bit little-endian count of pixels in this frame

    DMX Protocol (macro 2):
      [0xAD] [universe: 1B] [0x00] [0x00] [512 bytes of channel data]
      Pixel mapping: pixel[i].R = ch[i*3], .G = ch[i*3+1], .B = ch[i*3+2]
      universe maps to pin_idx (universe 0 = first pin)
    """

    MAGIC = 0xAD

    def __init__(self, physical_strips, pin_list):
        # physical_strips: {pin_num: neopixel_obj}
        # pin_list: sorted list of pin nums (index 0 = first strip)
        self._hw = physical_strips
        self._pins = pin_list

        self._poll = uselect.poll()
        self._poll.register(sys.stdin, uselect.POLLIN)

        # Parser state machine
        self._state = 0             # 0=wait_magic, 1=header, 2=data
        self._header = bytearray(3)
        self._hpos = 0
        self._pin_idx = 0
        self._n_pixels = 0
        self._data_len = 0
        self._buf = bytearray(512 * 3)  # largest possible frame (DMX = 512 ch = 170 px × 3)
        self._dpos = 0
        self.exit_requested = False  # set True when exit frame [0xAD 0xFF 0x00 0x00] received

    def update(self, mode):
        """
        Poll stdin and process binary frames.
        mode: 1 = pixel map, 2 = DMX
        Returns number of complete frames written to hardware this call.
        """
        if not self._poll.poll(0):
            return 0

        frames = 0
        while self._poll.poll(0):
            try:
                chunk = os.read(0, 512)  # read up to 512 bytes at once
            except:
                break
            if not chunk:
                break
            for b in chunk:
                if self._step(b, mode):
                    frames += 1
        return frames

    def _step(self, b, mode):
        """Process one byte. Returns True when a complete frame was written."""
        s = self._state

        if s == 0:  # wait for magic byte
            if b == self.MAGIC:
                self._state = 1
                self._hpos = 0

        elif s == 1:  # collect 3 header bytes
            self._header[self._hpos] = b
            self._hpos += 1
            if self._hpos == 3:
                self._pin_idx = self._header[0]
                if self._pin_idx == 0xFF:
                    # Exit binary mode signal — [0xAD 0xFF 0x00 0x00]
                    self.exit_requested = True
                    self._state = 0
                    return False
                if mode == 2:
                    # DMX: always 512 bytes regardless of header[1]/[2]
                    self._n_pixels = 170
                    self._data_len = 512
                else:
                    # Pixel map: explicit pixel count in header[1..2] LE
                    self._n_pixels = self._header[1] | (self._header[2] << 8)
                    self._data_len = self._n_pixels * 3
                if self._data_len == 0 or self._data_len > len(self._buf):
                    self._state = 0  # invalid frame — re-sync
                else:
                    self._dpos = 0
                    self._state = 2

        elif s == 2:  # collect data bytes
            self._buf[self._dpos] = b
            self._dpos += 1
            if self._dpos >= self._data_len:
                self._write_frame()
                self._state = 0
                return True

        return False

    @micropython.native
    def _write_frame(self):
        """Write buffered pixel data directly to neopixel hardware. No pipeline."""
        if self._pin_idx >= len(self._pins):
            return
        hw = self._hw.get(self._pins[self._pin_idx])
        if hw is None:
            return

        buf = self._buf
        n = self._n_pixels
        hw_len = len(hw)
        if n > hw_len:
            n = hw_len

        for i in range(n):
            j = i * 3
            hw[i] = (buf[j], buf[j + 1], buf[j + 2])
        hw.write()
