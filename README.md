# LinuxClickPaste

A Linux equivalent of the Windows ClickPaste application - paste clipboard contents as keystrokes into applications that don't support regular paste operations.

Perfect for system administrators working with VNC sessions, iDRAC/iLO consoles, virtual machines, and other remote access tools where clipboard integration doesn't work.

## 🎯 Features

- **System Tray Integration** - Runs quietly in your system tray
- **Click-to-Paste** - Click the tray icon, then click where you want to paste
- **Global Hotkeys** - Configure keyboard shortcuts for quick access
- **Multiple Input Methods**:
  - XTest (native X11)
  - xdotool (works with X11 and XWayland)
  - ydotool (works with both X11 and Wayland)
- **Smart Delays** - Configurable keystroke delays for laggy connections
- **Safety Features** - Confirmation dialog for large pastes, ESC key cancellation
- **Cross-Desktop** - Works with GNOME, KDE, XFCE, and other desktop environments

## 📋 Requirements

- Linux with X11 or Wayland (XWayland supported)
- Python 3.8+
- GTK 4.0
- System tray support

## 🚀 Quick Start

### Install Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3-pip python3-gi python3-gi-cairo \
                 gir1.2-gtk-4.0 gir1.2-appindicator3-0.1 \
                 gir1.2-keybinder-3.0 xdotool

pip3 install --user PyGObject python-xlib
```

**Fedora:**
```bash
sudo dnf install python3-pip python3-gobject gtk4 \
                 libappindicator-gtk3 keybinder3 xdotool

pip3 install --user python-xlib
```

**Arch Linux:**
```bash
sudo pacman -S python-pip python-gobject gtk4 \
               libappindicator-gtk3 libkeybinder3 xdotool

pip install python-xlib
```

### Download and Run

```bash
# Clone the repository
git clone https://github.com/dresden196/linuxclickpaste.git
cd linuxclickpaste

# Make executable
chmod +x linuxclickpaste.py

# Run
./linuxclickpaste.py
```

## 💻 Usage

1. **Copy text to clipboard** (Ctrl+C)
2. **Click the tray icon** or use your configured hotkey
3. **Click where you want to paste** - cursor changes to crosshair
4. **Watch it type** - the text is typed as keystrokes

### Settings

Right-click the tray icon → Settings to configure:
- **Hotkey**: Set a global keyboard shortcut
- **Delays**: Adjust typing speed for your connection
- **Type Method**: Choose between XTest, xdotool, or ydotool
- **Confirmation**: Set threshold for paste confirmation dialog

## 🖥️ Display Server Support

| Display Server | Support Level | Notes |
|----------------|---------------|-------|
| **X11** | ✅ Full | All features work perfectly |
| **XWayland** | ✅ Full | Most apps on Wayland use this |
| **Wayland (Native)** | ✅ Good | Use ydotool for native Wayland apps |

See [wayland.md](wayland.md) for detailed Wayland information.

## 🔧 Wayland Setup (Optional)

For native Wayland applications:

```bash
# Install ydotool
sudo apt install ydotool  # or equivalent for your distro

# Enable ydotool daemon
systemctl --user enable --now ydotoold

# In LinuxClickPaste settings, select "ydotool" as the type method
```

## 🎮 Use Cases

- **VNC Sessions** - TigerVNC, RealVNC, TightVNC
- **Server Consoles** - iDRAC, iLO, IPMI
- **Virtual Machines** - VirtualBox, VMware, QEMU
- **Remote Desktop** - When clipboard sync fails
- **Web Consoles** - Cloud provider VNC consoles
- **Any Application** - That doesn't accept normal paste

## ⚙️ Advanced Configuration

### Auto-start on Login

```bash
# Create desktop entry
mkdir -p ~/.config/autostart
cp ~/.config/autostart/linuxclickpaste.desktop <<EOF
[Desktop Entry]
Type=Application
Name=LinuxClickPaste
Exec=/path/to/linuxclickpaste.py
Icon=edit-paste
Comment=Paste clipboard as keystrokes
X-GNOME-Autostart-enabled=true
EOF
```

### Custom Delays for Different Scenarios

In Settings, you can configure delays:
- **Local VMs**: 5-10ms
- **LAN VNC**: 20-50ms  
- **Remote VNC**: 50-100ms
- **Very Slow**: 200ms+

## 🐛 Troubleshooting

**"Already running" error**
- LinuxClickPaste is already in your system tray

**No system tray icon**
- Install AppIndicator support for your desktop
- GNOME: `gnome-shell-extension-appindicator`

**Hotkeys don't work on Wayland**
- Use your desktop's keyboard shortcuts to launch LinuxClickPaste
- See [wayland.md](wayland.md) for details

**Characters are dropped/garbled**
- Increase the keystroke delay in settings
- Try a different input method (xdotool/ydotool)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

## 📜 License

GPL-3.0 License - see [LICENSE](LICENSE) file

## 🙏 Acknowledgments

- Inspired by [ClickPaste for Windows](https://github.com/Collective-Software/ClickPaste)
- Thanks to the GTK and Python communities

## 📞 Support

- **Issues**: [GitHub Issues](https://github.com/dresden196/linuxclickpaste/issues)
- **Discussions**: [GitHub Discussions](https://github.com/dresden196/linuxclickpaste/discussions)

---

**Note for System Administrators**: This tool was specifically created with you in mind. No more manually typing long passwords or configuration commands into console windows that don't support paste!
