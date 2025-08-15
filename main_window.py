import psutil
import cpuinfo
import multiprocessing
import numpy as np
import csv
import os
import time
from datetime import datetime
from PyQt5.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QFormLayout, QLabel, QLineEdit, QPushButton, QGroupBox, QFrame,
                             QMessageBox, QFileDialog, QComboBox, QStackedWidget,
                             QTextEdit, QInputDialog)
from PyQt5.QtCore import Qt, QTimer
from pyqtgraph import PlotWidget, mkPen, InfiniteLine

from stress_test import cpu_stress_worker

class MainWindow(QMainWindow):
    """
    The main window for the CPU-Monitor-Stress-Tool application.
    It contains the UI for setting parameters, starting/stopping the test,
    and viewing system metrics.
    """
    def __init__(self):
        super().__init__()

        self.setWindowTitle("CPU Monitor & Stress Tool")
        self.workers = []
        self.stress_pool = None
        self.test_end_timer = None
        self.profile_timer = QTimer()
        self.is_test_running = False

        # Data storage for the graph (stores all points, but displays last 60)
        self.max_data_points = 60 # For display only
        self.time_counter = 0
        self.test_start_time = 0
        self.event_markers = [] # Stores (timestamp, text, line_object)

        # Shared value for dynamic load control
        self.shared_load_ratio = multiprocessing.Value('d', 0.0)
        self.time_data, self.load_data, self.temp_data, self.power_data = [], [], [], []

        # For direct power reading from SysFS
        self.energy_file_path, self.max_energy_file_path = self._find_energy_files()
        self.last_energy_uj = 0
        self.last_energy_time = 0
        self.max_energy_range_uj = 0 # Will be read once



        # --- Main Layout ---
        main_layout = QHBoxLayout()

        # --- Left Panel (Controls & Info) ---
        left_panel_layout = QVBoxLayout()
        
        # Control Group - Now with Profiles
        control_group = QGroupBox("Stress Test Profile")
        control_layout = QVBoxLayout()
        self._setup_profile_controls(control_layout)
        control_group.setLayout(control_layout)

        # Action Buttons
        action_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Test")
        self.stop_button = QPushButton("Stop Test")
        self.stop_button.setEnabled(False) # Disabled by default
        action_layout.addWidget(self.start_button)
        action_layout.addWidget(self.stop_button)

        # System Info Group
        sys_info_group = QGroupBox("System Information")
        sys_info_layout = QFormLayout()
        self.cpu_model_label = QLabel("N/A")
        self.cpu_cores_label = QLabel("N/A")
        sys_info_layout.addRow("CPU Model:", self.cpu_model_label)
        sys_info_layout.addRow("Cores/Threads:", self.cpu_cores_label)
        sys_info_group.setLayout(sys_info_layout)

        # Add all widgets to the left panel
        left_panel_layout.addWidget(control_group)
        left_panel_layout.addLayout(action_layout)
        left_panel_layout.addWidget(sys_info_group)
        left_panel_layout.addStretch() # Pushes everything up

        # --- Right Panel (Monitoring & Graphs) ---
        right_panel_layout = QVBoxLayout()

        # Real-time Metrics
        metrics_group = QGroupBox("Real-time Metrics")
        metrics_layout = QFormLayout()
        self.cpu_load_label = QLabel("0 %")
        self.cpu_temp_label = QLabel("0 °C")
        self.cpu_power_label = QLabel("0 W")
        metrics_layout.addRow("Current CPU Load:", self.cpu_load_label)
        metrics_layout.addRow("CPU Temperature:", self.cpu_temp_label)
        metrics_layout.addRow("CPU Power:", self.cpu_power_label)
        metrics_group.setLayout(metrics_layout)

        # Graph Placeholder
        graph_group = QGroupBox("Data Visualization")
        graph_layout = QVBoxLayout()
        self.graph_widget = PlotWidget()
        self.graph_widget.setBackground('w')
        self.graph_widget.showGrid(x=True, y=True)
        graph_layout.addWidget(self.graph_widget)
        graph_group.setLayout(graph_layout)
        
        # Event Log
        log_group = QGroupBox("Event Log")
        log_layout = QVBoxLayout()
        self.event_log = QTextEdit()
        self.event_log.setReadOnly(True)
        log_layout.addWidget(self.event_log)
        log_group.setLayout(log_layout)

        # Action Buttons for Right Panel
        right_action_layout = QHBoxLayout()
        self.add_marker_button = QPushButton("Add Marker")
        self.export_button = QPushButton("Export Data")
        right_action_layout.addWidget(self.add_marker_button)
        right_action_layout.addWidget(self.export_button)

        right_panel_layout.addWidget(metrics_group)
        right_panel_layout.addWidget(graph_group, 1) # Give graph more space
        right_panel_layout.addWidget(log_group)
        right_panel_layout.addLayout(right_action_layout)

        # --- Assemble Main Window ---
        left_widget = QWidget()
        left_widget.setLayout(left_panel_layout)
        right_widget = QWidget()
        right_widget.setLayout(right_panel_layout)

        main_layout.addWidget(left_widget, 1) # 1/3 of the space
        main_layout.addWidget(right_widget, 2) # 2/3 of the space

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

        # Populate static info on startup
        self._populate_system_info()

        # Connect signals to slots
        self.start_button.clicked.connect(self._start_stress_test)
        self.stop_button.clicked.connect(self._stop_stress_test)
        self.add_marker_button.clicked.connect(self._add_marker)
        self.export_button.clicked.connect(self._export_data)

        # Set up the timer for real-time metrics
        self._setup_metrics_timer()

        # Set up the graph plot
        self._setup_graph()

    def _setup_profile_controls(self, parent_layout):
        """Creates the UI elements for selecting and configuring stress profiles."""
        # Profile Selector
        profile_form_layout = QFormLayout()
        self.profile_selector = QComboBox()
        self.profile_selector.addItems(["Constant", "Pulsed", "Ramp"])
        profile_form_layout.addRow("Profile Type:", self.profile_selector)
        parent_layout.addLayout(profile_form_layout)

        # --- Profile Parameters ---
        self.profile_stack = QStackedWidget()

        # Constant Profile Widget
        constant_widget = QWidget()
        constant_layout = QFormLayout()
        self.constant_load_input = QLineEdit("80")
        constant_layout.addRow("CPU Load (%):", self.constant_load_input)
        constant_widget.setLayout(constant_layout)

        # Pulsed Profile Widget
        pulsed_widget = QWidget()
        pulsed_layout = QFormLayout()
        self.pulsed_high_load_input = QLineEdit("90")
        self.pulsed_low_load_input = QLineEdit("10")
        self.pulsed_on_time_input = QLineEdit("5")
        self.pulsed_off_time_input = QLineEdit("5")
        pulsed_layout.addRow("High Load (%):", self.pulsed_high_load_input)
        pulsed_layout.addRow("Low Load (%):", self.pulsed_low_load_input)
        pulsed_layout.addRow("On Time (s):", self.pulsed_on_time_input)
        pulsed_layout.addRow("Off Time (s):", self.pulsed_off_time_input)
        pulsed_widget.setLayout(pulsed_layout)

        # Ramp Profile Widget
        ramp_widget = QWidget()
        ramp_layout = QFormLayout()
        self.ramp_start_load_input = QLineEdit("10")
        self.ramp_end_load_input = QLineEdit("100")
        ramp_layout.addRow("Start Load (%):", self.ramp_start_load_input)
        ramp_layout.addRow("End Load (%):", self.ramp_end_load_input)
        ramp_widget.setLayout(ramp_layout)

        self.profile_stack.addWidget(constant_widget)
        self.profile_stack.addWidget(pulsed_widget)
        self.profile_stack.addWidget(ramp_widget)
        parent_layout.addWidget(self.profile_stack)

        # General Duration Input
        duration_form_layout = QFormLayout()
        self.duration_input = QLineEdit("60")
        duration_form_layout.addRow("Total Duration (s):", self.duration_input)
        parent_layout.addLayout(duration_form_layout)

        self.profile_selector.currentIndexChanged.connect(self.profile_stack.setCurrentIndex)

    def _find_energy_files(self):
        """
        Finds the path to the CPU package energy file ('energy_uj') and the
        max energy file ('max_energy_range_uj') in SysFS.
        It specifically looks for the 'package-0' sensor.
        """
        base_path = "/sys/class/powercap/"
        try:
            if not os.path.exists(base_path):
                return None, None
            
            for entry in os.listdir(base_path):
                if 'intel-rapl' in entry and os.path.isdir(os.path.join(base_path, entry)):
                    try:
                        name_path = os.path.join(base_path, entry, "name")
                        with open(name_path, 'r') as f:
                            sensor_name = f.read().strip()
                        
                        if sensor_name == 'package-0':
                            energy_path = os.path.join(base_path, entry, "energy_uj")
                            max_energy_path = os.path.join(base_path, entry, "max_energy_range_uj")
                            
                            if os.path.exists(energy_path) and os.path.exists(max_energy_path):
                                print(f"DEBUG: Found CPU package-0 energy file at: {energy_path}")
                                return energy_path, max_energy_path
                    except (FileNotFoundError, PermissionError):
                        continue # Check the next entry
        except (FileNotFoundError, PermissionError):
            return None, None
        return None, None

    def _get_cpu_model_name(self):
        """
        Fetches the CPU model name in a cross-platform way.
        """
        try:
            return cpuinfo.get_cpu_info()['brand_raw']
        except Exception:
            return "N/A"  # Fallback in case of error

    def _populate_system_info(self):
        """
        Fetches static system information and updates the UI labels.
        """
        self.cpu_model_label.setText(self._get_cpu_model_name())

        logical_cores = psutil.cpu_count(logical=True)
        physical_cores = psutil.cpu_count(logical=False)
        self.cpu_cores_label.setText(f"{logical_cores} Threads ({physical_cores} Cores)")

    def _setup_metrics_timer(self):
        """
        Initializes and starts a QTimer to periodically update real-time metrics.
        """
        # Initialize cpu_percent. The first call returns 0.0 or a meaningless value;
        # subsequent calls with an interval will be correct.
        psutil.cpu_percent(interval=None)

        self.metrics_timer = QTimer()
        self.metrics_timer.timeout.connect(self._update_metrics)
        self.metrics_timer.start(1000)  # Update every 1000 ms (1 second)

    def _setup_graph(self):
        """
        Configures the pyqtgraph PlotWidget, setting up curves and labels.
        """
        self.graph_widget.setLabel('left', 'Value')
        self.graph_widget.setLabel('bottom', 'Time (s)')
        self.graph_widget.addLegend()
        self.load_curve = self.graph_widget.plot(pen=mkPen('b', width=2), name="Load (%)")
        self.temp_curve = self.graph_widget.plot(pen=mkPen('r', width=2), name="Temp (°C)")
        self.power_curve = self.graph_widget.plot(pen=mkPen('g', width=2), name="Power (W)")

    def _add_marker(self):
        """Adds a user-defined event marker to the log and graph."""
        if not self.is_test_running:
            QMessageBox.information(self, "Marker Info", "Markers can only be added during a test.")
            return

        text, ok = QInputDialog.getText(self, 'Add Event Marker', 'Enter marker text:')
        if ok and text:
            timestamp = self.time_counter
            marker_line = InfiniteLine(pos=timestamp, angle=90, movable=False, pen=mkPen('k', style=Qt.DashLine))
            self.graph_widget.addItem(marker_line)
            self.event_markers.append((timestamp, text, marker_line))
            self._log_event(f"Marker added: {text}")


    def _update_metrics(self):
        """
        Fetches real-time system metrics and updates the UI labels.
        This method is called by the QTimer.
        """
        # Update CPU Load
        cpu_load = psutil.cpu_percent(interval=None)
        self.load_data.append(cpu_load)
        self.cpu_load_label.setText(f"{cpu_load:.1f} %")

        # Update CPU Temperature (more robustly)
        temp_val = np.nan # Default to Not a Number if not found
        all_temps = []
        try:
            temp_stats = psutil.sensors_temperatures()
            if temp_stats:
                # Collect all available temperature readings from all sensors
                for name, entries in temp_stats.items():
                    for entry in entries:
                        if entry.current is not None:
                            all_temps.append(entry.current)
            
            if all_temps:
                # Display the maximum temperature found, which is usually the CPU core temp
                temp_val = max(all_temps)
                self.cpu_temp_label.setText(f"{temp_val:.1f} °C")
            else:
                self.cpu_temp_label.setText("N/A")
        except (AttributeError, KeyError):
            self.cpu_temp_label.setText("N/A")
        self.temp_data.append(temp_val)

        # Update CPU Power (Direct SysFS method)
        power_val = np.nan
        if self.energy_file_path:
            try:
                # Read the max energy value once if we haven't already
                if self.max_energy_range_uj == 0 and self.max_energy_file_path:
                    with open(self.max_energy_file_path, 'r') as f:
                        self.max_energy_range_uj = int(f.read())

                with open(self.energy_file_path, 'r') as f:
                    current_energy_uj = int(f.read())
                current_time = time.time()

                # We need two readings to calculate power over time
                if self.last_energy_time > 0:
                    delta_energy = current_energy_uj - self.last_energy_uj
                    delta_time = current_time - self.last_energy_time

                    # Handle counter rollover
                    if delta_energy < 0:
                        delta_energy += self.max_energy_range_uj

                    if delta_time > 0:
                        # Power (W) = Joules / second = (uJ / 1e6) / s
                        power_watts = (delta_energy / 1e6) / delta_time
                        power_val = power_watts
                        self.cpu_power_label.setText(f"{power_val:.2f} W")
                else:
                    self.cpu_power_label.setText("...")

                self.last_energy_uj = current_energy_uj
                self.last_energy_time = current_time
            except (PermissionError, FileNotFoundError, ValueError):
                self.cpu_power_label.setText("N/A (Access Error)")
                self.energy_file_path = None  # Stop trying if it fails
        else:
            self.cpu_power_label.setText("N/A (No Sensor)")
        self.power_data.append(power_val)

        # Update time and graph
        self.time_counter += 1
        self.time_data.append(self.time_counter)
        
        # Get the last N points for display to keep the graph clean
        display_time = self.time_data[-self.max_data_points:]
        display_load = self.load_data[-self.max_data_points:]
        display_temp = self.temp_data[-self.max_data_points:]
        display_power = self.power_data[-self.max_data_points:]

        self.load_curve.setData(display_time, display_load)
        self.temp_curve.setData(display_time, display_temp)
        self.power_curve.setData(display_time, display_power)

    def _reset_graph_data(self):
        """Clears all data from the graph to start a new test."""
        # Clear data lists
        self.time_counter = 0
        self.time_data.clear()
        self.load_data.clear()
        self.temp_data.clear()
        self.power_data.clear()
        
        # Clear event log and markers
        self.event_log.clear()
        for _, _, line in self.event_markers:
            self.graph_widget.removeItem(line)
        self.event_markers.clear()

    def _log_event(self, message):
        """Appends a timestamped message to the event log."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.event_log.append(f"[{timestamp}] {message}")

    def _start_stress_test(self):
        """
        Validates inputs, selects a profile, and starts the stress test.
        """
        self._reset_graph_data()
        self.current_profile = self.profile_selector.currentText()

        try:
            # General duration
            self.total_duration = int(self.duration_input.text())

            # Profile-specific parameter validation & set initial ratio
            if self.current_profile == "Constant":
                load = int(self.constant_load_input.text())
                self.shared_load_ratio.value = max(0, min(load, 100)) / 100.0
            elif self.current_profile == "Pulsed":
                self.pulsed_high = int(self.pulsed_high_load_input.text()) / 100.0
                self.pulsed_low = int(self.pulsed_low_load_input.text()) / 100.0
                self.pulsed_on_time = int(self.pulsed_on_time_input.text())
                self.pulsed_off_time = int(self.pulsed_off_time_input.text())
                self.shared_load_ratio.value = self.pulsed_high
            elif self.current_profile == "Ramp":
                self.ramp_start = int(self.ramp_start_load_input.text()) / 100.0
                self.ramp_end = int(self.ramp_end_load_input.text()) / 100.0
                self.shared_load_ratio.value = self.ramp_start

            # ====== 關鍵：先記錄開始時間 ======
            self.test_start_time = time.time()

            # 建立一個 worker 針對每個邏輯核心（你可改成 physical cores）
            num_cores = psutil.cpu_count(logical=True)
            from stress_test import cpu_stress_worker  # 避免循環匯入問題

            self.workers = []
            for core_id in range(num_cores):
                p = multiprocessing.Process(
                    target=cpu_stress_worker,
                    args=(self.shared_load_ratio, core_id, True),  # True=綁核心，想關閉就改 False
                    daemon=True
                )
                p.start()
                self.workers.append(p)

            # 啟動 profile 計時器（若需要）
            if self.current_profile != "Constant":
                # 先保險地斷開舊連線
                try:
                    self.profile_timer.timeout.disconnect(self._update_load_profile)
                except Exception:
                    pass
                self.profile_timer.timeout.connect(self._update_load_profile)
                self.profile_timer.start(250)  # 每 0.25s 更新一次 ratio

            # 自動停止計時器
            if self.test_end_timer:
                self.test_end_timer.stop()
            self.test_end_timer = QTimer()
            self.test_end_timer.setSingleShot(True)
            self.test_end_timer.timeout.connect(self._stop_stress_test)
            self.test_end_timer.start(self.total_duration * 1000)

            # 更新 UI 狀態與 log
            self.start_button.setEnabled(False)
            self.stop_button.setEnabled(True)
            self._log_event(f"Started '{self.current_profile}' test on {num_cores} cores for {self.total_duration}s.")
            self.is_test_running = True


        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid integer values for CPU Load and Duration.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")


    def _update_load_profile(self):
        """
        Called by a timer to dynamically update the shared load value
        based on the selected profile.
        """
        elapsed_time = time.time() - self.test_start_time

        if self.current_profile == "Pulsed":
            cycle_time = self.pulsed_on_time + self.pulsed_off_time
            position_in_cycle = elapsed_time % cycle_time
            if position_in_cycle < self.pulsed_on_time:
                self.shared_load_ratio.value = self.pulsed_high
            else:
                self.shared_load_ratio.value = self.pulsed_low

        elif self.current_profile == "Ramp":
            progress = min(elapsed_time / self.total_duration, 1.0)
            current_load = self.ramp_start + (self.ramp_end - self.ramp_start) * progress
            self.shared_load_ratio.value = current_load

    def _stop_stress_test(self):
        """
        Stops the currently running CPU stress test processes.
        """
        # 停掉 profile timer
        if self.profile_timer.isActive():
            self.profile_timer.stop()
            try:
                self.profile_timer.timeout.disconnect(self._update_load_profile)
            except TypeError:
                pass

        # 停掉 auto-stop timer（若是手動按下 Stop）
        if self.test_end_timer and self.test_end_timer.isActive():
            self.test_end_timer.stop()

        # 結束所有自管的 worker processes
        if getattr(self, "workers", None):
            for p in self.workers:
                try:
                    p.terminate()
                except Exception:
                    pass
            for p in self.workers:
                try:
                    p.join(timeout=1.0)
                except Exception:
                    pass
            self.workers = []

        # 為了相容舊欄位，確保 pool 不再使用
        if self.stress_pool:
            try:
                self.stress_pool.terminate()
                self.stress_pool.join()
            except Exception:
                pass
            self.stress_pool = None

        self._log_event("Stress test stopped.")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.is_test_running = False

    def closeEvent(self, event):
        """
        Ensure the stress test process is terminated when the window is closed.
        """
        self._stop_stress_test()
        event.accept()

    def _export_data(self):
        """
        Exports the collected metrics from the entire test run to a CSV file.
        """
        if not self.time_data:
            QMessageBox.warning(self, "Export Error", "No data has been recorded to export.")
            return

        # Generate a default filename with a timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"cpu_stress_test_{timestamp}.csv"

        # Open a file dialog to ask the user for a save location
        options = QFileDialog.Options()
        filePath, _ = QFileDialog.getSaveFileName(self, "Save Data File", default_filename, "CSV Files (*.csv);;All Files (*)", options=options)

        if filePath:
            try:
                with open(filePath, 'w', newline='') as csvfile:
                    writer = csv.writer(csvfile)
                    # Write data header
                    writer.writerow(['Time (s)', 'CPU Load (%)', 'Temperature (C)', 'Power (W)'])
                    # Write data rows
                    for i in range(len(self.time_data)):
                        writer.writerow([
                            self.time_data[i],
                            f"{self.load_data[i]:.2f}",
                            f"{self.temp_data[i]:.2f}" if not np.isnan(self.temp_data[i]) else "N/A",
                            f"{self.power_data[i]:.2f}" if not np.isnan(self.power_data[i]) else "N/A"
                        ])
                    
                    # Write event markers if any exist
                    if self.event_markers:
                        writer.writerow([]) # Blank row for separation
                        writer.writerow(['--- Event Markers ---'])
                        writer.writerow(['Time (s)', 'Event'])
                        for timestamp, text, _ in self.event_markers:
                            writer.writerow([timestamp, text])

                QMessageBox.information(self, "Export Successful", f"Data successfully exported to:\n{filePath}")
            except Exception as e:
                QMessageBox.critical(self, "Export Failed", f"An error occurred while exporting data:\n{e}")