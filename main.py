import sys
import os
import re
import threading
import subprocess
import adbutils

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QScrollArea, QFrame
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

class ADBApp(QMainWindow):
    log_signal = pyqtSignal(str)           # Сигнал для логирования в QTextEdit
    update_devices_signal = pyqtSignal()   # Сигнал для обновления списка устройств

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADB Device Manager")
        self.resize(900, 400)

        # Путь к APK-файлу (должен лежать рядом с main.py)
        self.apk_path = "mdmlab-MDM-launcher-6.19.apk"

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Левая панель
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # Индикатор для локального APK
        self.apk_indicator = QFrame()
        self.apk_indicator.setFixedSize(20, 20)
        self.apk_indicator.setStyleSheet("background-color: red; border: 1px solid black;")
        self.apk_label = QLabel("Checking local APK...")
        apk_layout = QHBoxLayout()
        apk_layout.addWidget(self.apk_indicator)
        apk_layout.addWidget(self.apk_label)
        left_layout.addLayout(apk_layout)

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

        # Правая панель (логи и кнопка)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        right_layout.addWidget(self.output_text)

        self.command_button = QPushButton("Install APK, Set Device Owner")
        self.command_button.setStyleSheet("font-size: 12pt; padding: 5px;")
        self.command_button.clicked.connect(self.send_command)
        right_layout.addWidget(self.command_button)

        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 2)

        # Подключаем сигнал для логов
        self.log_signal.connect(self.update_log)
        # Подключаем сигнал для обновления списка устройств
        self.update_devices_signal.connect(self.update_device_list)

        # Таймер обновления списка устройств
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_device_list)
        self.timer.start(3000)

        # Первоначальное заполнение списка
        self.update_device_list()

        # Проверяем наличие локального APK и его версию
        self.check_local_apk()

    def check_local_apk(self):
        """
        Проверяем, лежит ли локальный APK рядом с main.py и пытаемся узнать его версию через aapt.
        Если aapt недоступен или не установлен, версия будет 'unknown'.
        """
        if not os.path.exists(self.apk_path):
            self.apk_indicator.setStyleSheet("background-color: red; border: 1px solid black;")
            self.apk_label.setText("APK not found")
            return

        # Файл существует, пробуем получить версию
        version = "unknown"
        try:
            result = subprocess.run(["aapt", "dump", "badging", self.apk_path],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                import re
                match = re.search(r"versionName='([^']+)'", result.stdout)
                if match:
                    version = match.group(1)
        except Exception:
            # Если возникла ошибка (например, aapt не найден), просто оставляем "unknown"
            pass

        self.apk_indicator.setStyleSheet("background-color: green; border: 1px solid black;")
        self.apk_label.setText(f"APK found, version: {version}")

    def update_log(self, text):
        """Добавление текста в лог."""
        self.output_text.append(text)

    def update_device_list(self):
        """Обновление списка подключённых устройств."""
        # Удаляем старые записи, оставляя последний stretch
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
        """Добавление строки информации по одному устройству."""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Серийный номер
        serial_label = QLabel(device.serial)
        layout.addWidget(serial_label)

        # Проверка наличия device owner
        try:
            dump = device.shell("dumpsys device_policy")
            owner_set = ("Device Owner:" in dump)
        except Exception:
            owner_set = False

        owner_indicator = QFrame()
        owner_indicator.setFixedSize(20, 20)
        owner_color = "green" if owner_set else "red"
        owner_indicator.setStyleSheet(f"background-color: {owner_color}; border: 1px solid black;")
        layout.addWidget(owner_indicator)
        layout.addWidget(QLabel("Owner"))

        # Проверка установленного пакета
        try:
            pkg_list = device.shell("pm list packages")
            pkg_installed = ("com.hmdm.launcher" in pkg_list)
        except Exception:
            pkg_installed = False

        pkg_indicator = QFrame()
        pkg_indicator.setFixedSize(20, 20)
        pkg_color = "green" if pkg_installed else "red"
        pkg_indicator.setStyleSheet(f"background-color: {pkg_color}; border: 1px solid black;")
        layout.addWidget(pkg_indicator)
        layout.addWidget(QLabel("Launcher"))

        # Получаем версию установленного APK
        version = self.get_installed_version(device) if pkg_installed else "не установлено"
        version_label = QLabel(f"Версия: {version}")
        layout.addWidget(version_label)

        self.device_list_layout.insertWidget(0, widget)

    def get_installed_version(self, device):
        """
        Возвращает versionName пакета com.hmdm.launcher,
        извлекая его из вывода 'dumpsys package'.
        Если не найдено, вернёт 'N/A'.
        """
        try:
            pkg_info = device.shell("dumpsys package com.hmdm.launcher")
            # Ищем строку, начинающуюся с "versionName="
            for line in pkg_info.splitlines():
                line = line.strip()
                if line.startswith("versionName="):
                    return line.split("=", 1)[1].strip()
            return "N/A"
        except Exception:
            return "N/A"

    def send_command(self):
        """Обработка нажатия кнопки - установка APK и назначение Device Owner."""
        threading.Thread(target=self.run_command, daemon=True).start()

    def run_command(self):
        """
        Выполняется в отдельном потоке, чтобы не блокировать GUI.
        После установки/назначения Device Owner для каждого устройства,
        испускаем сигнал update_devices_signal, чтобы обновить индикаторы.
        """
        self.log_signal.emit("Sending command to all devices...\n")
        try:
            devices = adbutils.adb.device_list()
            if not devices:
                self.log_signal.emit("No devices connected.\n")
                return

            for device in devices:
                self.log_signal.emit(f"\nProcessing device: {device.serial}\n")

                # Проверяем, назначен ли уже device owner
                dump = device.shell("dumpsys device_policy")
                if "Device Owner:" in dump:
                    self.log_signal.emit(f"Device {device.serial} already has a device owner.\n")
                else:
                    # Установка APK (если есть локальный файл)
                    if not os.path.exists(self.apk_path):
                        self.log_signal.emit("Local APK not found. Skipping installation.\n")
                        continue

                    self.log_signal.emit("Installing APK...\n")
                    try:
                        # Если пакет уже есть, удаляем его (так как device owner нет)
                        pkg_list = device.shell("pm list packages")
                        if "com.hmdm.launcher" in pkg_list:
                            self.log_signal.emit("APK already installed, attempting to uninstall...\n")
                            try:
                                device.uninstall("com.hmdm.launcher")
                            except Exception as uninst_err:
                                self.log_signal.emit(f"Uninstall failed: {uninst_err}\n")

                        device.install(self.apk_path)
                        self.log_signal.emit("APK installed successfully.\n")
                    except Exception as e:
                        self.log_signal.emit(f"Failed to install APK on device {device.serial}: {e}\n")
                        # Переходим к следующему устройству
                        continue

                    # Повторно проверяем наличие device owner
                    dump = device.shell("dumpsys device_policy")
                    if "Device Owner:" not in dump:
                        output = device.shell("dpm set-device-owner com.hmdm.launcher/.AdminReceiver")
                        if "error" in output.lower() or "failure" in output.lower():
                            self.log_signal.emit(f"Command error on device {device.serial}: {output}\n")
                            self.log_signal.emit("Attempting to kill adb server...\n")
                            subprocess.run(["adb", "kill-server"], capture_output=True, text=True)
                            self.log_signal.emit("ADB server killed.\n")
                        else:
                            self.log_signal.emit(f"Command executed successfully on device {device.serial}.\n")

                # После обработки каждого устройства обновляем UI (в основном потоке)
                self.update_devices_signal.emit()

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
