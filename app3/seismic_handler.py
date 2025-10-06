# seismic_handler.py
# Contains the data loading and processing logic for the seismic trace viewer tab.
# This code operates on the shared app_state and does not create GUI elements directly,
# with the exception of popup windows for plots.

import dearpygui.dearpygui as dpg
import numpy as np
from obspy import read
import os
import threading

import app_state

RECORDS_FOLDER_NAME = "sismic_records"

def get_records_folder_path():
    """Gets the absolute path to the sismic_records folder."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(script_dir, RECORDS_FOLDER_NAME)

def load_data_for_viewer_thread():
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