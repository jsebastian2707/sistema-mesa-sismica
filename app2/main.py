from typing import Protocol, Any, cast
import dearpygui.dearpygui as _dpg # type: ignore
import time
from state import state
from logic import (find_serial_ports, SerialManager,processor)
import threading

"""falta definir si el thread de lectura lo dejamos en la clase de la conexion serial, lo arrancamos directamente en el gui
dado que arrancarlo antes que el bucle de dearpygui parece ayudar con los errores de lectuara"""

class DPGProtocol(Protocol):
    # Setup & Viewport
    def create_context(self) -> None: ...
    def destroy_context(self) -> None: ...
    def create_viewport(self, title: str, width: int, height: int, x_pos: int = ..., y_pos: int = ...) -> None: ...
    def setup_dearpygui(self) -> None: ...
    def show_viewport(self) -> None: ...
    def is_dearpygui_running(self) -> bool: ...
    def render_dearpygui_frame(self) -> None: ...
    def set_primary_window(self, tag: str, value: bool) -> None: ...
    def get_item_width(self, tag:str )-> int: ...
    def get_item_height(self, tag:str )-> int: ...
    def window(self, label: str, tag: str | int = ...) -> Any: ...
    def group(self, horizontal: bool = ..., width: int = ..., tag: str | int = ...) -> Any: ...
    def child_window(self, tag: str | int = ..., height: int = ..., width: int = ..., border: bool = ...) -> Any: ...
    

    # Widgets
    def add_button(self,tag:str=...,label: str = ..., width:int=...,show: bool= ..., callback: Any = ... ) -> None: ...
    def add_text(self, label: str = ...,tag:str=...) -> None: ...
    def add_checkbox(self, label: str = ..., tag: str | int = ..., callback: Any = ...) -> None: ...
    def add_separator(self, tag: str | int = ...) -> None: ...
    def add_combo(self, items: list[str] = ..., tag: str | int = ..., width: int = ..., default_value: str = ..., callback: Any = ...) -> None: ...
    def add_input_text(self, tag: str | int = ..., multiline: bool = ..., readonly: bool = ..., width: int = ..., height: int = ..., on_enter: bool = ..., callback: Any = ...) -> None: ...
    def add_slider_int(self, default_value: int, min_value: int,max_value: int, label: str = ..., tag: str | int = ...,width:int = ...) -> None: ...
    def add_slider_float(self,default_value: float, min_value: float, max_value: float, label: str = ..., tag: str | int = ...,format: str = ... , width:int = ...) -> None: ...

    # Item Manipulation
    def configure_item(self, item: str | int, show: bool = ..., items: list[str] = ..., enabled: bool = ... , width: int = ... ,height: int = ...,label:str=...)-> None: ...
    def does_item_exist(self, item: str | int) -> bool: ...
    def enable_item(self, item: str | int) -> None: ...
    def disable_item(self, item: str | int) -> None: ...
    def get_value(self,tag: str|int)-> int | str : ...
    def set_value(self,tag:str, value: str | int | list[list[float]])-> None: ...
    def set_y_scroll(self, tag: str|int, value: float) -> None: ...
    def bind_item_handler_registry(self,item:str,handler:str)-> None:...
    def item_handler_registry(self,tag:str)-> Any:...
    def add_item_resize_handler(self,callback:Any)-> None:...
    def show_item(self,tag:str)->None:...
    def is_item_shown(self, item: int|str)-> bool:...
    def get_item_label(self,tag:str)->str:...

    #plot
    mvXAxis: int
    mvYAxis: int
    def plot(self,label:str = ..., tag:str = ...)-> Any:...
    def add_plot_legend(self)-> None:...
    def add_plot_axis(self,axis:int,label:str,tag:str)-> Any:...
    def plot_axis(self,axis:int,label:str,tag:str)-> Any:...
    def add_line_series(self, x: list[Any], y: list[Any], label: str = ..., tag: str = ...) -> Any: ... 
    def fit_axis_data(self,axis:str)->None:...
    
    #files
    def add_file_dialog(self,show:bool, callback:Any,tag:str=..., cancel_callback:Any = ..., width:int =..., height:int =...)-> Any:...
    def file_dialog(self,show:bool, callback:Any,directory_selector: bool,tag:str=..., cancel_callback:Any = ..., width:int =..., height:int =...)->Any:...
    def add_file_extension(self,extension:str, color: tuple[int,int,int,int]=...,custom_text:str=...)-> None:...


dpg: DPGProtocol = cast(DPGProtocol, _dpg)

available_traces_list: list[str] = [] 

def update_ui_for_connection_state():
    if state.ser_manager:
        dpg.configure_item("connect_button", show=False)
        dpg.configure_item("disconnect_button", show=True)
        if dpg.does_item_exist("start_wave_button"):
            dpg.enable_item("start_wave_button")
        if dpg.does_item_exist("command_input"):
            dpg.enable_item("command_input")
        if dpg.does_item_exist("send_command_button"): 
            dpg.enable_item("send_command_button")
    else:
        dpg.configure_item("connect_button", show=True)
        dpg.configure_item("disconnect_button", show=False)
        if dpg.does_item_exist("start_wave_button"): 
            dpg.disable_item("start_wave_button")
        if dpg.does_item_exist("stop_wave_button"): 
            dpg.disable_item("stop_wave_button")
        if dpg.does_item_exist("command_input"): 
            dpg.disable_item("command_input")
        if dpg.does_item_exist("send_command_button"): 
            dpg.disable_item("send_command_button")
        refresh_ports_callback()
        
        
def connect_callback():
    port: str = str(dpg.get_value("ports_combo"))
    baudrate: int = int(dpg.get_value("baud_rate_combo"))
    if port and baudrate:
        state.ser_manager = SerialManager(port, baudrate)
        update_ui_for_connection_state()
        with state.data_lock:
            state.monitor_x.clear() 
            state.monitor_y.clear()
            state.validation_x.clear()
            state.validation_y.clear()
        state.start_time = time.time()

def disconnect_callback():
    if state.ser_manager and state.ser_manager.serial_port.is_open:
        state.ser_manager.close()
        state.ser_manager= None
    update_ui_for_connection_state()

def refresh_ports_callback():
    if dpg.does_item_exist("ports_combo"):
        dpg.configure_item("ports_combo", items=find_serial_ports())

def send_command_callback():
    cmd = dpg.get_value("command_input")
    if cmd and state.ser_manager is not None:
        state.ser_manager.send(str(cmd))
        if dpg.does_item_exist("command_input"):
            dpg.set_value("command_input", "")

def start_wave_callback():
    print("arranco la wave, o se detuvo dependiendo del estado ")
    if state.ser_manager:
        if not state.wave_running:
            if dpg.does_item_exist("start_wave_button"):
                dpg.configure_item("start_wave_button", label="Stop")
            threading.Thread(target=processor.run_sismo_thread, daemon=True).start()
        else:
            state.wave_running = False
            if dpg.does_item_exist("start_wave_button"): 
                dpg.configure_item("start_wave_button", label="Play")
            print("deberia detenerla")
    else:
        print("no conectado")
    # Lógica para detener
    # with state.data_lock:
    #     state.x_data.clear(); state.y_data.clear(); state.expected_wave_data.clear()
    #     state.plot_start_time = time.time()
    # if dpg.does_item_exist("speed_input"): send_command(f"s{dpg.get_value('speed_input')}")
    # if dpg.does_item_exist("accel_input"): send_command(f"a{dpg.get_value('accel_input')}")

def file_callback(sender:Any, app_data:Any):
    if 'file_path_name' in app_data:
        full_path = app_data['file_path_name']
        state.file_path= full_path
        state.is_file_selected_flag=True
        processor.load_trace()
        dpg.set_value("file_text",app_data['file_name'])
        if len(state.validation_x) > 0 and dpg.does_item_exist("series_expected_comp2"):
            dpg.set_value("series_expected_comp2", [list(state.validation_x), list(state.validation_y)])
            dpg.fit_axis_data("x_axis_comp2")
            dpg.fit_axis_data("y_axis_comp2")

def update_gui_callbacks():
    with state.data_lock:
        if not state.wave_running and dpg.does_item_exist("start_wave_button"):
            if dpg.get_item_label("start_wave_button") == "Stop":
                dpg.configure_item("start_wave_button", label="Play")
        # Actualizar gráfica Monitor (Tiempo Real)
        if len(state.monitor_x) > 0 and dpg.does_item_exist("series_real_comp"):
            dpg.set_value("series_real_comp", [list(state.monitor_x), list(state.monitor_y)])
            dpg.fit_axis_data("x_axis_comp")
            dpg.fit_axis_data("y_axis_comp")

        # Actualizar gráfica Validación (Esperada vs Real)
        # if len(state.validation_x) > 0 and dpg.does_item_exist("series_expected_comp2"):
        #     dpg.set_value("series_expected_comp2", [list(state.validation_x), list(state.validation_y)])
        #     dpg.fit_axis_data("x_axis_comp2")
        #     dpg.fit_axis_data("y_axis_comp2")
        # expected_x, expected_y = zip(*state.expected_wave_data)
        # dpg.set_value("series_expected_comp", [list(expected_x), list(expected_y)])
        # if (state.y_data or state.expected_wave_data) and dpg.does_item_exist("x_axis_comp"):
        #     dpg.fit_axis_data("x_axis_comp")
        #     dpg.fit_axis_data("y_axis_comp")
        
        if state.log_dirty:
            if dpg.does_item_exist("console_recv_output"):
                dpg.set_value("console_recv_output", "\n".join(state.log_read))
            if dpg.does_item_exist("console_send_output"): 
                dpg.set_value("console_send_output", "\n".join(state.log_send))
            if dpg.does_item_exist("console_recv_container"): 
                dpg.set_y_scroll("console_recv_container", -1.0)
            if dpg.does_item_exist("console_send_container"): 
                dpg.set_y_scroll("console_send_container", -1.0)
            state.log_dirty = False
 
def update_plot_sizes():##the function that updates the plot sizes when the window is resized
    if dpg.does_item_exist("main_window"):
        window_width = dpg.get_item_width("main_window")
        window_height = dpg.get_item_height("main_window")
        plot_width = int((window_width - 20) // 2.5)
        plot_width2 = int((window_width - 20) // 1.6666)
        plot_height = window_height - 400
        if dpg.does_item_exist("monitor"):
            dpg.configure_item("monitor", width=plot_width, height=plot_height)
        if dpg.does_item_exist("validation"):
            dpg.configure_item("validation", width=plot_width2, height=plot_height)
            
def create_gui():
    with dpg.window(label="Panel de Control", tag="main_window"):
        with dpg.group(horizontal=True):
            dpg.add_text("Puerto serial")
            dpg.add_combo(items=[], tag="ports_combo", width=150)
            dpg.add_button(label="Refresh", callback=refresh_ports_callback)
            dpg.add_text("Baud Rate")
            dpg.add_combo(["9600", "57600", "115200","230400","250000","921600"], tag="baud_rate_combo", default_value="250000", width=100)
            dpg.add_button(label="Connect", tag="connect_button", callback=connect_callback, width=100)
            dpg.add_button(label="Disconnect", tag="disconnect_button", callback=disconnect_callback, width=100, show=False)
            dpg.add_text("no file selected",tag="file_text")
            dpg.add_button(label="Directory Selector", callback=lambda: dpg.configure_item("file_dialog_id",show=not dpg.is_item_shown("file_dialog_id")))
            with dpg.file_dialog(directory_selector=False, show=False, callback=file_callback, tag="file_dialog_id", width=700 ,height=400):
                dpg.add_file_extension(".miniseed")
                dpg.add_file_extension("", color=(150, 255, 150, 255))
        with dpg.group(horizontal=True):
            dpg.add_button(label="play", tag="start_wave_button", callback=start_wave_callback, width=100)
            dpg.add_slider_int(label="Amplitude", tag="amplitude_slider", default_value=1600, min_value=100, max_value=10000,width=200)
            dpg.add_slider_float(label="Frequency", tag="frequency_slider", default_value=0.5, min_value=0.1, max_value=5.0, format="%.2f Hz", width=200) 
        # with dpg.group(horizontal=True):
        #     dpg.add_input_int(label="Speed (s)", tag="speed_input", default_value=50000)
        #     dpg.add_input_int(label="Acceleration (a)", tag="accel_input", default_value=20000)
        #     dpg.add_input_int(label="Commads per second", tag="commandsPerSecond_input", default_value=20000)
        #     dpg.add_separator()
        with dpg.group(horizontal=True):
            with dpg.plot(label="monitor", tag="monitor"):
                dpg.add_plot_legend()
                dpg.add_plot_axis(dpg.mvXAxis, label="Time (s)", tag="x_axis_comp")
                with dpg.plot_axis(dpg.mvYAxis, label="Position (steps)", tag="y_axis_comp"):
                    dpg.add_line_series([], [], label="Real", tag="series_real_comp")
            with dpg.plot(label="validation" , tag="validation"):
                dpg.add_plot_legend()
                dpg.add_plot_axis(dpg.mvXAxis, label="Time (s)", tag="x_axis_comp2")
                with dpg.plot_axis(dpg.mvYAxis, label="Position (steps)", tag="y_axis_comp2"):
                    dpg.add_line_series([], [], label="Expected", tag="series_expected_comp2")
                    dpg.add_line_series([], [], label="Real", tag="series_real_comp2")
        dpg.add_text("Manual Control & Send Log")
        with dpg.group(horizontal=True):
            with dpg.group(width=400):
                dpg.add_input_text(tag="command_input", on_enter=True, callback=send_command_callback)
                dpg.add_button(label="Send Command", tag="send_command_button", callback=send_command_callback)
                with dpg.child_window(tag="console_send_container", height=-1, border=True):
                    dpg.add_input_text(tag="console_send_output", multiline=True, readonly=True, width=-1, height=-1)
            with dpg.child_window(tag="console_recv_container", height=-1,width=-1, border=True):
                dpg.add_input_text(tag="console_recv_output", multiline=True, readonly=True, height=-1)
    with dpg.item_handler_registry(tag="window_resize_handler"):
        dpg.add_item_resize_handler(callback=update_plot_sizes)
    dpg.bind_item_handler_registry("main_window", "window_resize_handler")
    dpg.set_primary_window("main_window", True)
    if len(state.validation_x) > 0 and dpg.does_item_exist("series_expected_comp2"):
        dpg.set_value("series_expected_comp2", [list(state.validation_x), list(state.validation_y)])
        dpg.fit_axis_data("x_axis_comp2")
        dpg.fit_axis_data("y_axis_comp2")

def main():
    #threading.Thread(target=serial_controller_thread, daemon=True).start()
    dpg.create_context()
    processor.load_trace()
    create_gui()
    refresh_ports_callback()
    dpg.create_viewport(title='control mesa sismica', width=1200, height=700, x_pos=0, y_pos=0)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    while dpg.is_dearpygui_running():
        update_gui_callbacks()
        dpg.render_dearpygui_frame()
    if state.ser_manager and state.ser_manager.serial_port.is_open:
        state.ser_manager.close()
    state.running = False
    dpg.destroy_context()

if __name__ == "__main__":
    main()      