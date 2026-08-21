# AlmaLinux VPS Deployment Guide for Multi-LLM Consensus Bot

This guide explains how to deploy and run your bot on an **AlmaLinux VPS**.

Since MetaTrader 5 (MT5) and its Python library are Windows-only, the bot uses **Wine** (a compatibility layer to run Windows apps on Linux) and **Xvfb** (a virtual display server so the MT5 GUI can run in the background).

We have updated the bot's code to automatically detect if it is running on Linux and switch to the **`mt5linux`** bridge library. On Windows, it will continue to run natively without changes.

---

## 📋 Prerequisites on AlmaLinux

Ensure you have:
- Root or `sudo` access to the AlmaLinux VPS
- At least 2GB RAM (4GB recommended for Wine + MT5)

---

## 🛠️ Step-by-Step Installation

### Step 1: Install Wine & Xvfb (Virtual Screen)

Open your VPS terminal and execute the following commands:

```bash
# 1. Update system packages
sudo dnf update -y

# 2. Enable EPEL repository (required for Xvfb and Wine dependencies)
sudo dnf install -y epel-release

# 3. Add WineHQ repository for AlmaLinux (example for AlmaLinux 9)
sudo dnf config-manager --add-repo https://dl.winehq.org/wine-builds/almalinux/9/winehq.repo

# 4. Install Wine and Xvfb
sudo dnf install -y winehq-stable xorg-x11-server-Xvfb mesa-libGL
```

*(If you are on AlmaLinux 8, replace `/9/` with `/8/` in the repository URL).*

---

### Step 2: Install MT5 under Wine

MetaQuotes provides an official script to install MT5 on Linux:

```bash
# 1. Download the official installer script
wget https://download.terminal.free/cdn/web/metaquotes.software.corp/mt5/mt5linux.sh

# 2. Make it executable
chmod +x mt5linux.sh

# 3. Run the installer (this configures the Wine prefix and downloads MT5)
./mt5linux.sh
```

During this process, Wine will create a virtual Windows C: drive on your server at `~/.mt5/drive_c/`.

---

### Step 3: Install the `mt5linux` Library & Bot Dependencies

On your VPS, install the Python requirements:

```bash
# 1. Install pip package manager if not already installed
sudo dnf install -y python3-pip

# 2. Install native dependencies
pip3 install pandas numpy ta openai google-generativeai python-dotenv requests

# 3. Install the mt5linux bridge library
pip3 install mt5linux
```

---

### Step 4: Run the Virtual Display (Xvfb)

MT5 requires a display environment to run. Since your VPS is headless (no monitor), we create a virtual one:

```bash
# Start Xvfb virtual display in the background
Xvfb :1 -screen 0 1024x768x16 &

# Tell the terminal to direct GUI outputs to our virtual screen
export DISPLAY=:1
```

---

### Step 5: Start the MT5 Linux Server Bridge

The `mt5linux` library communicates with MT5 via a small helper program `mt5server.exe` running inside Wine:

```bash
# Run the mt5server inside Wine in the background
wine ~/.mt5/drive_c/Program\ Files/MetaTrader\ 5/mt5server.exe &
```

---

### Step 6: Configure `.env` & Start the Bot

1. Move your code files to the VPS (using `git clone` or `sftp`).
2. Create your `.env` file containing your API keys and MT5 account login details.
3. Start the bot:
   ```bash
   python3 main.py
   ```

---

## 🔄 Keeping the Bot Running 24/7

To prevent the bot and virtual screen from stopping when you close your SSH terminal, use **`screen`** or **`tmux`**:

```bash
# 1. Install screen
sudo dnf install -y screen

# 2. Start a new session
screen -S tradingbot

# 3. Inside the session, start Xvfb, mt5server, and the bot:
export DISPLAY=:1
Xvfb :1 -screen 0 1024x768x16 &
wine ~/.mt5/drive_c/Program\ Files/MetaTrader\ 5/mt5server.exe &
python3 main.py

# 4. Detach from session by pressing: Ctrl + A, then D
# You can now safely close your SSH terminal.

# 5. To re-attach to the session later:
screen -r tradingbot
```
