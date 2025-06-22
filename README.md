# LinuxClickPaste - Installation and Setup Guide

## Overview
LinuxClickPaste is a Linux equivalent of the Windows ClickPaste application. It allows you to paste clipboard contents as simulated keystrokes into applications that don't support regular paste functionality, such as VNC viewers, remote desktop tools, and virtual machines.

## Features
- System tray integration
- Click-to-paste functionality
- Configurable keystroke delay for compatibility with laggy connections
- Support for special characters and multi-line text
- Minimal resource usage
- GTK4-based interface

## Requirements
- Linux with X11 (Wayland support coming soon)
- Python 3.8+
- GTK 4.0
- Python libraries: PyGObject, python-xlib
- System tray support (most desktop environments)

## Installation

### 1. Install System Dependencies

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3-pip python3-gi python3-gi-cairo gir1.2-gtk-4.0 \
                 gir1.2-appindicator3-0.1 libgirepository1.0-dev gcc \
                 libcairo2-dev pkg-config python3-dev
```

**Fedora:**
```bash
sudo dnf install python3-pip python3-gobject gtk4 \
                 libappindicator-gtk3 python3-devel gcc \
                 gobject-introspection-devel cairo-devel
```

**Arch Linux:**
```bash
sudo pacman -S python-pip python-gobject gtk4 \
               libappindicator-gtk3 python-cairo
```

### 2. Install Python Dependencies
```bash
pip3 install --user python-xlib PyGObject
```

### 3. Download and Install LinuxClickPaste

#### Option A: Direct Installation
```bash
# Download the script
wget https://raw.githubusercontent.com/yourusername/linuxclickpaste/main/linuxclickpaste.py
chmod +x linuxclickpaste.py

# Move to local bin directory
mkdir -p ~/.local/bin
mv linuxclickpaste.py ~/.local/bin/linuxclickpaste

# Create desktop entry for autostart
mkdir -p ~/.config/autostart
cat > ~/.config/autostart/linuxclickpaste.desktop << EOF
[Desktop Entry]
Type=Application
Name=LinuxClickPaste
Exec=$HOME/.local/bin/linuxclickpaste
Icon=edit-paste
Comment=Paste clipboard as keystrokes
X-GNOME-Autostart-enabled=true
EOF
```

#### Option B: Git Clone
```bash
git clone https://github.com/yourusername/linuxclickpaste.git
cd linuxclickpaste
./install.sh
```

## Usage

### Basic Usage
1. **Start the application**: Run `linuxclickpaste` or click on it in your application menu
2. **Copy text**: Copy any text to your clipboard (Ctrl+C)
3. **Initiate paste**: Click the LinuxClickPaste icon in the system tray and select "Click to Paste"
4. **Select target**: Your cursor will change to a crosshair. Click where you want to paste
5. **Watch it type**: The application will simulate typing the clipboard contents

### Settings
- **Keystroke Delay**: Adjust the delay between keystrokes (in milliseconds)
  - Default: 10ms
  - For laggy VNC connections: 50-100ms
  - For very slow connections: 200ms+

### Tips for Best Results
1. **VNC/Remote Desktop**: Increase keystroke delay if characters are being dropped
2. **Special Characters**: The app handles most special characters, but some may require the target application to have the same keyboard layout
3. **Large Text**: For very large amounts of text, consider breaking it into smaller chunks
4. **Elevated Applications**: The app needs to run with the same privileges as the target application

## Troubleshooting

### Application doesn't start
- Check if all dependencies are installed: `python3 -c "import gi; gi.require_version('Gtk', '4.0')"`
- Ensure you have X11 (not pure Wayland): `echo $XDG_SESSION_TYPE`

### System tray icon not visible
- Some desktop environments hide tray icons by default
- GNOME: Install gnome-shell-extension-appindicator
- KDE: Should work out of the box
- XFCE: Check panel settings for "Status Tray Plugin"

### Characters are dropped or garbled
- Increase the keystroke delay in settings
- Ensure the target application has focus
- Check that keyboard layouts match between host and target

### Cannot paste into certain applications
- Some applications may block simulated input
- Try running LinuxClickPaste with elevated privileges if pasting into admin applications

## Building from Source

```bash
# Clone repository
git clone https://github.com/dresden196/linuxclickpaste.git
cd linuxclickpaste

# Create virtual environment (optional)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run
python3 linuxclickpaste.py
```

## Contributing
Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.

## License
GPL-3.0 License

## Comparison with Windows ClickPaste
| Feature | Windows ClickPaste | LinuxClickPaste |
|---------|-------------------|-----------------|
| System Tray | ✓ | ✓ |
| Click to Paste | ✓ | ✓ |
| Hotkey Support | ✓ | Coming Soon |
| Settings UI | ✓ | ✓ |
| Keystroke Delay | ✓ | ✓ |
| Special Characters | ✓ | ✓ |
| Multi-line Support | ✓ | ✓ |
| Wayland Support | N/A | Coming Soon |

## Future Enhancements
- [ ] Wayland support using libei
- [ ] Global hotkey configuration
- [ ] Paste history
- [ ] Smart delay (auto-adjust based on success rate)
- [ ] Multiple paste modes (line-by-line, word-by-word)
- [ ] Encryption for sensitive clipboard content
- [ ] Profile support for different applications
