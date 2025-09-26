import dearpygui.dearpygui as dpg
import numpy as np
from obspy import read
import os
from collections import defaultdict

# Configuración inicial de Dear PyGui
dpg.create_context()

class SeismicGroupedViewer:
    def __init__(self):
        self.seismic_files = {}  # Diccionario: archivo -> lista de trazas
        self.all_traces = []     # Lista plana de todas las trazas
        self.selected_file = None
        self.selected_trace_index = None
        self.expanded_files = set()  # Archivos expandidos en el árbol
        
    def load_seismic_data(self):
        """Cargar datos sísmicos desde archivos, agrupados por archivo"""
        try:
            # Intentar cargar archivos reales
            file_pattern = "multifiles/sismic_records/*"
            
            # Verificar si existe el directorio
            import glob
            files = glob.glob(file_pattern)
            
            if not files:
                print(f"No se encontraron archivos en {file_pattern}")
                print("Generando datos de demostración...")
                self.create_demo_data()
                return
            
            self.seismic_files = {}
            self.all_traces = []
            
            for file_path in files:
                try:
                    stream = read(file_path)
                    file_name = os.path.basename(file_path)
                    
                    file_traces = []
                    for trace in stream:
                        data_info = {
                            'id': trace.id,
                            'station': trace.stats.station,
                            'channel': trace.stats.channel,
                            'network': trace.stats.network,
                            'location': getattr(trace.stats, 'location', ''),
                            'times': trace.times(),
                            'data': trace.data,
                            'sampling_rate': trace.stats.sampling_rate,
                            'starttime': str(trace.stats.starttime),
                            'endtime': str(trace.stats.endtime),
                            'max_amp': np.max(np.abs(trace.data)),
                            'min_amp': np.min(trace.data),
                            'file_name': file_name,
                            'file_path': file_path,
                            'global_index': len(self.all_traces)
                        }
                        file_traces.append(data_info)
                        self.all_traces.append(data_info)
                    
                    self.seismic_files[file_name] = file_traces
                    print(f"Cargado {file_name}: {len(file_traces)} trazas")
                    
                except Exception as e:
                    print(f"Error cargando {file_path}: {e}")
            
            print(f"Total: {len(self.seismic_files)} archivos, {len(self.all_traces)} trazas")
            
        except Exception as e:
            print(f"Error general cargando datos: {e}")
    
    
    def update_file_tree(self):
        """Actualizar el árbol de archivos con trazas"""
        # Limpiar lista anterior si existe
        if dpg.does_item_exist("file_tree"):
            dpg.delete_item("file_tree", children_only=True)
        
        if not self.seismic_files:
            dpg.add_text("No hay archivos sísmicos cargados", parent="file_tree")
            return
        
        # Crear árbol por archivo
        for file_name, traces in self.seismic_files.items():
            file_expanded = file_name in self.expanded_files
            
            # Nodo del archivo
            with dpg.tree_node(label=f"*{file_name} ({len(traces)} trazas)",
                              default_open=file_expanded,
                              parent="file_tree") as file_node:
                
                # Información del archivo
                with dpg.group(horizontal=True):
                    dpg.add_text("*", color=(100, 149, 237))
                    if len(traces[0]['file_path']) > 60:
                        path_display = "..." + traces[0]['file_path'][-57:]
                    else:
                        path_display = traces[0]['file_path']
                    dpg.add_text(f"Archivo: {path_display}", color=(150, 150, 150))
                
                dpg.add_separator()
                
                # Lista de trazas del archivo
                for trace in traces:
                    is_selected = (self.selected_trace_index == trace['global_index'])
                    
                    # Indicador de selección y botón
                    with dpg.group(horizontal=True):
                        # Indicador de selección
                        indicator = "▶️" if is_selected else "⚬"
                        dpg.add_text(indicator)
                        
                        # Botón con información de la traza
                        trace_label = (f"{trace['id']} | "
                                     f"Max: {trace['max_amp']:.1e} | "
                                     f"{trace['sampling_rate']}Hz | "
                                     f"{len(trace['times'])/trace['sampling_rate']:.0f}s")
                        
                        # Usar diferentes colores según selección
                        if is_selected:
                            button_color = (100, 200, 100)  # Verde para seleccionado
                        else:
                            button_color = (70, 130, 180)   # Azul normal
                        
                        with dpg.theme() as trace_theme:
                            with dpg.theme_component(dpg.mvButton):
                                dpg.add_theme_color(dpg.mvThemeCol_Button, button_color)
                                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, 
                                                  (button_color[0]+20, button_color[1]+20, button_color[2]+20))
                        
                        btn = dpg.add_button(label=trace_label,
                                           callback=self.select_trace,
                                           user_data=trace['global_index'],
                                           width=650)
                        dpg.bind_item_theme(btn, trace_theme)
    
    def select_trace(self, sender, app_data, user_data):
        """Seleccionar una traza específica y mostrar en el plotter"""
        self.selected_trace_index = user_data
        selected_trace = self.all_traces[user_data]
        
        print(f"Seleccionada: {selected_trace['id']} del archivo {selected_trace['file_name']}")
        
        # Actualizar el árbol para mostrar la selección
        ##self.update_file_tree()
        
        # Actualizar el plot detallado usando DPG plotter
        self.update_detailed_plot(selected_trace)
    
    def update_detailed_plot(self, trace_data):
        """Actualizar el plot detallado usando DearPyGui plotter nativo"""
        
        # Limpiar plot anterior
        if dpg.does_item_exist("detailed_plot"):
            dpg.delete_item("detailed_plot")
        
        # Crear nuevo plot
        with dpg.plot(label=f"DETALLE: {trace_data['id']}", 
                     height=400, width=650,
                     parent="detailed_plot_container",
                     tag="detailed_plot"):
            
            # Configurar ejes
            dpg.add_plot_legend()
            
            # Eje X (tiempo)
            x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="Tiempo (s)")
            dpg.set_axis_limits(x_axis, 0, trace_data['times'][-1])
            
            # Eje Y (amplitud)
            y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Amplitud")
            y_min = trace_data['min_amp'] * 1.1
            y_max = trace_data['max_amp'] * 1.1
            dpg.set_axis_limits(y_axis, y_min, y_max)
            
            # Decimación para mejorar performance si hay muchos datos
            times = trace_data['times']
            data = trace_data['data']
            
            # Si hay más de 10000 puntos, decimar para mejor rendimiento
            if len(times) > 10000:
                step = len(times) // 10000
                times = times[::step]
                data = data[::step]
            
            # Añadir serie de datos
            dpg.add_line_series(times, data, 
                               label=f"{trace_data['id']}", 
                               parent=y_axis)
        
        # Actualizar información detallada
        if dpg.does_item_exist("trace_info_text"):
            dpg.delete_item("trace_info_text")
        
        info_text = (f"- {trace_data['id']} - {trace_data['file_name']}\n"
                    f"- Estación: {trace_data['station']} | Canal: {trace_data['channel']} | Red: {trace_data['network']}\n"
                    f"- Frecuencia: {trace_data['sampling_rate']} Hz | Duración: {len(trace_data['times'])/trace_data['sampling_rate']:.1f}s\n"
                    f"- Inicio: {trace_data['starttime']}\n"
                    f"- Amplitud Max: {trace_data['max_amp']:.2e} | Min: {trace_data['min_amp']:.2e}")
        
        dpg.add_text(info_text, 
                    parent="detailed_plot_container", 
                    tag="trace_info_text",
                    color=(200, 200, 255))
        
        # Añadir controles adicionales para el plot
        if not dpg.does_item_exist("plot_controls"):
            with dpg.group(horizontal=True, parent="detailed_plot_container", tag="plot_controls"):
                dpg.add_button(label="- Ajustar Vista", callback=self.fit_plot_view)
                dpg.add_button(label="- Ver Espectro", callback=self.show_spectrum)
                dpg.add_button(label="- Exportar Datos", callback=self.export_trace_data)
    
    def fit_plot_view(self, sender, app_data):
        """Ajustar la vista del plot a los datos"""
        if self.selected_trace_index is not None:
            trace_data = self.all_traces[self.selected_trace_index]
            
            if dpg.does_item_exist("detailed_plot"):
                # Obtener ejes del plot
                plot_children = dpg.get_item_children("detailed_plot", 1)
                
                for child in plot_children:
                    if dpg.get_item_type(child).endswith("mvXAxis"):
                        dpg.fit_axis_data(child)
                    elif dpg.get_item_type(child).endswith("mvYAxis"):
                        dpg.fit_axis_data(child)
        
        print("Vista ajustada a los datos")
    
    def show_spectrum(self, sender, app_data):
        """Mostrar espectro de frecuencias de la traza seleccionada"""
        if self.selected_trace_index is not None:
            trace_data = self.all_traces[self.selected_trace_index]
            
            # Calcular FFT
            data = trace_data['data']
            n_samples = len(data)
            fft_data = np.fft.fft(data)
            freqs = np.fft.fftfreq(n_samples, 1/trace_data['sampling_rate'])
            
            # Tomar solo frecuencias positivas
            positive_freqs = freqs[:n_samples//2]
            positive_fft = np.abs(fft_data[:n_samples//2])
            
            # Crear ventana de espectro
            if dpg.does_item_exist("spectrum_window"):
                dpg.delete_item("spectrum_window")
            
            with dpg.window(label=f"Espectro - {trace_data['id']}", 
                           width=700, height=400,
                           tag="spectrum_window"):
                
                with dpg.plot(label="Espectro de Frecuencias", height=300, width=650):
                    dpg.add_plot_legend()
                    
                    x_axis = dpg.add_plot_axis(dpg.mvXAxis, label="Frecuencia (Hz)")
                    dpg.set_axis_limits(x_axis, 0, trace_data['sampling_rate']/2)
                    
                    y_axis = dpg.add_plot_axis(dpg.mvYAxis, label="Amplitud")
                    dpg.set_axis_limits(y_axis, 0, np.max(positive_fft))
                    
                    # Decimación si hay muchos datos
                    if len(positive_freqs) > 5000:
                        step = len(positive_freqs) // 5000
                        positive_freqs = positive_freqs[::step]
                        positive_fft = positive_fft[::step]
                    
                    dpg.add_line_series(positive_freqs, positive_fft, 
                                       label="Espectro", parent=y_axis)
                
                dpg.add_text(f"Frecuencia de muestreo: {trace_data['sampling_rate']} Hz")
                dpg.add_text(f"Frecuencia máxima: {trace_data['sampling_rate']/2} Hz (Nyquist)")
        
        print("Mostrando espectro de frecuencias")
    
    def export_trace_data(self, sender, app_data):
        """Exportar datos de la traza seleccionada"""
        if self.selected_trace_index is not None:
            trace_data = self.all_traces[self.selected_trace_index]
            
            # Crear datos para exportar
            export_data = {
                'id': trace_data['id'],
                'times': trace_data['times'].tolist(),
                'amplitudes': trace_data['data'].tolist(),
                'sampling_rate': trace_data['sampling_rate'],
                'starttime': trace_data['starttime']
            }
            
            print(f"Datos listos para exportar: {trace_data['id']}")
            print(f"  - {len(trace_data['times'])} muestras")
            print(f"  - Duración: {len(trace_data['times'])/trace_data['sampling_rate']:.1f}s")
            print("  - Los datos están disponibles en la variable export_data")
    
    def expand_all_files(self, sender, app_data):
        """Expandir todos los archivos"""
        self.expanded_files = set(self.seismic_files.keys())
        self.update_file_tree()
        print("Todos los archivos expandidos")
    
    def collapse_all_files(self, sender, app_data):
        """Colapsar todos los archivos"""
        self.expanded_files.clear()
        self.update_file_tree()
        print("Todos los archivos colapsados")
    
    def load_data_callback(self, sender, app_data):
        """Callback para recargar datos"""
        print("Recargando datos...")
        self.selected_trace_index = None
        self.expanded_files.clear()
        
        # Limpiar plots existentes
        if dpg.does_item_exist("detailed_plot"):
            dpg.delete_item("detailed_plot")
        if dpg.does_item_exist("trace_info_text"):
            dpg.delete_item("trace_info_text")
        if dpg.does_item_exist("plot_controls"):
            dpg.delete_item("plot_controls")
        
        self.load_seismic_data()
        self.update_file_tree()
    
    def setup_interface(self):
        """Configurar la interfaz principal"""
        
        with dpg.window(label="Visualizador Sísmico - Agrupado por Archivos con DPG Plotter", 
                       width=1400, height=800,
                       tag="main_window"):
            
            # Panel de controles superior
            with dpg.group(horizontal=True):
                dpg.add_button(label="Cargar Datos", 
                              callback=self.load_data_callback,
                              width=120)
                dpg.add_separator()
                dpg.add_button(label="Expandir Todo", 
                              callback=self.expand_all_files,
                              width=120)
                dpg.add_button(label="Colapsar Todo", 
                              callback=self.collapse_all_files,
                              width=120)
            
            dpg.add_separator()
            
            # Layout principal en dos columnas
            with dpg.group(horizontal=True):
                
                # Columna izquierda: Árbol de archivos
                with dpg.child_window(label="Archivos y Trazas", 
                                     width=700, height=650,
                                     tag="file_tree_container"):
                    dpg.add_text("Archivos Sísmicos", color=(255, 255, 100))
                    dpg.add_separator()
                    
                    # Contenedor del árbol
                    with dpg.child_window(tag="file_tree", height=600):
                        dpg.add_text("Cargando...")
                
                # Columna derecha: Plot detallado
                with dpg.child_window(label="Vista Detallada", 
                                     width=680, height=650,
                                     tag="detailed_plot_container"):
                    dpg.add_text(" Plot Detallado con DPG", color=(255, 255, 100))
                    dpg.add_text("Selecciona una traza del árbol para ver detalles", 
                                color=(150, 150, 150))
                    dpg.add_separator()
                    
                    # Aquí aparecerá el plot detallado y controles

# Función principal
def main():
    viewer = SeismicGroupedViewer()
    
    # Configurar interfaz
    viewer.setup_interface()
    
    # Cargar datos iniciales
    viewer.load_seismic_data()
    viewer.update_file_tree()
    
    # Configurar viewport
    dpg.create_viewport(title="Visualizador Sísmico con DPG Plotter - Mesa Sísmica", 
                       width=1400, height=800)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main_window", True)
    
    # Loop principal
    dpg.start_dearpygui()
    dpg.destroy_context()

if __name__ == "__main__":
    main()