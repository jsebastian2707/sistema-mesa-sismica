import serial
import time
import math
import threading
import matplotlib.pyplot as plt

SERIAL_PORT = 'COM4' 
BAUD_RATE = 115200

MOTOR_SPEED_HZ = 1200000
MOTOR_ACCELERATION = 500000

COMMAND_FREQUENCY_HZ = 500
TEST_DURATION_SECONDS = 5

WAVE_AMPLITUDE_STEPS = 10
WAVE_FREQUENCY_HZ =35.6

is_running = True
expected_time_stamps = []
plot_data_expected = []
real_time_stamps = []
plot_data_real = []

# --- Funciones (sin cambios) ---
def serial_reader(ser):
    global is_running
    start_time = time.time()
    while is_running:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8').strip()
                angle_deg = float(line)
                real_time_stamps.append(time.time() - start_time)
                plot_data_real.append(angle_deg)
        except (ValueError, UnicodeDecodeError, serial.SerialException):
            pass

def update_plot(frame, ax):
    ax.clear()
    if expected_time_stamps:
        ax.plot(expected_time_stamps, plot_data_expected, 'r-', label='Esperada (grados)')
    if real_time_stamps:
        ax.plot(real_time_stamps, plot_data_real, 'b.-', label='Real (Encoder)', markersize=2)
    ax.legend(loc='upper left')
    ax.set_title(f'Comparación de Movimiento a {COMMAND_FREQUENCY_HZ} Hz')
    ax.set_xlabel('Tiempo (s)')
    ax.set_ylabel('Posición (grados)')
    ax.grid(True)

def main():
    global is_running
    
    print(f"Iniciando prueba de estrés a {COMMAND_FREQUENCY_HZ} Hz...")
    print(f"Puerto: {SERIAL_PORT}, Baud Rate: {BAUD_RATE}")

    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
        print("Puerto serial abierto. Esperando al ESP32 (3 segundos)...")
        time.sleep(3)
        ser.reset_input_buffer()
        print("Conexión establecida.")
    except serial.SerialException as e:
        print(f"Error al abrir el puerto serial: {e}")
        return

    # --- Enviar configuración del motor (sin cambios) ---
    try:
        print("-" * 30)
        print(f"Enviando configuración: Velocidad = {MOTOR_SPEED_HZ}, Aceleración = {MOTOR_ACCELERATION}")
        ser.write(f"s{MOTOR_SPEED_HZ}\n".encode('utf-8'))
        time.sleep(0.1)
        ser.write(f"a{MOTOR_ACCELERATION}\n".encode('utf-8'))
        time.sleep(0.1)
        print("Configuración enviada.")
        print("-" * 30)
    except serial.SerialException as e:
        print(f"Error al enviar la configuración: {e}")
        ser.close()
        return

    # --- Hilo lector y bucle principal (sin cambios) ---
    reader_thread = threading.Thread(target=serial_reader, args=(ser,))
    reader_thread.daemon = True
    reader_thread.start()

    start_time = time.time()
    loop_delay = 1.0 / COMMAND_FREQUENCY_HZ

    print("Enviando comandos de movimiento...")
    try:
        while time.time() - start_time < TEST_DURATION_SECONDS:
            loop_start_time = time.time()
            elapsed_time = time.time() - start_time
            target_pos_steps = int(WAVE_AMPLITUDE_STEPS * math.sin(2 * math.pi * WAVE_FREQUENCY_HZ * elapsed_time))
            
            expected_time_stamps.append(elapsed_time)
            # Corregimos la fórmula para que sea más directa y comparable al encoder
            target_pos_deg = (target_pos_steps * 360.0) / 4096.0
            plot_data_expected.append(target_pos_deg)

            command = f"m{target_pos_steps}\n"
            ser.write(command.encode('utf-8'))
            
            processing_time = time.time() - loop_start_time
            sleep_time = loop_delay - processing_time
            if sleep_time > 0:
                time.sleep(sleep_time)
    except KeyboardInterrupt:
        print("Prueba interrumpida.")
    finally:
        is_running = False
        print("Finalizando prueba...")
        try:
            ser.write(b'm0\n')
            time.sleep(0.5)
            ser.close()
        except serial.SerialException:
            pass
        reader_thread.join(timeout=1)
        print("Conexión cerrada.")

    print("Generando gráfico...")
    fig, ax = plt.subplots()
    update_plot(fig, ax)
    plt.show()

if __name__ == '__main__':
    main()