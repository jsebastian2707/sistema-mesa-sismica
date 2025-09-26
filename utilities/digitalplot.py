import dearpygui.dearpygui as dpg

dpg.create_context()

paused = False
time_markers_x = [] # Almacenará las coordenadas X de las líneas verticales
t_plot = 0
last_marker_time = -1 # Para rastrear el último segundo en el que se añadió un marcador

def pause_plot():
    global paused
    paused = not paused
    # Opcional: cambiar el texto del botón
    dpg.set_item_label("pause_button", "Resume" if paused else "Pause")

with dpg.window(label="Time Marker Plot"):
    with dpg.group(horizontal=True):
        dpg.add_button(label="Pause", callback=pause_plot, tag="pause_button")

    # Un botón para limpiar los datos si se desea
    # dpg.add_button(label="Clear Plot", callback=lambda: dpg.set_value("time_markers", []))

    with dpg.plot(tag="_time_plot", width=500, height=300): # Altura ajustada
        dpg.add_plot_axis(dpg.mvXAxis, label="Tiempo (s)", tag="x_axis_time")
        dpg.set_axis_limits(dpg.last_item(), -10, 0) # Rango inicial visible
        with dpg.plot_axis(dpg.mvYAxis, label="Marcador"):
            dpg.set_axis_limits(dpg.last_item(), 0, 1) # Un rango simple para el eje Y
            # La serie de líneas verticales
            dpg.add_vline_series([], label="Marcadores de Tiempo", tag="time_markers")

print("se ejecuta time_plot.py")

def _update_plot():
    global t_plot, last_marker_time, time_markers_x
    t_plot += dpg.get_delta_time()
    # Actualiza los límites del eje X para que el gráfico se desplace
    dpg.set_axis_limits('x_axis_time', t_plot - 10, t_plot)

    # Añadir un nuevo marcador vertical cada segundo
    current_integer_time = int(t_plot)
    if current_integer_time > last_marker_time:
        # Asegurarse de que no saltamos ningún segundo si la actualización es lenta
        for s in range(last_marker_time + 1, current_integer_time + 1):
            time_markers_x.append(float(s))
        last_marker_time = current_integer_time

    # Prunar marcadores antiguos para evitar que la lista crezca indefinidamente
    # Mantenemos los marcadores que están dentro del rango visible + un pequeño buffer
    min_visible_x = t_plot - 10
    time_markers_x = [x for x in time_markers_x if x >= min_visible_x - 1]

    # Actualizar la serie de líneas verticales
    dpg.set_value("time_markers", time_markers_x)

with dpg.item_handler_registry(tag="__time_plot_ref"):
    dpg.add_item_visible_handler(callback=_update_plot)
dpg.bind_item_handler_registry("_time_plot", dpg.last_container())

dpg.create_viewport(width=900, height=600, title='Time Marker Plot')
dpg.setup_dearpygui()
dpg.show_viewport()
dpg.start_dearpygui()
dpg.destroy_context()