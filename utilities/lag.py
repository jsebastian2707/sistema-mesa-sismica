import serial
import time
import threading

# --- CONFIGURACION ---
SERIAL_PORT = 'COM4' 
BAUD_RATE = 115200

TEST_ACCEL = 200000 
TEST_SPEED = 500000

NUM_TESTS = 10
MOVEMENT_THRESHOLD_DEG = 0.5 
PAUSE_BETWEEN_TESTS = 2
# --- FIN DE LA CONFIGURACION ---

class ESP32Monitor:
    """Clase simplificada para leer el angulo en un hilo separado."""
    def __init__(self, port, baudrate):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        self.latest_angle = 0.0
        self.is_running = True
        self.lock = threading.Lock()
        
        self.reader_thread = threading.Thread(target=self._read_serial_thread)
        self.reader_thread.daemon = True
        self.reader_thread.start()
        
        print(f"Conectado a {port}. Esperando datos del encoder...")
        time.sleep(2)

    def _read_serial_thread(self):
        self.ser.flushInput()
        while self.is_running:
            try:
                line = self.ser.readline().decode('utf-8').strip()
                if line:
                    clean_line = ''.join(filter(lambda x: x in '0123456789.-', line))
                    
                    # --- INICIO DE LA CORRECCION ---
                    # Ahora, intentamos la conversion. Si falla, simplemente
                    # ignoramos esta linea y continuamos con la siguiente.
                    if clean_line:
                        try:
                            self.latest_angle = float(clean_line)
                        except ValueError:
                            # Ocurrio un error (ej. se recibio '..', '-', etc.)
                            # Simplemente ignoramos esta linea de datos corrupta.
                            pass 
                    # --- FIN DE LA CORRECCION ---

            except (IOError, serial.SerialException):
                break

    def get_latest_angle(self):
        return self.latest_angle

    def send_command(self, command):
        self.ser.write((command + '\n').encode('utf-8'))

    def close(self):
        self.is_running = False
        if self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1)
        self.ser.close()
        print("Conexion cerrada.")

def measure_lag():
    """Ejecuta la prueba de medicion de latencia."""
    monitor = None
    try:
        monitor = ESP32Monitor(SERIAL_PORT, BAUD_RATE)
        lag_times = []

        monitor.send_command(f"a{TEST_ACCEL}")
        time.sleep(0.1)
        monitor.send_command(f"s{TEST_SPEED}")
        time.sleep(0.1)

        print("\n--- Iniciando Prueba de Latencia del Motor ---")
        
        print("Moviendo a posicion 0 para empezar...")
        monitor.send_command("m0")
        time.sleep(PAUSE_BETWEEN_TESTS)

        for i in range(NUM_TESTS):
            print(f"\n--- Prueba {i + 1}/{NUM_TESTS} ---")
            
            time.sleep(0.5)
            initial_angle = monitor.get_latest_angle()
            print(f"Posicion inicial estable: {initial_angle:.2f} grados")

            t_start = time.perf_counter()
            monitor.send_command("m4000")

            while True:
                current_angle = monitor.get_latest_angle()
                if abs(current_angle - initial_angle) > MOVEMENT_THRESHOLD_DEG:
                    t_end = time.perf_counter()
                    break
                time.sleep(0.001)

            lag_ms = (t_end - t_start) * 1000
            lag_times.append(lag_ms)
            print(f"Movimiento detectado! Latencia: {lag_ms:.2f} ms")

            print("Regresando a posicion 0...")
            monitor.send_command("m0")
            time.sleep(PAUSE_BETWEEN_TESTS)

        print("\n\n--- Resultados de la Prueba de Latencia ---")
        if lag_times:
            avg_lag = sum(lag_times) / len(lag_times)
            min_lag = min(lag_times)
            max_lag = max(lag_times)
            print(f"Pruebas realizadas: {len(lag_times)}")
            print(f"Latencia promedio: {avg_lag:.2f} ms")
            print(f"Latencia minima:   {min_lag:.2f} ms")
            print(f"Latencia maxima:   {max_lag:.2f} ms")
        else:
            print("No se completaron pruebas.")

    except serial.SerialException as e:
        print(f"Error de puerto serie: {e}")
    except KeyboardInterrupt:
        print("\nPrueba interrumpida por el usuario.")
    finally:
        if monitor:
            monitor.close()

if __name__ == "__main__":
    measure_lag()