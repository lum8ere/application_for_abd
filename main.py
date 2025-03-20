import sys
import os
import re
import threading
import subprocess
import adbutils
import tempfile

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QScrollArea, QFrame, QFileDialog
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal

class ADBApp(QMainWindow):
    log_signal = pyqtSignal(str)           # Сигнал для логирования в QTextEdit
    update_devices_signal = pyqtSignal()   # Сигнал для обновления списка устройств

    def __init__(self):
        super().__init__()
        self.setWindowTitle("ADB Device Manager")
        self.resize(900, 400)

        # Путь к временно загруженному APK (изначально None)
        self.temp_apk_path = None

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        # Левая панель (управление и список устройств)
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # Кнопка для выбора (загрузки) APK
        self.load_apk_button = QPushButton("Load APK")
        self.load_apk_button.setStyleSheet("font-size: 12pt; padding: 5px;")
        self.load_apk_button.clicked.connect(self.load_apk)
        left_layout.addWidget(self.load_apk_button)

        # Индикатор загруженного APK
        self.apk_indicator = QFrame()
        self.apk_indicator.setFixedSize(20, 20)
        self.apk_indicator.setStyleSheet("background-color: red; border: 1px solid black;")
        self.apk_label = QLabel("No APK loaded")
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

        # Правая панель (логи и кнопка запуска установки)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.output_text = QTextEdit()
        self.output_text.setReadOnly(True)
        right_layout.addWidget(self.output_text)

        # Кнопка установки и назначения Device Owner
        self.command_button = QPushButton("Install APK, Set Device Owner")
        # Изначально кнопка заблокирована и курсор показывает, что она недоступна.
        self.command_button.setEnabled(False)
        self.command_button.setCursor(Qt.CursorShape.ForbiddenCursor)
        self.command_button.setStyleSheet("font-size: 12pt; padding: 5px;")  # стандартное оформление
        self.command_button.clicked.connect(self.send_command)
        right_layout.addWidget(self.command_button)

        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 2)

        # Подключение сигналов
        self.log_signal.connect(self.update_log)
        self.update_devices_signal.connect(self.update_device_list)

        # Таймер обновления списка устройств
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_device_list)
        self.timer.start(3000)

        # Первоначальное обновление списка устройств
        self.update_device_list()

    def load_apk(self):
        """Открываем диалог для выбора APK и копируем выбранный файл во временное место."""
        # options = QFileDialog.Options()
        file_path, _ = QFileDialog.getOpenFileName(self, "Select APK file", "", "APK Files (*.apk);;All Files (*)")
        if file_path:
            # Если ранее был загружен файл, удаляем его
            if self.temp_apk_path and os.path.exists(self.temp_apk_path):
                try:
                    os.remove(self.temp_apk_path)
                except Exception as e:
                    self.log_signal.emit(f"Error removing previous temporary APK: {e}")
            # Создаём временный файл и копируем в него выбранный APK
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".apk") as tmp_file:
                    temp_file_path = tmp_file.name
                    with open(file_path, "rb") as src:
                        tmp_file.write(src.read())
                self.temp_apk_path = temp_file_path
                self.log_signal.emit(f"Loaded APK from {file_path} into temporary file {self.temp_apk_path}.")
                self.check_loaded_apk()
            except Exception as e:
                self.log_signal.emit(f"Failed to load APK: {e}")

    def check_loaded_apk(self):
        """
        Проверяем загруженный временный APK (через aapt) и обновляем индикатор.
        Для корректной работы требуется, чтобы утилита aapt была доступна в PATH.
        """
        if not self.temp_apk_path or not os.path.exists(self.temp_apk_path):
            self.apk_indicator.setStyleSheet("background-color: red; border: 1px solid black;")
            self.apk_label.setText("No APK loaded")
            self.command_button.setEnabled(False)
            self.command_button.setCursor(Qt.CursorShape.ForbiddenCursor)
            return

        version = "unknown"
        try:
            result = subprocess.run(["aapt", "dump", "badging", self.temp_apk_path],
                                    capture_output=True, text=True)
            if result.returncode == 0:
                match = re.search(r"versionName='([^']+)'", result.stdout)
                if match:
                    version = match.group(1)
        except Exception:
            pass

        self.apk_indicator.setStyleSheet("background-color: green; border: 1px solid black;")
        filename = os.path.basename(self.temp_apk_path)
        self.apk_label.setText(f"Loaded: {filename}, version: {version}")
        # Активируем кнопку и меняем курсор на указывающий (hand)
        self.command_button.setEnabled(True)
        self.command_button.setCursor(Qt.CursorShape.PointingHandCursor)

    def update_log(self, text: str):
        """Добавление текста в лог (правый виджет)."""
        self.output_text.append(text)

    def update_device_list(self):
        """Обновление списка подключённых устройств с отображением статусов."""
        # Удаляем старые записи, оставляя последний stretch
        while self.device_list_layout.count() > 1:
            item = self.device_list_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        try:
            # self.log_signal.emit("Updating device list...")
            devices = adbutils.adb.device_list()
            # self.log_signal.emit(f"Found {len(devices)} device(s) connected.")
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
        """Формирование строки информации для одного устройства."""
        widget = QWidget()
        layout = QHBoxLayout(widget)

        # Серийный номер
        serial_label = QLabel(device.serial)
        layout.addWidget(serial_label)

        # Проверка наличия Device Owner
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

        # Проверка установленного пакета Launcher
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

        # Получение версии установленного APK на устройстве
        version = self.get_installed_version(device) if pkg_installed else "not installed"
        version_label = QLabel(f"Version: {version}")
        layout.addWidget(version_label)

        self.device_list_layout.insertWidget(0, widget)

    def get_installed_version(self, device):
        """
        Извлечение versionName установленного пакета через 'dumpsys package com.hmdm.launcher'.
        Если не найдено, возвращает "N/A".
        """
        try:
            pkg_info = device.shell("dumpsys package com.hmdm.launcher")
            for line in pkg_info.splitlines():
                line = line.strip()
                if line.startswith("versionName="):
                    return line.split("=", 1)[1].strip()
            return "N/A"
        except Exception:
            return "N/A"

    def send_command(self):
        """Обработка нажатия кнопки: установка APK и назначение Device Owner."""
        threading.Thread(target=self.run_command, daemon=True).start()

    def run_command(self):
        """
        Для каждого устройства:
          - Проверяется наличие Device Owner.
          - Если его нет, производится установка APK (с использованием временного файла).
          - После установки пытаемся назначить Device Owner.
        После каждого устройства обновляется UI.
        """
        self.log_signal.emit("=== Starting bulk operation for all devices ===")
        try:
            devices = adbutils.adb.device_list()
            if not devices:
                self.log_signal.emit("No devices connected. Operation aborted.")
                return

            self.log_signal.emit(f"Total devices to process: {len(devices)}")

            for idx, device in enumerate(devices, start=1):
                self.log_signal.emit(f"\n--- Processing device #{idx}: {device.serial} ---")

                # Проверяем наличие Device Owner
                self.log_signal.emit("Checking if Device Owner is already set...")
                dump = device.shell("dumpsys device_policy")
                if "Device Owner:" in dump:
                    self.log_signal.emit("Device Owner is already set. Skipping installation/owner setup.")
                else:
                    # Проверяем, загружен ли APK
                    if not self.temp_apk_path or not os.path.exists(self.temp_apk_path):
                        self.log_signal.emit("No APK loaded. Please load an APK first. Skipping this device.")
                        continue

                    self.log_signal.emit("Attempting to install the launcher APK...")

                    # Если пакет уже установлен, удаляем его
                    pkg_list = device.shell("pm list packages")
                    if "com.hmdm.launcher" in pkg_list:
                        self.log_signal.emit("Launcher package already installed. Uninstalling it first...")
                        try:
                            uninstall_result = device.uninstall("com.hmdm.launcher")
                            self.log_signal.emit(f"Uninstall result: {uninstall_result}")
                        except Exception as uninst_err:
                            self.log_signal.emit(f"Uninstall failed: {uninst_err}")

                    # Устанавливаем APK из памяти (используя временный файл)
                    install_result = self.install_apk_from_memory(device, self.temp_apk_path)
                    self.log_signal.emit(f"Install result: {install_result}")

                    # Проверка и установка Device Owner, если необходимо
                    self.log_signal.emit("Re-checking Device Owner after install...")
                    dump = device.shell("dumpsys device_policy")
                    if "Device Owner:" not in dump:
                        self.log_signal.emit("Device Owner is not set. Attempting to set it now...")
                        output = device.shell("dpm set-device-owner com.hmdm.launcher/.AdminReceiver")
                        self.log_signal.emit(f"Device owner command result: {output}")
                        if "error" in output.lower() or "failure" in output.lower():
                            self.log_signal.emit("Error setting Device Owner. Attempting to kill ADB server.")
                            subprocess.run(["adb", "kill-server"], capture_output=True, text=True)
                            self.log_signal.emit("ADB server killed.")
                        else:
                            self.log_signal.emit("Device Owner set successfully.")
                    else:
                        self.log_signal.emit("Device Owner is now set.")

                # Обновляем UI для данного устройства
                self.log_signal.emit("Updating UI for this device...")
                self.update_devices_signal.emit()

            self.log_signal.emit("\n=== All devices have been processed. ===")

        except Exception as e:
            self.log_signal.emit(f"Exception occurred: {e}")
            self.log_signal.emit("Attempting to kill ADB server...")
            try:
                subprocess.run(["adb", "kill-server"], capture_output=True, text=True)
                self.log_signal.emit("ADB server killed.")
            except Exception as kill_e:
                self.log_signal.emit(f"Failed to kill ADB server: {kill_e}")

    def install_apk_from_memory(self, device, local_path: str) -> str:
        """
        Установка APK на устройство:
         1. Используется загруженный временный файл (local_path).
         2. Файл отправляется на устройство (device.push) по пути /data/local/tmp/tmp_mdm_launcher.apk.
         3. На устройстве выполняется установка через 'pm install'.
         4. (Опционально) временный файл на устройстве можно удалить.
        Возвращается результат выполнения установки.
        """
        remote_path = "/data/local/tmp/tmp_mdm_launcher.apk"

        # Отправляем файл на устройство
        try:
            device.push(local_path, remote_path)
        except Exception as e:
            return f"Failed to push APK to device: {e}"

        # Устанавливаем APK на устройстве
        try:
            install_output = device.shell(f"pm install {remote_path}")
        except Exception as e:
            return f"Failed to run pm install: {e}"

        return install_output

    def closeEvent(self, event):
        """При закрытии приложения удаляем временный загруженный файл, если он существует."""
        if self.temp_apk_path and os.path.exists(self.temp_apk_path):
            try:
                os.remove(self.temp_apk_path)
                self.log_signal.emit(f"Temporary APK file {self.temp_apk_path} removed.")
            except Exception as e:
                self.log_signal.emit(f"Error removing temporary APK file: {e}")
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = ADBApp()
    window.showMaximized()  # Открытие в оконном режиме на весь экран
    sys.exit(app.exec())
