# Configuración del Entorno Virtual

Este documento explica cómo configurar y usar el entorno virtual del proyecto.

## ✅ Entorno Virtual Creado

El entorno virtual ya ha sido creado en la carpeta `venv/`.

## 🚀 Activación del Entorno Virtual

### macOS / Linux

```bash
source venv/bin/activate
```

### Windows

```bash
venv\Scripts\activate
```

Una vez activado, verás `(venv)` al inicio de tu prompt de terminal.

## 📦 Instalación de Dependencias

Las dependencias ya están instaladas. Si necesitas reinstalarlas:

```bash
pip install -r requirements.txt
```

## 🏃 Ejecutar la Aplicación

Con el entorno virtual activado:

```bash
cd app
python main.py
```

O desde la raíz del proyecto:

```bash
python app/main.py
```

## 🔧 Dependencias Instaladas

- **dearpygui**: Interfaz gráfica de usuario
- **obspy**: Procesamiento de datos sísmicos
- **numpy**: Cálculos numéricos
- **scipy**: Funciones científicas adicionales
- **pyserial**: Comunicación serial con ESP32
- **matplotlib**: Visualización de datos

## 🛑 Desactivar el Entorno Virtual

Cuando termines de trabajar:

```bash
deactivate
```

## 🔄 Actualizar Dependencias

Si se agregan nuevas dependencias al proyecto:

```bash
# Activar el entorno virtual
source venv/bin/activate

# Instalar nuevas dependencias
pip install -r requirements.txt

# O instalar un paquete específico
pip install nombre-paquete

# Actualizar requirements.txt con las nuevas dependencias
pip freeze > requirements.txt
```

## ⚠️ Notas Importantes

- **Siempre activa el entorno virtual** antes de ejecutar la aplicación
- El entorno virtual está excluido del control de versiones (ver `.gitignore`)
- Si clonas el repositorio en otra máquina, necesitarás crear un nuevo entorno virtual:
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```

## 🐛 Solución de Problemas

### Error: "python3: command not found"
- En macOS, instala Python desde [python.org](https://www.python.org/downloads/) o usa Homebrew:
  ```bash
  brew install python3
  ```

### Error al instalar dependencias
- Asegúrate de tener pip actualizado:
  ```bash
  pip install --upgrade pip
  ```

### Error de permisos
- En algunos sistemas, puede ser necesario usar `python3 -m venv` en lugar de `python -m venv`

