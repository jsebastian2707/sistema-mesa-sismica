# seismic_handler.py
# Contains the data loading and processing logic for the seismic trace viewer tab.
# This code operates on the shared app_state and does not create GUI elements directly,
# with the exception of popup windows for plots.

import numpy as np
from obspy import read
import os

import app_state

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
    accel_data, times = trace_data.data, trace_data.times()
    app_state.expected_wave_data = trace_data.tolist()
    app_state.expected_wave_time = times.tolist()
    print("Viewer: Acceleration data ready.")

def trace_filters(trace): ###### trace filte example function
    """Applies a series of filters to the trace and returns the processed trace."""
    trace.detrend('linear')
    fmin, fmax = 0.1, 20
    trace.filter('bandpass', freqmin=fmin, freqmax=fmax, corners=4, zerophase=True)
    trace.differentiate()
    return trace