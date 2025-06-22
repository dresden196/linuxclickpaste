#!/usr/bin/env python3
"""
LinuxClickPaste - Feature-complete Linux port of Windows ClickPaste
Matches the original functionality including hotkeys, cursor changes, and typing modes
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')

# AppIndicator3 requires GTK 3, so we need to handle this carefully
try:
    # Try to import AppIndicator3 (requires GTK 3)
    import gi as gi3
    gi3.require_version('AppIndicator3', '0.1')
    from gi.repository import AppIndicator3
    APPINDICATOR_AVAILABLE = True
except:
    APPINDICATOR_AVAILABLE = False
    AppIndicator3 = None

# Keybinder also might have issues on Wayland
try:
    gi.require_version('Keybinder', '3.0')
    from gi.repository import Keybinder
    KEYBINDER_AVAILABLE = True
except:
    KEYBINDER_AVAILABLE = False
    Keybinder = None

from gi.repository import Gtk, Gdk, GLib
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
    type_method: TypeMethod = TypeMethod.XTEST
    
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

class YDoToolInputSimulator(InputSimulator):
    """Input simulation using ydotool (works on both X11 and Wayland)"""
    
    def __init__(self):
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
        
        # Initialize Keybinder for global hotkeys
        Keybinder.init()
    
    def on_activate(self, app):
        """Application activation"""
        # Check if we need elevated privileges
        if self.settings.run_elevated and os.geteuid() != 0:
            logger.warning("Run as root for elevated privileges")
        
        # Create input simulator
        self._create_input_simulator()
        
        # Create system tray
        self.create_indicator()
        
        # Create settings window
        self.create_settings_window()
        
        # Register hotkey
        self.start_hotkey()
        
        # Show ready notification
        if self.settings.show_notifications:
            self.show_notification("LinuxClickPaste Started", 
                                 "Ready to paste. Click tray icon or use hotkey.")
    
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
        # Detect theme (like Windows version)
        dark_theme = self._is_dark_theme()
        icon_name = "edit-paste" if dark_theme else "edit-paste"
        
        self.indicator = AppIndicator3.Indicator.new(
            "linuxclickpaste",
            icon_name,
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.create_menu())
        self.indicator.set_secondary_activate_target(self.create_menu())
        
        # Store original icon
        self.original_icon = icon_name
    
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
        """Create tray menu"""
        menu = Gtk.Menu()
        
        # Settings item
        item_settings = Gtk.MenuItem(label="Settings")
        item_settings.connect("activate", self.on_settings_click)
        menu.append(item_settings)
        
        # Separator
        menu.append(Gtk.SeparatorMenuItem())
        
        # Exit
        item_exit = Gtk.MenuItem(label="Exit")
        item_exit.connect("activate", self.on_exit)
        menu.append(item_exit)
        
        menu.show_all()
        return menu
    
    def create_settings_window(self):
        """Create settings window matching Windows version"""
        self.settings_window = Gtk.Window(title="LinuxClickPaste Settings")
        self.settings_window.set_default_size(450, 500)
        self.settings_window.set_hide_on_close(True)
        self.settings_window.connect("delete-event", self.on_settings_close)
        
        # Main container
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        
        # Hotkey section
        hotkey_frame = Gtk.Frame(label="Hot Key")
        hotkey_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        hotkey_box.set_margin_top(5)
        hotkey_box.set_margin_bottom(5)
        hotkey_box.set_margin_start(5)
        hotkey_box.set_margin_end(5)
        
        # Hotkey input
        hotkey_input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.hotkey_entry = Gtk.Entry()
        self.hotkey_entry.set_placeholder_text("Press a key combination")
        if self.settings.hotkey:
            self._update_hotkey_display()
        
        # Connect key press event
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_hotkey_pressed)
        self.hotkey_entry.add_controller(key_controller)
        
        hotkey_clear_btn = Gtk.Button(label="Clear")
        hotkey_clear_btn.connect("clicked", self.on_clear_hotkey)
        
        hotkey_input_box.append(self.hotkey_entry)
        hotkey_input_box.append(hotkey_clear_btn)
        hotkey_box.append(hotkey_input_box)
        
        # Hotkey mode
        self.hotkey_mode_combo = Gtk.ComboBoxText()
        self.hotkey_mode_combo.append_text("Show target cursor")
        self.hotkey_mode_combo.append_text("Paste immediately")
        self.hotkey_mode_combo.set_active(self.settings.hotkey_mode.value)
        self.hotkey_mode_combo.connect("changed", self.on_hotkey_mode_changed)
        hotkey_box.append(self.hotkey_mode_combo)
        
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
        
        # Start delay
        start_delay_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        start_delay_label = Gtk.Label(label="Delay before typing starts (ms):")
        self.start_delay_spin = Gtk.SpinButton()
        self.start_delay_spin.set_adjustment(Gtk.Adjustment(
            value=self.settings.start_delay_ms,
            lower=0,
            upper=5000,
            step_increment=10,
            page_increment=100
        ))
        self.start_delay_spin.connect("value-changed", self.on_start_delay_changed)
        start_delay_box.append(start_delay_label)
        start_delay_box.append(self.start_delay_spin)
        delays_box.append(start_delay_box)
        
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
        
        # Options
        options_frame = Gtk.Frame(label="Options")
        options_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        options_box.set_margin_top(5)
        options_box.set_margin_bottom(5)
        options_box.set_margin_start(5)
        options_box.set_margin_end(5)
        
        # Confirm checkbox
        confirm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        self.confirm_check = Gtk.CheckButton(label="Confirm before typing more than")
        self.confirm_check.set_active(self.settings.confirm)
        self.confirm_check.connect("toggled", self.on_confirm_toggled)
        
        self.confirm_spin = Gtk.SpinButton()
        self.confirm_spin.set_adjustment(Gtk.Adjustment(
            value=self.settings.confirm_over,
            lower=100,
            upper=10000,
            step_increment=100,
            page_increment=1000
        ))
        self.confirm_spin.connect("value-changed", self.on_confirm_over_changed)
        self.confirm_spin.set_sensitive(self.settings.confirm)
        
        confirm_label = Gtk.Label(label="characters")
        
        confirm_box.append(self.confirm_check)
        confirm_box.append(self.confirm_spin)
        confirm_box.append(confirm_label)
        options_box.append(confirm_box)
        
        # Run elevated
        self.elevated_check = Gtk.CheckButton(label="Request elevated privileges on startup")
        self.elevated_check.set_active(self.settings.run_elevated)
        self.elevated_check.connect("toggled", self.on_elevated_toggled)
        options_box.append(self.elevated_check)
        
        options_frame.set_child(options_box)
        main_box.append(options_frame)
        
        # Save button
        save_button = Gtk.Button(label="Save Settings")
        save_button.connect("clicked", self.on_save_settings)
        main_box.append(save_button)
        
        self.settings_window.set_child(main_box)
    
    def _update_hotkey_display(self):
        """Update hotkey display in entry"""
        parts = []
        if self.settings.hotkey_modifiers:
            parts.extend(self.settings.hotkey_modifiers)
        if self.settings.hotkey:
            parts.append(self.settings.hotkey)
        self.hotkey_entry.set_text(" + ".join(parts))
    
    def on_hotkey_pressed(self, controller, keyval, keycode, state):
        """Handle hotkey input"""
        # Get key name
        key_name = Gdk.keyval_name(keyval)
        if not key_name:
            return True
        
        # Get modifiers
        modifiers = []
        if state & Gdk.ModifierType.CONTROL_MASK:
            modifiers.append("Control")
        if state & Gdk.ModifierType.ALT_MASK:
            modifiers.append("Alt")
        if state & Gdk.ModifierType.SHIFT_MASK:
            modifiers.append("Shift")
        if state & Gdk.ModifierType.SUPER_MASK:
            modifiers.append("Super")
        
        # Update settings
        self.settings.hotkey = key_name
        self.settings.hotkey_modifiers = modifiers
        
        # Update display
        self._update_hotkey_display()
        
        return True
    
    def on_clear_hotkey(self, button):
        """Clear hotkey"""
        self.settings.hotkey = None
        self.settings.hotkey_modifiers = []
        self.hotkey_entry.set_text("")
    
    def on_hotkey_mode_changed(self, combo):
        """Handle hotkey mode change"""
        self.settings.hotkey_mode = HotKeyMode(combo.get_active())
    
    def on_key_delay_changed(self, spin):
        """Handle key delay change"""
        self.settings.key_delay_ms = int(spin.get_value())
    
    def on_start_delay_changed(self, spin):
        """Handle start delay change"""
        self.settings.start_delay_ms = int(spin.get_value())
    
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
    
    def on_confirm_toggled(self, check):
        """Handle confirm toggle"""
        self.settings.confirm = check.get_active()
        self.confirm_spin.set_sensitive(self.settings.confirm)
    
    def on_confirm_over_changed(self, spin):
        """Handle confirm threshold change"""
        self.settings.confirm_over = int(spin.get_value())
    
    def on_elevated_toggled(self, check):
        """Handle elevated toggle"""
        self.settings.run_elevated = check.get_active()
    
    def on_save_settings(self, button):
        """Save settings"""
        self.settings.save(self.settings_path)
        self.stop_hotkey()
        self.start_hotkey()
        if self.settings.show_notifications:
            self.show_notification("Settings Saved", "Your settings have been saved")
    
    def on_settings_click(self, widget):
        """Show settings window"""
        if not self.settings_window_open:
            self.settings_window_open = True
            self.stop_hotkey()
            self.settings_window.present()
    
    def on_settings_close(self, window, event):
        """Handle settings window close"""
        self.settings_window_open = False
        self.start_hotkey()
        return False
    
    def start_hotkey(self):
        """Register global hotkey"""
        self.stop_hotkey()
        
        if self.settings.hotkey:
            try:
                # Build hotkey string
                hotkey_str = ""
                if self.settings.hotkey_modifiers:
                    hotkey_str = "<" + "><".join(self.settings.hotkey_modifiers) + ">"
                hotkey_str += self.settings.hotkey
                
                # Register hotkey
                Keybinder.bind(hotkey_str, self.on_hotkey_activated)
                logger.info(f"Registered hotkey: {hotkey_str}")
            except Exception as e:
                logger.error(f"Failed to register hotkey: {e}")
                self.show_notification("Hotkey Error", 
                                     f"Could not register hotkey: {str(e)}")
    
    def stop_hotkey(self):
        """Unregister global hotkey"""
        try:
            Keybinder.unbind_all()
        except:
            pass
    
    def start_hotkey_escape(self):
        """Register escape key during typing"""
        self.stop_hotkey()
        try:
            Keybinder.bind("Escape", self.on_escape_pressed)
        except Exception as e:
            logger.error(f"Failed to register escape key: {e}")
    
    def on_hotkey_activated(self, keystring):
        """Handle hotkey activation"""
        self.stop_hotkey()
        
        # Wait for modifier keys to be released (like Windows version)
        if self.x_display:
            while self._is_modifier_pressed():
                time.sleep(0.3)
        
        # Handle based on mode
        if self.settings.hotkey_mode == HotKeyMode.TARGET:
            self.start_track()
        else:
            self.start_typing()
    
    def on_escape_pressed(self, keystring):
        """Handle escape key during typing"""
        if self.typing_active and self.input_simulator:
            self.input_simulator.cancel()
            self.stop_hotkey()
    
    def _is_modifier_pressed(self):
        """Check if any modifier key is pressed"""
        try:
            # Query keyboard state
            keys = self.x_display.query_keymap()
            
            # Check common modifier keycodes
            # These are typical but may vary by system
            shift_codes = [50, 62]      # Left/Right Shift
            ctrl_codes = [37, 105]      # Left/Right Ctrl
            alt_codes = [64, 108]       # Left/Right Alt
            super_codes = [133, 134]    # Left/Right Super
            
            for code in shift_codes + ctrl_codes + alt_codes + super_codes:
                byte_index = code // 8
                bit_index = code % 8
                if keys[byte_index] & (1 << bit_index):
                    return True
            
            return False
        except:
            return False
    
    def on_notify_click(self, *args):
        """Handle tray icon click"""
        if not self.settings_window_open:
            self.start_track()
    
    def start_track(self):
        """Start target selection mode"""
        if self.selecting_target:
            return
        
        self.selecting_target = True
        
        # Change cursor to crosshair
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
    
    def on_overlay_key_pressed(self, controller, keyval, keycode, state):
        """Handle key press during target selection"""
        if keyval == Gdk.KEY_Escape:
            self.end_track()
            self.start_hotkey()
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
                    self.start_hotkey()
                    return
                
                # Confirmation dialog if needed
                if self.settings.confirm and len(text) > self.settings.confirm_over:
                    dialog = Gtk.MessageDialog(
                        transient_for=None,
                        message_type=Gtk.MessageType.QUESTION,
                        buttons=Gtk.ButtonsType.YES_NO,
                        text=f"Confirm typing {len(text)} characters?"
                    )
                    dialog.set_secondary_text(f"To window: {self._get_active_window_title()}")
                    
                    response = dialog.run()
                    dialog.destroy()
                    
                    if response != Gtk.ResponseType.YES:
                        self.start_hotkey()
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
                self.start_hotkey()
        
        clipboard.read_text_async(None, clipboard_callback)
        return False
    
    def _get_active_window_title(self):
        """Get active window title"""
        try:
            # Use xdotool to get window title
            result = subprocess.run(
                ['xdotool', 'getactivewindow', 'getwindowname'],
                capture_output=True,
                text=True
            )
            if result.returncode == 0:
                return result.stdout.strip()[:50]
        except:
            pass
        return "Unknown"
    
    def _type_text_thread(self, text: str):
        """Type text in separate thread"""
        try:
            # Change tray icon to indicate typing
            GLib.idle_add(self._set_typing_icon, True)
            
            # Initial delay
            time.sleep(0.1 + self.settings.start_delay_ms / 1000.0)
            
            # Register escape hotkey
            GLib.idle_add(self.start_hotkey_escape)
            
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
            GLib.idle_add(self._set_typing_icon, False)
            GLib.idle_add(self.start_hotkey)
    
    def _set_typing_icon(self, typing: bool):
        """Change tray icon to indicate typing"""
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
        self.stop_hotkey()
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
    # Check dependencies
    if not XLIB_AVAILABLE:
        print("Error: python-xlib is required")
        print("Install with: pip install python-xlib")
        sys.exit(1)
    
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
