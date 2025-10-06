# app_state.py

import threading
from collections import deque

ser = None
app_running = True
data_lock = threading.Lock()

wave_running = False
sismo_running = False

x_data = deque(maxlen=500); y_data = deque(maxlen=500)
expected_wave_data = deque(maxlen=500); plot_start_time = 0; max_points = 500

log_recv = deque(maxlen=100); log_sent = deque(maxlen=100); log_dirty = False

viewer_seismic_files = {}
viewer_all_traces = []              
viewer_selected_trace_index = None
viewer_data_dirty = threading.Event() # Event to notify GUI to update viewer