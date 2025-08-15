## CPU Monitor & Stress Tool

A one-stop GUI for **controllable CPU load generation** and **real-time monitoring** on Linux.  
It integrates multiple load profiles (Constant / Pulsed / Ramp), live charts (Load / Temp / Power),  
event markers, and CSV export — so performance engineers and researchers can test and log quickly  
without juggling many terminals.

![screenshot](docs/demo.png)  
*(Add 1–2 screenshots under `docs/` and update the path here.)*

---

## ✨ Features

- **Load Profiles**
  - **Constant**: maintain a fixed load percentage.
  - **Pulsed**: alternate between high/low load to simulate bursty workloads.
  - **Ramp**: linearly increase load to observe dynamic response.

- **Real-time Monitoring**
  - CPU **Load (%)**
  - CPU **Temperature (°C)**
  - CPU **Power (W)** via Intel RAPL (`/sys/class/powercap/...`).

- **Data Export**: export full test data (Load/Temp/Power + event markers) to CSV.
- **Event Markers**: add vertical markers on the chart with notes during a run.
- **System Info**: CPU model, cores/threads.

---

## 📦 Installation & Run

### Option A — Download a Prebuilt Binary (Recommended)
1. Go to **Releases** and download the Linux binary.
2. Run:
   ```bash
   chmod +x CPU-Monitor-Stress-Tool
   ./CPU-Monitor-Stress-Tool

### Option B — Run from Source

```bash
git clone https://github.com/PME26Elvis/CPU-Monitor-Stress-Tool.git
cd CPU-Monitor-Stress-Tool
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
```

### Dependencies

See `requirements.txt`:

* PyQt5
* psutil (≥5.8.0)
* pyqtgraph
* py-cpuinfo
* numpy

---

## 🔐 Intel RAPL Permissions (Read CPU Power Without sudo)

By default, reading `/sys/class/powercap/intel-rapl:*` may require root.
To allow a normal user to read CPU power:

```bash
# 1) Make RAPL readable for the "power" group
echo 'SUBSYSTEM=="powercap", KERNEL=="intel-rapl:*", MODE="0644", GROUP="power"' | \
sudo tee /etc/udev/rules.d/90-intel-rapl.rules

# 2) Add your user to the group
sudo groupadd -f power
sudo usermod -aG power $USER

# 3) Reload & trigger udev, then re-login (or reboot)
sudo udevadm control --reload
sudo udevadm trigger
```

If you must run with sudo (not recommended for GUI), preserve desktop env vars:

```bash
sudo -E env XDG_RUNTIME_DIR=/run/user/$(id -u) ./CPU-Monitor-Stress-Tool
```

---

## 🖥️ How It Works

* **GUI / Plotting**: PyQt5 + pyqtgraph
* **System Metrics**: psutil, py-cpuinfo
* **CPU Power**: Intel RAPL via SysFS energy counters
* **Load Generation**: multiprocessing workers with busy-wait loops tuned by a shared `Value` (see `stress_test.py`)

---

## 🏗️ Build a Standalone Binary (PyInstaller)

For maintainers who want to ship a self-contained binary.

```bash
pip install pyinstaller

# Optional: create a spec for hidden imports
pyi-makespec --onefile --name CPU-Monitor-Stress-Tool --paths . main.py
```

In the generated `.spec`, add:

```python
hiddenimports=['main_window', 'stress_test']
```

Build:

```bash
pyinstaller CPU-Monitor-Stress-Tool.spec --clean
```

The binary will appear under `dist/`.

---

## 📊 CSV Export Format

```
Time (s), CPU Load (%), Temperature (C), Power (W)
...
--- Event Markers ---
Time (s), Event
<seconds>, <text>
```

---

## 🚀 Usage Tips

* Use **Pulsed** and **Ramp** profiles to study transient response (thermal throttling, boost behavior).
* Add markers at key moments (e.g., “fan ramp”, “profile switch”) to align events in post-analysis.

---

## 🧩 Troubleshooting

**Power shows N/A**

* RAPL counters not available or not readable. Apply the udev rule above, re-login, or try sudo.

**Qt platform plugin xcb error**

* Install missing libs:

```bash
sudo apt-get update
sudo apt-get install -y libxcb-cursor0 libxkbcommon-x11-0 libglu1-mesa
```

**Low load on high-end CPUs**

* The busy-wait loop depends on previous iteration state to prevent optimizations (see `stress_test.py`).

---

## 📷 Screenshots / Demo

* `docs/demo.png` — main window (plots + metrics + controls)
* `docs/markers.png` — example with event markers and CSV snippet

---

## 🤝 Contributing

* Small features: open a concise PR with before/after screenshots if UI is affected.
* Large changes: file an issue first to align on approach.

---

## 📜 License

MIT
