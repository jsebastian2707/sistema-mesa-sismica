import dearpygui.dearpygui as dpg
from obspy import read
import serial
import serial.tools.list_ports
import time
import math
import threading
from collections import deque
import os
import numpy as np
from tkinter import filedialog, Tk
import shutil

RECORDS_FOLDER_NAME = "sismic_records"
local_sismos = {}
    
## 1 plot
time_markers_x = [] # Almacenará las coordenadas X de las líneas verticales
t_plot = 0
last_marker_time = -1 # Para rastrear el último segundo en el que se añadió un marcador

ser = None
app_running = True
wave_running = False
log_dirty = False
data_lock = threading.Lock()
log_recv = deque(maxlen=100)
log_sent = deque(maxlen=100)
expected_wave_data = deque(maxlen=500)
x_data = deque(maxlen=500)
y_data = deque(maxlen=500)
plot_start_time = 0; max_points = 500

###
viewer_seismic_files = {}           # Files and their traces for the viewer
viewer_all_traces = []              # Flat list of all traces
viewer_selected_trace_index = None  # Index of the selected trace
viewer_data_dirty = threading.Event() # Event to notify GUI to update viewer

viewer_playback_status = "Idle"
viewer_playback_status_dirty = False
viewer_playback_amplitude = 1600


def refresh_ports_callback():
    if dpg.does_item_exist("ports_combo"):
        dpg.configure_item("ports_combo", items=find_serial_ports())
    else:
        print("Warning: 'ports_combo' item does not exist in the UI.")

def find_serial_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports] if ports else ["No Ports Found"]

def connect_callback():
    port = dpg.get_value("ports_combo")
    baud = dpg.get_value("baud_rate_combo")
    if port and baud:
        success, message = connect_serial(port, baud)
        if success:
            update_ui_for_connection_state(True)
            with data_lock:
                x_data.clear(); y_data.clear(); expected_wave_data.clear()
            plot_start_time = time.time()
        else:
            dpg.set_value("connection_status", f"Error: {message}")
            
def start_wave_callback():
    global wave_running
    if not wave_running:
        wave_running = True
        with data_lock:
            x_data.clear(); y_data.clear(); expected_wave_data.clear()
        plot_start_time = time.time()
        if dpg.does_item_exist("speed_input"): send_command(f"s{dpg.get_value('speed_input')}")
        if dpg.does_item_exist("accel_input"): send_command(f"a{dpg.get_value('accel_input')}")
        
        threading.Thread(target=wave_generator_thread, daemon=True).start()
        
        if dpg.does_item_exist("start_wave_button"): dpg.disable_item("start_wave_button")
        if dpg.does_item_exist("stop_wave_button"): dpg.enable_item("stop_wave_button")

def stop_wave_callback():
    global wave_running
    wave_running = False
    if dpg.does_item_exist("start_wave_button"): dpg.enable_item("start_wave_button")
    if dpg.does_item_exist("stop_wave_button"): dpg.disable_item("stop_wave_button")


def disconnect_callback():
    disconnect_serial()
    update_ui_for_connection_state(False)

def connect_serial(port, baud):
    global ser, log_dirty
    if port == "No Ports Found":
        return False, "No serial ports available."
    try:
        ser = serial.Serial(port, int(baud), timeout=1)
        with data_lock:
            log_recv.append(f"Conectado a {port} a {baud} baud.")
            log_dirty = True
        return True, f"Conectado a {port}"
    except serial.SerialException as e:
        ser = None
        return False, str(e)

def disconnect_serial():
    global ser, log_dirty
    if ser and ser.is_open:
        ser.close()
        ser = None # Ensure the object is cleared
        with data_lock:
            log_recv.append("Desconectado.")
            log_dirty = True
    print("Serial connection closed.")
 
def update_ui_for_connection_state(connected: bool):
    if connected:
        dpg.set_value("connection_status", f"Conectado a {ser.port}")
        dpg.configure_item("connect_button", show=False)
        dpg.configure_item("disconnect_button", show=True)
        if dpg.does_item_exist("start_wave_button"): dpg.enable_item("start_wave_button")
        if dpg.does_item_exist("command_input"): dpg.enable_item("command_input")
        if dpg.does_item_exist("send_command_button"): dpg.enable_item("send_command_button")
    else:
        dpg.set_value("connection_status", "Desconectado")
        dpg.configure_item("connect_button", show=True)
        dpg.configure_item("disconnect_button", show=False)
        if dpg.does_item_exist("start_wave_button"): dpg.disable_item("start_wave_button")
        if dpg.does_item_exist("stop_wave_button"): dpg.disable_item("stop_wave_button")
        if dpg.does_item_exist("command_input"): dpg.disable_item("command_input")
        if dpg.does_item_exist("send_command_button"): dpg.disable_item("send_command_button")
        refresh_ports_callback()

def send_command(command):
    global log_dirty
    if ser and ser.is_open:
        try:
            full_command = command + '\n'
            ser.write(full_command.encode("utf-8"))
            with data_lock:
                log_sent.append(f"[{time.strftime('%H:%M:%S')}] >> {command}")
                log_dirty = True
        except serial.SerialException as e:
            with data_lock:
                log_sent.append(f"ERROR: {e}")
                log_dirty = True
    else:
        with data_lock:
            log_sent.append(f"SKIPPED (not connected): {command}")
            log_dirty = True

def read_serial_thread():
  global plot_start_time, log_dirty
  while app_running:
    if ser and ser.is_open:
      try:
          line = ser.readline().decode("utf-8").strip()
          if line:
              with data_lock:
                log_recv.append(f"[{time.strftime('%H:%M:%S')}] << {line}")
                log_dirty = True
              try:
                  with data_lock:
                      current_time = time.time() - plot_start_time
                      x_data.append(current_time)
                      y_data.append(float(line))
                      if len(x_data) > max_points:
                          x_data.pop(0)
                          y_data.pop(0)
              except ValueError:
                      pass
      except (serial.SerialException, UnicodeDecodeError):
        time.sleep(0.5)
    else:
      time.sleep(0.5)

def send_manual_command_callback():
    command = dpg.get_value("command_input")
    if command: # Only send if command_input exists and has value
        send_command(command)
        if dpg.does_item_exist("command_input"):
            dpg.set_value("command_input", "")

def wave_generator_thread():
    amplitude = dpg.get_value("amplitude_slider")
    frequency = dpg.get_value("frequency_slider")
    start_time = time.time()
    
    while wave_running:
        elapsed_time = time.time() - start_time
        target_pos = amplitude * math.sin(2 * math.pi * frequency * elapsed_time)
        send_command(f"m{int(target_pos)}")
        time.sleep(0.02)
    
    send_command("m0")
 
def _update_plot():
    global t_plot, log_dirty
    t_plot += dpg.get_delta_time()
    dpg.set_axis_limits('x_axis_time', t_plot - 10, t_plot)
    dpg.set_axis_limits('x_axis_compare', t_plot - 10, t_plot)

    with data_lock:
        if x_data and y_data:
            dpg.set_value("series_real_comp", [list(x_data), list(y_data)])
            dpg.fit_axis_data("y_axis_encoder")
        
        if expected_wave_data:
            wave_x = [item[0] for item in expected_wave_data]
            wave_y = [item[1] for item in expected_wave_data]
            dpg.set_value("series_wave_comp", [wave_x, wave_y])
            dpg.fit_axis_data("y_axis_wave")
        
        if log_dirty:
            dpg.set_value("console_recv_output", "\n".join(log_recv))
            dpg.set_value("console_send_output", "\n".join(log_sent))
            log_dirty = False
 
def update_plot_sizes():
    if dpg.does_item_exist("Primary Window"):
        window_width = dpg.get_item_width("Primary Window")
        window_height = dpg.get_item_height("Primary Window")
        plot_width = (window_width - 40) // 2
        plot_height = window_height - 400
        if dpg.does_item_exist("_time_plot"):
            dpg.configure_item("_time_plot", width=plot_width, height=plot_height)
        if dpg.does_item_exist("_compare_plot"):
            dpg.configure_item("_compare_plot", width=plot_width, height=plot_height)
   
def toggle_element(sender, app_data):
    elemento_tag = "wave_generator_header"
    elemento_tag2 = "file_picker_header"
    if app_data:
        dpg.show_item(elemento_tag2)
        dpg.hide_item(elemento_tag)
    else:
        dpg.show_item(elemento_tag)
        dpg.hide_item(elemento_tag2)

def get_records_folder_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, RECORDS_FOLDER_NAME)

def scan_and_load_sismic_records(is_initial_load=False):
    folder_path = get_records_folder_path()
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    
    sismo_status_message = f"Cargando desde '{RECORDS_FOLDER_NAME}'..."
    local_sismos.clear()
    loaded_files = []

    try:
        filenames = sorted(os.listdir(folder_path))
        for filename in filenames:
            if filename.lower().endswith(('.mseed', '.msd', '.miniseed')):
                full_path = os.path.join(folder_path, filename)
                try:
                    st = read(full_path)
                    local_sismos[filename] = st
                    loaded_files.append(filename)
                except Exception as e:
                    print(f"Error al leer el archivo {filename}: {e}")
        
        if not loaded_files:
            sismo_status_message = f"No se encontraron archivos en '{RECORDS_FOLDER_NAME}'."
        else:
            sismo_status_message = f"Se cargaron {len(loaded_files)} archivos."
        
    except Exception as e:
        sismo_status_message = f"Error al acceder a la carpeta: {e}"
    finally:
        sismo_list_dirty = True

def import_and_copy_files_thread():
    sismo_status_message = "Abriendo selector de archivos..."
    try:
        root = Tk(); root.withdraw()
        filepaths = filedialog.askopenfilenames(title="Importar archivos MiniSEED", filetypes=[("MiniSEED", "*.mseed *.msd"), ("All files", "*.*")])
    finally:
        root.destroy()

    if not filepaths:
        sismo_status_message = "Importación cancelada."
        return

    records_folder = get_records_folder_path()
    copied_count = 0
    for fpath in filepaths:
        try:
            filename = os.path.basename(fpath)
            sismo_status_message = f"Importando: {filename}..."
            shutil.copy(fpath, os.path.join(records_folder, filename))
            copied_count += 1
        except Exception as e:
            print(f"Error al copiar {fpath}: {e}")
            sismo_status_message = f"Error importando {filename}."

    sismo_status_message = f"Se importaron {copied_count} archivos. Refrescando..."
    scan_and_load_sismic_records()

def _set_viewer_status(message: str) -> None:
    """Updates the shared playback status message and marks it dirty."""
    with data_lock:
        viewer_playback_status = message
        viewer_playback_status_dirty = True
    print(f"Viewer: {message}")

def get_records_folder_path():
    """Gets the absolute path to the sismic_records folder."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, RECORDS_FOLDER_NAME)

def load_data_for_viewer_thread():
    """Loads all seismic data from the records folder into the viewer's state variables."""
    print("Viewer: Starting data load...")
    _set_viewer_status("Loading seismic data...")
    folder_path = get_records_folder_path()

    # Reset state
    viewer_seismic_files.clear()
    viewer_all_traces.clear()
    viewer_selected_trace_index = None

    try:
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.mseed', '.msd', '.miniseed'))]
        if not files:
            print("Viewer: No seismic files found.")
            _set_viewer_status("No seismic files found in 'sismic_records'.")
            return

        for file_name in files:
            file_path = os.path.join(folder_path, file_name)
            try:
                stream = read(file_path)
                file_traces = []
                for trace in stream:
                    # Enrich trace data for the viewer
                    data_info = {
                        'id': trace.id, 'station': trace.stats.station, 'channel': trace.stats.channel,
                        'network': trace.stats.network, 'location': getattr(trace.stats, 'location', ''),
                        'times': trace.times(), 'data': trace.data, 'sampling_rate': trace.stats.sampling_rate,
                        'starttime': str(trace.stats.starttime), 'endtime': str(trace.stats.endtime),
                        'max_amp': np.max(np.abs(trace.data)) if trace.data.size > 0 else 0,
                        'min_amp': np.min(trace.data) if trace.data.size > 0 else 0,
                        'file_name': file_name, 'file_path': file_path,
                        'global_index': len(viewer_all_traces),
                        'obspy_trace': trace
                    }
                    file_traces.append(data_info)
                    viewer_all_traces.append(data_info)
                
                viewer_seismic_files[file_name] = file_traces
                print(f"Viewer: Loaded {file_name} with {len(file_traces)} traces.")

            except Exception as e:
                print(f"Viewer: Error loading {file_path}: {e}")

    except Exception as e:
        print(f"Viewer: General error loading data: {e}")
        _set_viewer_status(f"Error loading data: {e}")
    finally:
        # Signal the GUI thread that it needs to redraw the file list
        viewer_data_dirty.set()
        print("Viewer: Data load finished.")
        if viewer_all_traces:
            _set_viewer_status("Data loaded. Select a trace to play.")

def process_selected_trace():
    """Processes the currently selected trace to get acceleration and displays it."""
    if viewer_selected_trace_index is None:
        print("Viewer: No trace selected to process.")
        return

    trace_info = viewer_all_traces[viewer_selected_trace_index]
    original_trace = trace_info['obspy_trace'].copy()
    print(f"Viewer: Processing {original_trace.id} for shaking table.")

    # Processing pipeline
    original_trace.detrend('linear')
    fmin, fmax = 0.1, 20  # Recommended bandpass filter frequencies
    original_trace.filter('bandpass', freqmin=fmin, freqmax=fmax, corners=4, zerophase=True)
    original_trace.differentiate()
    print("Viewer: Detrend, filter, and differentiation complete.")

    # Visualization in a new window
    accel_data, times = original_trace.data, original_trace.times()
    
    if dpg.does_item_exist("acceleration_window"):
        dpg.delete_item("acceleration_window")

    with dpg.window(label=f"Acceleration - {trace_info['id']}", width=800, height=500, tag="acceleration_window"):
        dpg.add_text("Processed Acceleration Record", color=(100, 200, 255))
        dpg.add_text(f"Filter: {fmin}-{fmax} Hz. Units: m/s^2")
        dpg.add_separator()
        with dpg.plot(label="Acceleration Plot", height=-1, width=-1):
            dpg.add_plot_axis(dpg.mvXAxis, label="Time (s)", tag="accel_x_axis")
            with dpg.plot_axis(dpg.mvYAxis, label="Acceleration (m/s^2)", tag="accel_y_axis"):
                dpg.add_line_series(times.tolist(), accel_data.tolist(), label="Acceleration")
            dpg.fit_axis_data("accel_x_axis")
            dpg.fit_axis_data("accel_y_axis")


def _prepare_trace_for_playback(trace):
    """Generates the displacement sequence and sampling interval for playback."""
    working_trace = trace.copy()
    working_trace.detrend("linear")
    working_trace.taper(max_percentage=0.05, type="hann")
    working_trace.integrate(method='cumtrapz')
    working_trace.integrate(method='cumtrapz')

    data = working_trace.data.astype(np.float64)
    if data.size == 0:
        raise ValueError("Trace contains no samples.")

    max_abs = np.max(np.abs(data))
    if not np.isfinite(max_abs) or max_abs == 0:
        raise ValueError("Trace amplitude is zero.")

    with data_lock:
        amplitude = int(abs(viewer_playback_amplitude))
    amplitude = max(amplitude, 1)

    scaled = np.clip((data / max_abs) * amplitude, -amplitude, amplitude).astype(int)

    sample_interval = getattr(working_trace.stats, "delta", None)
    if sample_interval is None or not np.isfinite(sample_interval) or sample_interval <= 0:
        sample_interval = 0.01

    return scaled, float(sample_interval)


def start_playback():
    global sismo_running
    """Starts a background thread to play the selected seismic trace on the motor."""
    if not (ser and ser.is_open):
        _set_viewer_status("Error: Connect to the table first.")
        return

    with data_lock:
        selected_index = viewer_selected_trace_index
        is_running = sismo_running
        wave_running = wave_running
        trace_info = None
        if (selected_index is not None and
                0 <= selected_index < len(viewer_all_traces)):
            trace_info = viewer_all_traces[selected_index]

    if trace_info is None:
        _set_viewer_status("Error: Select a trace before playing.")
        return

    if is_running:
        _set_viewer_status("Playback already running.")
        return

    if wave_running:
        _set_viewer_status("Error: Stop the sine wave generator before playback.")
        return

    with data_lock:
        sismo_running = True

    metadata = {
        'id': trace_info['id'],
        'file_name': trace_info['file_name'],
        'num_samples': len(trace_info['data'])
    }
    trace_copy = trace_info['obspy_trace'].copy()

    _set_viewer_status(f"Preparing {metadata['id']} for playback...")
    threading.Thread(target=_playback_worker, args=(trace_copy, metadata), daemon=True).start()


def _playback_worker(trace, metadata):
    global sismo_running
    """Worker routine that streams the processed trace to the motor."""
    try:
        scaled_data, sample_interval = _prepare_trace_for_playback(trace)
    except Exception as exc:
        _set_viewer_status(f"Error: {exc}")
        with data_lock:
            sismo_running = False
        send_command("m0")
        return

    total_samples = len(scaled_data)
    if total_samples == 0:
        _set_viewer_status("Error: Trace produced no samples.")
        with data_lock:
            sismo_running = False
        send_command("m0")
        return

    sample_interval = max(sample_interval, 0.001)

    with data_lock:
        expected_wave_data.clear()
        x_data.clear()
        y_data.clear()
        plot_start_time = time.time()

    if dpg.does_item_exist("speed_input"):
        send_command(f"s{dpg.get_value('speed_input')}")
    if dpg.does_item_exist("accel_input"):
        send_command(f"a{dpg.get_value('accel_input')}")

    _set_viewer_status(f"Playing {total_samples} samples from {metadata.get('file_name', 'trace')}...")

    playback_start = time.time()
    try:
        for raw_position in scaled_data:
            if not sismo_running:
                _set_viewer_status("Playback stopped by user.")
                send_command("m0")
                return

            position = int(raw_position)
            send_command(f"m{position}")

            current_time = time.time() - playback_start
            with data_lock:
                expected_wave_data.append((current_time, position))
                if len(expected_wave_data) > max_points:
                    expected_wave_data.popleft()

            time.sleep(sample_interval)

    except Exception as exc:
        _set_viewer_status(f"Error during playback: {exc}")
    else:
        _set_viewer_status("Playback finished.")
    finally:
        send_command("m0")
        with data_lock:
            sismo_running = False


def stop_playback():
    global sismo_running
    """Signals the playback thread to stop streaming commands."""
    with data_lock:
        was_running = sismo_running
        sismo_running = False

    if was_running:
        _set_viewer_status("Stopping playback...")


dpg.create_context()
dpg.create_viewport(title='Serial Monitor with Plots', width=1200, height=600)

with dpg.window(tag="Primary Window", label="Serial Monitor"):
    with dpg.group(horizontal=True):
        with dpg.plot(tag="_time_plot", width=400, height=300):
                dpg.add_plot_axis(dpg.mvXAxis, label="Tiempo (s)", tag="x_axis_time")
                dpg.set_axis_limits(dpg.last_item(), -10, 0)
                with dpg.plot_axis(dpg.mvYAxis, label="Encoder", tag="y_axis_encoder"):
                        dpg.add_line_series([], [], label="Real", tag="series_real_comp")
        with dpg.plot(tag="_compare_plot", width=400, height=300):
                dpg.add_plot_axis(dpg.mvXAxis, label="Tiempo (s)", tag="x_axis_compare")
                dpg.set_axis_limits(dpg.last_item(), -10, 0)
                with dpg.plot_axis(dpg.mvYAxis, label="Wave", tag="y_axis_wave"):
                        dpg.add_line_series([], [], label="Wave", tag="series_wave_comp")

    with dpg.tab_bar():
        with dpg.tab(label="Connection"):
            dpg.add_text("Serial Connection Control")
            dpg.add_separator()
            dpg.add_text("Serial Port")
            with dpg.group(horizontal=True):
                dpg.add_combo(items=find_serial_ports(), tag="ports_combo", width=280)
                dpg.add_button(label="Refresh", callback=refresh_ports_callback)
            dpg.add_text("Baud Rate")
            dpg.add_combo(["9600", "57600", "115200", "921600"], tag="baud_rate_combo", default_value="115200", width=200)
            dpg.add_spacer(height=20)
            dpg.add_button(label="Connect", tag="connect_button", callback=connect_callback, width=-1, height=40)
            dpg.add_button(label="Disconnect", tag="disconnect_button", callback=disconnect_callback, width=-1, height=40, show=False)
            dpg.add_text("Disconnected", tag="connection_status", color=(255, 100, 100))
        with dpg.tab(label="control"):
            dpg.add_checkbox(label="usar datos reales", tag="generation_checkbox", callback=toggle_element, default_value=False)
            with dpg.collapsing_header(label="generar onda", tag="wave_generator_header"):
                with dpg.group(horizontal=True):
                    with dpg.group(width=300):
                        dpg.add_text("Sine Wave Generator")
                        dpg.add_slider_int(label="Amplitude", tag="amplitude_slider", default_value=1600, min_value=100, max_value=10000)
                        dpg.add_slider_float(label="Frequency", tag="frequency_slider", default_value=0.5, min_value=0.1, max_value=5.0, format="%.2f Hz")
                        dpg.add_separator()
                        dpg.add_text("Motor Settings")
                        dpg.add_input_int(label="Speed (s)", tag="speed_input", default_value=50000)
                        dpg.add_input_int(label="Acceleration (a)", tag="accel_input", default_value=20000)
                        dpg.add_separator()
                        with dpg.group(horizontal=True):
                                dpg.add_button(label="Start Wave", tag="start_wave_button", callback=start_wave_callback, width=-1)
                                dpg.add_button(label="Stop Wave", tag="stop_wave_button", callback=stop_wave_callback, width=-1)
                        dpg.add_separator()
                        dpg.add_text("Manual Control & Send Log")
                        dpg.add_input_text(tag="command_input", hint="Command (e.g., m0)", on_enter=True, callback=send_manual_command_callback)
                        dpg.add_button(label="Send Command", tag="send_command_button", callback=send_manual_command_callback, width=-1)
                        with dpg.child_window(tag="console_send_container", height=-1, border=True):
                                dpg.add_input_text(tag="console_send_output", multiline=True, readonly=True, width=-1, height=-1)
                    with dpg.group(width=-1):
                            dpg.add_text("Received from Table")
                            with dpg.child_window(tag="console_recv_container", height=-1, border=True):
                                    dpg.add_input_text(tag="console_recv_output", multiline=True, readonly=True, width=-1, height=-1)
            with dpg.collapsing_header(label="elegir registro", tag="file_picker_header", show=False):
                with dpg.group(horizontal=True):
                    with dpg.group(width=500):
                            dpg.add_text("Seismic Trace Selector")
                            dpg.add_button(label="Load Data from 'sismic_records'", 
                                                            callback=lambda: threading.Thread(target=load_data_for_viewer_thread, daemon=True).start(), 
                                                            width=-1, height=40)
                            dpg.add_separator()
                            with dpg.child_window(tag="viewer_file_tree", border=True):
                                    dpg.add_text("Click 'Load Data' to begin.")
                    with dpg.group(width=-1):
                            dpg.add_text("Detailed Trace View")
                            dpg.add_separator()
                            with dpg.child_window(tag="viewer_detailed_plot_container"):
                                    dpg.add_text("Select a trace from the list to see details.")

# Set up handlers
with dpg.item_handler_registry(tag="__time_plot_ref"):
    dpg.add_item_visible_handler(callback=_update_plot)
dpg.bind_item_handler_registry("_time_plot", "__time_plot_ref")

# Set up window resize handler
with dpg.item_handler_registry(tag="window_resize_handler"):
    dpg.add_item_resize_handler(callback=update_plot_sizes)

dpg.setup_dearpygui()
dpg.show_viewport()
dpg.maximize_viewport()

# Bind resize handler to the window
dpg.bind_item_handler_registry("Primary Window", "window_resize_handler")

dpg.set_primary_window("Primary Window", True)
dpg.render_dearpygui_frame()
update_plot_sizes()
serial_thread = threading.Thread(target=read_serial_thread, daemon=True)
serial_thread.start()
dpg.start_dearpygui()

app_running = False
if ser and ser.is_open:
    ser.close()
dpg.destroy_context()