import dearpygui.dearpygui as dpg
import random
import time
import numpy as np

dpg.create_context()

# --- Tus variables globales se mantienen igual ---
real_data_x = []
real_data_y = []
scrolling_x = []
scrolling_y = []
time_counter = 0
WINDOW_SIZE = 200
filling_x = []
filling_y = []
filling_counter = 0
MAX_POINTS = 200
sin_y = []
mixed_y = []

def update_scrolling_graph():
    global time_counter, scrolling_x, scrolling_y, sin_y, mixed_y
    
    time_counter += 1
    scrolling_x.append(time_counter)
    scrolling_y.append(random.uniform(0, 100))
    sin_y.append(np.sin(time_counter * 0.2) * 50 + 50)
    mixed_y.append(((sin_y[-1]*0.8+10)+ (scrolling_y[-1]-50)*0.15))
    
    if len(scrolling_x) > WINDOW_SIZE:
        scrolling_x = scrolling_x[-WINDOW_SIZE:]
        scrolling_y = scrolling_y[-WINDOW_SIZE:]
        sin_y = sin_y[-WINDOW_SIZE:]
        mixed_y = mixed_y[-WINDOW_SIZE:]
    
    dpg.configure_item('scrolling_line', x=scrolling_x, y=scrolling_y)
    dpg.configure_item('scrolling_line2', x=scrolling_x, y=sin_y)
    dpg.configure_item('scrolling_line3', x=scrolling_x, y=mixed_y) 
    
    # MODIFICACIÓN 2: Usar el valor del checkbox para decidir si se ajustan los ejes
    if dpg.get_value("auto_scroll_checkbox"):
        if len(scrolling_x) >= WINDOW_SIZE:
            dpg.set_axis_limits("scroll_xaxis", scrolling_x[0], scrolling_x[-1])
        # También fijamos el eje Y para que no salte
        dpg.set_axis_limits("scroll_yaxis", 0, 100)

def update_filling_graph():
    global filling_counter, filling_x, filling_y
    
    if filling_counter >= MAX_POINTS:
        filling_counter = 0
        filling_x = []
        filling_y = []
        # Al reiniciar, también actualizamos el límite del eje X
        if scrolling_x:
            dpg.set_axis_limits("fill_xaxis", scrolling_x[-1], scrolling_x[-1] + MAX_POINTS)

    if scrolling_x: # Asegurarse de que hay datos para añadir
        filling_x.append(scrolling_x[-1]) 
        filling_y.append(scrolling_y[-1])
        filling_counter += 1
    
    dpg.configure_item('filling_line', x=filling_x, y=filling_y)
    
    # El eje de llenado no necesita auto-scroll, ya que se llena y reinicia.
    # El usuario puede explorarlo libremente. El reinicio de datos ya ajusta el eje X.

# MODIFICACIÓN 3: Botón para ajustar los datos manualmente
def fit_plot_data():
    dpg.set_axis_limits_auto("scroll_xaxis")
    dpg.set_axis_limits_auto("scroll_yaxis")
    dpg.set_axis_limits_auto("fill_xaxis")
    dpg.set_axis_limits_auto("fill_yaxis")

def update_both_graphs():
    if dpg.get_value("enable_updates"):
        update_scrolling_graph()
        update_filling_graph()

with dpg.window(label="Real-time Graphs", tag="primary_window", pos=(10, 10), width=800, height=700):
    
    dpg.add_text("Real-time Graph Examples", color=(100, 200, 255))
    dpg.add_separator()
    
    with dpg.group(horizontal=True):
        dpg.add_checkbox(label="Enable Real-time Updates", tag="enable_updates", default_value=True)
        # MODIFICACIÓN 4: Checkbox para controlar el auto-scroll
        dpg.add_checkbox(label="Auto-Scroll", tag="auto_scroll_checkbox", default_value=True)

    dpg.add_slider_int(label="Update Speed (ms)", tag="update_speed", default_value=20, min_value=10, max_value=1000, width=200)
    
    # MODIFICACIÓN 5: Botón que llama a la nueva función de ajuste
    dpg.add_button(label="Fit Data to View", callback=fit_plot_data)
    
    dpg.add_separator()
    
    # --- Scrolling Graph ---
    dpg.add_text("1. Scrolling Graph (adds data on right, moving window)", color=(255, 200, 100))
    with dpg.plot(label="Scrolling Graph", height=250, width=750):
        # MODIFICACIÓN 1: Añadir 'no_autofit=True' para tomar control total
        dpg.add_plot_axis(dpg.mvXAxis, label="Time", tag="scroll_xaxis", auto_fit =False)
        dpg.add_plot_axis(dpg.mvYAxis, label="Value", tag="scroll_yaxis", auto_fit =False)
        
        dpg.add_line_series([], [], tag='scrolling_line2', parent="scroll_yaxis")
        dpg.add_line_series([], [], tag='scrolling_line', parent="scroll_yaxis", show=False)
        dpg.add_line_series([], [], tag='scrolling_line3', parent="scroll_yaxis")

        # Establecer los límites iniciales
        dpg.set_axis_limits("scroll_xaxis", 0, WINDOW_SIZE)
        dpg.set_axis_limits("scroll_yaxis", 0, 100)
    
    dpg.add_separator()
    
    # --- Filling Graph ---
    dpg.add_text("2. Filling Graph (fills left to right, then resets)", color=(100, 255, 150))
    with dpg.plot(label="Filling Graph", height=250, width=750):
        # MODIFICACIÓN 1: Añadir 'no_autofit=True' también aquí
        dpg.add_plot_axis(dpg.mvXAxis, label="Index", tag="fill_xaxis", auto_fit=False)
        dpg.add_plot_axis(dpg.mvYAxis, label="Value", tag="fill_yaxis", auto_fit =False)
        dpg.add_line_series([], [], tag='filling_line', parent="fill_yaxis")
        
        # Establecer los límites iniciales
        dpg.set_axis_limits("fill_xaxis", 0, MAX_POINTS)
        dpg.set_axis_limits("fill_yaxis", 0, 100)

dpg.create_viewport(x_pos=0, y_pos=0, height=750, title='Real-time Graph Examples')
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.set_primary_window("primary_window", True)

last_update = time.time()
while dpg.is_dearpygui_running():
    current_time = time.time()
    update_interval = dpg.get_value("update_speed") / 1000.0
    if current_time - last_update >= update_interval:
        update_both_graphs()
        last_update = current_time
    dpg.render_dearpygui_frame()
dpg.destroy_context()