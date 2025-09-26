# main.py
import dearpygui.dearpygui as dpg
import threading

import app_state
from gui import create_gui, update_gui_callbacks
from serial_handler import read_serial_thread, disconnect_serial

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