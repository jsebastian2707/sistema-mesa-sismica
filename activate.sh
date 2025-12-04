#!/bin/bash
# Script para activar el entorno virtual del proyecto

# Cambiar al directorio del script
cd "$(dirname "$0")"

# Activar el entorno virtual
source venv/bin/activate

echo "✅ Entorno virtual activado"
echo "📁 Directorio: $(pwd)"
echo ""
echo "Para ejecutar la aplicación:"
echo "  python app/main.py"
echo ""
echo "Para desactivar el entorno virtual:"
echo "  deactivate"

