# serial_handler.py
# Manages all serial port communication with the shake table.

import serial
import serial.tools.list_ports
import time
import math
import dearpygui.dearpygui as dpg

import app_state # Import shared state

def find_serial_ports():
    """Returns a list of available COM ports."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports] if ports else ["No Ports Found"]

def connect_serial(port, baud):
    """Attempts to connect to the given serial port."""
    if port == "No Ports Found":
        return False, "No serial ports available."
    try:
        app_state.ser = serial.Serial(port, int(baud), timeout=1)
        with app_state.data_lock:
            app_state.log_recv.append(f"Conectado a {port} a {baud} baud.")
            app_state.log_dirty = True
        return True, f"Conectado a {port}"
    except serial.SerialException as e:
        app_state.ser = None
        return False, str(e)

def disconnect_serial():
    """Closes the serial connection if it is open."""
    # <<< MODIFICADO: Agregado log al desconectar >>>
    if app_state.ser and app_state.ser.is_open:
        app_state.ser.close()
        app_state.ser = None # Ensure the object is cleared
        with app_state.data_lock:
            app_state.log_recv.append("Desconectado.")
            app_state.log_dirty = True
    print("Serial connection closed.")


def send_command(command):
    """Sends a command to the serial port if it is connected."""
    if app_state.ser and app_state.ser.is_open:
        try:
            full_command = command + '\n'
            app_state.ser.write(full_command.encode("utf-8"))
            with app_state.data_lock:
                app_state.log_sent.append(f"[{time.strftime('%H:%M:%S')}] >> {command}")
                app_state.log_dirty = True
        except serial.SerialException as e:
            with app_state.data_lock:
                app_state.log_sent.append(f"ERROR: {e}")
                app_state.log_dirty = True
    else:
        with app_state.data_lock:
            app_state.log_sent.append(f"SKIPPED (not connected): {command}")
            app_state.log_dirty = True


def read_serial_thread():
    """Background thread to continuously read data from the serial port."""
    prev_angle = None
    turns = 0
    while app_state.app_running:
        if app_state.ser and app_state.ser.is_open:
            try:
                line = app_state.ser.readline().decode("utf-8").strip()
                if line:
                    with app_state.data_lock:
                        app_state.log_recv.append(f"[{time.strftime('%H:%M:%S')}] << {line}")
                        app_state.log_dirty = True
                    try:
                        angle = float(line)
                        with app_state.data_lock:
                            if prev_angle is not None:
                                if prev_angle > 300 and angle < 60: turns += 1
                                elif prev_angle < 60 and angle > 300: turns -= 1
                            prev_angle = angle
                            absolute_angle = (turns * 360) + angle
                            current_time = time.time() - app_state.plot_start_time
                            app_state.x_data.append(current_time)
                            app_state.y_data.append(absolute_angle)
                            if len(app_state.x_data) > app_state.max_points:
                                app_state.x_data.pop(0)
                                app_state.y_data.pop(0)
                    except ValueError:
                        pass
            except (serial.SerialException, UnicodeDecodeError):
                time.sleep(0.5)
        else:
            time.sleep(0.5)

def wave_generator_thread():
    """Background thread to generate a sine wave and send motor commands."""
    amplitude = dpg.get_value("amplitude_slider")
    frequency = dpg.get_value("frequency_slider")
    start_time = time.time()
    
    while app_state.wave_running:
        elapsed_time = time.time() - start_time
        target_pos = amplitude * math.sin(2 * math.pi * frequency * elapsed_time)
        send_command(f"m{int(target_pos)}")
        time.sleep(0.02)
    
    send_command("m0")