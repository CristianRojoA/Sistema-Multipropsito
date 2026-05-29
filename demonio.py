"""
demonio.py — Proceso demonio de monitoreo y procesamiento automático
=====================================================================
Monitorea la carpeta entrada/ cada 10 segundos.  Cuando detecta archivos
nuevos, lanza un hilo por archivo para moverlo a procesados/.

Mecanismo de sincronización:
  - file_lock  (Lock)      : protege acceso al sistema de archivos
  - log_lock   (Lock)      : protege escrituras en registro.log
  - procesados_set         : conjunto de archivos ya procesados (en memoria)

Uso:
  python3 demonio.py              # ejecuta en primer plano (logs en consola)
  python3 demonio.py --daemon     # se desprende del terminal (daemoniza)
"""

import os
import sys
import time
import shutil
import logging
import argparse
import threading
from pathlib import Path
from datetime import datetime

# =============================================================================
# CONFIGURACIÓN DE RUTAS
# =============================================================================
BASE_DIR     = Path.home() / "servidor_archivos"
DIR_ENTRADA  = BASE_DIR / "entrada"
DIR_PROC     = BASE_DIR / "procesados"
DIR_LOGS     = BASE_DIR / "logs"
ARCHIVO_LOG  = DIR_LOGS / "registro.log"

INTERVALO_MONITOREO = 10  # segundos entre cada ciclo de revisión

# =============================================================================
# LOCKS Y ESTADO COMPARTIDO
# =============================================================================
file_lock  = threading.Lock()   # Protege operaciones de archivos (move/copy)
log_lock   = threading.Lock()   # Protege escrituras en registro.log

# Conjunto que guarda los nombres de archivos que ya están siendo procesados
# o que ya se procesaron en esta sesión.  Protegido por file_lock.
archivos_en_proceso: set = set()

# =============================================================================
# LOGGING EN CONSOLA
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("demonio")


# =============================================================================
# FUNCIÓN DE REGISTRO SINCRONIZADO (igual que en servidor.py)
# =============================================================================
def registrar(operacion: str, detalle: str, origen: str = "demonio") -> None:
    """
    Escribe en registro.log de forma thread-safe usando log_lock.

    La sección crítica garantiza que las escrituras de múltiples hilos
    no se entrelacen (interleaving), lo que podría corromper líneas del log.
    """
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"{marca} | {origen:20s} | {operacion:10s} | {detalle}\n"

    with log_lock:          # ← Sección crítica
        try:
            with open(ARCHIVO_LOG, "a", encoding="utf-8") as f:
                f.write(linea)
        except IOError as e:
            logger.error(f"No se pudo escribir en el log: {e}")

    logger.info(f"[{operacion}] {detalle}")


# =============================================================================
# FUNCIÓN DE PROCESAMIENTO DE UN ARCHIVO (ejecutada en un hilo)
# =============================================================================
def procesar_archivo(nombre: str) -> None:
    """
    Mueve un archivo de entrada/ a procesados/.

    Se ejecuta en un hilo separado por cada archivo nuevo detectado.
    Usa file_lock para evitar condiciones de carrera cuando dos hilos
    intentan mover/leer el mismo archivo simultáneamente.

    Flujo:
      1. Adquiere file_lock antes de verificar/mover el archivo.
      2. Verifica que el archivo sigue en entrada/ (podría haber sido
         tomado por otro hilo entre la detección y el lock).
      3. Mueve el archivo y actualiza archivos_en_proceso.
      4. Libera el lock.
      5. Registra la operación (log_lock interno).
    """
    origen  = DIR_ENTRADA / nombre
    destino = DIR_PROC / nombre

    # Sección crítica: verificación + movimiento atómico bajo lock
    with file_lock:
        # Re-verificar: entre que se detectó y se obtuvo el lock,
        # otro hilo pudo haberlo procesado ya.
        if not origen.is_file():
            logger.warning(f"'{nombre}' ya no existe en entrada/ (procesado por otro hilo).")
            archivos_en_proceso.discard(nombre)
            return
        try:
            shutil.move(str(origen), str(destino))
            logger.info(f"'{nombre}' movido a procesados/")
        except Exception as e:
            logger.error(f"Error al mover '{nombre}': {e}")
            archivos_en_proceso.discard(nombre)
            registrar("ERROR", f"No se pudo mover {nombre}: {e}")
            return

    # Fuera del file_lock: el log usa su propio lock
    registrar("PROCESAR", f"{nombre} movido a procesados/")


# =============================================================================
# BUCLE PRINCIPAL DE MONITOREO
# =============================================================================
def bucle_monitoreo() -> None:
    """
    Ciclo infinito que revisa entrada/ cada INTERVALO_MONITOREO segundos.

    Para cada archivo nuevo (no en archivos_en_proceso):
      - Lo añade al conjunto de "en proceso" bajo file_lock.
      - Lanza un hilo daemon para procesarlo.

    El uso de file_lock al consultar/modificar archivos_en_proceso evita
    que dos iteraciones del ciclo lancen hilos duplicados para el mismo archivo.
    """
    logger.info(f"Demonio iniciado. Monitoreando '{DIR_ENTRADA}' cada {INTERVALO_MONITOREO}s ...")
    registrar("START", f"Demonio iniciado — monitoreando {DIR_ENTRADA}")

    while True:
        try:
            # Obtener lista de archivos actuales en entrada/
            archivos_actuales = {f.name for f in DIR_ENTRADA.iterdir() if f.is_file()}

            # Detectar archivos nuevos (no marcados como en proceso)
            with file_lock:
                nuevos = archivos_actuales - archivos_en_proceso
                # Marcarlos inmediatamente para que el próximo ciclo no los redetecte
                archivos_en_proceso.update(nuevos)

            if nuevos:
                logger.info(f"Detectados {len(nuevos)} archivo(s) nuevo(s): {nuevos}")
                for nombre in nuevos:
                    hilo = threading.Thread(
                        target=procesar_archivo,
                        args=(nombre,),
                        name=f"Proc-{nombre}",
                        daemon=True
                    )
                    hilo.start()
            else:
                logger.debug("Sin archivos nuevos en esta iteración.")

        except Exception as e:
            logger.error(f"Error en el ciclo de monitoreo: {e}", exc_info=True)
            registrar("ERROR", f"Error en ciclo: {e}")

        time.sleep(INTERVALO_MONITOREO)


# =============================================================================
# DAEMONIZACIÓN (opcional — solo Linux/macOS)
# =============================================================================
def daemonizar() -> None:
    """
    Convierte el proceso en un demonio POSIX:
      1. Fork #1 → el padre sale (el hijo queda huérfano).
      2. setsid() → nuevo líder de sesión (sin terminal).
      3. Fork #2 → imposible readquirir una terminal.
      4. Redirige stdin/stdout/stderr a /dev/null.
    """
    if sys.platform == "win32":
        logger.warning("La daemonización POSIX no está soportada en Windows.")
        logger.warning("Ejecutando en primer plano ...")
        return

    # Fork #1
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    os.setsid()

    # Fork #2
    pid = os.fork()
    if pid > 0:
        sys.exit(0)

    # Redirigir E/S estándar
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull, "rb") as f:
        os.dup2(f.fileno(), sys.stdin.fileno())
    with open(os.devnull, "ab") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())

    # Guardar PID en archivo
    pid_file = BASE_DIR / "demonio.pid"
    pid_file.write_text(str(os.getpid()))
    logger.info(f"Demonio daemonizado. PID: {os.getpid()} → {pid_file}")


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Demonio de monitoreo de archivos")
    parser.add_argument("--daemon", action="store_true",
                        help="Ejecutar como proceso demonio (background, solo Linux/macOS)")
    parser.add_argument("--intervalo", default=10, type=int,
                        help="Segundos entre ciclos de monitoreo (default: 10)")
    args = parser.parse_args()

    INTERVALO_MONITOREO = args.intervalo

    # Crear carpetas si no existen
    for d in (DIR_ENTRADA, DIR_PROC, DIR_LOGS):
        d.mkdir(parents=True, exist_ok=True)

    if args.daemon:
        daemonizar()

    try:
        bucle_monitoreo()
    except KeyboardInterrupt:
        logger.info("Demonio detenido por el usuario (Ctrl+C).")
        registrar("STOP", "Demonio detenido manualmente")
