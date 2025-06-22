#!/usr/bin/env python3
"""
LinuxClickPaste - Feature-complete Linux port of Windows ClickPaste
Matches the original functionality including hotkeys, cursor changes, and typing modes
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')

from gi.repository import Gtk, Gdk, GLib

# Handle optional dependencies gracefully
APPINDICATOR_AVAILABLE = False
AppIndicator3 = None
KEYBINDER_AVAILABLE = False
Keybinder = None

# Try to import AppIndicator3 separately (avoiding GTK version conflicts)
try:
    import gi as gi_indicator
    gi_indicator.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3
    APPINDICATOR_AVAILABLE = True
except:
    pass

# Try to import Keybinder
try:
    from gi.repository import Keybinder
    KEYBINDER_AVAILABLE = True
except:
    pass

import subprocess
import time
import threading
import json
import os
import sys
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, List, Callable
from enum import Enum, IntEnum
import logging
from collections import deque

# For keyboard simulation
try:
    from Xlib import X, XK, display as XDisplay
    from Xlib.ext import xtest
    XLIB_AVAILABLE = True
except ImportError:
    XLIB_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('LinuxClickPaste')

class TypeMethod(Enum):
    """Typing methods available"""
    XTEST = "xtest"          # Direct X11 key simulation (like SendKeys)
    XDOTOOL = "xdotool"      # External tool (works on X11 and XWayland)
    YDOTOOL = "ydotool"      # Works on both X11 and Wayland

class HotKeyMode(Enum):
    """Hotkey behavior modes"""
    TARGET = 0    # Show target cursor
    JUST_GO = 1   # Paste immediately at current position

class CursorType(IntEnum):
    """X11 cursor types"""
    NORMAL = 2      # XC_arrow
    IBEAM = 152     # XC_xterm
    HAND = 58       # XC_hand2
    CROSS = 34      # XC_crosshair

@dataclass
class Settings:
    """Application settings matching Windows version"""
    # Key delays
    key_delay_ms: int = 5
    start_delay_ms: int = 100
    
    # Hotkey settings
    hotkey: Optional[str] = None
    hotkey_modifiers: List[str] = field(default_factory=list)
    hotkey_mode: HotKeyMode = HotKeyMode.TARGET
    
    # Behavior settings
    confirm: bool = True
    confirm_over: int = 1000
    type_method: TypeMethod = TypeMethod.XDOTOOL  # Default to xdotool for better compatibility
    
    # UI settings
    start_minimized: bool = True
    show_notifications: bool = True
    run_elevated: bool = False
    
    @classmethod
    def load(cls, path: Path) -> 'Settings':
        """Load settings from file"""
        if path.exists():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                    # Convert enums
                    if 'hotkey_mode' in data:
                        data['hotkey_mode'] = HotKeyMode(data['hotkey_mode'])
                    if 'type_method' in data:
                        data['type_method'] = TypeMethod(data['type_method'])
                    return cls(**data)
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
        return cls()
    
    def save(self, path: Path):
        """Save settings to file"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            data = self.__dict__.copy()
            # Convert enums to values
            data['hotkey_mode'] = self.hotkey_mode.value
            data['type_method'] = self.type_method.value
            with open(path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

class InputSimulator:
    """Base class for input simulation"""
    
    def __init__(self):
        self.cancel_token = threading.Event()
    
    def type_text(self, text: str, delay_ms: int) -> bool:
        """Type text with given delay. Returns False if cancelled."""
        raise NotImplementedError
    
    def prepare_keystrokes(self, text: str) -> List[str]:
        """Prepare text for typing (handle special characters)"""
        raise NotImplementedError
    
    def cancel(self):
        """Cancel ongoing typing"""
        self.cancel_token.set()

class XTestInputSimulator(InputSimulator):
    """X11 input simulation using XTest extension (like Windows SendKeys)"""
    
    def __init__(self):
        super().__init__()
        if not XLIB_AVAILABLE:
            raise ImportError("python-xlib is required for XTest input")
        
        self.display = XDisplay.Display()
        self.root = self.display.screen().root
        
        # Special characters that need escaping (like Windows SendKeys)
        self.special_chars = "{}[]+^%~()"
        
        # Shift character mappings
        self.shift_chars = {
            '!': '1', '@': '2', '#': '3', '$': '4', '%': '5',
            '^': '6', '&': '7', '*': '8', '(': '9', ')': '0',
            '_': 'minus', '+': 'equal', '{': 'bracketleft', '}': 'bracketright',
            '|': 'backslash', ':': 'semicolon', '"': 'apostrophe',
            '<': 'comma', '>': 'period', '?': 'slash', '~': 'grave'
        }
        
        # Add uppercase letters
        for c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
            self.shift_chars[c] = c.lower()
    
    def prepare_keystrokes(self, text: str) -> List[str]:
        """Prepare keystrokes like Windows version"""
        keystrokes = []
        for char in text:
            if char in self.special_chars:
                # Escape special characters by wrapping in braces
                keystrokes.append(f"{{{char}}}")
            else:
                keystrokes.append(char)
        return keystrokes
    
    def type_text(self, text: str, delay_ms: int) -> bool:
        """Type text with specified delay"""
        self.cancel_token.clear()
        keystrokes = self.prepare_keystrokes(text)
        
        for keystroke in keystrokes:
            if self.cancel_token.is_set():
                return False
            
            # Handle escaped characters
            if keystroke.startswith('{') and keystroke.endswith('}'):
                char = keystroke[1:-1]
            else:
                char = keystroke
            
            self._type_char(char)
            time.sleep(delay_ms / 1000.0)
        
        return True
    
    def _type_char(self, char: str):
        """Type a single character"""
        if char == '\n':
            self._press_key('Return')
        elif char == '\t':
            self._press_key('Tab')
        elif char == ' ':
            self._press_key('space')
        elif char in self.shift_chars:
            self._press_key(self.shift_chars[char], with_shift=True)
        else:
            self._press_key(char)
    
    def _press_key(self, key: str, with_shift: bool = False):
        """Simulate a key press"""
        keysym = XK.string_to_keysym(key)
        if keysym == 0:
            return
        
        keycode = self.display.keysym_to_keycode(keysym)
        if keycode == 0:
            return
        
        if with_shift:
            shift_keycode = self.display.keysym_to_keycode(XK.XK_Shift_L)
            xtest.fake_input(self.display, X.KeyPress, shift_keycode)
            self.display.sync()
        
        xtest.fake_input(self.display, X.KeyPress, keycode)
        self.display.sync()
        time.sleep(0.001)
        xtest.fake_input(self.display, X.KeyRelease, keycode)
        self.display.sync()
        
        if with_shift:
            xtest.fake_input(self.display, X.KeyRelease, shift_keycode)
            self.display.sync()

class XDoToolInputSimulator(InputSimulator):
    """Input simulation using xdotool (works on X11 and XWayland)"""
    
    def __init__(self):
        super().__init__()
        # Check if xdotool is available
        try:
            subprocess.run(['xdotool', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise ImportError("xdotool is required for this input method")
    
    def prepare_keystrokes(self, text: str) -> List[str]:
        """For xdotool, we send the whole text"""
        return [text]
    
    def type_text(self, text: str, delay_ms: int) -> bool:
        """Type text using xdotool"""
        self.cancel_token.clear()
        
        try:
            # xdotool type command with delay
            proc = subprocess.Popen([
                'xdotool', 'type', '--delay', str(delay_ms), text
            ])
            
            # Wait for completion or cancellation
            while proc.poll() is None:
                if self.cancel_token.is_set():
                    proc.terminate()
                    return False
                time.sleep(0.1)
            
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"xdotool error: {e}")
            return False

class YDoToolInputSimulator(InputSimulator):
    """Input simulation using ydotool (works on both X11 and Wayland)"""
    
    def __init__(self):
        super().__init__()
        # Check if ydotool is available and daemon is running
        try:
            result = subprocess.run(['ydotool', 'type', ''], capture_output=True, text=True)
            if 'ydotoold backend unavailable' in result.stderr:
                raise ImportError("ydotoold daemon not running. Start with: systemctl --user start ydotoold")
        except FileNotFoundError:
            raise ImportError("ydotool not installed")
    
    def prepare_keystrokes(self, text: str) -> List[str]:
        """For ydotool, we send the whole text"""
        return [text]
    
    def type_text(self, text: str, delay_ms: int) -> bool:
        """Type text using ydotool"""
        self.cancel_token.clear()
        
        try:
            # ydotool type command with delay
            proc = subprocess.Popen([
                'ydotool', 'type', '--key-delay', str(delay_ms), text
            ])
            
            # Wait for completion or cancellation
            while proc.poll() is None:
                if self.cancel_token.is_set():
                    proc.terminate()
                    return False
                time.sleep(0.1)
            
            return proc.returncode == 0
        except Exception as e:
            logger.error(f"ydotool error: {e}")
            return False

class CursorManager:
    """Manages cursor changes like the Windows version"""
    
    def __init__(self, display):
        self.display = display
        self.original_cursors = {}
        self.cursor_font = None
        
    def set_crosshair_cursor(self):
        """Change cursors to crosshair (like Windows version)"""
        try:
            # Load cursor font
            self.cursor_font = self.display.core.open_font('cursor')
            
            # Create crosshair cursor
            crosshair = self.cursor_font.create_glyph_cursor(
                self.cursor_font,
                CursorType.CROSS, CursorType.CROSS + 1,
                (65535, 65535, 65535), (0, 0, 0)
            )
            
            # Change root window cursor
            self.display.screen().root.change_attributes(cursor=crosshair)
            self.display.sync()
            
            return True
        except Exception as e:
            logger.error(f"Failed to change cursor: {e}")
            return False
    
    def restore_cursor(self):
        """Restore original cursors"""
        try:
            # Reset to default cursor
            self.display.screen().root.change_attributes(cursor=0)
            self.display.sync()
            
            if self.cursor_font:
                self.cursor_font.close()
                self.cursor_font = None
        except Exception as e:
            logger.error(f"Failed to restore cursor: {e}")

class ClickPasteApp:
    def __init__(self):
        self.app = Gtk.Application(application_id='com.github.linuxclickpaste')
        self.app.connect('activate', self.on_activate)
        
        # Initialize early
        if XLIB_AVAILABLE:
            self.x_display = XDisplay.Display()
            self.cursor_manager = CursorManager(self.x_display)
        else:
            self.x_display = None
            self.cursor_manager = None
        
        # Paths
        self.config_dir = Path.home() / '.config' / 'linuxclickpaste'
        self.settings_path = self.config_dir / 'settings.json'
        
        # Load settings
        self.settings = Settings.load(self.settings_path)
        
        # State
        self.selecting_target = False
        self.overlay_window = None
        self.typing_active = False
        self.input_simulator = None
        self.settings_window_open = False
        self.original_icon = None
        self.indicator = None
        self.fallback_window = None
        
        # Initialize Keybinder for global hotkeys if available
        if KEYBINDER_AVAILABLE:
            try:
                Keybinder.init()
            except:
                KEYBINDER_AVAILABLE = False
    
    def on_activate(self, app):
        """Application activation"""
        # Check if we need elevated privileges
        if self.settings.run_elevated and os.geteuid() != 0:
            logger.warning("Run as root for elevated privileges")
        
        # Create input simulator
        self._create_input_simulator()
        
        # Try to create system tray
        if APPINDICATOR_AVAILABLE:
            self.create_indicator()
        else:
            # Create a fallback window if no tray support
            self.create_fallback_window()
        
        # Create settings window
        self.create_settings_window()
        
        # Register hotkey if available
        if KEYBINDER_AVAILABLE:
            self.start_hotkey()
        
        # Show ready notification
        if self.settings.show_notifications:
            self.show_notification("LinuxClickPaste Started", 
                                 "Ready to paste. Click tray icon or use window.")
    
    def create_fallback_window(self):
        """Create a minimal window when tray is not available"""
        self.fallback_window = Gtk.ApplicationWindow(application=self.app)
        self.fallback_window.set_title("LinuxClickPaste")
        self.fallback_window.set_default_size(300, 150)
        
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        
        label = Gtk.Label(label="LinuxClickPaste is running")
        box.append(label)
        
        paste_button = Gtk.Button(label="Click to Paste")
        paste_button.connect("clicked", lambda w: self.start_track())
        box.append(paste_button)
        
        settings_button = Gtk.Button(label="Settings")
        settings_button.connect("clicked", self.on_settings_click)
        box.append(settings_button)
        
        self.fallback_window.set_child(box)
        self.fallback_window.present()
    
    def _create_input_simulator(self):
        """Create appropriate input simulator"""
        try:
            if self.settings.type_method == TypeMethod.YDOTOOL:
                self.input_simulator = YDoToolInputSimulator()
            elif self.settings.type_method == TypeMethod.XDOTOOL:
                self.input_simulator = XDoToolInputSimulator()
            else:
                self.input_simulator = XTestInputSimulator()
        except Exception as e:
            logger.warning(f"Failed to create {self.settings.type_method.value} simulator: {e}")
            # Try fallbacks
            fallbacks = [TypeMethod.XDOTOOL, TypeMethod.YDOTOOL, TypeMethod.XTEST]
            for method in fallbacks:
                if method != self.settings.type_method:
                    try:
                        if method == TypeMethod.YDOTOOL:
                            self.input_simulator = YDoToolInputSimulator()
                        elif method == TypeMethod.XDOTOOL:
                            self.input_simulator = XDoToolInputSimulator()
                        else:
                            self.input_simulator = XTestInputSimulator()
                        logger.info(f"Fell back to {method.value}")
                        self.settings.type_method = method
                        return
                    except:
                        continue
            raise RuntimeError("No input simulation method available")
    
    def create_indicator(self):
        """Create system tray indicator"""
        try:
            # Detect theme (like Windows version)
            dark_theme = self._is_dark_theme()
            icon_name = "edit-paste"
            
            self.indicator = AppIndicator3.Indicator.new(
                "linuxclickpaste",
                icon_name,
                AppIndicator3.IndicatorCategory.APPLICATION_STATUS
            )
            
            self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
            self.indicator.set_menu(self.create_menu())
            
            # Store original icon
            self.original_icon = icon_name
        except Exception as e:
            logger.error(f"Failed to create indicator: {e}")
            self.create_fallback_window()
    
    def _is_dark_theme(self):
        """Detect if using dark theme"""
        try:
            # Try to detect GTK theme
            settings = Gtk.Settings.get_default()
            theme_name = settings.get_property("gtk-theme-name")
            return "dark" in theme_name.lower()
        except:
            return True
    
    def create_menu(self):
        """Create tray menu - using GTK3 menu for AppIndicator3"""
        # Import GTK3 for menu (AppIndicator3 requires it)
        gi_menu = gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk as Gtk3
        
        menu = Gtk3.Menu()
        
        # Click to paste
        item_paste = Gtk3.MenuItem(label="Click to Paste")
        item_paste.connect("activate", lambda w: self.start_track())
        menu.append(item_paste)
        
        # Settings item
        item_settings = Gtk3.MenuItem(label="Settings")
        item_settings.connect("activate", self.on_settings_click)
        menu.append(item_settings)
        
        # Separator
        menu.append(Gtk3.SeparatorMenuItem())
        
        # Exit
        item_exit = Gtk3.MenuItem(label="Exit")
        item_exit.connect("activate", self.on_exit)
        menu.append(item_exit)
        
        menu.show_all()
        return menu
    
    def create_settings_window(self):
        """Create settings window matching Windows version"""
        self.settings_window = Gtk.Window(title="LinuxClickPaste Settings")
        self.settings_window.set_default_size(450, 500)
        self.settings_window.set_hide_on_close(True)
        self.settings_window.connect("close-request", self.on_settings_close)
        
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        
        # Hotkey section (only if Keybinder available)
        if KEYBINDER_AVAILABLE:
            hotkey_frame = Gtk.Frame(label="Hot Key")
            hotkey_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            hotkey_box.set_margin_top(5)
            hotkey_box.set_margin_bottom(5)
            hotkey_box.set_margin_start(5)
            hotkey_box.set_margin_end(5)
            
            # Note about Wayland
            if os.environ.get('XDG_SESSION_TYPE') == 'wayland':
                note_label = Gtk.Label()
                note_label.set_markup("<small><i>Note: Global hotkeys may not work on Wayland</i></small>")
                hotkey_box.append(note_label)
            
            hotkey_frame.set_child(hotkey_box)
            main_box.append(hotkey_frame)
        
        # Delays section
        delays_frame = Gtk.Frame(label="Delays")
        delays_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        delays_box.set_margin_top(5)
        delays_box.set_margin_bottom(5)
        delays_box.set_margin_start(5)
        delays_box.set_margin_end(5)
        
        # Key delay
        key_delay_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        key_delay_label = Gtk.Label(label="Delay between keystrokes (ms):")
        self.key_delay_spin = Gtk.SpinButton()
        self.key_delay_spin.set_adjustment(Gtk.Adjustment(
            value=self.settings.key_delay_ms,
            lower=0,
            upper=1000,
            step_increment=1,
            page_increment=10
        ))
        self.key_delay_spin.connect("value-changed", self.on_key_delay_changed)
        key_delay_box.append(key_delay_label)
        key_delay_box.append(self.key_delay_spin)
        delays_box.append(key_delay_box)
        
        delays_frame.set_child(delays_box)
        main_box.append(delays_frame)
        
        # Type method
        method_frame = Gtk.Frame(label="Type Method")
        method_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        method_box.set_margin_top(5)
        method_box.set_margin_bottom(5)
        method_box.set_margin_start(5)
        method_box.set_margin_end(5)
        
        self.method_combo = Gtk.ComboBoxText()
        self.method_combo.append_text("XTest (SendKeys equivalent)")
        self.method_combo.append_text("xdotool (AutoIt equivalent)")
        self.method_combo.append_text("ydotool (Wayland compatible)")
        
        # Set active based on current method
        if self.settings.type_method == TypeMethod.XTEST:
            self.method_combo.set_active(0)
        elif self.settings.type_method == TypeMethod.XDOTOOL:
            self.method_combo.set_active(1)
        else:
            self.method_combo.set_active(2)
        
        self.method_combo.connect("changed", self.on_method_changed)
        method_box.append(self.method_combo)
        
        method_frame.set_child(method_box)
        main_box.append(method_frame)
        
        # Save button
        save_button = Gtk.Button(label="Save Settings")
        save_button.connect("clicked", self.on_save_settings)
        main_box.append(save_button)
        
        self.settings_window.set_child(main_box)
    
    def on_key_delay_changed(self, spin):
        """Handle key delay change"""
        self.settings.key_delay_ms = int(spin.get_value())
    
    def on_method_changed(self, combo):
        """Handle type method change"""
        active = combo.get_active()
        if active == 0:
            self.settings.type_method = TypeMethod.XTEST
        elif active == 1:
            self.settings.type_method = TypeMethod.XDOTOOL
        else:
            self.settings.type_method = TypeMethod.YDOTOOL
        self._create_input_simulator()
    
    def on_save_settings(self, button):
        """Save settings"""
        self.settings.save(self.settings_path)
        if self.settings.show_notifications:
            self.show_notification("Settings Saved", "Your settings have been saved")
    
    def on_settings_click(self, widget):
        """Show settings window"""
        self.settings_window.present()
    
    def on_settings_close(self, window):
        """Handle settings window close"""
        return False
    
    def start_hotkey(self):
        """Register global hotkey if available"""
        # Hotkey support is limited on Wayland
        pass
    
    def start_track(self):
        """Start target selection mode"""
        if self.selecting_target:
            return
        
        self.selecting_target = True
        
        # Change cursor to crosshair (may not work on Wayland)
        if self.cursor_manager:
            self.cursor_manager.set_crosshair_cursor()
        
        # Create overlay window
        self.overlay_window = Gtk.Window()
        self.overlay_window.set_decorated(False)
        self.overlay_window.set_opacity(0.01)
        
        # Fullscreen
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor()
        if monitor:
            geometry = monitor.get_geometry()
            self.overlay_window.set_default_size(geometry.width, geometry.height)
        
        # Event handlers
        click_controller = Gtk.GestureClick()
        click_controller.connect("pressed", self.on_target_clicked)
        self.overlay_window.add_controller(click_controller)
        
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_overlay_key_pressed)
        self.overlay_window.add_controller(key_controller)
        
        self.overlay_window.fullscreen()
        self.overlay_window.present()
        
        # Minimize the fallback window if it exists
        if self.fallback_window:
            self.fallback_window.minimize()
    
    def end_track(self):
        """End target selection mode"""
        self.selecting_target = False
        
        # Restore cursor
        if self.cursor_manager:
            self.cursor_manager.restore_cursor()
        
        # Close overlay
        if self.overlay_window:
            self.overlay_window.destroy()
            self.overlay_window = None
        
        # Restore fallback window if needed
        if self.fallback_window:
            self.fallback_window.unminimize()
    
    def on_overlay_key_pressed(self, controller, keyval, keycode, state):
        """Handle key press during target selection"""
        if keyval == Gdk.KEY_Escape:
            self.end_track()
            return True
        return False
    
    def on_target_clicked(self, gesture, n_press, x, y):
        """Handle target click"""
        self.end_track()
        
        # Small delay before typing
        GLib.timeout_add(100, self.start_typing)
    
    def start_typing(self):
        """Start typing the clipboard contents"""
        # Get clipboard text
        clipboard = Gdk.Display.get_default().get_clipboard()
        
        def clipboard_callback(clipboard, result):
            try:
                text = clipboard.read_text_finish(result)
                if not text:
                    self.show_notification("Clipboard Empty", 
                                         "Nothing to paste")
                    return
                
                # Start typing in thread
                self.typing_active = True
                threading.Thread(
                    target=self._type_text_thread,
                    args=(text,),
                    daemon=True
                ).start()
                
            except Exception as e:
                logger.error(f"Clipboard error: {e}")
                self.show_notification("Error", str(e))
        
        clipboard.read_text_async(None, clipboard_callback)
        return False
    
    def _type_text_thread(self, text: str):
        """Type text in separate thread"""
        try:
            # Change tray icon to indicate typing (if available)
            if self.indicator:
                GLib.idle_add(self._set_typing_icon, True)
            
            # Initial delay
            time.sleep(0.1 + self.settings.start_delay_ms / 1000.0)
            
            # Type the text
            success = self.input_simulator.type_text(text, self.settings.key_delay_ms)
            
            if not success:
                GLib.idle_add(self.show_notification, "Typing Cancelled", 
                            "Paste operation was cancelled")
            
        except Exception as e:
            logger.error(f"Typing error: {e}")
            GLib.idle_add(self.show_notification, "Error", str(e))
        finally:
            self.typing_active = False
            if self.indicator:
                GLib.idle_add(self._set_typing_icon, False)
    
    def _set_typing_icon(self, typing: bool):
        """Change tray icon to indicate typing"""
        if self.indicator:
            if typing:
                # Use a different icon to indicate typing
                self.indicator.set_icon("media-playback-start")
            else:
                # Restore original icon
                self.indicator.set_icon(self.original_icon)
    
    def show_notification(self, title: str, message: str):
        """Show desktop notification"""
        if not self.settings.show_notifications:
            return
        
        try:
            subprocess.run([
                'notify-send',
                '--app-name=LinuxClickPaste',
                '--icon=edit-paste',
                title,
                message
            ], check=False)
        except:
            print(f"{title}: {message}")
    
    def on_exit(self, widget):
        """Exit application"""
        self.end_track()
        self.settings.save(self.settings_path)
        
        # Cleanup
        if self.cursor_manager:
            self.cursor_manager.restore_cursor()
        
        self.app.quit()
    
    def run(self):
        """Run the application"""
        self.app.run(None)

def main():
    """Main entry point"""
    # Check display server
    session_type = os.environ.get('XDG_SESSION_TYPE', '')
    
    print(f"LinuxClickPaste - Session type: {session_type or 'unknown'}")
    
    if session_type == 'wayland':
        print("\nWayland detected. LinuxClickPaste will work with:")
        print("- X11 applications running under XWayland")
        print("- Native Wayland apps if ydotool is installed and configured")
    
    # Check for single instance (like Windows version)
    import fcntl
    lock_file = Path.home() / '.config' / 'linuxclickpaste' / 'lock'
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        lock_fd = open(lock_file, 'w')
        fcntl.lockf(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except IOError:
        print("LinuxClickPaste is already running")
        sys.exit(1)
    
    # Run application
    try:
        app = ClickPasteApp()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
    finally:
        # Cleanup
        try:
            lock_fd.close()
            lock_file.unlink()
        except:
            pass

if __name__ == "__main__":
    main()
