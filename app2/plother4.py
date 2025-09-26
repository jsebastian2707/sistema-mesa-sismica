import serial
import serial.tools.list_ports
import threading
import time
import dearpygui.dearpygui as dpg
from collections import deque
import math
import requests
import numpy as np # <<< NUEVA DEPENDENCIA

# <<< NUEVO: Dependencias de ObsPy >>>
from obspy.clients.fdsn import Client
from obspy import UTCDateTime

# --- Globales y Configuración ---
ser = None
app_running = True
wave_running = False
sismo_running = False # <<< NUEVO: Flag para controlar la reproducción del sismo

# --- Datos para las Gráficas ---
x_data = [] # Tiempo real
y_data = [] # Posición real del encoder
expected_wave_data = deque() # <<< NUEVO: Datos de la onda esperada (para comparación)
max_points = 1000 # Aumentado para ver más detalle
plot_start_time = 0

# --- Locks para proteger los datos compartidos ---
data_lock = threading.Lock()
api_lock = threading.Lock()

# --- Deques para los logs de la consola ---
log_recv = deque(maxlen=100)
log_sent = deque(maxlen=100)
log_dirty = False

# --- Global para almacenar los datos de los sismos ---
sismos_data = []

# --- Lógica de Comunicación Serial y de Hilos ---
def find_serial_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

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

def read_serial_thread():
    global x_data, y_data, log_dirty
    prev_angle = None
    turns = 0
    while app_running:
        if ser and ser.is_open:
            try:
                line = ser.readline().decode("utf-8").strip()
                if line:
                    with data_lock:
                        log_recv.append(f"[{time.strftime('%H:%M:%S')}] << {line}")
                        log_dirty = True
                    try:
                        angle = float(line)
                        with data_lock:
                            if prev_angle is not None:
                                if prev_angle > 300 and angle < 60: turns += 1
                                elif prev_angle < 60 and angle > 300: turns -= 1
                            prev_angle = angle
                            absolute_angle = (turns * 360) + angle
                            current_time = time.time() - plot_start_time
                            x_data.append(current_time)
                            y_data.append(absolute_angle)
                            if len(x_data) > max_points:
                                x_data.pop(0)
                                y_data.pop(0)
                    except ValueError:
                        pass
            except (serial.SerialException, UnicodeDecodeError):
                time.sleep(0.5)
        else:
            time.sleep(0.5)

def wave_generator_thread():
    global wave_running
    amplitude = dpg.get_value("amplitude_slider")
    frequency = dpg.get_value("frequency_slider")
    start_time = time.time()
    while wave_running:
        elapsed_time = time.time() - start_time
        target_pos = amplitude * math.sin(2 * math.pi * frequency * elapsed_time)
        send_command(f"m{int(target_pos)}")
        time.sleep(0.02) # ~50 Hz update rate
    send_command("m0")

def search_sismos_thread():
    global sismos_data
    dpg.set_value("sismo_status", "Buscando sismos...")
    dpg.configure_item("sismo_list", items=[])
    dpg.set_value("sismo_details", "")
    dpg.disable_item("play_sismo_button")

    min_mag = dpg.get_value("min_mag_input")
    max_mag = dpg.get_value("max_mag_input")
    url = f"https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&minmagnitude={min_mag}&maxmagnitude={max_mag}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        with api_lock:
            sismos_data = data.get("features", [])
        if not sismos_data:
            dpg.set_value("sismo_status", "No se encontraron sismos con esos criterios.")
            return
        sismo_titles = [f"{s['properties']['mag']:.1f} mag - {s['properties']['place']}" for s in sismos_data]
        dpg.configure_item("sismo_list", items=sismo_titles)
        dpg.set_value("sismo_status", f"Se encontraron {len(sismos_data)} eventos.")
    except requests.exceptions.RequestException as e:
        dpg.set_value("sismo_status", f"Error de red: {e}")
    finally:
        dpg.enable_item("search_sismos_button")
        

def play_sismo_thread():
    global sismo_running, plot_start_time, expected_wave_data
    
    # 1. Obtener ID del sismo desde la UI
    with api_lock:
        selected_title = dpg.get_value("sismo_list")
        sismo_info = None
        for sismo in sismos_data:
            title = f"{sismo['properties']['mag']:.1f} mag - {sismo['properties']['place']}"
            if title == selected_title:
                sismo_info = sismo
                break
    
    if not sismo_info:
        dpg.set_value("sismo_playback_status", "Error: No hay sismo seleccionado.")
        return

    # 2. Descargar datos con ObsPy
    try:
        dpg.set_value("sismo_playback_status", "Descargando datos de forma de onda...")
        client = Client("IRIS")
        event_time = UTCDateTime(sismo_info['properties']['time'] / 1000.0)
        
        # Buscamos datos de aceleración de banda ancha (BH) para el evento
        # Buscamos en un rango de 5 minutos después del sismo
        
        # --- LA LÍNEA CORREGIDA ESTÁ AQUÍ ---
        st = client.get_waveforms(network="*", station="*", location="*", channel="BH?",
                                  starttime=event_time, endtime=event_time + 300,
                                  attach_response=True)
        # --- FIN DE LA CORRECCIÓN ---
        
        if not st:
            dpg.set_value("sismo_playback_status", "No se encontraron datos de forma de onda (waveform).")
            sismo_running = False
            dpg.enable_item("play_sismo_button"); dpg.disable_item("stop_sismo_button")
            return
            
        # Pre-procesamiento: convertir a desplazamiento
        dpg.set_value("sismo_playback_status", "Procesando datos (integrando)...")
        # Unimos trazas separadas por gaps y las rellenamos con ceros
        st.merge(method=0, fill_value=0) 
        st.detrend("linear")
        st.taper(max_percentage=0.05, type="hann")
        
        # Removemos la respuesta del instrumento para obtener la aceleración real
        # y filtramos para evitar errores en la integración
        st.remove_response(output="ACC", pre_filt=(0.05, 0.1, 10.0, 15.0))
        
        st.integrate(method='cumtrapz') # Primera integración a velocidad
        st.integrate(method='cumtrapz') # Segunda integración a desplazamiento
        
        # Usamos el primer canal disponible (p.ej. Norte)
        trace = st[0]
        data = trace.data

        # 3. Normalizar y escalar los datos
        dpg.set_value("sismo_playback_status", "Escalando datos para el motor...")
        max_abs_val = np.max(np.abs(data))
        if max_abs_val == 0:
            dpg.set_value("sismo_playback_status", "Error: Datos del sismo vacíos después del procesamiento.")
            sismo_running = False
            return
            
        normalized_data = data / max_abs_val
        
        playback_amplitude = dpg.get_value("sismo_amplitude_slider")
        scaled_data = (normalized_data * playback_amplitude).astype(int)
        
        # 4. Iniciar la reproducción
        dpg.set_value("sismo_playback_status", f"Reproduciendo {len(scaled_data)} puntos...")
        
        # Limpiar y preparar la gráfica de comparación
        with data_lock:
            x_data.clear()
            y_data.clear()
            expected_wave_data.clear()
        plot_start_time = time.time()
        
        # Intervalo de tiempo entre muestras
        sample_interval = trace.stats.delta 

        for position in scaled_data:
            if not sismo_running:
                dpg.set_value("sismo_playback_status", "Reproducción detenida por el usuario.")
                break
            
            send_command(f"m{position}")
            
            # Guardamos el dato esperado para la gráfica
            current_time = time.time() - plot_start_time
            with data_lock:
                expected_wave_data.append((current_time, position))
                if len(expected_wave_data) > max_points:
                    expected_wave_data.popleft()

            time.sleep(sample_interval)

    except Exception as e:
        dpg.set_value("sismo_playback_status", f"Error: {e}")
    finally:
        send_command("m0") # Asegurarse que el motor vuelva a cero
        sismo_running = False
        dpg.enable_item("play_sismo_button")
        dpg.disable_item("stop_sismo_button")
        if dpg.does_item_exist('sismo_playback_status') and "Reproduciendo" in dpg.get_value("sismo_playback_status"):
             dpg.set_value("sismo_playback_status", "Reproducción finalizada.")

def connect_callback():
    global ser, plot_start_time
    port = dpg.get_value("ports_combo")
    baud = dpg.get_value("baud_rate_combo")
    if port and baud:
        try:
            ser = serial.Serial(port, int(baud), timeout=1)
            with data_lock:
                x_data.clear(); y_data.clear(); expected_wave_data.clear()
                log_recv.append(f"Conectado a {port} a {baud} baud.")
                log_dirty = True
            plot_start_time = time.time()
        except serial.SerialException as e:
            dpg.set_value("connection_status", f"Error: {e}")

def send_manual_command_callback():
    command = dpg.get_value("command_input")
    if command: send_command(command); dpg.set_value("command_input", "")

def refresh_ports_callback():
    dpg.configure_item("ports_combo", items=find_serial_ports())

def start_wave_callback():
    global wave_running, plot_start_time
    if not wave_running:
        wave_running = True
        with data_lock: x_data.clear(); y_data.clear(); expected_wave_data.clear()
        plot_start_time = time.time()
        send_command(f"s{dpg.get_value('speed_input')}")
        send_command(f"a{dpg.get_value('accel_input')}")
        threading.Thread(target=wave_generator_thread, daemon=True).start()
        dpg.disable_item("start_wave_button"); dpg.enable_item("stop_wave_button")

def stop_wave_callback():
    global wave_running
    wave_running = False
    dpg.enable_item("start_wave_button"); dpg.disable_item("stop_wave_button")

def search_sismos_callback():
    dpg.disable_item("search_sismos_button")
    threading.Thread(target=search_sismos_thread, daemon=True).start()

def sismo_selected_callback(sender, app_data):
    selected_title = app_data
    with api_lock:
        for sismo in sismos_data:
            title = f"{sismo['properties']['mag']:.1f} mag - {sismo['properties']['place']}"
            if title == selected_title:
                props = sismo['properties']
                fecha = time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(props['time'] / 1000.))
                details = (
                    f"Lugar: {props['place']}\n"
                    f"Fecha (UTC): {fecha}\n"
                    f"Magnitud: {props['mag']:.2f}\n"
                    f"Profundidad: {sismo['geometry']['coordinates'][2]:.2f} km\n"
                    f"ID: {sismo['id']}"
                )
                dpg.set_value("sismo_details", details)
                dpg.enable_item("play_sismo_button")
                break

def play_sismo_callback():
    global sismo_running
    if not sismo_running:
        sismo_running = True
        dpg.disable_item("play_sismo_button")
        dpg.enable_item("stop_sismo_button")
        threading.Thread(target=play_sismo_thread, daemon=True).start()

def stop_sismo_callback():
    global sismo_running
    sismo_running = False

def update_gui_callbacks():
    global log_dirty
    # Actualizar gráfica principal
    with data_lock:
        if x_data and y_data:
            dpg.set_value("series_real_main", [list(x_data), list(y_data)])
            dpg.fit_axis_data("x_axis_main"); dpg.fit_axis_data("y_axis_main")
        
        # <<< NUEVO: Actualizar gráfica de comparación >>>
        if dpg.does_item_exist("comparison_plot"):
            if y_data: # Real
                dpg.set_value("series_real_comp", [list(x_data), list(y_data)])
            if expected_wave_data: # Esperado
                expected_x, expected_y = zip(*expected_wave_data)
                dpg.set_value("series_expected_comp", [list(expected_x), list(expected_y)])
            
            if y_data or expected_wave_data:
                dpg.fit_axis_data("x_axis_comp")
                dpg.fit_axis_data("y_axis_comp")

        if log_dirty:
            dpg.set_value("console_recv_output", "\n".join(log_recv))
            dpg.set_value("console_send_output", "\n".join(log_sent))
            dpg.set_y_scroll("console_recv_container", -1.0)
            dpg.set_y_scroll("console_send_container", -1.0)
            log_dirty = False

def cleanup():
    global app_running, wave_running, sismo_running
    print("Cerrando aplicación...")
    wave_running = False; app_running = False; sismo_running = False
    time.sleep(0.1)
    if ser and ser.is_open: ser.close()
    dpg.destroy_context()

dpg.create_context()
    

with dpg.window(label="Panel de Control", tag="main_window", width=1200, height=700):
    with dpg.plot(label="Feedback de Posicion", height=400, width=-1):
        dpg.add_plot_legend()
        dpg.add_plot_axis(dpg.mvXAxis, label="Tiempo (s)", tag="x_axis_main")
        with dpg.plot_axis(dpg.mvYAxis, label="Posicion (pasos)", tag="y_axis_main"):
            dpg.add_line_series([], [], label="Posicion Real", tag="series_real_main")
    with dpg.tab_bar():
        with dpg.tab(label="conexion"):
            with dpg.group(horizontal=True):
                dpg.add_combo(items=find_serial_ports(), tag="ports_combo", width=280)
                dpg.add_button(label="Actualizar", callback=refresh_ports_callback)
            dpg.add_text("Selecciona la velocidad (Baud Rate):")
            dpg.add_combo(["9600", "57600", "115200", "921600"], tag="baud_rate_combo", default_value="115200", width=200)
            dpg.add_separator()
            dpg.add_button(label="Conectar", callback=connect_callback, width=-1, height=40)
            dpg.add_text("", tag="connection_status", color=(255, 0, 0))
        # --- PESTAÑA 1: GENERADOR DE ONDAS ---
        with dpg.tab(label="Generador de Ondas"):
            with dpg.group(horizontal=True):
                with dpg.group(width=300):
                    # ... (Controles sin cambios) ...
                    dpg.add_text("Generador de Onda Senoidal")
                    dpg.add_slider_int(label="Amplitud", tag="amplitude_slider", default_value=1600, min_value=100, max_value=10000)
                    dpg.add_slider_float(label="Frecuencia", tag="frequency_slider", default_value=0.5, min_value=0.1, max_value=5.0, format="%.2f Hz")
                    dpg.add_separator()
                    dpg.add_text("Ajustes del Motor")
                    dpg.add_input_int(label="Velocidad (s)", tag="speed_input", default_value=50000)
                    dpg.add_input_int(label="Aceleracion (a)", tag="accel_input", default_value=20000)
                    dpg.add_separator()
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Iniciar Onda", tag="start_wave_button", callback=start_wave_callback, width=-1)
                        dpg.add_button(label="Detener Onda", tag="stop_wave_button", callback=stop_wave_callback, width=-1); dpg.disable_item("stop_wave_button")
                    dpg.add_separator()
                    dpg.add_text("Control Manual y Log")
                    dpg.add_input_text(tag="command_input", hint="Comando (ej. m0)", on_enter=True, callback=send_manual_command_callback)
                    dpg.add_button(label="Enviar Comando", callback=send_manual_command_callback, width=-1)
                    with dpg.child_window(tag="console_send_container", height=150, border=True):
                        dpg.add_input_text(tag="console_send_output", multiline=True, readonly=True, width=-1, height=-1)
                
                with dpg.group():
                    
                    dpg.add_text("Recibido desde la Mesa")
                    with dpg.child_window(tag="console_recv_container", border=True):
                        dpg.add_input_text(tag="console_recv_output", multiline=True, readonly=True, width=-1, height=-1)

        # --- PESTAÑA 2: BÚSQUEDA DE SISMOS ---
        with dpg.tab(label="Búsqueda de Sismos (USGS)"):
            with dpg.group(horizontal=True):
                with dpg.group(width=450):
                    dpg.add_text("Buscar Sismos (USGS - Ultimo Mes)")
                    dpg.add_input_float(label="Magnitud Mínima", tag="min_mag_input", default_value=5.0, step=0.1, format="%.1f")
                    dpg.add_input_float(label="Magnitud Máxima", tag="max_mag_input", default_value=8.0, step=0.1, format="%.1f")
                    dpg.add_button(label="Buscar Sismos", tag="search_sismos_button", callback=search_sismos_callback, width=-1)
                    dpg.add_text("Buscando...", tag="sismo_status")
                    dpg.add_listbox(tag="sismo_list", callback=sismo_selected_callback, width=-1, num_items=18)

                with dpg.group():
                    dpg.add_text("Detalles del Sismo Seleccionado")
                    dpg.add_input_text(tag="sismo_details", multiline=True, readonly=True, width=-1, height=200)
                    dpg.add_separator()
                    dpg.add_text("Controles de Reproducción")
                    dpg.add_slider_int(label="Amplitud de Reproducción", tag="sismo_amplitude_slider", min_value=100, max_value=20000, default_value=5000)
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Reproducir Sismo", tag="play_sismo_button", callback=play_sismo_callback, width=200)
                        dpg.add_button(label="Detener Reproducción", tag="stop_sismo_button", callback=stop_sismo_callback, width=200)
                    dpg.disable_item("play_sismo_button"); dpg.disable_item("stop_sismo_button")
                    dpg.add_text("Estado: Listo", tag="sismo_playback_status")

        # <<< NUEVO: PESTAÑA 3: COMPARACIÓN DE MOVIMIENTO >>>
        with dpg.tab(label="Playback & Comparison"):
            dpg.add_text("Comparación de Movimiento Esperado vs. Real")
            dpg.add_separator()
            with dpg.plot(label="Comparación de Movimiento", tag="comparison_plot", height=-1, width=-1):
                dpg.add_plot_legend()
                dpg.add_plot_axis(dpg.mvXAxis, label="Tiempo (s)", tag="x_axis_comp")
                with dpg.plot_axis(dpg.mvYAxis, label="Posicion (pasos)", tag="y_axis_comp"):
                    dpg.add_line_series([], [], label="Movimiento Esperado (Sismo)", tag="series_expected_comp")
                    dpg.add_line_series([], [], label="Movimiento Real (Encoder)", tag="series_real_comp")


# --- Configuración del Viewport y Bucle Principal ---
dpg.create_viewport(title='Controlador Mesa Sísmica Avanzado', width=1200, height=700)
dpg.setup_dearpygui()
dpg.set_primary_window("main_window", True)
threading.Thread(target=read_serial_thread, daemon=True).start()
dpg.show_viewport()

while dpg.is_dearpygui_running():
    update_gui_callbacks()
    dpg.render_dearpygui_frame()

cleanup()


