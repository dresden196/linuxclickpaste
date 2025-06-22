#!/usr/bin/env python3
"""
Enhanced LinuxClickPaste - Modular architecture with better error handling
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Gdk', '4.0')
gi.require_version('AppIndicator3', '0.1')

from gi.repository import Gtk, Gdk, GLib, AppIndicator3, Gio
import subprocess
import time
import threading
import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Callable
from enum import Enum
import logging

# For keyboard simulation
try:
    from Xlib import X, XK, display as XDisplay
    from Xlib.ext import xtest
    XLIB_AVAILABLE = True
except ImportError:
    XLIB_AVAILABLE = False

# For Wayland support (future)
try:
    import pywayland
    WAYLAND_AVAILABLE = True
except ImportError:
    WAYLAND_AVAILABLE = False

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('LinuxClickPaste')

class DisplayServer(Enum):
    X11 = "x11"
    WAYLAND = "wayland"
    UNKNOWN = "unknown"

@dataclass
class Settings:
    """Application settings"""
    delay_between_keys: float = 0.01
    hotkey: Optional[str] = None
    start_minimized: bool = True
    show_notifications: bool = True
    paste_method: str = "xtest"  # xtest, xdotool, ydotool
    auto_detect_delay: bool = False
    profiles: Dict[str, Dict] = None
    
    def __post_init__(self):
        if self.profiles is None:
            self.profiles = {
                "default": {"delay": 0.01},
                "vnc": {"delay": 0.05},
                "slow_vnc": {"delay": 0.1},
                "very_slow": {"delay": 0.2}
            }
    
    @classmethod
    def load(cls, path: Path) -> 'Settings':
        """Load settings from file"""
        if path.exists():
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                return cls(**data)
            except Exception as e:
                logger.error(f"Failed to load settings: {e}")
        return cls()
    
    def save(self, path: Path):
        """Save settings to file"""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(self.__dict__, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")

class InputSimulator:
    """Abstract base class for input simulation"""
    
    def type_text(self, text: str, delay: float):
        raise NotImplementedError
    
    def click_at(self, x: int, y: int):
        raise NotImplementedError
    
    def move_mouse(self, x: int, y: int):
        raise NotImplementedError

class XTestInputSimulator(InputSimulator):
    """X11 input simulation using XTest extension"""
    
    def __init__(self):
        if not XLIB_AVAILABLE:
            raise ImportError("python-xlib is required for X11 support")
        
        self.display = XDisplay.Display()
        self.root = self.display.screen().root
        
        # Special character mappings
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
    
    def move_mouse(self, x: int, y: int):
        """Move mouse to specified position"""
        self.display.warp_pointer(x, y)
        self.display.sync()
    
    def click_at(self, x: int, y: int):
        """Click at specified position"""
        self.move_mouse(x, y)
        xtest.fake_input(self.display, X.ButtonPress, 1)
        self.display.sync()
        time.sleep(0.01)
        xtest.fake_input(self.display, X.ButtonRelease, 1)
        self.display.sync()
    
    def type_text(self, text: str, delay: float):
        """Type text with specified delay between keystrokes"""
        for char in text:
            self._type_char(char)
            time.sleep(delay)
    
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
        # Get keysym
        keysym = XK.string_to_keysym(key)
        if keysym == 0:
            logger.warning(f"Unknown key: {key}")
            return
        
        # Get keycode
        keycode = self.display.keysym_to_keycode(keysym)
        if keycode == 0:
            logger.warning(f"No keycode for keysym: {keysym}")
            return
        
        # Press shift if needed
        if with_shift:
            shift_keycode = self.display.keysym_to_keycode(XK.XK_Shift_L)
            xtest.fake_input(self.display, X.KeyPress, shift_keycode)
            self.display.sync()
        
        # Press and release key
        xtest.fake_input(self.display, X.KeyPress, keycode)
        self.display.sync()
        time.sleep(0.005)
        xtest.fake_input(self.display, X.KeyRelease, keycode)
        self.display.sync()
        
        # Release shift if pressed
        if with_shift:
            xtest.fake_input(self.display, X.KeyRelease, shift_keycode)
            self.display.sync()

class XDoToolInputSimulator(InputSimulator):
    """Input simulation using xdotool command"""
    
    def __init__(self):
        # Check if xdotool is available
        try:
            subprocess.run(['xdotool', '--version'], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise ImportError("xdotool is required for this input method")
    
    def move_mouse(self, x: int, y: int):
        subprocess.run(['xdotool', 'mousemove', str(x), str(y)])
    
    def click_at(self, x: int, y: int):
        subprocess.run(['xdotool', 'mousemove', str(x), str(y), 'click', '1'])
    
    def type_text(self, text: str, delay: float):
        # xdotool can handle delay internally
        delay_ms = int(delay * 1000)
        subprocess.run(['xdotool', 'type', '--delay', str(delay_ms), text])

class ClickPasteApp:
    def __init__(self):
        self.app = Gtk.Application(application_id='com.github.linuxclickpaste')
        self.app.connect('activate', self.on_activate)
        
        # Paths
        self.config_dir = Path.home() / '.config' / 'linuxclickpaste'
        self.settings_path = self.config_dir / 'settings.json'
        
        # Load settings
        self.settings = Settings.load(self.settings_path)
        
        # Detect display server
        self.display_server = self._detect_display_server()
        
        # Initialize input simulator
        self.input_simulator = self._create_input_simulator()
        
        # State
        self.selecting_target = False
        self.overlay_window = None
        
    def _detect_display_server(self) -> DisplayServer:
        """Detect which display server is running"""
        session_type = os.environ.get('XDG_SESSION_TYPE', '').lower()
        if session_type == 'x11':
            return DisplayServer.X11
        elif session_type == 'wayland':
            return DisplayServer.WAYLAND
        else:
            # Try to detect based on environment variables
            if os.environ.get('DISPLAY'):
                return DisplayServer.X11
            elif os.environ.get('WAYLAND_DISPLAY'):
                return DisplayServer.WAYLAND
        return DisplayServer.UNKNOWN
    
    def _create_input_simulator(self) -> InputSimulator:
        """Create appropriate input simulator based on settings and availability"""
        if self.display_server == DisplayServer.WAYLAND:
            logger.warning("Wayland detected. Full support coming soon. Trying compatibility mode...")
        
        if self.settings.paste_method == "xdotool":
            try:
                return XDoToolInputSimulator()
            except ImportError:
                logger.warning("xdotool not available, falling back to XTest")
        
        # Default to XTest
        try:
            return XTestInputSimulator()
        except ImportError as e:
            logger.error(f"No input simulation method available: {e}")
            raise
    
    def on_activate(self, app):
        """Application activation callback"""
        # Create system tray indicator
        self.create_indicator()
        
        # Create settings window
        self.create_settings_window()
        
        # Show notification
        if self.settings.show_notifications:
            self.show_notification("LinuxClickPaste Started", 
                                 "Click the tray icon to paste")
    
    def create_indicator(self):
        """Create system tray indicator"""
        self.indicator = AppIndicator3.Indicator.new(
            "linuxclickpaste",
            "edit-paste",
            AppIndicator3.IndicatorCategory.APPLICATION_STATUS
        )
        
        self.indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
        self.indicator.set_menu(self.create_menu())
    
    def create_menu(self):
        """Create tray menu with profiles"""
        menu = Gtk.Menu()
        
        # Click to Paste
        item_paste = Gtk.MenuItem(label="Click to Paste")
        item_paste.connect("activate", self.on_paste_click)
        menu.append(item_paste)
        
        # Separator
        menu.append(Gtk.SeparatorMenuItem())
        
        # Profile submenu
        profiles_item = Gtk.MenuItem(label="Profiles")
        profiles_menu = Gtk.Menu()
        
        for profile_name, profile_data in self.settings.profiles.items():
            profile_item = Gtk.MenuItem(label=profile_name.replace('_', ' ').title())
            profile_item.connect("activate", self.on_profile_select, profile_name)
            profiles_menu.append(profile_item)
        
        profiles_item.set_submenu(profiles_menu)
        menu.append(profiles_item)
        
        # Settings
        item_settings = Gtk.MenuItem(label="Settings")
        item_settings.connect("activate", self.on_settings_click)
        menu.append(item_settings)
        
        # About
        item_about = Gtk.MenuItem(label="About")
        item_about.connect("activate", self.on_about_click)
        menu.append(item_about)
        
        # Separator
        menu.append(Gtk.SeparatorMenuItem())
        
        # Quit
        item_quit = Gtk.MenuItem(label="Quit")
        item_quit.connect("activate", self.on_quit)
        menu.append(item_quit)
        
        menu.show_all()
        return menu
    
    def create_settings_window(self):
        """Create settings window with tabs"""
        self.settings_window = Gtk.Window(title="LinuxClickPaste Settings")
        self.settings_window.set_default_size(500, 400)
        self.settings_window.set_hide_on_close(True)
        
        # Create notebook for tabs
        notebook = Gtk.Notebook()
        
        # General tab
        general_box = self._create_general_settings()
        notebook.append_page(general_box, Gtk.Label(label="General"))
        
        # Advanced tab
        advanced_box = self._create_advanced_settings()
        notebook.append_page(advanced_box, Gtk.Label(label="Advanced"))
        
        # About tab
        about_box = self._create_about_tab()
        notebook.append_page(about_box, Gtk.Label(label="About"))
        
        self.settings_window.set_child(notebook)
    
    def _create_general_settings(self):
        """Create general settings tab"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        
        # Delay setting
        delay_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        delay_label = Gtk.Label(label="Delay between keystrokes (ms):")
        self.delay_spin = Gtk.SpinButton()
        self.delay_spin.set_adjustment(Gtk.Adjustment(
            value=self.settings.delay_between_keys * 1000,
            lower=1,
            upper=1000,
            step_increment=1,
            page_increment=10
        ))
        self.delay_spin.connect("value-changed", self.on_delay_changed)
        delay_box.append(delay_label)
        delay_box.append(self.delay_spin)
        box.append(delay_box)
        
        # Show notifications
        self.notify_check = Gtk.CheckButton(label="Show notifications")
        self.notify_check.set_active(self.settings.show_notifications)
        self.notify_check.connect("toggled", self.on_notify_toggled)
        box.append(self.notify_check)
        
        # Start minimized
        self.start_min_check = Gtk.CheckButton(label="Start minimized to tray")
        self.start_min_check.set_active(self.settings.start_minimized)
        self.start_min_check.connect("toggled", self.on_start_min_toggled)
        box.append(self.start_min_check)
        
        # Save button
        save_button = Gtk.Button(label="Save Settings")
        save_button.connect("clicked", self.on_save_settings)
        box.append(save_button)
        
        return box
    
    def _create_advanced_settings(self):
        """Create advanced settings tab"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        
        # Input method
        method_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        method_label = Gtk.Label(label="Input method:")
        self.method_combo = Gtk.ComboBoxText()
        self.method_combo.append("xtest", "XTest (recommended)")
        self.method_combo.append("xdotool", "xdotool")
        self.method_combo.set_active_id(self.settings.paste_method)
        self.method_combo.connect("changed", self.on_method_changed)
        method_box.append(method_label)
        method_box.append(self.method_combo)
        box.append(method_box)
        
        # Display server info
        info_label = Gtk.Label()
        info_label.set_markup(f"<b>Display Server:</b> {self.display_server.value}")
        box.append(info_label)
        
        return box
    
    def _create_about_tab(self):
        """Create about tab"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)
        
        # Logo/Icon
        icon = Gtk.Image.new_from_icon_name("edit-paste")
        icon.set_pixel_size(64)
        box.append(icon)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<b><big>LinuxClickPaste</big></b>")
        box.append(title)
        
        # Version
        version = Gtk.Label(label="Version 1.0.0")
        box.append(version)
        
        # Description
        desc = Gtk.Label()
        desc.set_markup(
            "A Linux equivalent of ClickPaste for Windows\n"
            "Paste clipboard contents as keystrokes\n\n"
            "<b>Perfect for:</b>\n"
            "• VNC Sessions\n"
            "• Remote Desktop\n"
            "• Virtual Machines\n"
            "• Any application that doesn't support paste"
        )
        desc.set_wrap(True)
        desc.set_justify(Gtk.Justification.CENTER)
        box.append(desc)
        
        return box
    
    def on_delay_changed(self, spin_button):
        """Handle delay change"""
        self.settings.delay_between_keys = spin_button.get_value() / 1000.0
    
    def on_notify_toggled(self, check_button):
        """Handle notification toggle"""
        self.settings.show_notifications = check_button.get_active()
    
    def on_start_min_toggled(self, check_button):
        """Handle start minimized toggle"""
        self.settings.start_minimized = check_button.get_active()
    
    def on_method_changed(self, combo):
        """Handle input method change"""
        self.settings.paste_method = combo.get_active_id()
        try:
            self.input_simulator = self._create_input_simulator()
        except Exception as e:
            self.show_notification("Error", f"Failed to change input method: {e}")
    
    def on_save_settings(self, button):
        """Save settings to file"""
        self.settings.save(self.settings_path)
        if self.settings.show_notifications:
            self.show_notification("Settings Saved", "Your settings have been saved")
    
    def on_profile_select(self, widget, profile_name):
        """Handle profile selection"""
        profile = self.settings.profiles.get(profile_name, {})
        if 'delay' in profile:
            self.settings.delay_between_keys = profile['delay']
            if hasattr(self, 'delay_spin'):
                self.delay_spin.set_value(profile['delay'] * 1000)
        
        if self.settings.show_notifications:
            self.show_notification("Profile Selected", 
                                 f"Using {profile_name.replace('_', ' ').title()} profile")
    
    def on_paste_click(self, widget):
        """Handle paste menu click"""
        # Get clipboard content
        clipboard = Gdk.Display.get_default().get_clipboard()
        
        def clipboard_callback(clipboard, result):
            try:
                text = clipboard.read_text_finish(result)
                if text:
                    self.start_target_selection(text)
                else:
                    self.show_notification("Clipboard Empty", 
                                         "Please copy some text first")
            except Exception as e:
                logger.error(f"Clipboard error: {e}")
                self.show_notification("Error", 
                                     f"Failed to read clipboard: {str(e)}")
        
        clipboard.read_text_async(None, clipboard_callback)
    
    def start_target_selection(self, text):
        """Start target selection process"""
        self.selecting_target = True
        self.text_to_paste = text
        
        # Create overlay window
        self.overlay_window = Gtk.Window()
        self.overlay_window.set_decorated(False)
        self.overlay_window.set_opacity(0.01)
        
        # Get screen dimensions
        display = Gdk.Display.get_default()
        monitor = display.get_monitor_at_surface(self.overlay_window.get_surface())
        if monitor:
            geometry = monitor.get_geometry()
            self.overlay_window.set_default_size(geometry.width, geometry.height)
        
        # Set cursor
        cursor = Gdk.Cursor.new_from_name("crosshair", None)
        self.overlay_window.set_cursor(cursor)
        
        # Click handler
        click_controller = Gtk.GestureClick()
        click_controller.connect("pressed", self.on_target_clicked)
        self.overlay_window.add_controller(click_controller)
        
        # Key handler for escape
        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.overlay_window.add_controller(key_controller)
        
        # Show window
        self.overlay_window.fullscreen()
        self.overlay_window.present()
    
    def on_key_pressed(self, controller, keyval, keycode, state):
        """Handle key press during target selection"""
        if keyval == Gdk.KEY_Escape:
            self.cancel_target_selection()
            return True
        return False
    
    def cancel_target_selection(self):
        """Cancel target selection"""
        if self.overlay_window:
            self.overlay_window.destroy()
            self.overlay_window = None
        self.selecting_target = False
        
        if self.settings.show_notifications:
            self.show_notification("Cancelled", "Paste operation cancelled")
    
    def on_target_clicked(self, gesture, n_press, x, y):
        """Handle target click"""
        # Get screen coordinates
        widget = gesture.get_widget()
        
        # Close overlay
        if self.overlay_window:
            self.overlay_window.destroy()
            self.overlay_window = None
        
        self.selecting_target = False
        
        # Perform paste after a short delay
        GLib.timeout_add(100, self.perform_paste, int(x), int(y))
    
    def perform_paste(self, x, y):
        """Perform the paste operation"""
        try:
            # Click at target
            self.input_simulator.click_at(x, y)
            time.sleep(0.1)
            
            # Type text in thread
            threading.Thread(
                target=self._type_text_thread,
                args=(self.text_to_paste,),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"Paste error: {e}")
            self.show_notification("Error", f"Failed to paste: {str(e)}")
        
        return False
    
    def _type_text_thread(self, text):
        """Type text in a separate thread"""
        try:
            self.input_simulator.type_text(text, self.settings.delay_between_keys)
            
            if self.settings.show_notifications:
                GLib.idle_add(
                    self.show_notification,
                    "Paste Complete",
                    f"Typed {len(text)} characters"
                )
        except Exception as e:
            logger.error(f"Typing error: {e}")
            GLib.idle_add(
                self.show_notification,
                "Error",
                f"Failed to type: {str(e)}"
            )
    
    def show_notification(self, title, message):
        """Show desktop notification"""
        try:
            subprocess.run([
                'notify-send',
                '--app-name=LinuxClickPaste',
                '--icon=edit-paste',
                title,
                message
            ], check=False)
        except Exception as e:
            logger.warning(f"Failed to show notification: {e}")
            print(f"{title}: {message}")
    
    def on_settings_click(self, widget):
        """Show settings window"""
        self.settings_window.present()
    
    def on_about_click(self, widget):
        """Show about dialog"""
        about = Gtk.AboutDialog()
        about.set_program_name("LinuxClickPaste")
        about.set_version("1.0.0")
        about.set_comments(
            "Paste clipboard contents as keystrokes\n"
            "For VNC, RDP, and other remote tools"
        )
        about.set_website("https://github.com/yourusername/linuxclickpaste")
        about.set_website_label("GitHub Repository")
        about.set_authors(["Your Name"])
        about.set_license_type(Gtk.License.GPL_3_0)
        about.present()
    
    def on_quit(self, widget):
        """Quit application"""
        # Save settings
        self.settings.save(self.settings_path)
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
    
    # Check display server
    session_type = os.environ.get('XDG_SESSION_TYPE', '')
    if session_type == 'wayland' and not os.environ.get('XWAYLAND'):
        print("Warning: Wayland detected. LinuxClickPaste works best on X11.")
        print("You may experience limited functionality.")
    
    # Run application
    try:
        app = ClickPasteApp()
        app.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
