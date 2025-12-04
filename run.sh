#!/bin/bash
# Script para ejecutar la aplicación con el entorno virtual activado

# Cambiar al directorio del script
cd "$(dirname "$0")"

# Activar el entorno virtual
source venv/bin/activate

# Ejecutar la aplicación
echo "🚀 Iniciando Sistema de Mesa Sísmica..."
python app/main.py

