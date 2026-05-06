import mss
import mss.tools
from PIL import Image
import io
import threading
from PyQt6.QtCore import QObject, pyqtSignal

class ScreenCapture(QObject):
    frame_ready = pyqtSignal(bytes)
    
    def __init__(self, fps=15):
        super().__init__()
        self.fps = fps
        self.running = False
        self.thread = None
        self.quality = 50
    
    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._capture_loop)
            self.thread.daemon = True
            self.thread.start()
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
    
    def set_quality(self, quality: int):
        self.quality = max(10, min(100, quality))
    
    def set_fps(self, fps: int):
        self.fps = max(1, min(60, fps))
    
    def _capture_loop(self):
        import time
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            while self.running:
                start_time = time.time()
                
                screenshot = sct.grab(monitor)
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=self.quality)
                img_byte_arr = img_byte_arr.getvalue()
                
                self.frame_ready.emit(img_byte_arr)
                
                elapsed = time.time() - start_time
                sleep_time = max(0, 1.0 / self.fps - elapsed)
                time.sleep(sleep_time)
