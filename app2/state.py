from collections import deque
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logic import SerialManager 



class StateClass:
    def __init__(self):
        # Serial
        self.ser_manager : SerialManager | None = None

        ##flags  
        self.running: bool = True ##son dos running por que puedes estar pausada la wave pero moviendose para el centro 
        self.wave_running: bool= False

        ##trace
        self.is_file_selected_flag: bool =False
        self.file_path:str= ""
        self.seismic_trace: tuple[int, ...] = 0,  # The processed steps
        #  self.playback_index: int = 0        # Where we are (0 to len-1)
        
        # Plots (Stateful data)
        self.data_lock = threading.Lock()
        self.max_points = 500
        self.monitor_x: deque[float] = deque(maxlen=self.max_points)
        self.monitor_y: deque[float] = deque(maxlen=self.max_points)
        self.validation_x: deque[float] = deque(maxlen=self.max_points)
        self.validation_y: deque[float] = deque(maxlen=self.max_points)
        self.start_time: float = 0

        # Logs
        self.log_dirty:bool = False
        self.log_read: deque[str]  = deque(maxlen=100)
        self.log_send: deque[str]  = deque(maxlen=100)

        # Custom Wave
        self.amplitude = 0
        self.frequency = 0

    def reset_plots(self):
        with self.data_lock:
            self.monitor_x.clear()
            self.monitor_y.clear()
            self.start_time: float = 0

state = StateClass()