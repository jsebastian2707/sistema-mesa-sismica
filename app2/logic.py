import serial
import serial.tools.list_ports
import state
import time
import math
import queue
def goHome():
    ##centrar la mesa hasta que la señal del enconder quede lo mas cerca cero
    print("xd")

def runSismo():
    ##only if the running flag is true works
    print("xd")

def wave_generator_thread():
    """Background thread to generate a sine wave and send motor commands."""
    start_time = time.time()
    while state.running:
        elapsed_time = time.time() - start_time
        target_pos = state.amplitude * math.sin(2 * math.pi * state.frequency * elapsed_time)
        state.cmd_queue.put(f"m{int(target_pos)}")
        time.sleep(0.02)

def find_serial_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports] if ports else ["No Ports Found"]

def connect_serial(port, baud):
    if port == "No Ports Found":
        print("No serial ports available.")
    try:
        state.ser = serial.Serial(port, int(baud), timeout=1, write_timeout=0.5)
        with state.data_lock:
            state.log_send.append(f"Conectado a {port} a {baud} baud.")
            state.log_dirty = True
    except serial.SerialException as e:
        print("error"+e)
        state.ser = None

def closeSerial():
    if state.ser and state.ser.is_open:
        state.ser.close()
        state.ser = None


# def send_command(command):
#     """Sends a command to the serial port if it is connected."""
#     if state.ser and state.ser.is_open:
#         try:
#             #full_command = command + '\n'
#             state.ser.write(command.encode("utf-8"))
#             state.ser.flush()
#             with state.data_lock:
#                 state.log_send.append(f"[{time.strftime('%H:%M:%S')}] >> {command}")
#                 state.log_dirty = True
#         except serial.SerialException as e:
#             print("error " + e)
#     else:   
#         print("error ser is close")


# def readSerialThread():
#     """ lee la informacion del serial y la añade tanto a los logs 
#     como a la data de los plots"""
#     while state.running:
#         if state.ser and state.ser.is_open:
#             if state.ser.in_waiting > 0:
#                 try:
#                     line = state.ser.readline().decode("utf-8", errors='replace').strip()
#                     if line:
#                         with state.data_lock: ##aqui va el formato de los logs 
#                             state.log_read.append(f"[{time.strftime('%H:%M:%S')}] << {line}")
#                             state.log_dirty = True
#                         try:
#                             angle = float(line)
#                             with state.data_lock:
#                                 current_time = time.time() - state.start_time
#                                 state.monitor_x.append(current_time)
#                                 state.monitor_y.append(angle)
#                                 if len(state.monitor_x) > state.max_points:
#                                     state.monitor_x.pop(0)
#                                     state.monitor_y.pop(0)
#                         except ValueError:
#                             pass
#                 except (serial.SerialException, UnicodeDecodeError,):
#                     time.sleep(0.5)
#         else:
#             time.sleep(0.5)

def serial_controller_thread():
    while state.running:
        if state.ser and state.ser.is_open:
            try:
                try:
                    cmd = state.cmd_queue.get_nowait()
                    #full_command = command + '\n'z
                    state.ser.write((cmd + '\n').encode("utf-8"))
                    state.ser.flush()
                    print("herereeee")
                    with state.data_lock:
                        state.log_send.append(f"[{time.strftime('%H:%M:%S')}] >> {cmd}")
                        state.log_dirty = True
                    
                except queue.Empty:
                    pass
                if state.ser.in_waiting > 0:
                    try:
                        line = state.ser.readline().decode("utf-8", errors='replace').strip()
                        if line:
                            with state.data_lock: ##aqui va el formato de los logs 
                                state.log_read.append(f"[{time.strftime('%H:%M:%S')}] << {line}")
                                state.log_dirty = True
                            try:
                                angle = float(line)
                                with state.data_lock:
                                    current_time = time.time() - state.start_time
                                    state.monitor_x.append(current_time)
                                    state.monitor_y.append(angle)
                                    if len(state.monitor_x) > state.max_points:
                                        state.monitor_x.pop(0)
                                        state.monitor_y.pop(0)
                            except ValueError:
                                pass
                    except:
                        pass
            except (OSError, serial.SerialException):
                    print("Error: Port disconnected while writing.")
                    break # Optional: Break loop or handle disconnection
            time.sleep(0.001) 
        else:
            time.sleep(0.1)