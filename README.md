# Sistema de Archivos Remoto — Multipropósito

Sistema cliente-servidor en Python con multihilos, sincronización y una interfaz web. Permite gestionar archivos remotamente desde la terminal o desde cualquier navegador.

---

## ¿Qué hace el sistema?

- Un **servidor TCP** recibe conexiones de múltiples clientes simultáneamente (hasta 10 en paralelo).
- Un **cliente de terminal** permite subir, descargar, leer y copiar archivos remotamente.
- Un **demonio** monitorea la carpeta `entrada/` cada 10 segundos y mueve automáticamente los archivos nuevos a `procesados/`.
- Una **interfaz web** accesible desde cualquier navegador muestra el estado del sistema en tiempo real.
- Todo queda registrado en `logs/registro.log` con timestamp y acceso sincronizado.

---

## Estructura de carpetas (en el servidor)

```
~/servidor_archivos/
├── entrada/       ← archivos subidos por clientes o por la web
├── procesados/    ← archivos procesados por el demonio o copiados manualmente
└── logs/
    └── registro.log  ← historial de operaciones
```

---

## Requisitos

- Python 3.8 o superior
- Flask (`pip install flask`)
- Sistema operativo Linux (servidor) / Windows o Linux (cliente)

---

## Cómo ejecutar

### 1. Preparar el entorno (solo la primera vez)

```bash
bash setup.sh
```

Crea las carpetas y archivos de prueba en `~/servidor_archivos/`.

### 2. Iniciar el servidor TCP

```bash
python3 servidor.py
# Puerto por defecto: 9000
# Para otro puerto: python3 servidor.py --puerto 8000
```

### 3. Iniciar el demonio

```bash
python3 demonio.py
# Con daemonización real (Linux): python3 demonio.py --daemon
```

### 4. Iniciar la interfaz web

```bash
python3 web.py
# Acceder en: http://localhost:5000
```

### 5. Conectar el cliente

```bash
# Local
python3 cliente.py

# Remoto por dominio
python3 cliente.py --host test.appscristianrojo.cl --puerto 9000
```

---

## Menú del cliente

| Opción | Acción |
|--------|--------|
| 1 | Listar archivos en `entrada/` |
| 2 | Leer contenido de un archivo |
| 3 | Copiar archivo a `procesados/` |
| 4 | Subir archivo desde tu PC al servidor |
| 5 | Descargar archivo del servidor a tu PC |
| 6 | Ver logs del servidor |
| 7 | Listar archivos en `procesados/` |
| 0 | Salir |

---

## Interfaz web

Disponible en **https://web.appscristianrojo.cl**

- Ver archivos en `entrada/` y `procesados/`
- Descargar y eliminar archivos de `procesados/`
- Ver el registro de operaciones con colores en tiempo real

---

## Despliegue permanente (Ubuntu con systemd)

Los tres servicios están configurados para arrancar automáticamente:

```bash
# Ver estado de todos los servicios
sudo systemctl status servidor-archivos web-archivos demonio-archivos cloudflared

# Reiniciar un servicio
sudo systemctl restart servidor-archivos
```

| Servicio | Descripción |
|----------|-------------|
| `servidor-archivos` | Servidor TCP en puerto 9000 |
| `web-archivos` | Interfaz web Flask en puerto 5000 |
| `demonio-archivos` | Monitor automático de `entrada/` |
| `cloudflared` | Tunnel hacia `web.appscristianrojo.cl` |

---

## Sincronización y concurrencia

| Mecanismo | Uso |
|-----------|-----|
| `threading.Thread` | Un hilo por cliente conectado |
| `threading.Semaphore(10)` | Límite de 10 clientes simultáneos |
| `threading.Lock` (file_lock) | Protege lectura/escritura/copia de archivos |
| `threading.Lock` (log_lock) | Protege escritura en `registro.log` |

El demonio usa un `set` protegido por `file_lock` para evitar procesar el mismo archivo dos veces si dos hilos lo detectan al mismo tiempo.

---

## Dominio y acceso externo

| Subdominio | Uso | Puerto |
|------------|-----|--------|
| `web.appscristianrojo.cl` | Interfaz web (Cloudflare Tunnel) | 443 (HTTPS) |
