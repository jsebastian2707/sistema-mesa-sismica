import dearpygui.dearpygui as dpg
import threading
import time

# Import the shared state
import app_state
from serial_handler import (find_serial_ports, connect_serial, disconnect_serial, 
                            send_command, wave_generator_thread, read_serial_thread)
import seismic_handler as sh

prefab = True

def update_ui_for_connection_state(connected: bool):
    """Enables or disables UI elements based on the connection state."""
    if connected:
        dpg.configure_item("connect_button", show=False)
        dpg.configure_item("disconnect_button", show=True)
        if dpg.does_item_exist("start_wave_button"): dpg.enable_item("start_wave_button")
        if dpg.does_item_exist("command_input"): dpg.enable_item("command_input")
        if dpg.does_item_exist("send_command_button"): dpg.enable_item("send_command_button")
    else:
        dpg.configure_item("connect_button", show=True)
        dpg.configure_item("disconnect_button", show=False)
        if dpg.does_item_exist("start_wave_button"): dpg.disable_item("start_wave_button")
        if dpg.does_item_exist("stop_wave_button"): dpg.disable_item("stop_wave_button")
        if dpg.does_item_exist("command_input"): dpg.disable_item("command_input")
        if dpg.does_item_exist("send_command_button"): dpg.disable_item("send_command_button")
        refresh_ports_callback()
        
def checkbox_callback(sender, app_data, user_data):
    if app_data:
        dpg.configure_item("t2", show=True)
        dpg.configure_item("t1", show=False)
    else:
        dpg.configure_item("t2", show=False)
        dpg.configure_item("t1", show=True)
        
def connect_callback():
    port = dpg.get_value("ports_combo")
    baud = dpg.get_value("baud_rate_combo")
    if port and baud:
        success, message = connect_serial(port, baud)
        if success:
            update_ui_for_connection_state(True)
            with app_state.data_lock:
                app_state.x_data.clear(); app_state.y_data.clear(); app_state.expected_wave_data.clear()
            app_state.plot_start_time = time.time()
        else:
            dpg.set_value("connection_status", f"Error: {message}")

def disconnect_callback():
    disconnect_serial()
    update_ui_for_connection_state(False)

def refresh_ports_callback():
    if dpg.does_item_exist("ports_combo"):
        dpg.configure_item("ports_combo", items=find_serial_ports())

def send_manual_command_callback():
    command = dpg.get_value("command_input")
    if command:
        send_command(command)
        if dpg.does_item_exist("command_input"):
            dpg.set_value("command_input", "")

def start_wave_callback():
    if not app_state.wave_running:
        app_state.wave_running = True
        with app_state.data_lock:
            app_state.x_data.clear(); app_state.y_data.clear(); app_state.expected_wave_data.clear()
        app_state.plot_start_time = time.time()
        if dpg.does_item_exist("speed_input"): send_command(f"s{dpg.get_value('speed_input')}")
        if dpg.does_item_exist("accel_input"): send_command(f"a{dpg.get_value('accel_input')}")
        threading.Thread(target=wave_generator_thread, daemon=True).start()
        if dpg.does_item_exist("start_wave_button"): dpg.disable_item("start_wave_button")
        if dpg.does_item_exist("stop_wave_button"): dpg.enable_item("stop_wave_button")

def stop_wave_callback():
    app_state.wave_running = False
    if dpg.does_item_exist("start_wave_button"): dpg.enable_item("start_wave_button")
    if dpg.does_item_exist("stop_wave_button"): dpg.disable_item("stop_wave_button")

def _viewer_on_trace_select(sender, app_data, user_data):
    app_state.viewer_selected_trace_index = user_data
    _update_viewer_file_tree()
    _update_viewer_detailed_plot()

def _update_viewer_file_tree():
    if not dpg.does_item_exist("viewer_file_tree"): return
    dpg.delete_item("viewer_file_tree", children_only=True)
    if not app_state.viewer_seismic_files:
        dpg.add_text("No data loaded. Click 'Load Data'.", parent="viewer_file_tree")
        return
    for file_name, traces in app_state.viewer_seismic_files.items():
        with dpg.tree_node(label=f"{file_name} ({len(traces)} traces)", parent="viewer_file_tree", default_open=True):
            for trace in traces:
                is_selected = (app_state.viewer_selected_trace_index == trace['global_index'])
                indicator = "▶" if is_selected else " "
                label = f"{indicator} {trace['id']} | SR: {trace['sampling_rate']}Hz"
                dpg.add_button(label=label, width=-1, callback=_viewer_on_trace_select, user_data=trace['global_index'])

def _update_viewer_detailed_plot():
    parent_container = "viewer_detailed_plot_container"
    if not dpg.does_item_exist(parent_container): return
    dpg.delete_item(parent_container, children_only=True)
    if app_state.viewer_selected_trace_index is None:
        dpg.add_text("Select a trace from the list to see details.", parent=parent_container)
        return
    try:
        trace_data = app_state.viewer_all_traces[app_state.viewer_selected_trace_index]
    except IndexError:
        app_state.viewer_selected_trace_index = None
        dpg.add_text("Error: Invalid trace index. Selection reset.", parent=parent_container)
        return
    info = (f"ID: {trace_data['id']}\nFile: {trace_data['file_name']}\n"
            f"Frequency: {trace_data['sampling_rate']} Hz\nSamples: {len(trace_data['data'])}\n"
            f"Max Amplitude: {trace_data['max_amp']:.3e}")
    dpg.add_text(info, parent=parent_container)
    dpg.add_separator(parent=parent_container)
    with dpg.plot(label="Detailed View", height=-50, width=-1, parent=parent_container):
        x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="Time (s)")
        with dpg.plot_axis(dpg.mvYAxis, label="Amplitude") as y_axis:
            dpg.add_line_series(trace_data['times'].tolist(), trace_data['data'].tolist(), label=trace_data['id'])
        dpg.fit_axis_data(x_axis)
        dpg.fit_axis_data(y_axis)
    with dpg.group(horizontal=True, parent=parent_container):
        dpg.add_button(label="Process for Shaking Table", callback=sh.process_selected_trace, width=-1, height=30)
        dpg.add_button(label="▶ Play on Table", callback=lambda: sh.start_seismic_playback(amplitude=1600), width=-1, height=30)
        dpg.add_button(label="⏹ Stop Playback", callback=sh.stop_seismic_playback, width=-1, height=30)

def update_gui_callbacks():
    if app_state.viewer_data_dirty.is_set():
        _update_viewer_file_tree()
        _update_viewer_detailed_plot()
        app_state.viewer_data_dirty.clear()
    
    with app_state.data_lock:
        if app_state.x_data and app_state.y_data and dpg.does_item_exist("series_real_comp"):
            dpg.set_value("series_real_comp", [list(app_state.x_data), list(app_state.y_data)])
        if app_state.expected_wave_data and dpg.does_item_exist("series_expected_comp"):
            expected_x, expected_y = zip(*app_state.expected_wave_data)
            dpg.set_value("series_expected_comp", [list(expected_x), list(expected_y)])
        
        if (app_state.y_data or app_state.expected_wave_data) and dpg.does_item_exist("x_axis_comp"):
            dpg.fit_axis_data("x_axis_comp")
            dpg.fit_axis_data("y_axis_comp")
        
        if app_state.log_dirty:
            if dpg.does_item_exist("console_recv_output"): dpg.set_value("console_recv_output", "\n".join(app_state.log_recv))
            if dpg.does_item_exist("console_send_output"): dpg.set_value("console_send_output", "\n".join(app_state.log_sent))
            if dpg.does_item_exist("console_recv_container"): dpg.set_y_scroll("console_recv_container", -1.0)
            if dpg.does_item_exist("console_send_container"): dpg.set_y_scroll("console_send_container", -1.0)
            app_state.log_dirty = False

def update_plot_sizes():##the function that updates the plot sizes when the window is resized
    if dpg.does_item_exist("main_window"):
        window_width = dpg.get_item_width("main_window")
        window_height = dpg.get_item_height("main_window")
        plot_width = (window_width - 20) // 2.5
        plot_width2 = (window_width - 20) // 1.6666
        plot_height = window_height - 400
        if dpg.does_item_exist("monitor"):
            dpg.configure_item("monitor", width=plot_width, height=plot_height)
        if dpg.does_item_exist("validation"):
            dpg.configure_item("validation", width=plot_width2, height=plot_height)
            
def create_gui():
    dpg.create_context()
    with dpg.window(label="Panel de Control", tag="main_window"):
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
        with dpg.group(horizontal=True):
            dpg.add_text("Serial Port")
            dpg.add_combo(items=[], tag="ports_combo", width=150)
            dpg.add_button(label="Refresh", callback=refresh_ports_callback)
            dpg.add_text("Baud Rate")
            dpg.add_combo(["9600", "57600", "115200", "921600"], tag="baud_rate_combo", default_value="115200", width=100)
            dpg.add_button(label="Connect", tag="connect_button", callback=connect_callback, width=100)
            dpg.add_button(label="Disconnect", tag="disconnect_button", callback=disconnect_callback, width=100, show=False)
            dpg.add_checkbox(label="ondas basicas", tag="checkbox_onda", callback=checkbox_callback)
        with dpg.tab_bar():
            with dpg.tab(label="Seismic Trace Viewer"):
                with dpg.group(tag="t1", show=True):
                    with dpg.group(horizontal=True):
                        with dpg.group(width=500):
                            dpg.add_text("Seismic Trace Selector")
                            dpg.add_button(label="Load Data from 'sismic_records'", 
                                callback=lambda: threading.Thread(target=sh.load_traces_from_folder_thread, daemon=True).start(), 
                                width=-1, height=40)
                            dpg.add_separator()
                            with dpg.child_window(tag="viewer_file_tree", border=True):
                                dpg.add_text("Click 'Load Data' to begin.")
                        with dpg.group(width=-1):
                            dpg.add_text("Detailed Trace View")
                            dpg.add_separator()
                            with dpg.child_window(tag="viewer_detailed_plot_container"):
                                dpg.add_text("Select a trace from the list to see details.")
                with dpg.group(tag="t2", show=False):
                    with dpg.group(horizontal=True):
                        with dpg.group(width=300):
                            dpg.add_text("Sine Wave Generator")
                            dpg.add_slider_int(label="Amplitude", tag="amplitude_slider", default_value=1600, min_value=100, max_value=10000)
                            dpg.add_slider_float(label="Frequency", tag="frequency_slider", default_value=0.5, min_value=0.1, max_value=5.0, format="%.2f Hz")
                            dpg.add_separator()
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="Start Wave", tag="start_wave_button", callback=start_wave_callback, width=-1)
                                dpg.add_button(label="Stop Wave", tag="stop_wave_button", callback=stop_wave_callback, width=-1)
                            dpg.add_separator()
                            dpg.add_text("Manual Control & Send Log")
            with dpg.tab(label="manual"):
                with dpg.group(horizontal=True):
                    with dpg.group(width=400):
                        dpg.add_input_text(tag="command_input", hint="Command (e.g., m0)", on_enter=True, callback=send_manual_command_callback)
                        dpg.add_button(label="Send Command", tag="send_command_button", callback=send_manual_command_callback)
                        with dpg.child_window(tag="console_send_container", height=-1, border=True):
                            dpg.add_input_text(tag="console_send_output", multiline=True, readonly=True, width=-1, height=-1)
                    with dpg.child_window(tag="console_recv_container", height=-1,width=-1, border=True):
                        dpg.add_input_text(tag="console_recv_output", multiline=True, readonly=True, height=-1)
            with dpg.tab(label="opciones"):
                dpg.add_input_int(label="Speed (s)", tag="speed_input", default_value=50000)
                dpg.add_input_int(label="Acceleration (a)", tag="accel_input", default_value=20000)
                dpg.add_input_int(label="Commads per second", tag="commandsPerSecond_input", default_value=20000)

    with dpg.item_handler_registry(tag="window_resize_handler"):
        dpg.add_item_resize_handler(callback=update_plot_sizes)
    dpg.bind_item_handler_registry("main_window", "window_resize_handler")
    dpg.create_viewport(title='Modular Seismic Table Controller', width=1200, height=700,x_pos=0, y_pos=0)
    dpg.set_primary_window("main_window", True)
    dpg.setup_dearpygui()
    update_ui_for_connection_state(False)

def cleanup():
    disconnect_serial()
    app_state.app_running = False

def main():
    create_gui()
    threading.Thread(target=read_serial_thread, daemon=True).start()
    dpg.show_viewport()

    while dpg.is_dearpygui_running():
        update_gui_callbacks()
        dpg.render_dearpygui_frame()

    cleanup()

if __name__ == "__main__":
    main()