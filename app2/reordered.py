# =============================================================================
# I. IMPORTS
# =============================================================================
import serial
import serial.tools.list_ports
import threading
import time
import math
from collections import deque

import dearpygui.dearpygui as dpg
import numpy as np
import requests
from obspy.clients.fdsn import Client
from obspy import UTCDateTime


# =============================================================================
# II. CONFIGURATION & GLOBAL STATE
# =============================================================================
# --- Application State ---
app_running = True  # Global flag to signal all threads to exit when the app closes.
ser = None          # The serial port object. None if not connected.

# --- Task-specific State Flags ---
wave_running = False  # True if the sine wave generator thread is active.
sismo_running = False # True if the seismic data playback thread is active.

# --- Data for Plots ---
# These deques and lists store the data points for the real-time graphs.
# They are shared between the serial thread (writer) and the GUI thread (reader).
max_points = 1000               # Max number of data points to keep in the plot history.
plot_start_time = 0             # Timestamp used as a reference (time=0) for the plots.
x_data = []                     # Stores the time values (X-axis).
y_data = []                     # Stores the real motor position from the encoder (Y-axis).
expected_wave_data = deque()    # Stores the target motor position (for comparison plots).

# --- Threading Locks ---
# Locks are crucial for preventing race conditions when multiple threads access the same data.
data_lock = threading.Lock() # Protects access to shared plot data (x_data, y_data) and logs.
api_lock = threading.Lock()  # Protects access to sismos_data, which is fetched from an API.

# --- Console Logs ---
# Deques are used for efficient appending and popping from either end.
log_recv = deque(maxlen=100) # Stores last 100 messages received from the serial device.
log_sent = deque(maxlen=100) # Stores last 100 commands sent to the serial device.
log_dirty = False            # An efficiency flag. If True, the GUI knows it needs to redraw the logs.

# --- Seismic Data ---
sismos_data = [] # Stores the list of earthquakes fetched from the USGS API.


# =============================================================================
# III. CORE LOGIC & BACKGROUND THREADS
#
# These functions perform the main work of the application in background
# threads, so the user interface remains responsive.
# =============================================================================

def send_command(command: str):
    """Encodes and sends a command string over the active serial connection."""
    global log_dirty
    if ser and ser.is_open:
        try:
            full_command = command + '\n'
            ser.write(full_command.encode("utf-8"))
            # Safely update the log using the lock
            with data_lock:
                log_sent.append(f"[{time.strftime('%H:%M:%S')}] >> {command}")
                log_dirty = True
        except serial.SerialException as e:
            with data_lock:
                log_sent.append(f"ERROR: {e}")
                log_dirty = True

def read_serial_thread():
    """
    Runs in a continuous loop to read data from the serial port.
    This is the primary source of real-time data from the hardware.
    """
    global x_data, y_data, log_dirty
    prev_angle = None
    turns = 0
    while app_running:
        if ser and ser.is_open:
            try:
                line = ser.readline().decode("utf-8").strip()
                if line:
                    # Update the raw log
                    with data_lock:
                        log_recv.append(f"[{time.strftime('%H:%M:%S')}] << {line}")
                        log_dirty = True

                    # Try to parse the line as a number (angle) for the plot
                    try:
                        angle = float(line)
                        with data_lock:
                            # This logic handles continuous rotation of a 360-degree encoder
                            if prev_angle is not None:
                                if prev_angle > 300 and angle < 60: turns += 1
                                elif prev_angle < 60 and angle > 300: turns -= 1
                            prev_angle = angle
                            absolute_angle = (turns * 360) + angle

                            # Update plot data
                            current_time = time.time() - plot_start_time
                            x_data.append(current_time)
                            y_data.append(absolute_angle)

                            # Trim old data to keep the plot from getting too crowded
                            if len(x_data) > max_points:
                                x_data.pop(0)
                                y_data.pop(0)
                    except ValueError:
                        # The line was not a number, so we just log it and ignore for plotting.
                        pass
            except (serial.SerialException, UnicodeDecodeError):
                # Handle potential connection errors or garbage data
                time.sleep(0.5)
        else:
            # If not connected, wait before checking again
            time.sleep(0.5)

def wave_generator_thread():
    """
    Generates a sine wave and sends position commands to the motor
    at a fixed rate. Runs while `wave_running` is True.
    """
    amplitude = dpg.get_value("amplitude_slider")
    frequency = dpg.get_value("frequency_slider")
    start_time = time.time()

    while wave_running:
        elapsed_time = time.time() - start_time
        # Calculate the target position using a sine function
        target_pos = amplitude * math.sin(2 * math.pi * frequency * elapsed_time)
        send_command(f"m{int(target_pos)}")
        time.sleep(0.02) # Update rate of ~50 Hz

    send_command("m0") # Return to zero position when finished

# --- Seismic Playback Helper Functions ---

def _fetch_waveform_data(event_time: UTCDateTime):
    """Connects to IRIS client and downloads seismic waveform data."""
    client = Client("IRIS")
    # Fetch broadband (BH) data for 5 minutes after the event time
    st = client.get_waveforms(network="*", station="*", location="*", channel="BH?",
                              starttime=event_time, endtime=event_time + 300,
                              attach_response=True)
    return st

def _process_waveform_to_displacement(st):
    """
    Takes raw waveform data (Stream object) and processes it to get displacement.
    This involves several steps to clean and integrate the signal.
    """
    # Merge traces, detrend, and taper to reduce processing artifacts
    st.merge(method=0, fill_value=0)
    st.detrend("linear")
    st.taper(max_percentage=0.05, type="hann")

    # Remove instrument response to get true ground motion (acceleration)
    # A pre-filter is applied to prevent errors during integration
    st.remove_response(output="ACC", pre_filt=(0.05, 0.1, 10.0, 15.0))

    # Integrate twice: acceleration -> velocity -> displacement
    st.integrate(method='cumtrapz')
    st.integrate(method='cumtrapz')
    return st[0].data # Return the data from the first available trace

def _scale_data_for_motor(data, amplitude):
    """Normalizes and scales the displacement data to fit the motor's range."""
    max_abs_val = np.max(np.abs(data))
    if max_abs_val == 0:
        return None # Avoid division by zero
    normalized_data = data / max_abs_val
    return (normalized_data * amplitude).astype(int)

def play_sismo_thread():
    """
    The main thread for seismic playback. It coordinates fetching, processing,
    and sending data to the motor.
    """
    global sismo_running, plot_start_time, expected_wave_data

    # Step 1: Get the selected earthquake from the GUI
    sismo_info = None
    with api_lock:
        selected_title = dpg.get_value("sismo_list")
        for sismo in sismos_data:
            title = f"{sismo['properties']['mag']:.1f} mag - {sismo['properties']['place']}"
            if title == selected_title:
                sismo_info = sismo
                break
    if not sismo_info:
        dpg.set_value("sismo_playback_status", "Error: No sismo selected.")
        return

    try:
        # Step 2: Download the waveform data
        dpg.set_value("sismo_playback_status", "Downloading waveform data...")
        event_time = UTCDateTime(sismo_info['properties']['time'] / 1000.0)
        stream = _fetch_waveform_data(event_time)
        if not stream:
            dpg.set_value("sismo_playback_status", "No waveform data found.")
            return

        # Step 3: Process the data to get displacement
        dpg.set_value("sismo_playback_status", "Processing data (integrating)...")
        displacement_data = _process_waveform_to_displacement(stream)
        sample_interval = stream[0].stats.delta

        # Step 4: Scale the data for the motor
        dpg.set_value("sismo_playback_status", "Scaling data for motor...")
        playback_amplitude = dpg.get_value("sismo_amplitude_slider")
        scaled_data = _scale_data_for_motor(displacement_data, playback_amplitude)
        if scaled_data is None:
            dpg.set_value("sismo_playback_status", "Error: Processed data is empty.")
            return

        # Step 5: Start playback
        dpg.set_value("sismo_playback_status", f"Playing {len(scaled_data)} points...")
        with data_lock:
            x_data.clear(); y_data.clear(); expected_wave_data.clear()
        plot_start_time = time.time()

        for position in scaled_data:
            if not sismo_running:
                dpg.set_value("sismo_playback_status", "Playback stopped by user.")
                break
            send_command(f"m{position}")

            # Update the expected wave plot for comparison
            current_time = time.time() - plot_start_time
            with data_lock:
                expected_wave_data.append((current_time, position))
                if len(expected_wave_data) > max_points:
                    expected_wave_data.popleft()
            time.sleep(sample_interval)

    except Exception as e:
        dpg.set_value("sismo_playback_status", f"Error: {e}")
    finally:
        # Cleanup after playback finishes, is stopped, or an error occurs
        send_command("m0")
        sismo_running = False
        dpg.enable_item("play_sismo_button")
        dpg.disable_item("stop_sismo_button")
        if dpg.does_item_exist('sismo_playback_status') and "Playing" in dpg.get_value("sismo_playback_status"):
             dpg.set_value("sismo_playback_status", "Playback finished.")


# =============================================================================
# IV. GUI CALLBACKS
#
# These functions are directly called by Dear PyGui when the user interacts
# with a widget (e.g., clicks a button, selects an item).
# =============================================================================

def connect_callback():
    """Handles the 'Connect' button click."""
    global ser, plot_start_time
    port = dpg.get_value("ports_combo")
    baud = dpg.get_value("baud_rate_combo")
    if port and baud:
        try:
            ser = serial.Serial(port, int(baud), timeout=1)
            with data_lock:
                x_data.clear(); y_data.clear(); expected_wave_data.clear()
                log_recv.append(f"Connected to {port} at {baud} baud.")
                log_dirty = True
            plot_start_time = time.time()
        except serial.SerialException as e:
            dpg.set_value("connection_status", f"Error: {e}")

def refresh_ports_callback():
    """Handles the 'Refresh' button click for serial ports."""
    dpg.configure_item("ports_combo", items=find_serial_ports())

def send_manual_command_callback():
    """Sends the command from the manual input box."""
    command = dpg.get_value("command_input")
    if command:
        send_command(command)
        dpg.set_value("command_input", "")

def start_wave_callback():
    """Starts the sine wave generator thread."""
    global wave_running, plot_start_time
    if not wave_running:
        wave_running = True
        with data_lock:
            x_data.clear(); y_data.clear(); expected_wave_data.clear()
        plot_start_time = time.time()
        # Send motor speed/acceleration settings before starting
        send_command(f"s{dpg.get_value('speed_input')}")
        send_command(f"a{dpg.get_value('accel_input')}")
        threading.Thread(target=wave_generator_thread, daemon=True).start()
        dpg.disable_item("start_wave_button"); dpg.enable_item("stop_wave_button")

def stop_wave_callback():
    """Stops the sine wave generator thread."""
    global wave_running
    wave_running = False
    dpg.enable_item("start_wave_button"); dpg.disable_item("stop_wave_button")

def sismo_selected_callback(sender, app_data):
    """Updates the details view when a sismo is selected from the listbox."""
    selected_title = app_data
    with api_lock:
        for sismo in sismos_data:
            title = f"{sismo['properties']['mag']:.1f} mag - {sismo['properties']['place']}"
            if title == selected_title:
                props = sismo['properties']
                event_time = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(props['time'] / 1000.))
                details = (
                    f"Place: {props['place']}\n"
                    f"Date (UTC): {event_time}\n"
                    f"Magnitude: {props['mag']:.2f}\n"
                    f"Depth: {sismo['geometry']['coordinates'][2]:.2f} km\n"
                    f"ID: {sismo['id']}"
                )
                dpg.set_value("sismo_details", details)
                dpg.enable_item("play_sismo_button")
                break

def play_sismo_callback():
    """Starts the seismic data playback thread."""
    global sismo_running
    if not sismo_running:
        sismo_running = True
        dpg.disable_item("play_sismo_button")
        dpg.enable_item("stop_sismo_button")
        threading.Thread(target=play_sismo_thread, daemon=True).start()

def stop_sismo_callback():
    """Stops the seismic data playback thread."""
    global sismo_running
    sismo_running = False


# =============================================================================
# V. GUI UPDATE & HELPER FUNCTIONS
# =============================================================================

def find_serial_ports():
    """Scans for and returns a list of available serial COM ports."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def main_render_loop_update():
    """
    This function is called on every frame of the GUI. It's responsible
    for updating the plots and logs with new data from the background threads.
    """
    global log_dirty
    with data_lock:
        # Update the main position plot
        if x_data and y_data:
            dpg.set_value("series_real_main", [list(x_data), list(y_data)])
            dpg.fit_axis_data("x_axis_main")
            dpg.fit_axis_data("y_axis_main")

        # Update the comparison plot
        if dpg.does_item_exist("compare_plot"):
            if y_data: # Real data from encoder
                dpg.set_value("series_real_comp", [list(x_data), list(y_data)])
            if expected_wave_data: # Expected data from sismo/wave
                expected_x, expected_y = zip(*expected_wave_data)
                dpg.set_value("series_expected_comp", [list(expected_x), list(expected_y)])
            if y_data or expected_wave_data:
                dpg.fit_axis_data("x_axis_comp")
                dpg.fit_axis_data("y_axis_comp")

        # Update console logs only if new data has arrived (efficiency)
        if log_dirty:
            dpg.set_value("console_recv_output", "\n".join(log_recv))
            dpg.set_value("console_send_output", "\n".join(log_sent))
            # Auto-scroll to the bottom
            dpg.set_y_scroll("console_recv_container", -1.0)
            dpg.set_y_scroll("console_send_container", -1.0)
            log_dirty = False

def update_plot_sizes(sender, app_data):
    """Callback that resizes the plots to fit the window."""
    if dpg.does_item_exist("main_window"):
        window_width = dpg.get_item_width("main_window")
        window_height = dpg.get_item_height("main_window")
        # Set plots to be half the window width and a fixed height
        plot_width = (window_width - 40) // 2
        plot_height = window_height - 400
        if dpg.does_item_exist("time_plot"):
            dpg.configure_item("time_plot", width=plot_width, height=plot_height)
        if dpg.does_item_exist("compare_plot"):
            dpg.configure_item("compare_plot", width=plot_width, height=plot_height)

def cleanup():
    """Gracefully shuts down the application."""
    global app_running
    print("Closing application...")
    app_running = False # Signal threads to stop
    time.sleep(0.1)     # Give threads a moment to exit
    if ser and ser.is_open:
        ser.close()
    dpg.destroy_context()


# =============================================================================
# VI. MAIN APPLICATION SETUP & LIFECYCLE
# =============================================================================

# 1. Initialize Dear PyGui
dpg.create_context()

# 2. Define the User Interface
with dpg.window(label="Panel de Control", tag="main_window"):
    with dpg.group(horizontal=True):
        with dpg.plot(label="Feedback de Posicion", tag="time_plot", height=400, width=580):
            dpg.add_plot_legend()
            dpg.add_plot_axis(dpg.mvXAxis, label="Tiempo (s)", tag="x_axis_main")
            with dpg.plot_axis(dpg.mvYAxis, label="Posicion (pasos)", tag="y_axis_main"):
                dpg.add_line_series([], [], label="Posicion Real", tag="series_real_main")

        with dpg.plot(label="Comparación de Movimiento", tag="compare_plot", height=400, width=580):
            dpg.add_plot_legend()
            dpg.add_plot_axis(dpg.mvXAxis, label="Tiempo (s)", tag="x_axis_comp")
            with dpg.plot_axis(dpg.mvYAxis, label="Posicion (pasos)", tag="y_axis_comp"):
                dpg.add_line_series([], [], label="Movimiento Esperado (Sismo/Onda)", tag="series_expected_comp")
                dpg.add_line_series([], [], label="Movimiento Real (Encoder)", tag="series_real_comp")

    with dpg.tab_bar():
        with dpg.tab(label="Conexión"):
            dpg.add_text("Control de Conexión Serial")
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_combo(items=find_serial_ports(), tag="ports_combo", width=280, label="Puerto")
                dpg.add_button(label="Actualizar", callback=refresh_ports_callback)
            dpg.add_combo(["9600", "57600", "115200", "921600"], tag="baud_rate_combo", default_value="115200", width=200, label="Baud Rate")
            dpg.add_separator()
            dpg.add_button(label="Conectar", callback=connect_callback, width=-1, height=40)
            dpg.add_text("", tag="connection_status", color=(255, 0, 0))

        with dpg.tab(label="Control y Logs"):
            with dpg.group(horizontal=True):
                # Left side: Controls
                with dpg.group(width=450):
                    with dpg.collapsing_header(label="Generador de Onda Senoidal", default_open=True):
                        dpg.add_slider_int(label="Amplitud", tag="amplitude_slider", default_value=1600, min_value=100, max_value=10000)
                        dpg.add_slider_float(label="Frecuencia (Hz)", tag="frequency_slider", default_value=0.5, min_value=0.1, max_value=5.0)
                        dpg.add_input_int(label="Velocidad Motor", tag="speed_input", default_value=50000)
                        dpg.add_input_int(label="Aceleración Motor", tag="accel_input", default_value=20000)
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="Iniciar Onda", tag="start_wave_button", callback=start_wave_callback, width=-1)
                            dpg.add_button(label="Detener Onda", tag="stop_wave_button", callback=stop_wave_callback, width=-1)
                        dpg.disable_item("stop_wave_button")

                    with dpg.collapsing_header(label="Reproductor de Sismos (USGS)", default_open=True):
                        dpg.add_text("Detalles del Sismo Seleccionado")
                        dpg.add_input_text(tag="sismo_details", multiline=True, readonly=True, width=-1, height=150)
                        dpg.add_slider_int(label="Amplitud Reproducción", tag="sismo_amplitude_slider", min_value=100, max_value=20000, default_value=5000)
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="Reproducir Sismo", tag="play_sismo_button", callback=play_sismo_callback, width=-1)
                            dpg.add_button(label="Detener", tag="stop_sismo_button", callback=stop_sismo_callback, width=-1)
                        dpg.disable_item("play_sismo_button"); dpg.disable_item("stop_sismo_button")
                        dpg.add_text("Estado: Listo", tag="sismo_playback_status")

                # Right side: Logs and Manual Commands
                with dpg.group(width=-1):
                    dpg.add_text("Control Manual y Logs")
                    dpg.add_input_text(tag="command_input", hint="Comando (ej. m0)", on_enter=True, callback=send_manual_command_callback)
                    dpg.add_button(label="Enviar Comando", callback=send_manual_command_callback, width=-1)
                    dpg.add_text("Enviado a la Mesa")
                    with dpg.child_window(tag="console_send_container", height=150, border=True):
                        dpg.add_input_text(tag="console_send_output", multiline=True, readonly=True, width=-1, height=-1)
                    dpg.add_text("Recibido desde la Mesa")
                    with dpg.child_window(tag="console_recv_container", border=True, height=-1):
                        dpg.add_input_text(tag="console_recv_output", multiline=True, readonly=True, width=-1, height=-1)

# 3. Setup window resize handler
with dpg.item_handler_registry(tag="window_resize_handler"):
    dpg.add_item_resize_handler(callback=update_plot_sizes)
dpg.bind_item_handler_registry("main_window", "window_resize_handler")

# 4. Configure viewport and start the application
dpg.create_viewport(title='Controlador Mesa Sísmica', width=1200, height=800)
dpg.setup_dearpygui()
dpg.set_primary_window("main_window", True)

# 5. Start the background thread for reading serial data
threading.Thread(target=read_serial_thread, daemon=True).start()

# 6. Show the viewport and run the main loop
dpg.show_viewport()
dpg.maximize_viewport()
update_plot_sizes(None, None) # Initial call to set plot sizes correctly

while dpg.is_dearpygui_running():
    main_render_loop_update()      # Update GUI elements
    dpg.render_dearpygui_frame() # Render the frame

# 7. Cleanup when the application is closed
cleanup()