# seismic_viewer_handler.py
# Contains the data loading and processing logic for the seismic trace viewer tab.
# This code operates on the shared app_state and does not create GUI elements directly,
# with the exception of popup windows for plots.

import dearpygui.dearpygui as dpg
import numpy as np
from obspy import read
import os
import threading
import time

import app_state
from serial_handler import send_command

RECORDS_FOLDER_NAME = "sismic_records"

def _set_viewer_status(message: str) -> None:
    """Updates the shared playback status message and marks it dirty."""
    with app_state.data_lock:
        app_state.viewer_playback_status = message
        app_state.viewer_playback_status_dirty = True
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
    app_state.viewer_seismic_files.clear()
    app_state.viewer_all_traces.clear()
    app_state.viewer_selected_trace_index = None

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
        _set_viewer_status(f"Error loading data: {e}")
    finally:
        # Signal the GUI thread that it needs to redraw the file list
        app_state.viewer_data_dirty.set()
        print("Viewer: Data load finished.")
        if app_state.viewer_all_traces:
            _set_viewer_status("Data loaded. Select a trace to play.")

def process_selected_trace():
    """Processes the currently selected trace to get acceleration and displays it."""
    if app_state.viewer_selected_trace_index is None:
        print("Viewer: No trace selected to process.")
        return

    trace_info = app_state.viewer_all_traces[app_state.viewer_selected_trace_index]
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

    with app_state.data_lock:
        amplitude = int(abs(app_state.viewer_playback_amplitude))
    amplitude = max(amplitude, 1)

    scaled = np.clip((data / max_abs) * amplitude, -amplitude, amplitude).astype(int)

    sample_interval = getattr(working_trace.stats, "delta", None)
    if sample_interval is None or not np.isfinite(sample_interval) or sample_interval <= 0:
        sample_interval = 0.01

    return scaled, float(sample_interval)

def start_playback():
    """Starts a background thread to play the selected seismic trace on the motor."""
    if not (app_state.ser and app_state.ser.is_open):
        _set_viewer_status("Error: Connect to the table first.")
        return

    with app_state.data_lock:
        selected_index = app_state.viewer_selected_trace_index
        is_running = app_state.sismo_running
        wave_running = app_state.wave_running
        trace_info = None
        if (selected_index is not None and
                0 <= selected_index < len(app_state.viewer_all_traces)):
            trace_info = app_state.viewer_all_traces[selected_index]

    if trace_info is None:
        _set_viewer_status("Error: Select a trace before playing.")
        return

    if is_running:
        _set_viewer_status("Playback already running.")
        return

    if wave_running:
        _set_viewer_status("Error: Stop the sine wave generator before playback.")
        return

    with app_state.data_lock:
        app_state.sismo_running = True

    metadata = {
        'id': trace_info['id'],
        'file_name': trace_info['file_name'],
        'num_samples': len(trace_info['data'])
    }
    trace_copy = trace_info['obspy_trace'].copy()

    _set_viewer_status(f"Preparing {metadata['id']} for playback...")
    threading.Thread(target=_playback_worker, args=(trace_copy, metadata), daemon=True).start()

def _playback_worker(trace, metadata):
    """Worker routine that streams the processed trace to the motor."""
    try:
        scaled_data, sample_interval = _prepare_trace_for_playback(trace)
    except Exception as exc:
        _set_viewer_status(f"Error: {exc}")
        with app_state.data_lock:
            app_state.sismo_running = False
        send_command("m0")
        return

    total_samples = len(scaled_data)
    if total_samples == 0:
        _set_viewer_status("Error: Trace produced no samples.")
        with app_state.data_lock:
            app_state.sismo_running = False
        send_command("m0")
        return

    sample_interval = max(sample_interval, 0.001)

    with app_state.data_lock:
        app_state.expected_wave_data.clear()
        app_state.x_data.clear()
        app_state.y_data.clear()
        app_state.plot_start_time = time.time()

    if dpg.does_item_exist("speed_input"):
        send_command(f"s{dpg.get_value('speed_input')}")
    if dpg.does_item_exist("accel_input"):
        send_command(f"a{dpg.get_value('accel_input')}")

    _set_viewer_status(f"Playing {total_samples} samples from {metadata.get('file_name', 'trace')}...")

    playback_start = time.time()
    try:
        for raw_position in scaled_data:
            if not app_state.sismo_running:
                _set_viewer_status("Playback stopped by user.")
                send_command("m0")
                return

            position = int(raw_position)
            send_command(f"m{position}")

            current_time = time.time() - playback_start
            with app_state.data_lock:
                app_state.expected_wave_data.append((current_time, position))
                if len(app_state.expected_wave_data) > app_state.max_points:
                    app_state.expected_wave_data.popleft()

            time.sleep(sample_interval)

    except Exception as exc:
        _set_viewer_status(f"Error during playback: {exc}")
    else:
        _set_viewer_status("Playback finished.")
    finally:
        send_command("m0")
        with app_state.data_lock:
            app_state.sismo_running = False

def stop_playback():
    """Signals the playback thread to stop streaming commands."""
    with app_state.data_lock:
        was_running = app_state.sismo_running
        app_state.sismo_running = False

    if was_running:
        _set_viewer_status("Stopping playback...")
