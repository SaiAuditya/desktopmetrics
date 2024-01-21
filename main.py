import ast
import logging
import mimetypes

import pynput.keyboard
from pynput.mouse import Listener as MouseListener
from pynput.keyboard import Listener as KeyboardListener
import time
import pygetwindow as gw
import threading
import platform
import subprocess
import os
from datetime import datetime
import psutil
import uuid
import gzip
import json
import requests
from urllib.parse import urlparse
import httpx
from logging.handlers import RotatingFileHandler


from enum import Enum

from urllib3.exceptions import MaxRetryError, NewConnectionError

# Check if the platform is macOS

# Configure the logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s]: %(message)s',
    handlers=[
        logging.FileHandler('monitoring.log'),  # Save logs to a file
        logging.StreamHandler()  # Print logs to the console
    ]
)



DELIMITER = '---'
config_path = 'config.json'


with open(config_path, 'r') as file:
    json_data = json.load(file)


URL = json_data["ingestUrl"]
LOG_SIZE = json_data["logSize"]
LOG_BACKUP = json_data["logBackUp"]
BATCH_SIZE = json_data["eventChunkSize"]
COUNTER = 1

system_info = {
    'System': platform.system(),
    'User': json_data["optionalUserName"] if json_data["optionalUserName"] else os.getlogin(),
    'Node Name': platform.node(),
    'Release': platform.release(),
    'Version': platform.version(),
    'Machine': platform.machine(),
    'Processor': platform.processor(),
}

handler = RotatingFileHandler('my_log.log', maxBytes=LOG_SIZE, backupCount=LOG_BACKUP)


class EventTypes(Enum):
    CLICK_EVENT = "CLICK"
    KEY_PRESS = "GENERAL_KEY_PRESS"
    ERROR_KEY_PRESS = "ERROR_KEY_PRESS"
    COPY_EVENT = "COPY"
    PASTE_EVENT = "PASTE"
    IDLE_EVENT = "IDLE"


class Observer:
    def update(self, message):
        pass


class Subject:
    def __init__(self):
        self.event_pay_load = None
        self._observers = []
        self.pay_loads_array = []
        self.counter = 0

    def add_observer(self, observer):
        if observer not in self._observers:
            self._observers.append(observer)

    def remove_observer(self, observer):
        self._observers.remove(observer)

    def notify_observers(self, message, event_type, title, start_time, end_time, duration):

        for observer in self._observers:
            guid = uuid.uuid4()
            current_utc_time = datetime.utcfromtimestamp(time.time())
            global COUNTER
            COUNTER+=1
            if event_type.value == 'CLICK':
                self.event_pay_load = {"click": 1, "idle": 0, "keypress": 0, "errorpress": 0, "copy": 0, "paste": 0}
            elif event_type.value == 'IDLE':
                self.event_pay_load = {"click": 0, "idle": 1, "keypress": 0, "errorpress": 0, "copy": 0, "paste": 0}
            elif event_type.value == EventTypes.KEY_PRESS.value:
                self.event_pay_load = {"click": 0, "idle": 0, "keypress": 1, "errorpress": 0, "copy": 0, "paste": 0}
            elif event_type.value == EventTypes.ERROR_KEY_PRESS.value:
                self.event_pay_load = {"click": 0, "idle": 0, "keypress": 0, "errorpress": 1, "copy": 0, "paste": 0}
            elif event_type.value == EventTypes.COPY_EVENT.value:
                self.event_pay_load = {"click": 0, "idle": 0, "keypress": 0, "errorpress": 0, "copy": 1, "paste": 0}
            elif event_type.value == EventTypes.PASTE_EVENT.value:
                self.event_pay_load = {"click": 0, "idle": 0, "keypress": 0, "errorpress": 0, "copy": 0, "paste": 1}
            else:
                self.event_pay_load = {"click": 0, "idle": 0, "keypress": 0, "errorpress": 0, "copy": 0, "paste": 0}

            pay_load_1 = {"guid": str(guid), "current_utc_time": str(current_utc_time),
                          "user": str(system_info["User"]),
                          "machine": str(system_info["Machine"]),
                          "version": str(system_info["Version"].replace("/", "")),
                          "event_type": str(event_type.value), "process": str(title.split(DELIMITER)[0]).strip(),
                          "title": str(title.split(DELIMITER)[1]).strip(), "start_time": str(start_time),
                          "url": str(title.split(DELIMITER)[2]).strip(),
                          "domain": str(title.split(DELIMITER)[3]).strip(),
                          "end_time": str(end_time),
                          "duration": duration}

            pay_load = {**pay_load_1, **self.event_pay_load}

            logging.info(pay_load)
            logging.info(COUNTER)
            self.event_pay_load = None

            if COUNTER == BATCH_SIZE:
                self.save_payloads_to_gzip()
                COUNTER = 1

            self.pay_loads_array.append(pay_load)
            observer.update(message, event_type, title, start_time, end_time, duration)

    def save_payloads_to_gzip(self):
        # Convert objects to JSON string
        # parsed_payload = json.loads(ast.literal_eval(self.pay_loads_array))
        try:
            # For example, you can save it to a file
            # Convert the timestamp to a datetime object
            timestamp = time.time()
            datetime_object = datetime.fromtimestamp(timestamp)

            # Format the datetime object as a string suitable for a path
            formatted_string = datetime_object.strftime('%Y%m%d_%H%M%S')

            file_path = ("pay_load_" + formatted_string + ".json.gz")

            #with open(file_path, 'w') as file:
             #   for event in self.pay_loads_array:
              #      json_line = json.dumps(event)
               #     file.write(json_line + '\n')

            with gzip.open(file_path, 'wt', encoding='utf-8') as file:
                for event in self.pay_loads_array:
                    json_line = json.dumps(event)
                    file.write(json_line + '\n')

            api_url = URL
            boundary = "----WebKitFormBoundaryexampleboundary"

            # Set up the request headers with the correct Content-Type
            request_headers = {
                "Content-Type": f"multipart/form-data; boundary={boundary}"
            }

            with open(file_path, 'rb') as file2:
                files = {'file': (file2.name, file2, 'application/octet-stream')}
                response = httpx.post(api_url, files=files, headers=request_headers)

            if response.status_code == 200:
                logging.info("Ingestion task submitted successfully.")
            else:
                logging.info(f"Failed to submit ingestion task. Status code: {response.status_code}")
                logging.info(response.text)

            self.pay_loads_array.clear()

            try:
                os.remove(file_path)
                print(f"File '{file_path}' deleted successfully.")
            except OSError as e:
                print(f"Error deleting file '{file_path}': {e}")

        except Exception:
            logging.info("Error occured while doing the upload")
            self.pay_loads_array.clear()
            try:
                os.remove(file_path)
                print(f"File '{file_path}' deleted successfully.")
            except OSError as e:
                print(f"Error deleting file '{file_path}': {e}")

    def gzip_payload_send_to_druid(self):
        self.save_payloads_to_gzip()


class ConcreteObserver(Observer):
    def update(self, message, event_type, title, start_time, end_time, duration):
        logging.info(f"Received message: {message}")


class ClickObserver(Observer):
    def update(self, message, event_type, title, start_time, end_time, duration):
        logging.info(f"{message}, {event_type},{title}")


class KeyboardObserver(Observer):
    def update(self, message, event_type, title, start_time, end_time, duration):
        current_utc_time = datetime.utcfromtimestamp(time.time())
        logging.info(f"{message}, {title}")


#
class ClickSubject(Subject):
    def __init__(self):
        super().__init__()
        self.last_activity_time = datetime.utcfromtimestamp(time.time())
        logging.info("Idle monitoring..")
        self.idle_threshold = 60  # Set your desired idle threshold in seconds
        self.start_time = datetime.utcfromtimestamp(time.time())
        self.end_time = datetime.utcfromtimestamp(time.time())
        self.last_clicked_title = None
        self.idle_duration = 0
        self.ignoreCheckIdle = False

    def check_idle_time(self):
        idle_time = datetime.utcfromtimestamp(time.time()) - self.last_activity_time
        if idle_time.total_seconds() > self.idle_threshold and self.ignoreCheckIdle == False:
            active_window_title = get_active_window_title()
            self.notify_observers(f"Idle event detected {idle_time}", EventTypes.IDLE_EVENT,
                                  active_window_title, self.last_activity_time, datetime.utcfromtimestamp(time.time()),
                                  idle_time.total_seconds())
            logging.info("Idle event triggered")
            self.idle_duration = idle_time.total_seconds()
            self.last_activity_time = datetime.utcfromtimestamp(time.time())
            self.ignoreCheckIdle == True
        else:
            self.ignoreCheckIdle = False

    def start_click_monitor(self):
        with MouseListener(on_click=self.on_click, on_move=self.on_move, on_scroll=self.on_scroll) as listener:
            listener.join()

    def on_move(self, x, y):
        # self.last_activity_time = datetime.utcfromtimestamp(time.time())
        # logging.info("mouse movement detected")
        if (datetime.utcfromtimestamp(time.time()) - self.last_activity_time).total_seconds() > self.idle_threshold:
            self.check_idle_time()
        else:
            self.ignoreCheckIdle = True

    def on_scroll(self, x1, y1, x2, y2):
        if (datetime.utcfromtimestamp(time.time()) - self.last_activity_time).total_seconds() > self.idle_threshold:
            self.check_idle_time()
        else:
            self.ignoreCheckIdle = True

    def on_click(self, x, y, button, pressed):
        if pressed:
            title = get_active_window_title()
            self.check_idle_time()
            if self.last_clicked_title == title or (self.last_clicked_title is None):
                self.notify_observers(f"Click at ({x}, {y}) with button {button}", EventTypes.CLICK_EVENT, title,
                                      self.start_time, self.start_time, 0)
                self.start_time = datetime.utcfromtimestamp(time.time())
                self.idle_duration = 0

            else:
                end_time = datetime.utcfromtimestamp(time.time())
                duration = end_time - self.last_activity_time
                self.notify_observers(f"Click at ({x}, {y}) with button {button}", EventTypes.CLICK_EVENT,
                                      self.last_clicked_title,
                                      self.start_time, end_time, duration.total_seconds())
                self.notify_observers(f"Click at ({x}, {y}) with button {button}", EventTypes.CLICK_EVENT, title,
                                      self.end_time, self.end_time, 0)
                self.last_activity_time = end_time
                self.start_time = datetime.utcfromtimestamp(time.time())
                self.idle_duration = 0

            self.last_clicked_title = title
            self.last_activity_time = datetime.utcfromtimestamp(time.time())


# def on_move(self, x, y):
# title = get_active_window_title()
#    self.notify_observers(f"moved mouse", "no title")
#   self.check_idle_time()


class KeyboardSubject(Subject):
    def __init__(self):
        super().__init__()
        self.last_key = None
        self.last_activity_time = datetime.utcfromtimestamp(time.time())
        logging.info("Idle monitoring..")
        self.idle_threshold = 60  # Set your desired idle threshold in seconds
        self.start_time = datetime.utcfromtimestamp(time.time())
        self.end_time = datetime.utcfromtimestamp(time.time())
        self.last_clicked_title = None
        self.idle_duration = 0

    def check_idle_time(self):
        idle_time = datetime.utcfromtimestamp(time.time()) - self.last_activity_time
        if idle_time.total_seconds() > self.idle_threshold:
            active_window_title = get_active_window_title()
            self.notify_observers(f"Idle event detected {idle_time}", EventTypes.IDLE_EVENT,
                                  active_window_title, self.last_activity_time, datetime.utcfromtimestamp(time.time()),
                                  idle_time.total_seconds())
            logging.info("Idle event triggered")
            self.idle_duration = idle_time.total_seconds()

    def start_keyboard_monitor(self):
        with KeyboardListener(on_press=self.on_press) as listener:
            listener.join()

    def on_press(self, key):
        title = get_active_window_title()
        logging.info("Inside on press")
        self.check_idle_time()
        if title == self.last_clicked_title or (self.last_clicked_title is None):
            logging.info("Inside last clicked none check")
            try:
                if key == pynput.keyboard.Key.backspace or key == pynput.keyboard.Key.delete:
                    self.notify_observers(f"Error Key pressed:", EventTypes.ERROR_KEY_PRESS, title,
                                          self.last_activity_time, self.last_activity_time, 0)
                    logging.info("Inside Error key check")

                elif key.char == 'c' and (
                        self.last_key == pynput.keyboard.Key.cmd or self.last_key == pynput.keyboard.Key.ctrl):
                    title = get_active_window_title()
                    self.notify_observers("Copy detected", EventTypes.COPY_EVENT, title, self.last_activity_time,
                                          self.last_activity_time, 0)

                elif key.char == 'v' and (
                        self.last_key == pynput.keyboard.Key.cmd or self.last_key == pynput.keyboard.Key.ctrl):
                    title = get_active_window_title()
                    self.notify_observers("Paste detected", EventTypes.PASTE_EVENT, title, self.last_activity_time,
                                          self.last_activity_time, 0)
                else:
                    self.notify_observers(f"Key pressed", EventTypes.KEY_PRESS, title, self.last_activity_time,
                                          self.last_activity_time, 0)
                    logging.info("Else condition check in None")

                self.last_key = key
                self.last_clicked_title = title
                self.last_activity_time = datetime.utcfromtimestamp(time.time())

            except AttributeError:
                self.last_key = key
                self.last_clicked_title = title
                self.last_activity_time = datetime.utcfromtimestamp(time.time())
                self.notify_observers(f"Key pressed:", EventTypes.KEY_PRESS, title,
                                      self.last_activity_time, self.start_time, 0)
                self.last_activity_time=datetime.utcfromtimestamp(time.time())
                pass  # Ignore non-character keys

        else:
            end_time = datetime.utcfromtimestamp(time.time())
            duration_seconds = end_time - self.last_activity_time
            duration = duration_seconds.total_seconds()
            logging.info("Else condition If title is not null, first time keypress")
            self.notify_observers(f"Error Key pressed:", EventTypes.KEY_PRESS, self.last_clicked_title,
                                  self.start_time, end_time, duration - self.idle_duration)
            self.last_activity_time = end_time
            self.start_time = end_time
            self.idle_duration = 0
            try:
                if key == pynput.keyboard.Key.backspace or key == pynput.keyboard.Key.delete:
                    self.notify_observers(f"Error Key pressed:", EventTypes.ERROR_KEY_PRESS, title,
                                          self.last_activity_time, end_time, 0)
                    logging.info("Error key press once last title is available")

                elif key.char == 'c' and (
                        self.last_key == pynput.keyboard.Key.cmd or self.last_key == pynput.keyboard.Key.ctrl):
                    title = get_active_window_title()
                    self.notify_observers("Copy detected", EventTypes.COPY_EVENT, title,
                                          self.last_activity_time, end_time, 0)
                elif key.char == 'v' and (
                        self.last_key == pynput.keyboard.Key.cmd or self.last_key == pynput.keyboard.Key.ctrl):
                    title = get_active_window_title()
                    self.notify_observers("Paste detected", EventTypes.PASTE_EVENT, title, self.start_time,
                                          end_time, 0)
                else:
                    self.notify_observers(f"Key pressed", EventTypes.KEY_PRESS, title, self.start_time, end_time,
                                          0)
                    logging.info("Else condition for normal key press when last title is present")

                    self.last_key = key
                    self.last_clicked_title = title
                    self.last_activity_time = datetime.utcfromtimestamp(time.time())

            except AttributeError:
                self.last_key = key
                self.last_clicked_title = title
                self.notify_observers(f"Key pressed:", EventTypes.KEY_PRESS, title,
                                      self.last_activity_time, end_time, 0)
                self.last_activity_time = end_time
                self.start_time = end_time
                self.idle_duration = 0
                pass  # Ignore non-character keys


def get_active_window_title():
    if platform.system() == "Windows":
        import ctypes
        import psutil
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            # Get the length of the window title text
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd) + 1

            # Create a buffer to store the window title
            buffer = ctypes.create_unicode_buffer(length)

            # Get the window title and store it in the buffer
            ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length)

            active_window = buffer.value
            pid = ctypes.c_ulong(0)
            ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

            # Open the process with PROCESS_QUERY_INFORMATION and PROCESS_VM_READ permissions
            process_handle = ctypes.windll.kernel32.OpenProcess(0x0410, False, pid.value)
            if process_handle == 0:
                raise Exception(f"Failed to open process. Error code: {ctypes.windll.kernel32.GetLastError()}")

            # Get the executable file name of the process
            buffer_size = 260  # MAX_PATH
            executable_buffer = ctypes.create_unicode_buffer(buffer_size)
            ctypes.windll.psapi.GetModuleFileNameExW(process_handle, 0, executable_buffer, buffer_size)

            # Close the process handle
            ctypes.windll.kernel32.CloseHandle(process_handle)

            # Extract the process name from the file path
            process = executable_buffer.value.split('\\')[-1]
            url = 'none'

            if "Google Chrome" in active_window or "Mozilla Firefox" in active_window or "Microsoft Edge" in active_window:
                # Get the URL of the active browser window
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                buffer = ctypes.create_unicode_buffer(length + 1)
                ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
                url = buffer.value

                # Parse the URL to extract the domain
                parsed_url = urlparse(url)
                domain = parsed_url.netloc

                return f"{process} --- {active_window.title()}---{url}---{domain}"
            else:
                return f"{process} --- {active_window.title()}---None---None"

        except Exception:
            return "None---None---None---None"

    if platform.system() == "Darwin":  # macOS
        try:
            result = subprocess.run(['osascript', "./appleScript.scpt"], capture_output=True, text=True, check=True)
            logging.info(result)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            print(f"Error: {e}")
            return "None---None---None---None"


# Example usage with ClickObserver, KeyboardObserver, IdleObserver, and ActiveWindowObserver:
click_observer = ClickObserver()
keyboard_observer = KeyboardObserver()

click_subject = ClickSubject()
keyboard_subject = KeyboardSubject()

click_subject.add_observer(click_observer)
keyboard_subject.add_observer(keyboard_observer)

# Start monitors based on the platform
if platform.system() == "Windows":
    click_monitor_thread = threading.Thread(target=click_subject.start_click_monitor)
    click_monitor_thread.start()

    keyboard_monitor_thread = threading.Thread(target=keyboard_subject.start_keyboard_monitor)
    keyboard_monitor_thread.start()

elif platform.system() == "Darwin":  # macOS
    click_monitor_thread_mac = threading.Thread(target=click_subject.start_click_monitor)
    click_monitor_thread_mac.start()
    keyboard_monitor_thread_mac = threading.Thread(target=keyboard_subject.start_keyboard_monitor)
    keyboard_monitor_thread_mac.start()

# Wait for the monitors to finish (optional)
if platform.system() == "Windows":
    click_monitor_thread.join()
    keyboard_monitor_thread.join()
elif platform.system() == "Darwin":  # macOS
    click_monitor_thread_mac.join()
    keyboard_monitor_thread_mac.join()
