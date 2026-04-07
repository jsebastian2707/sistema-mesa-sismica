#types
from typing import TypedDict,NotRequired,Any
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
                                    state.monitor_x.append(time.time() - 10)##current time
                                    state.monitor_y.append(angle)
                                if(state.wave_running):
                                    state.validation_x2.append(time.time() - state.start_time)##current time
                                    state.validation_y2.append(angle*8)
                            except ValueError:
                                print(ValueError)
                    except (serial.SerialException, UnicodeDecodeError,):
                        time.sleep(0.5)
            else:
                time.sleep(0.5)

    def send(self,command:str):
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.write((command+"\n").encode("utf-8"))
                #self.serial_port.flush()
                print(self.serial_port.out_waiting)
                """bloqueante hasta que el buffer de salida se desocupe, cuando la velocidad 
                de trasmision es suficiente no representa ningun cambio """
                with state.data_lock:
                    state.log_send.append(f"[{time.strftime('%H:%M:%S')}] >> {command}")
                    state.log_dirty = True
            except serial.SerialException as e:
                print(f"error:{e}")
        else:   
            print("error ser is close")

    def close(self):
        if self.serial_port and self.serial_port.is_open:
            self.stop_event.set()
            self.reader_thread.join()
            self.serial_port.close()
            state.ser_manager = None

METER_X_REV = 0.008 #segun varilla roscada que usemos
STEPS_X_REV = 3200 #segun el ajuste del controlador del motor 
STEPS_PER_METER = STEPS_X_REV/METER_X_REV 

class StatsType(TypedDict):
    network: NotRequired[str]
    station: NotRequired[str]
    location: str
    channel: str
    npts: int
    sampling_rate: float
    starttime: UTCDateTime

class SeismicProcessor:

    ##tienen que generarse la lista de pasos con velocidades y tiempo, y ya despues de eso si se puede ejecutar el sismo

    def go_home_thread(self):
        if not state.ser_manager:
            print("Serial no conectado")
            return
        
        precision_threshold = 5 
        pos= 0
        while state.running:
            with state.data_lock:
                # Obtenemos la última posición conocida del encoder
                if not state.monitor_y:
                    current_pos = 0
                else:
                    current_pos = state.monitor_y[-1] # Último valor del deque
            
            # Calculamos el error (cuánto nos falta para llegar a 0)
            error = 0 - current_pos
            if abs(error) <= precision_threshold:
                break
            correction = int(error *8* 0.8) # Ganancia de 0.8 para no pasarse (overshoot)
            if abs(correction) > 10000:
                correction = 10000 if correction > 0 else -10000
            pos += correction
            state.ser_manager.send(f"m{pos}")
            time.sleep(0.5)

        # Al finalizar el bucle (llegamos al centro), mandamos el comando 'z'
        state.ser_manager.send("z")
    
    def load_trace(self):
        if not state.is_file_selected_flag:
            duration = 5.0              # Seconds
            frequency = 1.0             # Hz
            amplitude = 1600           # steps
            
            t = np.linspace(0, duration, int(state.sampling_rate * duration), endpoint=False)
            synthetic_data : NDArray[np.float64]  = amplitude * np.sin(2 * np.pi * frequency * t)

            stats: StatsType = {
                'location': '00',
                'channel': 'HXZ',
                'npts': len(synthetic_data),
                'sampling_rate': state.sampling_rate,
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
        tr.resample(state.sampling_rate)
        #tr.plot() ##solo para pruebas, tiene conflictos con dpg 
        steps_array = (tr.data).astype(int)
        #steps_array_relative = np.diff(steps_array, prepend=0)
        with state.data_lock:
            state.seismic_trace = tuple(steps_array.tolist())
            state.validation_x.clear()
            state.validation_y.clear()
            t = np.linspace(0, float(tr.stats.npts / tr.stats.sampling_rate), tr.stats.npts)
            for i, step in enumerate(steps_array):
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
        state.start_time = time.time()
        state.wave_running = True
        period=1.0 / state.sampling_rate
        for i, target_step in enumerate(state.seismic_trace):
            if not state.wave_running:
                break
            # Send command (assuming 'm' is absolute move) si el movimiento es relativo usar diff  
            state.ser_manager.send(f"m{target_step}" )
            #state.playback_index = i #si se desea pausar y despuasar la reproduccion del sismo, se debe guardar este index
            sleep_time =  ((i + 1) * period )- (time.time() - state.start_time) ##expected nextime * elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        state.wave_running = False
        with state.data_lock:
            state.log_send.append("Playback Finished.")
            state.log_dirty = True

processor = SeismicProcessor()