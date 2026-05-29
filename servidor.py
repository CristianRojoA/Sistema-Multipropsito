"""
servidor.py — Servidor TCP multihilo para gestión remota de archivos
=====================================================================
Escucha conexiones en el puerto 9000 y crea un hilo por cada cliente.

Protocolo de comandos (texto, terminado en \\n):
  LIST                        → lista archivos en entrada/
  READ <nombre>               → devuelve contenido del archivo
  COPY <nombre>               → copia archivo de entrada/ a procesados/
  UPLOAD <nombre> <bytes>     → recibe un archivo y lo guarda en entrada/
  DOWNLOAD <nombre>           → envía un archivo desde entrada/ o procesados/
  LOGS                        → devuelve el contenido de registro.log
  EXIT                        → cierra la conexión

Respuestas del servidor:
  OK <datos>                  → operación exitosa
  ERROR <mensaje>             → error
  DATA <n_bytes>\\n<payload>   → envío de datos binarios

Uso:
  python3 servidor.py [--host 0.0.0.0] [--puerto 9000]
"""

import socket
import threading
import os
import shutil
import logging
import argparse
import time
from datetime import datetime
from pathlib import Path

# =============================================================================
# CONFIGURACIÓN DE RUTAS
# =============================================================================
BASE_DIR     = Path.home() / "servidor_archivos"
DIR_ENTRADA  = BASE_DIR / "entrada"
DIR_PROC     = BASE_DIR / "procesados"
DIR_LOGS     = BASE_DIR / "logs"
ARCHIVO_LOG  = DIR_LOGS / "registro.log"

# =============================================================================
# LOCK GLOBAL PARA EL ARCHIVO DE LOG
# Garantiza que solo un hilo escribe en registro.log a la vez,
# evitando condiciones de carrera sobre el fichero de registro.
# =============================================================================
log_lock = threading.Lock()

# Semáforo que limita el número de clientes simultáneos a 10
sem_clientes = threading.Semaphore(10)

# =============================================================================
# CONFIGURACIÓN DEL LOGGER DE PYTHON (consola)
# =============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("servidor")


# =============================================================================
# FUNCIÓN DE REGISTRO SINCRONIZADO
# =============================================================================
def registrar(operacion: str, detalle: str, cliente: str = "sistema") -> None:
    """
    Escribe una línea en registro.log de forma thread-safe.

    Usa log_lock (threading.Lock) para que nunca dos hilos escriban
    simultáneamente, evitando interleaving y corrupción del log.
    """
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"{marca} | {cliente:20s} | {operacion:10s} | {detalle}\n"

    with log_lock:          # Sección crítica — acceso exclusivo al archivo
        try:
            with open(ARCHIVO_LOG, "a", encoding="utf-8") as f:
                f.write(linea)
        except IOError as e:
            logger.error(f"No se pudo escribir en el log: {e}")

    logger.info(f"[{cliente}] {operacion}: {detalle}")


# =============================================================================
# MANEJADOR DE CLIENTE (se ejecuta en su propio hilo)
# =============================================================================
class ManejadorCliente(threading.Thread):
    """
    Hilo dedicado a atender a un cliente conectado.

    Cada instancia representa una conexión independiente.
    Los recursos compartidos (log, sistema de archivos) se protegen
    con log_lock y file_lock respectivamente.
    """

    # Lock compartido entre TODOS los hilos para operaciones sobre archivos
    # (evita que dos hilos muevan/lean el mismo archivo simultáneamente)
    file_lock = threading.Lock()

    def __init__(self, conn: socket.socket, addr: tuple):
        super().__init__(daemon=True)
        self.conn    = conn
        self.addr    = addr
        self.cliente = f"{addr[0]}:{addr[1]}"
        self.name    = f"Hilo-{addr[1]}"   # nombre visible en logs

    # ------------------------------------------------------------------
    # Helpers de E/S
    # ------------------------------------------------------------------
    def enviar(self, mensaje: str) -> None:
        """Envía una cadena UTF-8 terminada en \\n."""
        self.conn.sendall((mensaje + "\n").encode("utf-8"))

    def recibir_linea(self) -> str:
        """Lee hasta encontrar \\n y devuelve la línea decodificada."""
        datos = b""
        while not datos.endswith(b"\n"):
            chunk = self.conn.recv(4096)
            if not chunk:
                raise ConnectionResetError("Cliente desconectado")
            datos += chunk
        return datos.decode("utf-8").strip()

    def recibir_bytes(self, n: int) -> bytes:
        """Lee exactamente n bytes del socket."""
        datos = b""
        while len(datos) < n:
            chunk = self.conn.recv(min(4096, n - len(datos)))
            if not chunk:
                raise ConnectionResetError("Cliente desconectado durante transferencia")
            datos += chunk
        return datos

    def enviar_archivo(self, ruta: Path) -> None:
        """Envía un archivo precedido de su tamaño: DATA <n>\\n<bytes>."""
        tamanio = ruta.stat().st_size
        self.enviar(f"DATA {tamanio}")
        with open(ruta, "rb") as f:
            self.conn.sendall(f.read())

    # ------------------------------------------------------------------
    # Operaciones del protocolo
    # ------------------------------------------------------------------
    def op_list(self) -> None:
        archivos = [f.name for f in DIR_ENTRADA.iterdir() if f.is_file()]
        if archivos:
            self.enviar("OK " + ",".join(archivos))
        else:
            self.enviar("OK (vacío)")
        registrar("LIST", f"{len(archivos)} archivo(s)", self.cliente)

    def op_read(self, nombre: str) -> None:
        # Busca primero en entrada/, luego en procesados/
        ruta = DIR_ENTRADA / nombre
        if not ruta.is_file():
            ruta = DIR_PROC / nombre
        if not ruta.is_file():
            self.enviar(f"ERROR Archivo '{nombre}' no encontrado")
            registrar("READ", f"ERROR — {nombre} no existe", self.cliente)
            return
        # Sección crítica: lectura del archivo
        with ManejadorCliente.file_lock:
            contenido = ruta.read_text(encoding="utf-8", errors="replace")
        self.enviar(f"DATA {len(contenido.encode())}")
        self.conn.sendall(contenido.encode("utf-8"))
        registrar("READ", f"{nombre} ({len(contenido)} chars)", self.cliente)

    def op_copy(self, nombre: str) -> None:
        origen  = DIR_ENTRADA / nombre
        destino = DIR_PROC / nombre
        if not origen.is_file():
            self.enviar(f"ERROR Archivo '{nombre}' no encontrado en entrada/")
            registrar("COPY", f"ERROR — {nombre} no existe", self.cliente)
            return
        # Sección crítica: copia de archivo
        with ManejadorCliente.file_lock:
            shutil.copy2(str(origen), str(destino))
        self.enviar(f"OK Archivo '{nombre}' copiado a procesados/")
        registrar("COPY", f"{nombre} → procesados/", self.cliente)

    def op_upload(self, nombre: str, n_bytes: int) -> None:
        ruta = DIR_ENTRADA / nombre
        contenido = self.recibir_bytes(n_bytes)
        with ManejadorCliente.file_lock:
            ruta.write_bytes(contenido)
        self.enviar(f"OK Archivo '{nombre}' recibido ({n_bytes} bytes)")
        registrar("UPLOAD", f"{nombre} ({n_bytes} bytes)", self.cliente)

    def op_download(self, nombre: str) -> None:
        # Busca primero en entrada/, luego en procesados/
        ruta = DIR_ENTRADA / nombre
        if not ruta.is_file():
            ruta = DIR_PROC / nombre
        if not ruta.is_file():
            self.enviar(f"ERROR Archivo '{nombre}' no encontrado")
            registrar("DOWNLOAD", f"ERROR — {nombre} no existe", self.cliente)
            return
        self.enviar_archivo(ruta)
        registrar("DOWNLOAD", f"{nombre} ({ruta.stat().st_size} bytes)", self.cliente)

    def op_listproc(self) -> None:
        archivos = [f.name for f in DIR_PROC.iterdir() if f.is_file()]
        if archivos:
            self.enviar("OK " + ",".join(archivos))
        else:
            self.enviar("OK (vacío)")
        registrar("LISTPROC", f"{len(archivos)} archivo(s)", self.cliente)

    def op_logs(self) -> None:
        with log_lock:
            contenido = ARCHIVO_LOG.read_text(encoding="utf-8") if ARCHIVO_LOG.exists() else ""
        self.enviar(f"DATA {len(contenido.encode())}")
        self.conn.sendall(contenido.encode("utf-8"))
        registrar("LOGS", "Log consultado", self.cliente)

    # ------------------------------------------------------------------
    # Bucle principal del hilo
    # ------------------------------------------------------------------
    def run(self) -> None:
        registrar("CONNECT", "Cliente conectado", self.cliente)
        try:
            while True:
                linea = self.recibir_linea()
                if not linea:
                    continue

                partes = linea.split(" ", 2)
                cmd    = partes[0].upper()

                if cmd == "LIST":
                    self.op_list()

                elif cmd == "READ":
                    nombre = partes[1] if len(partes) > 1 else ""
                    self.op_read(nombre)

                elif cmd == "COPY":
                    nombre = partes[1] if len(partes) > 1 else ""
                    self.op_copy(nombre)

                elif cmd == "UPLOAD":
                    if len(partes) < 3:
                        self.enviar("ERROR Sintaxis: UPLOAD <nombre> <bytes>")
                        continue
                    nombre  = partes[1]
                    n_bytes = int(partes[2])
                    self.op_upload(nombre, n_bytes)

                elif cmd == "DOWNLOAD":
                    nombre = partes[1] if len(partes) > 1 else ""
                    self.op_download(nombre)

                elif cmd == "LISTPROC":
                    self.op_listproc()

                elif cmd == "LOGS":
                    self.op_logs()

                elif cmd == "EXIT":
                    self.enviar("OK Hasta luego")
                    break

                else:
                    self.enviar(f"ERROR Comando desconocido: {cmd}")

        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as e:
            logger.warning(f"[{self.cliente}] Conexión interrumpida: {e}")
        except Exception as e:
            logger.error(f"[{self.cliente}] Error inesperado: {e}", exc_info=True)
        finally:
            registrar("DISCONNECT", "Cliente desconectado", self.cliente)
            self.conn.close()
            sem_clientes.release()   # Libera el semáforo al terminar


# =============================================================================
# SERVIDOR PRINCIPAL
# =============================================================================
def iniciar_servidor(host: str = "0.0.0.0", puerto: int = 9000) -> None:
    """
    Abre el socket TCP, acepta conexiones y lanza un hilo por cliente.

    El semáforo sem_clientes limita la concurrencia a 10 clientes
    simultáneos sin rechazar conexiones: simplemente bloquea el accept
    hasta que se libere un slot.
    """
    # Verificar que existen las carpetas
    for directorio in (DIR_ENTRADA, DIR_PROC, DIR_LOGS):
        directorio.mkdir(parents=True, exist_ok=True)

    registrar("START", f"Servidor iniciado en {host}:{puerto}")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as servidor:
        servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        servidor.bind((host, puerto))
        servidor.listen(20)
        logger.info(f"Servidor escuchando en {host}:{puerto} ...")

        try:
            while True:
                conn, addr = servidor.accept()
                sem_clientes.acquire()          # Bloquea si hay 10 clientes activos
                hilo = ManejadorCliente(conn, addr)
                hilo.start()
                logger.info(f"Nuevo cliente: {addr[0]}:{addr[1]} — hilos activos: {threading.active_count()-1}")
        except KeyboardInterrupt:
            logger.info("Servidor detenido por el usuario (Ctrl+C)")
            registrar("STOP", "Servidor detenido manualmente")


# =============================================================================
# PUNTO DE ENTRADA
# =============================================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Servidor TCP multihilo de archivos")
    parser.add_argument("--host",   default="0.0.0.0", help="Interfaz de escucha (default: 0.0.0.0)")
    parser.add_argument("--puerto", default=9000, type=int, help="Puerto TCP (default: 9000)")
    args = parser.parse_args()

    iniciar_servidor(args.host, args.puerto)
