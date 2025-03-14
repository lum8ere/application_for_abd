import tkinter as tk
import threading
import subprocess
import adbutils

class ADBApp:
    def __init__(self, master):
        self.master = master
        master.title("ADB Device Manager")
        master.geometry("700x400")
        
        # Левая панель (список устройств)
        self.left_frame = tk.Frame(master, width=300, bd=2, relief="groove")
        self.left_frame.grid(row=0, column=0, sticky="ns", padx=5, pady=5)
        
        # Правая панель (вывод и кнопка)
        self.right_frame = tk.Frame(master, bd=2, relief="groove")
        self.right_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        master.grid_columnconfigure(1, weight=1)
        master.grid_rowconfigure(0, weight=1)
        
        # Заголовок для левой панели
        tk.Label(self.left_frame, text="Connected Devices", font=("Helvetica", 14)).pack(pady=10)
        
        # Фрейм для списка устройств
        self.device_list_frame = tk.Frame(self.left_frame)
        self.device_list_frame.pack(fill="both", expand=True)
        
        # Текстовое поле для вывода (справа)
        self.output_text = tk.Text(self.right_frame, height=20, width=50)
        self.output_text.pack(pady=10, padx=10, fill="both", expand=True)
        
        # Кнопка для установки device owner
        self.command_button = tk.Button(
            self.right_frame, 
            text="Set Device Owner", 
            command=self.send_command, 
            font=("Helvetica", 12)
        )
        self.command_button.pack(pady=10)
        
        # Запуск периодического обновления списка устройств
        self.update_device_list()

    def update_device_list(self):
        """Обновление списка подключённых устройств и их статусов."""
        # Очищаем предыдущие элементы
        for widget in self.device_list_frame.winfo_children():
            widget.destroy()
        
        try:
            devices = adbutils.adb.list()
            if devices:
                for device in devices:
                    self.add_device_entry(device)
            else:
                tk.Label(self.device_list_frame, text="No devices connected").pack(pady=5)
        except Exception as e:
            tk.Label(self.device_list_frame, text=f"Error: {e}", fg="red").pack(pady=5)
        
        # Обновление каждые 3 секунды
        self.master.after(3000, self.update_device_list)

    def add_device_entry(self, device: adbutils.AdbDeviceInfo):
        """Добавление записи для одного устройства в список."""
        frame = tk.Frame(self.device_list_frame, pady=5)
        frame.pack(fill="x", padx=5)
        
        # Отображаем серийный номер устройства
        serial_label = tk.Label(frame, text=device.serial, font=("Helvetica", 10))
        serial_label.pack(side="left", padx=5)
        
        # Проверяем наличие device owner через dumpsys device_policy
        device_policy_dump = adbutils.adb.shell(device.serial, "dumpsys device_policy")
        if "Device Owner:" in device_policy_dump:
            owner_set = True
        else:
            owner_set = False
        
        # Индикатор device owner (квадрат 20x20)
        owner_canvas = tk.Canvas(frame, width=20, height=20, highlightthickness=0)
        owner_canvas.pack(side="left", padx=5)
        color_owner = "green" if owner_set else "red"
        owner_canvas.create_rectangle(0, 0, 20, 20, fill=color_owner)
        tk.Label(frame, text="Owner", font=("Helvetica", 8)).pack(side="left", padx=(0, 10))
        
        # Проверяем, установлен ли пакет com.hmdm.launcher
        pkg_list = adbutils.adb.shell(device.serial, "pm list packages")
        if "com.hmdm.launcher" in pkg_list:
            pkg_installed = True
        else:
            pkg_installed = False
        
        # Индикатор наличия пакета (квадрат 20x20)
        pkg_canvas = tk.Canvas(frame, width=20, height=20, highlightthickness=0)
        pkg_canvas.pack(side="left", padx=5)
        color_pkg = "green" if pkg_installed else "red"
        pkg_canvas.create_rectangle(0, 0, 20, 20, fill=color_pkg)
        tk.Label(frame, text="Launcher", font=("Helvetica", 8)).pack(side="left")
    
    def send_command(self):
        """Запуск выполнения команды для всех устройств в отдельном потоке."""
        threading.Thread(target=self.run_command).start()

    def run_command(self):
        self.append_output("Sending command to all devices...\n")
        try:
            devices = adbutils.adb.list()
            if not devices:
                self.append_output("No devices connected.\n")
                return
            
            for device in devices:
                self.append_output(f"\nProcessing device: {device.serial}\n")
                
                # Проверяем наличие device owner через dumpsys device_policy
                device_policy_dump = adbutils.adb.shell(device.serial, "dumpsys device_policy")
                if "Device Owner:" in device_policy_dump:
                    self.append_output(f"Device {device.serial} already has a device owner.\n")
                    continue
                
                # Проверяем, установлен ли нужный пакет (com.hmdm.launcher)
                pkg_list = adbutils.adb.shell(device.serial, "pm list packages")
                if "com.hmdm.launcher" not in pkg_list:
                    self.append_output(f"Package 'com.hmdm.launcher' is missing on {device.serial}.\n")
                    continue
                
                # Выполняем команду установки device owner
                output = adbutils.adb.shell(device.serial, "dpm set-device-owner com.hmdm.launcher/.AdminReceiver")
                if "error" in output.lower() or "failure" in output.lower():
                    self.append_output(f"Command error on device {device.serial}: {output}\n")
                    self.append_output("Attempting to kill adb server...\n")
                    subprocess.run(["adb", "kill-server"], capture_output=True, text=True)
                    self.append_output("ADB server killed.\n")
                else:
                    self.append_output(f"Command executed successfully on device {device.serial}.\n")
        except Exception as e:
            self.append_output(f"Exception occurred: {e}\n")
            self.append_output("Attempting to kill adb server...\n")
            try:
                subprocess.run(["adb", "kill-server"], capture_output=True, text=True)
                self.append_output("ADB server killed.\n")
            except Exception as kill_e:
                self.append_output(f"Failed to kill adb server: {kill_e}\n")

    def append_output(self, text: str):
        """Добавление текста в окно вывода."""
        self.output_text.insert(tk.END, text)
        self.output_text.see(tk.END)

if __name__ == "__main__":
    root = tk.Tk()
    app = ADBApp(root)
    root.mainloop()