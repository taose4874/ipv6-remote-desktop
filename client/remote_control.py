import threading
from pynput import mouse, keyboard
from PyQt6.QtCore import QObject, pyqtSignal

class RemoteController(QObject):
    def __init__(self):
        super().__init__()
        self.mouse_controller = mouse.Controller()
        self.keyboard_controller = keyboard.Controller()
        self.input_callback = None
    
    def set_input_callback(self, callback):
        self.input_callback = callback
    
    def handle_mouse_event(self, x: int, y: int, button: str, pressed: bool):
        try:
            self.mouse_controller.position = (x, y)
            if button == 'left':
                btn = mouse.Button.left
            elif button == 'right':
                btn = mouse.Button.right
            elif button == 'middle':
                btn = mouse.Button.middle
            else:
                return
            
            if pressed:
                self.mouse_controller.press(btn)
            else:
                self.mouse_controller.release(btn)
        except:
            pass
    
    def handle_keyboard_event(self, key: str, pressed: bool):
        try:
            if key.startswith('Key.'):
                key_name = key.split('.')[1]
                key_obj = getattr(keyboard.Key, key_name, None)
                if key_obj:
                    if pressed:
                        self.keyboard_controller.press(key_obj)
                    else:
                        self.keyboard_controller.release(key_obj)
            else:
                if len(key) == 1:
                    if pressed:
                        self.keyboard_controller.press(key)
                    else:
                        self.keyboard_controller.release(key)
        except:
            pass
    
    def start_input_monitoring(self):
        mouse_listener = mouse.Listener(
            on_click=self._on_mouse_click,
            on_move=self._on_mouse_move
        )
        keyboard_listener = keyboard.Listener(
            on_press=self._on_key_press,
            on_release=self._on_key_release
        )
        mouse_listener.start()
        keyboard_listener.start()
        return mouse_listener, keyboard_listener
    
    def _on_mouse_move(self, x, y):
        if self.input_callback:
            self.input_callback('mouse_move', x=x, y=y)
    
    def _on_mouse_click(self, x, y, button, pressed):
        if self.input_callback:
            btn_name = button.name if hasattr(button, 'name') else str(button)
            self.input_callback('mouse_click', x=x, y=y, button=btn_name, pressed=pressed)
    
    def _on_key_press(self, key):
        if self.input_callback:
            key_str = str(key)
            self.input_callback('key_press', key=key_str, pressed=True)
    
    def _on_key_release(self, key):
        if self.input_callback:
            key_str = str(key)
            self.input_callback('key_press', key=key_str, pressed=False)
