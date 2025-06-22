# Wayland Support for LinuxClickPaste

## Current Status
LinuxClickPaste has good Wayland support:

✅ **XWayland**: Most applications run through XWayland, so LinuxClickPaste works normally  
✅ **ydotool**: Provides native Wayland support for input simulation  
⚠️ **Global Hotkeys**: Limited but workable through desktop shortcuts  

## What Works on Wayland

### 1. XWayland Applications (Most Apps!)
If your target application is running through XWayland (which includes most traditional Linux applications), LinuxClickPaste works exactly as it does on X11:
- Full cursor changing
- Click targeting
- All input methods work

To check if an app uses XWayland:
```bash
xprop | grep WM_CLASS
# If it works, the app is using XWayland
```

### 2. Native Wayland with ydotool
For native Wayland applications, use ydotool:

#### Install ydotool:
```bash
# Ubuntu/Debian
sudo apt install ydotool

# Arch
yay -S ydotool

# Or build from source for latest version
git clone https://github.com/ReimuNotMoe/ydotool
cd ydotool
mkdir build && cd build
cmake ..
make && sudo make install
```

#### Setup ydotool:
```bash
# Enable and start the daemon (user service)
systemctl --user enable ydotoold
systemctl --user start ydotoold

# Or for system-wide service
sudo systemctl enable ydotool
sudo systemctl start ydotool
```

#### Configure LinuxClickPaste:
1. Open Settings in LinuxClickPaste
2. Select "ydotool (Wayland compatible)" as the Type Method
3. Save settings

### 3. Global Hotkeys Workaround
While Wayland doesn't support global hotkeys directly, you can:

1. **Use your desktop environment's shortcuts**:
   - GNOME: Settings → Keyboard → Custom Shortcuts
   - KDE: System Settings → Shortcuts → Custom Shortcuts
   - Add command: `linuxclickpaste` (or path to the script)

2. **The hotkey triggers LinuxClickPaste to show the target cursor**

## Compositor Support

| Compositor | XWayland | ydotool | wtype | Notes |
|------------|----------|---------|-------|-------|
| GNOME/Mutter | ✅ | ✅ | ❌ | Most common, good support |
| KDE/KWin | ✅ | ✅ | ❌ | Excellent support |
| Sway | ✅ | ✅ | ✅ | wlroots-based |
| Wayfire | ✅ | ✅ | ✅ | Raspberry Pi OS default |
| Hyprland | ✅ | ✅ | ✅ | Has own protocols too |

## Quick Setup Guide

### For Most Users (GNOME/KDE):
```bash
# 1. Install dependencies
sudo apt install ydotool xdotool

# 2. Setup ydotool daemon
systemctl --user enable --now ydotoold

# 3. Run LinuxClickPaste
./linuxclickpaste.py

# 4. In settings, choose ydotool as input method
```

### Force X11 Mode (100% Compatibility):
```bash
# Run LinuxClickPaste in X11 mode even on Wayland
GDK_BACKEND=x11 ./linuxclickpaste.py
```

## Troubleshooting

### "ydotoold backend unavailable"
```bash
# Check if daemon is running
systemctl --user status ydotoold

# If not, start it
systemctl --user start ydotoold
```

### Cursor doesn't change to crosshair
- This is normal on pure Wayland - security restriction
- The click targeting still works, just without visual cursor change
- Most apps run through XWayland where cursor changing works

### Can't set global hotkey
- Use your desktop environment's keyboard shortcut settings
- Set it to run: `linuxclickpaste` or full path to the script

## Feature Comparison

| Feature | X11 | XWayland Apps | Native Wayland |
|---------|-----|---------------|----------------|
| System tray | ✅ | ✅ | ✅ |
| Click to paste | ✅ | ✅ | ✅ |
| Cursor change | ✅ | ✅ | ❌ |
| Input simulation | ✅ | ✅ | ✅ (ydotool) |
| Global hotkeys | ✅ | ✅ | ⚠️ (via DE) |
| Target selection | ✅ | ✅ | ✅ |

## For VNC/Remote Desktop Users

Good news! Most VNC viewers and remote desktop tools still use XWayland, so LinuxClickPaste works perfectly for the intended use case:
- TigerVNC ✅
- RealVNC ✅
- Remmina ✅
- Chrome Remote Desktop ✅
- Most web-based consoles ✅

## Future Improvements

Wayland is actively developing:
- Input method protocols are improving
- Portal APIs for secure automation
- More compositors adding needed protocols

We'll continue updating LinuxClickPaste as new capabilities become available!
