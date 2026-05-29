"""
web.py — Interfaz web para el sistema de archivos
==================================================
Servidor HTTP Flask que expone el sistema de archivos
como una página web accesible desde cualquier navegador.

Uso:
  python3 web.py

Acceder en:
  http://localhost:8080
  http://test.appscristianrojo.cl  (con Cloudflare)

Instalar dependencia:
  pip3 install flask
"""

from flask import Flask, request, jsonify, send_file, render_template_string
from pathlib import Path
import shutil, threading, os, io
from datetime import datetime

# ── Rutas ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path.home() / "servidor_archivos"
DIR_ENTRADA = BASE_DIR / "entrada"
DIR_PROC    = BASE_DIR / "procesados"
DIR_LOGS    = BASE_DIR / "logs"
ARCHIVO_LOG = DIR_LOGS / "registro.log"

for d in (DIR_ENTRADA, DIR_PROC, DIR_LOGS):
    d.mkdir(parents=True, exist_ok=True)

log_lock  = threading.Lock()
file_lock = threading.Lock()

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB máximo

# ── Log sincronizado ───────────────────────────────────────────────────────────
def registrar(op, detalle, origen="web"):
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"{marca} | {origen:15s} | {op:10s} | {detalle}\n"
    with log_lock:
        with open(ARCHIVO_LOG, "a", encoding="utf-8") as f:
            f.write(linea)

# ══════════════════════════════════════════════════════════════════════════════
# HTML DE LA PÁGINA (todo en un solo archivo)
# ══════════════════════════════════════════════════════════════════════════════
HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Sistema de Archivos — appscristianrojo.cl</title>
<style>
  :root {
    --bg: #0f1117; --panel: #1a1d2e; --card: #22263a;
    --accent: #4f8ef7; --accent2: #7c3aed; --green: #22c55e;
    --red: #ef4444; --yellow: #f59e0b; --text: #e2e8f0;
    --muted: #64748b; --border: #2d3148;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; min-height: 100vh; }

  /* ── Header ── */
  header { background: var(--panel); border-bottom: 1px solid var(--border); padding: 16px 32px; display: flex; align-items: center; gap: 12px; }
  header .logo { width: 36px; height: 36px; background: linear-gradient(135deg, var(--accent), var(--accent2)); border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 18px; }
  header h1 { font-size: 18px; font-weight: 600; }
  header span { font-size: 13px; color: var(--muted); margin-left: auto; }
  .dot { width: 8px; height: 8px; background: var(--green); border-radius: 50%; display: inline-block; margin-right: 6px; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }

  /* ── Layout ── */
  main { max-width: 1100px; margin: 0 auto; padding: 28px 24px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
  @media(max-width:768px){ main { grid-template-columns: 1fr; } }

  /* ── Cards ── */
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 20px; }
  .card h2 { font-size: 14px; font-weight: 600; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; margin-bottom: 16px; display: flex; align-items: center; gap: 8px; }
  .card h2 svg { opacity: .7; }
  .full { grid-column: 1 / -1; }

  /* ── Botones ── */
  .btn { display: inline-flex; align-items: center; gap: 6px; padding: 7px 14px; border-radius: 7px; font-size: 13px; font-weight: 500; cursor: pointer; border: none; transition: opacity .15s, transform .1s; }
  .btn:hover { opacity: .85; transform: translateY(-1px); }
  .btn:active { transform: translateY(0); }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-success { background: var(--green); color: #000; }
  .btn-danger  { background: #ef4444; color: #fff; }
  .btn-danger  { background: var(--red);   color: #fff; }
  .btn-ghost   { background: var(--border); color: var(--text); }
  .btn-sm { padding: 4px 10px; font-size: 12px; }

  /* ── Lista de archivos ── */
  #file-list { list-style: none; display: flex; flex-direction: column; gap: 8px; min-height: 60px; }
  #file-list li { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 10px 14px; display: flex; align-items: center; gap: 10px; }
  #file-list li .name { flex: 1; font-size: 14px; font-family: monospace; }
  #file-list li .actions { display: flex; gap: 6px; }
  .empty { color: var(--muted); font-size: 13px; text-align: center; padding: 20px; }

  /* ── Upload ── */
  .drop-zone { border: 2px dashed var(--border); border-radius: 10px; padding: 32px; text-align: center; cursor: pointer; transition: border-color .2s, background .2s; }
  .drop-zone:hover, .drop-zone.drag { border-color: var(--accent); background: rgba(79,142,247,.06); }
  .drop-zone p { color: var(--muted); font-size: 14px; margin-top: 8px; }
  #file-input { display: none; }

  /* ── Modal visor ── */
  .modal-bg { display: none; position: fixed; inset: 0; background: rgba(0,0,0,.7); z-index: 100; align-items: center; justify-content: center; }
  .modal-bg.open { display: flex; }
  .modal { background: var(--panel); border: 1px solid var(--border); border-radius: 14px; width: 90%; max-width: 700px; max-height: 80vh; display: flex; flex-direction: column; }
  .modal-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
  .modal-body { padding: 20px; overflow-y: auto; flex: 1; }
  .modal-body pre { font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; color: var(--text); font-family: 'Cascadia Code', 'Fira Code', monospace; }

  /* ── Logs ── */
  #log-content { font-size: 12px; font-family: monospace; line-height: 1.7; color: #94a3b8; max-height: 280px; overflow-y: auto; background: var(--panel); border-radius: 8px; padding: 14px; }
  #log-content .log-line { display: block; }
  #log-content .log-line:hover { background: rgba(255,255,255,.03); }

  /* ── Toast ── */
  #toast { position: fixed; bottom: 24px; right: 24px; background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 12px 18px; font-size: 14px; transform: translateY(80px); opacity: 0; transition: all .3s; z-index: 200; max-width: 320px; }
  #toast.show { transform: translateY(0); opacity: 1; }
  #toast.ok  { border-left: 3px solid var(--green); }
  #toast.err { border-left: 3px solid var(--red); }

  /* ── Tabs procesados ── */
  .tabs { display: flex; gap: 4px; margin-bottom: 14px; }
  .tab { padding: 6px 14px; border-radius: 6px; font-size: 13px; cursor: pointer; border: 1px solid var(--border); color: var(--muted); background: transparent; }
  .tab.active { background: var(--accent); color: #fff; border-color: var(--accent); }

  input[type=text] { background: var(--panel); border: 1px solid var(--border); border-radius: 7px; padding: 8px 12px; color: var(--text); font-size: 14px; width: 100%; outline: none; }
  input[type=text]:focus { border-color: var(--accent); }
</style>
</head>
<body>

<header>
  <div class="logo">📁</div>
  <h1>Sistema de Archivos Remoto</h1>
  <span><span class="dot"></span>appscristianrojo.cl</span>
</header>

<main>

  <!-- ── Archivos entrada ──────────────────────────────────── -->
  <div class="card">
    <h2>
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"/></svg>
      Carpeta entrada/
    </h2>
    <ul id="file-list"><li class="empty">Cargando...</li></ul>
    <div style="margin-top:12px">
      <button class="btn btn-ghost btn-sm" onclick="loadFiles()">↺ Actualizar</button>
    </div>
  </div>

  <!-- ── Subir archivo ─────────────────────────────────────── -->
  <div class="card">
    <h2>
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12"/></svg>
      Subir archivo
    </h2>
    <div class="drop-zone" id="drop-zone" onclick="document.getElementById('file-input').click()">
      <div style="font-size:32px">☁️</div>
      <p>Clic aquí o arrastra un archivo</p>
      <p style="font-size:12px; margin-top:4px">Máximo 50 MB</p>
    </div>
    <input type="file" id="file-input" onchange="uploadFile(this.files[0])">
    <div id="upload-progress" style="display:none; margin-top:12px">
      <div style="background:var(--border);border-radius:4px;height:6px;overflow:hidden">
        <div id="progress-bar" style="height:100%;background:var(--accent);width:0%;transition:width .3s"></div>
      </div>
      <p style="font-size:12px;color:var(--muted);margin-top:6px" id="progress-text">Subiendo...</p>
    </div>
  </div>

  <!-- ── Procesados ────────────────────────────────────────── -->
  <div class="card">
    <h2>
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 12l2 2 4-4M7.835 4.697a3.42 3.42 0 001.946-.806 3.42 3.42 0 014.438 0 3.42 3.42 0 001.946.806 3.42 3.42 0 013.138 3.138 3.42 3.42 0 00.806 1.946 3.42 3.42 0 010 4.438 3.42 3.42 0 00-.806 1.946 3.42 3.42 0 01-3.138 3.138 3.42 3.42 0 00-1.946.806 3.42 3.42 0 01-4.438 0 3.42 3.42 0 00-1.946-.806 3.42 3.42 0 01-3.138-3.138 3.42 3.42 0 00-.806-1.946 3.42 3.42 0 010-4.438 3.42 3.42 0 00.806-1.946 3.42 3.42 0 013.138-3.138z"/></svg>
      Carpeta procesados/
    </h2>
    <ul id="proc-list"><li class="empty">Cargando...</li></ul>
    <div style="margin-top:12px">
      <button class="btn btn-ghost btn-sm" onclick="loadProc()">↺ Actualizar</button>
    </div>
  </div>

  <!-- ── Logs ──────────────────────────────────────────────── -->
  <div class="card">
    <h2>
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
      Registro de operaciones
    </h2>
    <div id="log-content">Cargando logs...</div>
    <div style="margin-top:12px; display:flex; gap:8px">
      <button class="btn btn-ghost btn-sm" onclick="loadLogs()">↺ Actualizar</button>
      <button class="btn btn-ghost btn-sm" onclick="toggleAutoRefresh()" id="auto-btn">▶ Auto-refresh</button>
    </div>
  </div>

</main>

<!-- ── Modal visor de archivo ─────────────────────────────── -->
<div class="modal-bg" id="modal">
  <div class="modal">
    <div class="modal-header">
      <strong id="modal-title">archivo.txt</strong>
      <button class="btn btn-ghost btn-sm" onclick="closeModal()">✕ Cerrar</button>
    </div>
    <div class="modal-body">
      <pre id="modal-content"></pre>
    </div>
  </div>
</div>

<!-- ── Toast notificaciones ───────────────────────────────── -->
<div id="toast"></div>

<script>
let autoRefreshTimer = null;

// ── Toast ──────────────────────────────────────────────────
function toast(msg, type='ok') {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'show ' + type;
  clearTimeout(t._timer);
  t._timer = setTimeout(() => t.className = '', 3500);
}

// ── Cargar lista de archivos ───────────────────────────────
async function loadFiles() {
  const res = await fetch('/api/list?dir=entrada');
  const d = await res.json();
  renderList('file-list', d.files, 'entrada');
}

async function loadProc() {
  const res = await fetch('/api/list?dir=procesados');
  const d = await res.json();
  renderList('proc-list', d.files, 'procesados');
}

function renderList(listId, files, dir) {
  const ul = document.getElementById(listId);
  if (!files || files.length === 0) {
    ul.innerHTML = '<li class="empty">Carpeta vacía</li>';
    return;
  }
  ul.innerHTML = files.map(f => `
    <li>
      <span class="name">📄 ${f.name}</span>
      <span style="font-size:11px;color:var(--muted)">${f.size}</span>
      <div class="actions">
        <button class="btn btn-ghost btn-sm" onclick="readFile('${f.name}','${dir}')">👁 Ver</button>
        ${dir==='entrada' ? `<button class="btn btn-primary btn-sm" onclick="copyFile('${f.name}')">📋 Copiar</button>` : ''}
        <button class="btn btn-success btn-sm" onclick="downloadFile('${f.name}','${dir}')">⬇ Descargar</button>
        ${dir==='procesados' ? `<button class="btn btn-danger btn-sm" onclick="deleteFile('${f.name}')">🗑 Eliminar</button>` : ''}
      </div>
    </li>`).join('');
}

// ── Leer archivo ──────────────────────────────────────────
async function readFile(name, dir) {
  const res = await fetch(`/api/read?name=${encodeURIComponent(name)}&dir=${dir}`);
  const d = await res.json();
  if (d.ok) {
    document.getElementById('modal-title').textContent = name;
    document.getElementById('modal-content').textContent = d.content;
    document.getElementById('modal').classList.add('open');
  } else {
    toast('Error: ' + d.error, 'err');
  }
}

function closeModal() {
  document.getElementById('modal').classList.remove('open');
}

// ── Eliminar de procesados ────────────────────────────────
async function deleteFile(name) {
  if (!confirm(`¿Eliminar '${name}' de procesados/?`)) return;
  const res = await fetch('/api/delete', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name})
  });
  const d = await res.json();
  if (d.ok) { toast(`✓ '${name}' eliminado`); loadProc(); }
  else toast('Error: ' + d.error, 'err');
}
// ── Copiar a procesados ────────────────────────────────────
async function copyFile(name) {
  const res = await fetch('/api/copy', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({name})
  });
  const d = await res.json();
  if (d.ok) { toast(`✓ '${name}' copiado a procesados/`); loadProc(); }
  else toast('Error: ' + d.error, 'err');
}

// ── Descargar archivo ─────────────────────────────────────
function downloadFile(name, dir) {
  window.location = `/api/download?name=${encodeURIComponent(name)}&dir=${dir}`;
  registrar_log('DOWNLOAD', name);
}

// ── Subir archivo ─────────────────────────────────────────
async function uploadFile(file) {
  if (!file) return;
  const prog = document.getElementById('upload-progress');
  const bar  = document.getElementById('progress-bar');
  const txt  = document.getElementById('progress-text');
  prog.style.display = 'block';
  bar.style.width = '30%';
  txt.textContent = `Subiendo ${file.name} (${formatSize(file.size)})...`;

  const form = new FormData();
  form.append('file', file);
  try {
    bar.style.width = '70%';
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const d = await res.json();
    bar.style.width = '100%';
    if (d.ok) {
      toast(`✓ '${file.name}' subido correctamente`);
      loadFiles();
    } else {
      toast('Error: ' + d.error, 'err');
    }
  } catch(e) {
    toast('Error de red', 'err');
  }
  setTimeout(() => { prog.style.display = 'none'; bar.style.width = '0%'; }, 1500);
  document.getElementById('file-input').value = '';
}

// ── Logs ──────────────────────────────────────────────────
async function loadLogs() {
  const res = await fetch('/api/logs');
  const d = await res.json();
  const el = document.getElementById('log-content');
  if (!d.lines || d.lines.length === 0) {
    el.textContent = 'Sin registros aún.';
    return;
  }
  el.innerHTML = d.lines.slice(-50).reverse().map(l => {
    let color = '#94a3b8';   // gris por defecto (LIST, LOGS, READ)
    if (l.includes('| PROCESAR |') || l.includes('movido a procesados')) color = '#22c55e';   // verde
    if (l.includes('UPLOAD'))                                color = '#4f8ef7';   // azul
    if (l.includes('DOWNLOAD'))                              color = '#22c55e';   // verde
    if (l.includes('COPY'))                                  color = '#f59e0b';   // naranja
    if (l.includes('DELETE'))                                color = '#ef4444';   // rojo
    if (l.includes('ERROR'))                                 color = '#ff0000';   // rojo fuerte
    if (l.includes('START') || l.includes('DISCONNECT'))     color = '#f87171';   // rojo claro
    if (l.includes('CONNECT') && !l.includes('DISCONNECT'))  color = '#a78bfa';   // violeta
    return `<span class="log-line" style="color:${color}">${l}</span>`;
  }).join('<br>');
}

function toggleAutoRefresh() {
  const btn = document.getElementById('auto-btn');
  if (autoRefreshTimer) {
    clearInterval(autoRefreshTimer);
    autoRefreshTimer = null;
    btn.textContent = '▶ Auto-refresh';
  } else {
    autoRefreshTimer = setInterval(() => { loadLogs(); loadFiles(); loadProc(); }, 5000);
    btn.textContent = '⏸ Pausar';
    toast('Auto-refresh activado (5s)');
  }
}

// ── Drag & Drop ───────────────────────────────────────────
const dz = document.getElementById('drop-zone');
dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('drag'); });
dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
dz.addEventListener('drop', e => {
  e.preventDefault(); dz.classList.remove('drag');
  if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
});

// ── Modal cerrar con Escape ────────────────────────────────
document.addEventListener('keydown', e => { if (e.key==='Escape') closeModal(); });
document.getElementById('modal').addEventListener('click', e => {
  if (e.target === document.getElementById('modal')) closeModal();
});

// ── Helpers ───────────────────────────────────────────────
function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1048576) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/1048576).toFixed(1) + ' MB';
}

// ── Inicio ────────────────────────────────────────────────
loadFiles(); loadProc(); loadLogs();
</script>
</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
# RUTAS API
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/api/list")
def api_list():
    directorio = request.args.get("dir", "entrada")
    carpeta = DIR_ENTRADA if directorio == "entrada" else DIR_PROC
    archivos = []
    for f in sorted(carpeta.iterdir()):
        if f.is_file():
            size = f.stat().st_size
            if size < 1024:        size_str = f"{size} B"
            elif size < 1048576:   size_str = f"{size/1024:.1f} KB"
            else:                  size_str = f"{size/1048576:.1f} MB"
            archivos.append({"name": f.name, "size": size_str})
    registrar("LIST", f"{directorio}/ ({len(archivos)} archivos)")
    return jsonify({"ok": True, "files": archivos})

@app.route("/api/read")
def api_read():
    nombre    = request.args.get("name", "")
    directorio = request.args.get("dir", "entrada")
    carpeta   = DIR_ENTRADA if directorio == "entrada" else DIR_PROC
    ruta      = carpeta / nombre
    if not ruta.is_file():
        return jsonify({"ok": False, "error": "Archivo no encontrado"})
    with file_lock:
        contenido = ruta.read_text(encoding="utf-8", errors="replace")
    registrar("READ", f"{nombre} ({len(contenido)} chars)")
    return jsonify({"ok": True, "content": contenido})

@app.route("/api/copy", methods=["POST"])
def api_copy():
    nombre  = request.json.get("name", "")
    origen  = DIR_ENTRADA / nombre
    destino = DIR_PROC / nombre
    if not origen.is_file():
        return jsonify({"ok": False, "error": "Archivo no encontrado en entrada/"})
    with file_lock:
        shutil.copy2(str(origen), str(destino))
    registrar("COPY", f"{nombre} → procesados/")
    return jsonify({"ok": True})

@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No se recibió archivo"})
    archivo = request.files["file"]
    if not archivo.filename:
        return jsonify({"ok": False, "error": "Nombre de archivo vacío"})
    ruta = DIR_ENTRADA / archivo.filename
    with file_lock:
        archivo.save(str(ruta))
    registrar("UPLOAD", f"{archivo.filename} ({ruta.stat().st_size} bytes)")
    return jsonify({"ok": True, "name": archivo.filename})

@app.route("/api/download")
def api_download():
    nombre     = request.args.get("name", "")
    directorio = request.args.get("dir", "entrada")
    carpeta    = DIR_ENTRADA if directorio == "entrada" else DIR_PROC
    ruta       = carpeta / nombre
    if not ruta.is_file():
        return jsonify({"ok": False, "error": "Archivo no encontrado"}), 404
    registrar("DOWNLOAD", f"{nombre} ({ruta.stat().st_size} bytes)")
    return send_file(str(ruta), as_attachment=True, download_name=nombre)

@app.route("/api/delete", methods=["POST"])
def api_delete():
    nombre = request.json.get("name", "")
    ruta   = DIR_PROC / nombre
    if not ruta.is_file():
        return jsonify({"ok": False, "error": "Archivo no encontrado en procesados/"})
    with file_lock:
        ruta.unlink()
    registrar("DELETE", f"{nombre} eliminado de procesados/")
    return jsonify({"ok": True})

@app.route("/api/logs")
def api_logs():
    if not ARCHIVO_LOG.exists():
        return jsonify({"ok": True, "lines": []})
    with log_lock:
        lineas = ARCHIVO_LOG.read_text(encoding="utf-8").splitlines()
    return jsonify({"ok": True, "lines": lineas})


# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("=" * 50)
    print("  Sistema de Archivos — Interfaz Web")
    print("  http://0.0.0.0:8080")
    print("=" * 50)
    app.run(host="0.0.0.0", port=8080, debug=False, threaded=True)
