# seismic_handler.py
# Contains the data loading and processing logic for the seismic trace viewer tab.
# This code operates on the shared app_state and does not create GUI elements directly,
# with the exception of popup windows for plots.

import numpy as np
from obspy import read
import os
import threading
import time
import dearpygui.dearpygui as dpg

import app_state
from serial_handler import send_command

def get_records_folder_path():
    """Gets the absolute path to the sismic_records folder."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, "sismic_records")

def load_traces_from_folder_thread():
    """Loads all seismic data from the records folder into the viewer's state variables."""
    print("Viewer: Starting data load...")
    folder_path = get_records_folder_path()
    
    # Reset state
    app_state.viewer_seismic_files.clear()
    app_state.viewer_all_traces.clear()
    app_state.viewer_selected_trace_index = None

    try:
        files = [f for f in os.listdir(folder_path) if f.lower().endswith(('.mseed', '.msd', '.miniseed'))]
        if not files:
            print("Viewer: No seismic files found.")
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
                        'global_index': len(app_state.viewer_all_traces),
                        'obspy_trace': trace
                    }
                    file_traces.append(data_info)
                    app_state.viewer_all_traces.append(data_info)
                
                app_state.viewer_seismic_files[file_name] = file_traces
                print(f"Viewer: Loaded {file_name} with {len(file_traces)} traces.")

            except Exception as e:
                print(f"Viewer: Error loading {file_path}: {e}")

    except Exception as e:
        print(f"Viewer: General error loading data: {e}")
    finally:
        # Signal the GUI thread that it needs to redraw the file list
        app_state.viewer_data_dirty.set()
        print("Viewer: Data load finished.")

def process_selected_trace():
    """Processes the currently selected trace to get acceleration and displays it."""
    if app_state.viewer_selected_trace_index is None:
        print("Viewer: No trace selected to process.")
        return

    trace_info = app_state.viewer_all_traces[app_state.viewer_selected_trace_index]
    trace_data = trace_info['obspy_trace'].copy()
    print(f"Viewer: Processing {trace_data.id} for shaking table.")

    # Processing pipeline
    trace_data.detrend('linear')
    fmin, fmax = 0.1, 20
    trace_data.filter('bandpass', freqmin=fmin, freqmax=fmax, corners=4, zerophase=True)
    trace_data.differentiate()
    #print("Viewer: Detrend, filter, and differentiation complete.")
    # Visualization in a new window
    times = trace_data.times()
    accel_data = trace_data.data
    
    # Almacenar en formato (tiempo, valor) para compatibilidad con visualización
    with app_state.data_lock:
        app_state.expected_wave_data.clear()
        for t, val in zip(times, accel_data):
            app_state.expected_wave_data.append((float(t), float(val)))
        app_state.expected_wave_time = list(times)
    
    print("Viewer: Acceleration data ready.")

def _prepare_trace_for_playback(trace, amplitude=1600):
    """
    Prepara la traza sísmica para reproducción en la mesa.
    Convierte aceleración/velocidad a desplazamiento mediante integración doble.
    
    Args:
        trace: Traza de ObsPy (puede ser aceleración, velocidad o desplazamiento)
        amplitude: Amplitud máxima en pasos del motor (default: 1600)
    
    Returns:
        tuple: (datos_escalados, intervalo_muestreo)
    """
    working_trace = trace.copy()
    
    # Paso 1: Detrend y taper para reducir artefactos
    working_trace.detrend('linear')
    working_trace.taper(max_percentage=0.05, type='hann')
    
    # Paso 2: Filtrado bandpass para eliminar ruido
    fmin, fmax = 0.1, 20
    working_trace.filter('bandpass', freqmin=fmin, freqmax=fmax, corners=4, zerophase=True)
    
    # Paso 3: Integración doble (aceleración → velocidad → desplazamiento)
    # Si la traza ya es desplazamiento, esto no causará problemas
    working_trace.integrate(method='cumtrapz')
    working_trace.integrate(method='cumtrapz')
    
    # Convertir a array numpy
    data = working_trace.data.astype(np.float64)
    
    if data.size == 0:
        raise ValueError("La traza no contiene muestras.")
    
    # Normalizar y escalar
    max_abs = np.max(np.abs(data))
    if not np.isfinite(max_abs) or max_abs == 0:
        raise ValueError("La amplitud de la traza es cero o inválida.")
    
    # Escalar a la amplitud deseada (en pasos del motor)
    amplitude = max(int(abs(amplitude)), 1)
    scaled = np.clip((data / max_abs) * amplitude, -amplitude, amplitude).astype(int)
    
    # Obtener intervalo de muestreo
    sample_interval = getattr(working_trace.stats, 'delta', None)
    if sample_interval is None or not np.isfinite(sample_interval) or sample_interval <= 0:
        sample_interval = 0.01  # Default: 100 Hz
    
    print(f"Viewer: Traza preparada - {len(scaled)} muestras, intervalo: {sample_interval:.4f}s, amplitud: ±{amplitude} pasos")
    return scaled, float(sample_interval)

def start_seismic_playback(amplitude=1600):
    """
    Inicia la reproducción de la traza sísmica seleccionada en el controlador.
    
    Args:
        amplitude: Amplitud máxima en pasos del motor (default: 1600)
    """
    # Verificar conexión
    if not (app_state.ser and app_state.ser.is_open):
        print("Error: Debe estar conectado al ESP32 antes de reproducir.")
        return False
    
    # Verificar que hay una traza seleccionada
    if app_state.viewer_selected_trace_index is None:
        print("Error: Debe seleccionar una traza antes de reproducir.")
        return False
    
    # Verificar que no hay otra reproducción activa
    with app_state.data_lock:
        if app_state.sismo_running:
            print("Error: Ya hay una reproducción sísmica en curso.")
            return False
        if app_state.wave_running:
            print("Error: Detenga el generador de ondas antes de reproducir.")
            return False
        app_state.sismo_running = True
    
    # Obtener la traza seleccionada
    try:
        trace_info = app_state.viewer_all_traces[app_state.viewer_selected_trace_index]
        trace_copy = trace_info['obspy_trace'].copy()
    except (IndexError, KeyError) as e:
        print(f"Error: No se pudo obtener la traza seleccionada: {e}")
        with app_state.data_lock:
            app_state.sismo_running = False
        return False
    
    # Iniciar thread de reproducción
    print(f"Iniciando reproducción de {trace_info['id']}...")
    threading.Thread(
        target=_playback_worker_thread,
        args=(trace_copy, trace_info, amplitude),
        daemon=True
    ).start()
    
    return True

def _playback_worker_thread(trace, trace_info, amplitude):
    """
    Thread worker que envía los comandos de posición al controlador.
    
    Args:
        trace: Traza de ObsPy a reproducir
        trace_info: Información de la traza (metadata)
        amplitude: Amplitud máxima en pasos
    """
    try:
        # Preparar la traza para reproducción
        scaled_data, sample_interval = _prepare_trace_for_playback(trace, amplitude)
    except Exception as exc:
        print(f"Error al preparar la traza: {exc}")
        with app_state.data_lock:
            app_state.sismo_running = False
        send_command("m0")
        return
    
    total_samples = len(scaled_data)
    if total_samples == 0:
        print("Error: La traza no produjo muestras válidas.")
        with app_state.data_lock:
            app_state.sismo_running = False
        send_command("m0")
        return
    
    # Asegurar intervalo mínimo
    sample_interval = max(sample_interval, 0.001)
    
    # Limpiar datos de visualización
    with app_state.data_lock:
        app_state.expected_wave_data.clear()
        app_state.x_data.clear()
        app_state.y_data.clear()
        app_state.plot_start_time = time.time()
    
    # Enviar configuración del motor
    if dpg.does_item_exist("speed_input"):
        speed = dpg.get_value("speed_input")
        send_command(f"s{speed}")
        print(f"Configuración: Velocidad = {speed}")
    
    if dpg.does_item_exist("accel_input"):
        accel = dpg.get_value("accel_input")
        send_command(f"a{accel}")
        print(f"Configuración: Aceleración = {accel}")
    
    print(f"Reproduciendo {total_samples} muestras (duración aproximada: {total_samples * sample_interval:.2f}s)")
    
    playback_start = time.time()
    samples_sent = 0
    
    try:
        for raw_position in scaled_data:
            # Verificar si se debe detener
            if not app_state.sismo_running:
                print("Reproducción detenida por el usuario.")
                send_command("m0")
                return
            
            # Enviar comando de posición
            position = int(raw_position)
            send_command(f"m{position}")
            samples_sent += 1
            
            # Almacenar posición esperada para visualización
            current_time = time.time() - playback_start
            with app_state.data_lock:
                app_state.expected_wave_data.append((current_time, position))
                if len(app_state.expected_wave_data) > app_state.max_points:
                    app_state.expected_wave_data.popleft()
            
            # Esperar el intervalo de muestreo
            time.sleep(sample_interval)
        
        print(f"Reproducción completada. {samples_sent} muestras enviadas.")
        
    except Exception as exc:
        print(f"Error durante la reproducción: {exc}")
    finally:
        # Detener el motor y limpiar estado
        send_command("m0")
        with app_state.data_lock:
            app_state.sismo_running = False
        print("Reproducción finalizada.")

def stop_seismic_playback():
    """Detiene la reproducción sísmica en curso."""
    with app_state.data_lock:
        was_running = app_state.sismo_running
        app_state.sismo_running = False
    
    if was_running:
        print("Deteniendo reproducción sísmica...")
        send_command("m0")

def trace_filters(trace): ###### trace filte example function
    """Applies a series of filters to the trace and returns the processed trace."""
    trace.detrend('linear')
    fmin, fmax = 0.1, 20
    trace.filter('bandpass', freqmin=fmin, freqmax=fmax, corners=4, zerophase=True)
    trace.differentiate()
    return trace