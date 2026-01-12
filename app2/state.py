from collections import deque
import threading
import queue

##serial
ser = None
running: bool = True
viewer_all_traces: list = []
cmd_queue = queue.Queue()

##plots
data_lock = threading.Lock()
max_points = 500
monitor_x = deque(maxlen=500)
monitor_y = deque(maxlen=500)
validation_x = deque(maxlen=500)
validation_y = deque(maxlen=500)
start_time: float = 0    

##logs
log_dirty = False
log_read = deque(maxlen=100)
log_send = deque(maxlen=100)

##custom wave 
amplitude: int = 0
frecuency: int = 0  