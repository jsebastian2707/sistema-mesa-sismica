#types
from typing import TypedDict
from typing import Any
from numpy.typing import NDArray
import serial
import serial.tools.list_ports
from state import state
import time
#import math
import queue
import threading

##for seismic procesor 
from obspy import read, UTCDateTime # type: ignore
from obspy.core import Trace  # type: ignore 
import numpy as np

def find_serial_ports():
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports] if ports else ["No Ports Found"]

class SerialManager: 
    """read and send estan dobles """
    def __init__(self, port:str, baudrate: int):
        try:
            self.serial_port = serial.Serial(port, baudrate, timeout=1)
            self.read_queue: queue.Queue[str]  = queue.Queue()
            self.stop_event = threading.Event()
            with state.data_lock:
                state.log_send.append(f"Conectado a {port} a {baudrate} baud.")
                state.log_dirty = True
        except serial.SerialException as e:
            print(f"error: {e}")
            state.ser_manager = None
        
        # Iniciar el hilo de lectura
        self.reader_thread = threading.Thread(target=self.read_thread, daemon=True)
        self.reader_thread.start()

    def read_thread(self):
        """ lee la informacion del serial y la añade tanto a los logs 
        como a la data de los plots"""
        while state.running and not self.stop_event.is_set():
            if self.serial_port and self.serial_port.is_open:
                if self.serial_port.in_waiting > 0:
                    try:
                        line = self.serial_port.readline().decode("utf-8", errors='replace').strip()
                        if line:
                            with state.data_lock: ##aqui va el formato de los logs 
                                state.log_read.append(f"[{time.strftime('%H:%M:%S')}] << {line}")
                                state.log_dirty = True
                            try:
                                angle = float(line)
                                with state.data_lock:
                                    current_time = time.time() - state.start_time
                                    state.monitor_x.append(current_time)
                                    state.monitor_y.append(angle)
                            except ValueError:
                                print(ValueError)
                    except (serial.SerialException, UnicodeDecodeError,):
                        time.sleep(0.5)
            else:
                time.sleep(0.5)

    def send(self,command:str):
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.write(command.encode("utf-8"))
                #self.serial_port.flush()
                with state.data_lock:
                    state.log_send.append(f"[{time.strftime('%H:%M:%S')}] >> {command}")
                    state.log_dirty = True
            except serial.SerialException as e:
                print(f"error:{e}")
        else:   
            print("error ser is close")

    def close(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.stop_event.set()
            self.reader_thread.join()
            state.ser_manager = None

METER_X_REV = 0.008 #segun varilla roscada que usemos
STEPS_X_REV = 3200 #segun el ajuste del controlador del motor 
#import numpy as np  
STEPS_PER_METER = STEPS_X_REV/METER_X_REV 

sampling_rate = 20.0 

class StatsType(TypedDict):
    network: str
    station: str
    location: str
    channel: str
    npts: int
    sampling_rate: float
    starttime: UTCDateTime

class SeismicProcessor:

    ##tienen que generarse la lista de pasos con velocidades y tiempo, y ya despues de eso si se puede ejecutar el sismo

    def goHome(self):
        ##centrar la mesa hasta que la señal del enconder quede lo mas cerca cero
        print("xd")


    # def wave_generator_thread(self):
    #     """Background thread to generate a sine wave and send motor commands."""
    #     start_time = time.time()
    #     while state.running:
    #         elapsed_time = time.time() - start_time
    #         target_pos = state.amplitude * math.sin(2 * math.pi * state.frequency * elapsed_time)
    #         if state.ser_manager is not None:
    #             state.ser_manager.send(f"m{int(target_pos)}")
    #         time.sleep(0.02)
    
    # def generate_synthetic_trace(self):
    #     duration = 5.0              # Seconds
    #     frequency = 1.0             # Hz
    #     amplitude = 0.005           # Meters (Reduced from 0.05 for safety on table testing, adjust as needed)
        
    #     # 2. Generate Synthetic Data (NumPy)
    #     t = np.linspace(0, duration, int(sampling_rate * duration), endpoint=False)
    #     synthetic_data : NDArray[np.float64]  = amplitude * np.sin(2 * np.pi * frequency * t)

    #     stats: StatsType = {
    #         'network': 'TEST',
    #         'station': 'SYNTH', 
    #         'location': '00',
    #         'channel': 'HXZ',
    #         'npts': len(synthetic_data),
    #         'sampling_rate': sampling_rate,
    #         'starttime': UTCDateTime() 
    #     }
    #     synth_trace: Any = Trace(data=synthetic_data, header=stats)
    #     steps_array: NDArray[np.int_] = (cast(NDArray[np.float64], synth_trace.data) * STEPS_PER_METER).astype(int)
        
    #     # 5. Store in State for UI and Playback
    #     with state.data_lock:
    #         state.seismic_trace = tuple(steps_array.tolist())
    #         #state.playback_index = 0
            
    #         # Update Validation Plot (Expected Data)
    #         state.validation_x.clear()
    #         state.validation_y.clear()
    #         for i, step in enumerate(steps_array):
    #             state.validation_x.append(t[i])
    #             state.validation_y.append(step)
                
    #         state.log_send.append(f"Trace Generated: {len(steps_array)} points, Max Amp: {max(steps_array)} steps")
    #         state.log_dirty = True

    #     print("Trace ready in state.")
    
    def load_trace(self):
        """
        Called when the user selects an item in the Combo Box.
        Decides whether to generate math or load a file.
        """
        if not state.is_file_selected_flag:
            #self.generate_synthetic_trace()
            duration = 5.0              # Seconds
            frequency = 1.0             # Hz
            amplitude = 0.005           # Meters (Reduced from 0.05 for safety on table testing, adjust as needed)
            
            # 2. Generate Synthetic Data (NumPy)
            t = np.linspace(0, duration, int(sampling_rate * duration), endpoint=False)
            synthetic_data : NDArray[np.float64]  = amplitude * np.sin(2 * np.pi * frequency * t)

            stats: StatsType = {
                'network': 'TEST',
                'station': 'SYNTH', 
                'location': '00',
                'channel': 'HXZ',
                'npts': len(synthetic_data),
                'sampling_rate': sampling_rate,
                'starttime': UTCDateTime() 
            }
            tr: Any = Trace(data=synthetic_data, header=stats)
        else:
            try:
                st = read(state.file_path)
                tr = st[0]
            except Exception as e:
                print(f"Error loading file: {e}")
                return
        tr.resample(sampling_rate)
        steps_array = (tr.data * STEPS_PER_METER).astype(int)
        #steps_array_relative = np.diff(steps_array, prepend=0)
        # 4. Save to State
        with state.data_lock:
            state.seismic_trace = tuple(steps_array.tolist())
            state.validation_x.clear()
            state.validation_y.clear()
            # Generate a simple time axis for the plot
            t = np.linspace(0, float(tr.stats.npts / tr.stats.sampling_rate), tr.stats.npts)
            for i, step in enumerate(steps_array):
                if i < state.max_points:
                    state.validation_x.append(t[i])
                    state.validation_y.append(step)

    def run_sismo_thread(self):
        """
        Sends the generated steps to the serial port at the correct sampling rate.
        """
        if not state.ser_manager:
            print("Serial not connected")
            return
            
        if not state.seismic_trace:
            print("No trace loaded")
            return

        state.wave_running = True
        period=1.0 / sampling_rate
        start_time = time.time()
        
        # Go through the tuple of steps
        for i, target_step in enumerate(state.seismic_trace):
            if not state.wave_running:
                break
            
            # Send command (assuming 'm' is absolute move)
            cmd = f"m{target_step}" 
            state.ser_manager.send(cmd)
            #state.playback_index = i
            
            # Precise timing
            elapsed = time.time() - start_time
            expected_next_time = (i + 1) * period
            sleep_time = expected_next_time - elapsed
            
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        state.wave_running = False
        print("Seismic Playback Finished.")
        with state.data_lock:
            state.log_send.append("Playback Finished.")
            state.log_dirty = True

processor = SeismicProcessor()