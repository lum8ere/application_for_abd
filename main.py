import sys
import threading
import subprocess
import adbutils

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QScrollArea, QFrame
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

class ADBApp(QMainWindow):
    log_signal = pyqtSignal(str)  # Сигнал для обновления логов

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADB Device Manager")
        self.resize(900, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Левая панель для списка устройств
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        title_label = QLabel("Connected Devices")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 14pt;")
        left_layout.addWidget(title_label)

        # Область прокрутки для списка устройств
        self.device_scroll = QScrollArea()
        self.device_scroll.setWidgetResizable(True)
        self.device_list_widget = QWidget()
        self.device_list_layout = QVBoxLayout(self.device_list_widget)
        self.device_list_layout.addStretch()
        self.device_scroll.setWidget(self.device_list_widget)
        left_layout.addWidget(self.device_scroll)

        # Правая панель для вывода и кнопки
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        right_layout.addWidget(self.output_text)
        self.command_button = QPushButton("Set Device Owner")
        self.command_button.setStyleSheet("font-size: 12pt; padding: 5px;")
        self.command_button.clicked.connect(self.send_command)
        right_layout.addWidget(self.command_button)

        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 2)

        # Подключаем сигнал для обновления логов
        self.log_signal.connect(self.update_log)

        # Обновление списка устройств каждые 3 секунды
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_device_list)
        self.timer.start(3000)

        self.update_device_list()

    def update_log(self, text):
        """Слот для обновления виджета логов."""
        self.output_text.append(text)

    def update_device_list(self):
        """Обновление списка подключённых устройств."""
        # Удаляем старые записи, оставляя последний spacer
        while self.device_list_layout.count() > 1:
            item = self.device_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        try:
            devices = adbutils.adb.device_list()
            if devices:
                for device in devices:
                    self.add_device_entry(device)
            else:
                label = QLabel("No devices connected")
                self.device_list_layout.insertWidget(0, label)
        except Exception as e:
            label = QLabel(f"Error: {e}")
            label.setStyleSheet("color: red;")
            self.device_list_layout.insertWidget(0, label)

    def add_device_entry(self, device):
        """Добавление записи для одного устройства."""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Отображение серийного номера
        serial_label = QLabel(device.serial)
        layout.addWidget(serial_label)

        # Проверка наличия device owner через dumpsys device_policy
        try:
            dump = device.shell("dumpsys device_policy")
            owner_set = "Device Owner:" in dump
        except Exception:
            owner_set = False

        owner_indicator = QFrame()
        owner_indicator.setFixedSize(20, 20)
        owner_color = "green" if owner_set else "red"
        owner_indicator.setStyleSheet(f"background-color: {owner_color}; border: 1px solid black;")
        layout.addWidget(owner_indicator)
        layout.addWidget(QLabel("Owner"))

        # Проверка установленного пакета com.hmdm.launcher
        try:
            pkg_list = device.shell("pm list packages")
            pkg_installed = "com.hmdm.launcher" in pkg_list
        except Exception:
            pkg_installed = False

        pkg_indicator = QFrame()
        pkg_indicator.setFixedSize(20, 20)
        pkg_color = "green" if pkg_installed else "red"
        pkg_indicator.setStyleSheet(f"background-color: {pkg_color}; border: 1px solid black;")
        layout.addWidget(pkg_indicator)
        layout.addWidget(QLabel("Launcher"))

        self.device_list_layout.insertWidget(0, widget)

    def send_command(self):
        """Запуск выполнения команды для всех устройств в отдельном потоке."""
        threading.Thread(target=self.run_command, daemon=True).start()

    def run_command(self):
        self.log_signal.emit("Sending command to all devices...\n")
        try:
            devices = adbutils.adb.device_list()
            if not devices:
                self.log_signal.emit("No devices connected.\n")
                return

            for device in devices:
                self.log_signal.emit(f"\nProcessing device: {device.serial}\n")
                dump = device.shell("dumpsys device_policy")
                if "Device Owner:" in dump:
                    self.log_signal.emit(f"Device {device.serial} already has a device owner.\n")
                    continue

                pkg_list = device.shell("pm list packages")
                if "com.hmdm.launcher" not in pkg_list:
                    self.log_signal.emit(f"Package 'com.hmdm.launcher' is missing on {device.serial}.\n")
                    continue

                output = device.shell("dpm set-device-owner com.hmdm.launcher/.AdminReceiver")
                if "error" in output.lower() or "failure" in output.lower():
                    self.log_signal.emit(f"Command error on device {device.serial}: {output}\n")
                    self.log_signal.emit("Attempting to kill adb server...\n")
                    subprocess.run(["adb", "kill-server"], capture_output=True, text=True)
                    self.log_signal.emit("ADB server killed.\n")
                else:
                    self.log_signal.emit(f"Command executed successfully on device {device.serial}.\n")
        except Exception as e:
            self.log_signal.emit(f"Exception occurred: {e}\n")
            self.log_signal.emit("Attempting to kill adb server...\n")
            try:
                subprocess.run(["adb", "kill-server"], capture_output=True, text=True)
                self.log_signal.emit("ADB server killed.\n")
            except Exception as kill_e:
                self.log_signal.emit(f"Failed to kill adb server: {kill_e}\n")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ADBApp()
    window.show()
    sys.exit(app.exec())
