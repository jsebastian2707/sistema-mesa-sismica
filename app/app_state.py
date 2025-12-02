# app_state.py
# se usa threading para el bloquear la escritura del panel donde se muestran los datos seriales
import threading
from collections import deque

#ser es el objeto serial que dejamos aqui para llamarlo en varias partes del codigo 
ser = None
app_running = True
data_lock = threading.Lock()

wave_running = False
sismo_running = False

x_data = deque(maxlen=500)
y_data = deque(maxlen=500)
expected_wave_data = deque(maxlen=500)
expected_wave_time = deque(maxlen=500)
plot_start_time = 0
max_points = 500

log_recv = deque(maxlen=100)
log_sent = deque(maxlen=100)
log_dirty = False

viewer_seismic_files = {}
viewer_all_traces = []              
viewer_selected_trace_index = None
viewer_data_dirty = threading.Event()