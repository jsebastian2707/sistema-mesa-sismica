import serial
import time
from collections import deque
import threading

# --- CONFIGURACION ---
SERIAL_PORT = 'COM4' 
BAUD_RATE = 115200

# Parametros del motor (ajusta a tu configuracion)
STEPS_PER_REVOLUTION = 3200

# CAMBIO 1: Rangos de prueba mas altos para buscar los limites reales.
# Puedes ajustar estos valores segun sea necesario.
ACCEL_START = 200000
ACCEL_END = 1000000
ACCEL_STEP = 100000

SPEED_START = 500000
SPEED_END = 1200000
SPEED_STEP = 50000

# Parametros del test de movimiento
# La direccion se alternara automaticamente en cada prueba.
BASE_MOVE_DEGREES = 360 * 3 
ERROR_TOLERANCE_DEGREES = 10.0

# Parametros para la deteccion de parada del motor
STABILITY_WINDOW_SEC = 0.3
STABILITY_THRESHOLD_DEG = 0.2
# --- FIN DE LA CONFIGURACION ---


class ESP32Monitor:
    """
    Gestiona la comunicacion y el monitoreo del ESP32 sin modificar su codigo.
    Lee el flujo de datos del encoder en un hilo separado.
    """
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
        """Hilo que lee y parsea los datos del encoder continuamente."""
        self.ser.flushInput()
        while self.is_running:
            try:
                line = self.ser.readline().decode('utf-8').strip()
                if line:
                    clean_line = ''.join(filter(lambda x: x in '0123456789.-', line))
                    if clean_line:
                        angle = float(clean_line)
                        with self.lock:
                            self.latest_angle = angle
            except (ValueError, UnicodeDecodeError):
                pass
            except serial.SerialException:
                print("Error de puerto serie. Saliendo del hilo.")
                break

    def get_latest_angle(self):
        """Obtiene el ultimo angulo leido de forma segura."""
        with self.lock:
            return self.latest_angle

    def send_command(self, command):
        """Envia un comando al ESP32."""
        print(f"-> Enviando: {command}")
        self.ser.write((command + '\n').encode('utf-8'))
        time.sleep(0.05)

    def wait_for_stop(self):
        """Espera hasta que el motor se detenga."""
        print("... Esperando a que el motor se detenga...")
        num_readings = int(STABILITY_WINDOW_SEC / 0.005)
        history = deque(maxlen=num_readings)
        time.sleep(0.1) 

        while True:
            history.append(self.get_latest_angle())
            if len(history) == num_readings:
                delta = max(history) - min(history)
                if delta < STABILITY_THRESHOLD_DEG:
                    print("Motor detenido detectado!")
                    time.sleep(0.1)
                    return self.get_latest_angle()
            time.sleep(0.01)

    def close(self):
        """Cierra la conexion y detiene el hilo."""
        self.is_running = False
        if self.reader_thread.is_alive():
            self.reader_thread.join(timeout=1)
        self.ser.close()
        print("Conexion cerrada.")


def run_calibration():
    """Ejecuta el proceso completo de calibracion."""
    results = {}
    current_step_pos = 0
    # CAMBIO 2: Variable para alternar la direccion
    direction_multiplier = 1 

    try:
        monitor = ESP32Monitor(SERIAL_PORT, BAUD_RATE)
        initial_pos = monitor.wait_for_stop()
        # CAMBIO 3: Se quitan las tildes de los prints
        print(f"Posicion inicial estable: {initial_pos:.2f} grados")

        for accel in range(ACCEL_START, ACCEL_END + 1, ACCEL_STEP):
            monitor.send_command(f"a{accel}")
            last_successful_speed = 0
            
            print(f"\n--- Probando Aceleracion: {accel} steps/s^2 ---")
            
            for speed in range(SPEED_START, SPEED_END + 1, SPEED_STEP):
                monitor.send_command(f"s{speed}")
                
                # Alternar direccion en cada prueba de velocidad
                move_degrees_this_test = BASE_MOVE_DEGREES * direction_multiplier
                
                start_angle = monitor.get_latest_angle()
                expected_angle_change = abs(move_degrees_this_test)
                
                steps_to_move = int((move_degrees_this_test / 360.0) * STEPS_PER_REVOLUTION)
                target_step_pos = current_step_pos + steps_to_move
                
                print(f"Probando Velocidad: {speed} Hz... (Direccion: {'Positiva' if direction_multiplier > 0 else 'Negativa'})")
                monitor.send_command(f"m{target_step_pos}")

                final_angle = monitor.wait_for_stop()
                
                actual_angle_change = abs(final_angle - start_angle)
                error = abs(expected_angle_change - actual_angle_change)

                if error <= ERROR_TOLERANCE_DEGREES:
                    print(f"  EXITO. Error: {error:.2f} grados.")
                    last_successful_speed = speed
                    current_step_pos = target_step_pos
                else:
                    print(f"  FALLO. Error: {error:.2f} grados (Esperado: {expected_angle_change:.2f}, Obtenido: {actual_angle_change:.2f}).")
                    monitor.send_command("m0")
                    monitor.wait_for_stop()
                    current_step_pos = 0
                    break
                
                # Invertir la direccion para la proxima prueba
                direction_multiplier *= -1

            results[accel] = last_successful_speed
            print(f"-> Maxima velocidad para aceleracion {accel} es: {last_successful_speed} Hz")

    except serial.SerialException as e:
        print(f"Error de puerto serie: {e}")
    finally:
        if 'monitor' in locals():
            monitor.close()
    
    return results

if __name__ == "__main__":
    final_results = run_calibration()
    print("\n\n--- Resumen de Calibracion ---")
    if not final_results:
        print("No se completo ninguna prueba.")
    else:
        for accel, speed in final_results.items():
            print(f"Aceleracion: {accel:<8} -> Vel. Maxima Sostenible: {speed} Hz")