# seismic_handler.py
# NO CONTIENE LLAMADAS A DPG. SOLO MODIFICA EL app_state.

import os
import time
import numpy as np
from obspy import read as obspy_read
from tkinter import filedialog, Tk
import shutil 
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg

import app_state
from serial_handler import send_command

RECORDS_FOLDER_NAME = "sismic_records"
if not hasattr(app_state, 'local_sismos'):
    app_state.local_sismos = {}

def get_records_folder_path():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, RECORDS_FOLDER_NAME)

def scan_and_load_sismic_records(is_initial_load=False):
    folder_path = get_records_folder_path()
    if not os.path.exists(folder_path):
        os.makedirs(folder_path)
    
    app_state.sismo_status_message = f"Cargando desde '{RECORDS_FOLDER_NAME}'..."
    app_state.local_sismos.clear()
    loaded_files = []

    try:
        filenames = sorted(os.listdir(folder_path))
        for filename in filenames:
            if filename.lower().endswith(('.mseed', '.msd', '.miniseed')):
                full_path = os.path.join(folder_path, filename)
                try:
                    st = obspy_read(full_path)
                    app_state.local_sismos[filename] = st
                    loaded_files.append(filename)
                except Exception as e:
                    print(f"Error al leer el archivo {filename}: {e}")
        
        if not loaded_files:
            app_state.sismo_status_message = f"No se encontraron archivos en '{RECORDS_FOLDER_NAME}'."
        else:
            app_state.sismo_status_message = f"Se cargaron {len(loaded_files)} archivos."
        
    except Exception as e:
        app_state.sismo_status_message = f"Error al acceder a la carpeta: {e}"
    finally:
        # Levanta la bandera para que la GUI sepa que debe redibujarse
        app_state.sismo_list_dirty = True

def import_and_copy_files_thread():
    app_state.sismo_status_message = "Abriendo selector de archivos..."
    try:
        root = Tk(); root.withdraw()
        filepaths = filedialog.askopenfilenames(title="Importar archivos MiniSEED", filetypes=[("MiniSEED", "*.mseed *.msd"), ("All files", "*.*")])
    finally:
        root.destroy()

    if not filepaths:
        app_state.sismo_status_message = "Importación cancelada."
        return

    records_folder = get_records_folder_path()
    copied_count = 0
    for fpath in filepaths:
        try:
            filename = os.path.basename(fpath)
            app_state.sismo_status_message = f"Importando: {filename}..."
            shutil.copy(fpath, os.path.join(records_folder, filename))
            copied_count += 1
        except Exception as e:
            print(f"Error al copiar {fpath}: {e}")
            app_state.sismo_status_message = f"Error importando {filename}."

    app_state.sismo_status_message = f"Se importaron {copied_count} archivos. Refrescando..."
    scan_and_load_sismic_records()

def play_local_sismo_thread():
    if not app_state.ser or not app_state.ser.is_open:
        app_state.sismo_playback_status_message = "Error: Conecte la mesa primero."
        app_state.sismo_running = False
        return

    try:
        selected_file = app_state.selected_sismo_file
        if not selected_file or selected_file not in app_state.local_sismos:
            app_state.sismo_playback_status_message = "Error: No hay archivo válido seleccionado."
            return
        
        st = app_state.local_sismos[selected_file].copy()
        
        app_state.sismo_playback_status_message = "Procesando datos..."
        st.merge(method=0, fill_value=0); st.detrend("linear"); st.taper(max_percentage=0.05, type="hann")
        st.integrate(method='cumtrapz'); st.integrate(method='cumtrapz')
        trace = st[0]; data = trace.data

        app_state.sismo_playback_status_message = "Escalando datos..."
        max_abs_val = np.max(np.abs(data))
        if max_abs_val == 0:
            app_state.sismo_playback_status_message = "Error: Datos vacíos."
            return
        
        normalized_data = data / max_abs_val
        playback_amplitude = dpg.get_value("sismo_amplitude_slider") # Leer valor de la UI es seguro
        scaled_data = (normalized_data * playback_amplitude).astype(int)
        
        app_state.sismo_playback_status_message = f"Reproduciendo {len(scaled_data)} puntos..."
        with app_state.data_lock: app_state.x_data.clear(); app_state.y_data.clear(); app_state.expected_wave_data.clear()
        app_state.plot_start_time = time.time(); sample_interval = trace.stats.delta
        
        for position in scaled_data:
            if not app_state.sismo_running:
                app_state.sismo_playback_status_message = "Reproducción detenida."
                break
            send_command(f"m{position}")
            current_time = time.time() - app_state.plot_start_time
            with app_state.data_lock:
                app_state.expected_wave_data.append((current_time, position))
                if len(app_state.expected_wave_data) > app_state.max_points: app_state.expected_wave_data.popleft()
            time.sleep(sample_interval)

    except Exception as e:
        app_state.sismo_playback_status_message = f"Error: {e}"
    finally:
        send_command("m0"); app_state.sismo_running = False
        app_state.sismo_playback_status_message = "Reproducción finalizada."


def create_waveform_image(trace, width=400, height=80):
    plt.switch_backend('Agg'); fig, ax = plt.subplots(figsize=(width / 100, height / 100), dpi=100)
    fig.patch.set_facecolor('#252525'); ax.set_facecolor('#1E1E1E')
    ax.plot(trace.times(), trace.data, 'c-', linewidth=0.7)
    ax.axes.get_xaxis().set_visible(False); ax.axes.get_yaxis().set_visible(False)
    ax.spines['top'].set_visible(False); ax.spines['right'].set_visible(False)
    ax.spines['bottom'].set_visible(False); ax.spines['left'].set_visible(False)
    plt.tight_layout(pad=0); canvas = FigureCanvasAgg(fig); canvas.draw()
    buf = canvas.buffer_rgba(); img_array = np.asarray(buf)
    img_flat = img_array.flatten().astype(np.float32) / 255.0; plt.close(fig)
    return {'data': img_flat, 'width': img_array.shape[1], 'height': img_array.shape[0]}