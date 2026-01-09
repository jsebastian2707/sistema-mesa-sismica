import serial
import serial.tools.list_ports
import state
import time
import math


def goHome():
    ##centrar la mesa hasta que la señal del enconder quede lo mas cerca cero
    print("xd")

def runSismo():
    ##only if the running flag is true works
    print("xd")


def find_serial_ports():
    """Returns a list of available COM ports."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports] if ports else ["No Ports Found"]

def connect_serial(port, baud):
    """Attempts to connect to the given serial port."""
    if port == "No Ports Found":
        return False, "No serial ports available."
    try:
        state.ser = serial.Serial(port, int(baud), timeout=1)
        with state.data_lock:
            state.log_recv.append(f"Conectado a {port} a {baud} baud.")
            state.log_dirty = True
        return True, f"Conectado a {port}"
    except serial.SerialException as e:
        state.ser = None
        return False, str(e)

def disconnect_serial():
    """Closes the serial connection if it is open."""
    # <<< MODIFICADO: Agregado log al desconectar >>>
    if state.ser and state.ser.is_open:
        state.ser.close()
        state.ser = None # Ensure the object is cleared
        with state.data_lock:
            state.log_recv.append("Desconectado.")
            state.log_dirty = True
    print("Serial connection closed.")


def send_command(command):
    """Sends a command to the serial port if it is connected."""
    if state.ser and state.ser.is_open:
        try:
            full_command = command + '\n'
            state.ser.write(full_command.encode("utf-8"))
            with state.data_lock:
                state.log_sent.append(f"[{time.strftime('%H:%M:%S')}] >> {command}")
                state.log_dirty = True
        except serial.SerialException as e:
            with state.data_lock:
                state.log_sent.append(f"ERROR: {e}")
                state.log_dirty = True
    else:
        with state.data_lock:
            state.log_sent.append(f"SKIPPED (not connected): {command}")
            state.log_dirty = True


def read_serial_thread():
    """Background thread to continuously read data from the serial port."""
    prev_angle = None
    turns = 0
    while state.running:
        if state.ser and state.ser.is_open:
            try:
                line = state.ser.readline().decode("utf-8").strip()
                if line:
                    with state.data_lock:
                        state.log_recv.append(f"[{time.strftime('%H:%M:%S')}] << {line}")
                        state.log_dirty = True
                    try:
                        angle = float(line)
                        with state.data_lock:
                            if prev_angle is not None:
                                if prev_angle > 300 and angle < 60: turns += 1
                                elif prev_angle < 60 and angle > 300: turns -= 1
                            prev_angle = angle
                            absolute_angle = (turns * 360) + angle
                            current_time = time.time() - state.plot_start_time
                            state.x_data.append(current_time)
                            state.y_data.append(absolute_angle)
                            if len(state.x_data) > state.max_points:
                                state.x_data.pop(0)
                                state.y_data.pop(0)
                    except ValueError:
                        pass
            except (serial.SerialException, UnicodeDecodeError):
                time.sleep(0.5)
        else:
            time.sleep(0.5)

def wave_generator_thread():
    """Background thread to generate a sine wave and send motor commands."""
    start_time = time.time()
    
    while state.running:
        elapsed_time = time.time() - start_time
        target_pos = state.amplitude * math.sin(2 * math.pi * state.frequency * elapsed_time)
        send_command(f"m{int(target_pos)}")
        time.sleep(0.02)
    