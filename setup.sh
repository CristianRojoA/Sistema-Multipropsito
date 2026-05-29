#!/bin/bash
# =============================================================================
# setup.sh — Preparación del entorno para el sistema cliente-servidor
# =============================================================================
# Crea la estructura de carpetas necesaria y genera archivos de prueba
# Uso: bash setup.sh
# =============================================================================

set -e  # Detener ante cualquier error

BASE_DIR="$HOME/servidor_archivos"
ENTRADA="$BASE_DIR/entrada"
PROCESADOS="$BASE_DIR/procesados"
LOGS="$BASE_DIR/logs"

echo "============================================="
echo "  Configuración del entorno - Servidor       "
echo "============================================="

# --- 1. Crear estructura de carpetas ---
echo "[1/3] Creando estructura de carpetas en $BASE_DIR ..."

mkdir -p "$ENTRADA"
mkdir -p "$PROCESADOS"
mkdir -p "$LOGS"

echo "  Carpetas creadas:"
echo "    $ENTRADA"
echo "    $PROCESADOS"
echo "    $LOGS"

# --- 2. Asignar permisos ---
echo "[2/3] Asignando permisos (rwxr-x---) ..."

# El propietario (servidor) puede leer, escribir y ejecutar.
# El grupo puede leer y ejecutar. Otros no tienen acceso.
chmod 750 "$BASE_DIR"
chmod 770 "$ENTRADA"      # Escritura necesaria para el cliente al subir
chmod 770 "$PROCESADOS"   # El demonio y servidor escriben aquí
chmod 770 "$LOGS"         # El servidor escribe el registro.log aquí

echo "  Permisos aplicados:"
ls -ld "$BASE_DIR" "$ENTRADA" "$PROCESADOS" "$LOGS"

# --- 3. Generar archivos de prueba en entrada/ ---
echo "[3/3] Generando archivos de prueba en $ENTRADA ..."

cat > "$ENTRADA/archivo1.txt" << 'EOF'
Archivo de prueba #1
====================
Este es el primer archivo de texto generado automáticamente
para probar el sistema de transferencia de archivos.

Contenido: Lorem ipsum dolor sit amet, consectetur adipiscing
elit. Sed do eiusmod tempor incididunt ut labore et dolore
magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation.

Fecha generación: $(date)
Número de líneas: 10
EOF

cat > "$ENTRADA/archivo2.txt" << 'EOF'
Archivo de prueba #2
====================
Segundo archivo de prueba para el sistema cliente-servidor.

Datos de ejemplo:
- Registro A: 192.168.1.10 | usuario_01 | 2025-01-15 10:30
- Registro B: 192.168.1.11 | usuario_02 | 2025-01-15 11:45
- Registro C: 10.0.0.5     | admin      | 2025-01-15 14:20

Este archivo simula un log de accesos de red.
EOF

cat > "$ENTRADA/archivo3.txt" << 'EOF'
Archivo de prueba #3
====================
Tercer archivo de prueba: configuración de ejemplo.

[servidor]
host = 0.0.0.0
puerto = 9000
max_clientes = 10
timeout = 30

[rutas]
entrada    = ~/servidor_archivos/entrada
procesados = ~/servidor_archivos/procesados
logs       = ~/servidor_archivos/logs

[opciones]
debug = false
log_nivel = INFO
EOF

echo "  Archivos generados:"
ls -lh "$ENTRADA/"

# --- 4. Crear archivo de log vacío ---
touch "$LOGS/registro.log"
chmod 660 "$LOGS/registro.log"
echo "  Log inicializado: $LOGS/registro.log"

echo ""
echo "============================================="
echo "  Entorno listo. Puedes ejecutar:"
echo "    python3 servidor.py"
echo "    python3 demonio.py"
echo "    python3 cliente.py"
echo "============================================="
