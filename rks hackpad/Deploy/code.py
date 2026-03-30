import board
import digitalio
import neopixel
import time
import usb_hid
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keycode import Keycode
import displayio
import adafruit_displayio_ssd1306
from i2cdisplaybus import I2CDisplayBus
import os

class KeyScan:
    def __init__(self):
        self.rows_pins = [board.D10, board.D9, board.D8]
        self.cols_pins = [board.D0, board.D1, board.D2, board.D3]

        self.NUM_COLS = 4
        self.NUM_ROWS = 3

        self.keycode_map = {
            (0, 0): Keycode.SEVEN, (0, 1): Keycode.EIGHT, (0, 2): Keycode.NINE,
            (1, 0): Keycode.FOUR, (1, 1): Keycode.FIVE, (1, 2): Keycode.SIX,
            (2, 0): Keycode.ONE, (2, 1): Keycode.TWO, (2, 2): Keycode.THREE,
            (3, 0): Keycode.WINDOWS, (3, 1): Keycode.ZERO, (3, 2): Keycode.PERIOD
        }

        self.rows = [digitalio.DigitalInOut(p) for p in self.rows_pins]
        for r in self.rows:
            r.direction = digitalio.Direction.INPUT
            r.pull = digitalio.Pull.UP

        self.cols = [digitalio.DigitalInOut(p) for p in self.cols_pins]
        for c in self.cols:
            c.direction = digitalio.Direction.OUTPUT
            c.value = True

        self.keyboard = Keyboard(usb_hid.devices)
        self.pressed_prev = set()

    def scan(self):
        pressed = set()
        for c_idx, col in enumerate(self.cols):
            col.value = False
            for r_idx, row in enumerate(self.rows):
                if not row.value:
                    pressed.add((c_idx, r_idx))
            col.value = True
        return pressed

    def send_hid(self, pressed):
        for key in pressed - self.pressed_prev:
            try:
                self.keyboard.press(self.keycode_map[key])
            except:
                pass

        for key in self.pressed_prev - pressed:
            try:
                self.keyboard.release(self.keycode_map[key])
            except:
                pass

        self.pressed_prev = pressed


class NeoPixels:
    def __init__(self):
        self.NUM_COLS = 4
        self.NUM_ROWS = 3

        self.NUM_PIXELS = 12
        self.LED_PIN = board.D6

        self.DIM = 0.3
        self.BRIGHT = 1.0
        self.PRESS_RAMP = 0.1
        self.FADE_MAIN = 0.008
        self.FADE_NEIGH = 0.02
        self.SPREAD_DELAY = 0.01

        self.key_to_led = {
            (0, 0): 9, (0, 1): 10, (0, 2): 11,
            (1, 0): 8, (1, 1): 7, (1, 2): 6,
            (2, 0): 3, (2, 1): 4, (2, 2): 5,
            (3, 0): 2, (3, 1): 1, (3, 2): 0
        }

        self.pixels = neopixel.NeoPixel(self.LED_PIN, self.NUM_PIXELS, auto_write=False)
        self.key_state = {}
        self.neighbors = {}

        self.pixels.fill((int(150*self.DIM), int(2*self.DIM), int(255*self.DIM)))
        self.pixels.show()

    def get_neighbors(self, c, r):
        out = []
        for dc, dr in [(-1,0),(1,0),(0,-1),(0,1)]:
            nc, nr = c+dc, r+dr
            if 0 <= nc < self.NUM_COLS and 0 <= nr < self.NUM_ROWS:
                out.append((nc, nr))
        return out

    def update(self, pressed):
        now = time.monotonic()

        for key in pressed:
            if key not in self.key_state:
                self.key_state[key] = {'time': now, 'neighbors': False}

            elapsed = now - self.key_state[key]['time']
            ramp = min(elapsed / self.PRESS_RAMP, 1.0)

            idx = self.key_to_led[key]
            b = self.DIM + ramp * (self.BRIGHT - self.DIM)
            self.pixels[idx] = (int(150*b), int(2*b), int(255*b))

            if not self.key_state[key]['neighbors'] and elapsed > self.SPREAD_DELAY:
                for n in self.get_neighbors(*key):
                    self.neighbors[self.key_to_led[n]] = self.BRIGHT
                self.key_state[key]['neighbors'] = True

        for idx in list(self.neighbors):
            self.neighbors[idx] -= self.FADE_NEIGH
            if self.neighbors[idx] <= self.DIM:
                self.neighbors.pop(idx)
                self.pixels[idx] = (int(150*self.DIM), int(2*self.DIM), int(255*self.DIM))
            else:
                self.pixels[idx] = (int(150*self.neighbors[idx]), int(2*self.neighbors[idx]), int(255*self.neighbors[idx]))

        for key in list(self.key_state):
            if key not in pressed:
                idx = self.key_to_led[key]
                r = self.pixels[idx][0] / 150
                r -= self.FADE_MAIN
                if r <= self.DIM:
                    self.key_state.pop(key)
                    r = self.DIM
                self.pixels[idx] = (int(150*r), int(2*r), int(255*r))

        self.pixels.show()

class OLED:
    def __init__(self):
        displayio.release_displays()

        i2c = board.I2C()
        display_bus = I2CDisplayBus(i2c, device_address=0x3C)

        self.display = adafruit_displayio_ssd1306.SSD1306(
            display_bus,
            width=128,
            height=32
        )

        self.display.auto_refresh = True

        main_group = displayio.Group()
        self.display.root_group = main_group

        bmp_folder = "/animation_bmps"
        filenames = sorted(f for f in os.listdir(bmp_folder) if f.endswith(".bmp"))

        bitmap_files = []
        self.bitmaps = []

        for name in filenames:
            f = open(bmp_folder + "/" + name, "rb")
            bmp = displayio.OnDiskBitmap(f)
            bitmap_files.append(f)
            self.bitmaps.append(bmp)

        self.tile_grid = displayio.TileGrid(
            self.bitmaps[0],
            pixel_shader=self.bitmaps[0].pixel_shader
        )

        main_group.append(self.tile_grid)
        self.display.refresh()
        
        self.frame_index = 0
        self.total_frames = len(self.bitmaps)
        
    def update_oled(self):
        self.tile_grid.bitmap = self.bitmaps[self.frame_index]
        self.frame_index = (self.frame_index + 1) % self.total_frames

oled = OLED()
scanner = KeyScan()
leds = NeoPixels()
last_oled_time = 0


while True:
    startTime = time.monotonic()

    pressed = scanner.scan()
    scanner.send_hid(pressed)
    
    if time.monotonic() - last_oled_time >= 0.2:
        oled.update_oled()
        last_oled_time = time.monotonic()
            
    leds.update(pressed)
    
    elapsed = time.monotonic() - startTime

    if elapsed < 0.001:
        time.sleep(0.001 - elapsed)
