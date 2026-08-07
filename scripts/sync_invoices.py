import os
import sys
import time
import uuid
import shutil
import signal
import logging
from pathlib import Path

# ========================
# Configuración
# ========================

# Ruta base del repo en producción
REPO_DIR = Path("/dir_path_change_me")
ENV_FILE = REPO_DIR / ".env"
LOCAL_DIR = REPO_DIR / "remote-facturas"

# Backoff en segundos
INITIAL_BACKOFF = 5
MAX_BACKOFF = 60

# Verificación de estabilidad del archivo remoto
STABILITY_WAIT = 1        # segundos entre dos checks de tamaño
MIN_AGE = 3               # segundos desde última modificación

SMB_CONNECTION_TIMEOUT = 10

# ========================
# Logging
# ========================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("sync-invoices")

# ========================
# Control de señales para cierre graceful
# ========================

_shutdown_requested = False

def _handle_sigterm(signum, frame):
    global _shutdown_requested
    log.info("Señal SIGTERM recibida. Cerrando gracefulmente...")
    _shutdown_requested = True

signal.signal(signal.SIGTERM, _handle_sigterm)
signal.signal(signal.SIGINT, _handle_sigterm)

# ========================
# Helpers
# ========================

def load_env(path):
    """Carga variables clave=valor desde un archivo .env simple."""
    env = {}
    if not path.exists():
        log.error("No se encontró el archivo .env en %s", path)
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env

def ensure_local_dir():
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

def is_stable_file(smbclient, remote_path):
    """
    Verifica que el archivo remoto sea estable:
    1. Edad mínima desde última modificación.
    2. Tamaño constante durante STABILITY_WAIT segundos.
    """
    try:
        stat1 = smbclient.stat(remote_path)
    except Exception as e:
        log.warning("No se puede stat el archivo remoto %s: %s", remote_path, e)
        return False

    age = time.time() - stat1.st_mtime
    if age < MIN_AGE:
        return False

    size1 = stat1.st_size
    time.sleep(STABILITY_WAIT)

    try:
        stat2 = smbclient.stat(remote_path)
    except Exception as e:
        log.warning("No se puede re-stat el archivo remoto %s: %s", remote_path, e)
        return False

    size2 = stat2.st_size
    return size1 == size2

def atomic_move(src: Path, dst: Path):
    """Mueve un archivo de forma atómica usando os.replace."""
    os.replace(str(src), str(dst))

# ========================
# SMB
# ========================

def get_smb_config(env):
    host = env.get("SMB_HOST", "")
    port = int(env.get("SMB_PORT", "445"))
    user = env.get("SMB_USER", "")
    password = env.get("SMB_PASSWORD", "")
    domain = env.get("SMB_DOMAIN", "WORKGROUP")
    share = env.get("SMB_SHARE", "")
    path = env.get("SMB_PATH", "")

    if not host or not share:
        log.critical("Faltan variables SMB_HOST o SMB_SHARE en .env")
        sys.exit(1)

    # Normalizar barras en el path interno del share
    if path:
        path = path.replace("/", "\\")

    # smbprotocol recibe el dominio como parte del username
    if domain and domain.upper() != "WORKGROUP":
        username = f"{domain}\\{user}"
    else:
        username = user

    return host, port, username, password, share, path

def build_remote_path(host, share, smb_path, fname=""):
    r"""Construye una ruta UNC tipo \\host\share\path\fname."""
    parts = [f"\\\\{host}", share]
    if smb_path:
        parts.append(smb_path)
    if fname:
        parts.append(fname)
    return "\\".join(parts)

def sync_cycle(smbclient, host, port, username, password, share, smb_path):
    remote_base = build_remote_path(host, share, smb_path)

    try:
        smbclient.register_session(
            host,
            username=username,
            password=password,
            port=port,
            connection_timeout=SMB_CONNECTION_TIMEOUT,
        )
    except Exception as e:
        log.warning("Error registrando sesión SMB con %s:%s: %s", host, port, e)
        return False

    try:
        try:
            entries = smbclient.scandir(remote_base)
        except Exception as e:
            log.warning("Error listando share remoto %s: %s", remote_base, e)
            return False

        csv_files = []
        for entry in entries:
            if not entry.name.lower().endswith(".csv"):
                continue
            # Filtrar directorios
            try:
                if entry.is_dir():
                    continue
            except Exception:
                pass
            csv_files.append(entry.name)

        if not csv_files:
            return True

        for fname in csv_files:
            if _shutdown_requested:
                log.info("Shutdown solicitado. Abortando ciclo de sincronización.")
                return True

            remote_path = build_remote_path(host, share, smb_path, fname)
            local_path = LOCAL_DIR / fname

            try:
                # Si ya existe localmente, renombramos para evitar colisión
                if local_path.exists():
                    new_name = f"{uuid.uuid4()}_{fname}"
                    local_path = LOCAL_DIR / new_name
                    log.info("Archivo %s ya existe localmente, renombrado a %s", fname, new_name)

                log.info("Verificando estabilidad de %s", fname)
                if not is_stable_file(smbclient, remote_path):
                    log.info("Archivo %s aún inestable, se omitirá en este ciclo", fname)
                    continue

                # Descarga atómica a archivo temporal
                tmp_path = LOCAL_DIR / f".{fname}.tmp"
                log.info("Descargando %s → %s", fname, tmp_path)
                with smbclient.open_file(remote_path, mode="rb") as remote_fd:
                    with open(tmp_path, "wb") as local_fd:
                        shutil.copyfileobj(remote_fd, local_fd)

                # Verificar que la descarga local tenga tamaño > 0
                if tmp_path.stat().st_size == 0:
                    log.error("Descarga de %s resultó vacía. Se elimina temporal y se reintentará.", fname)
                    tmp_path.unlink()
                    continue

                # Commit atómico
                atomic_move(tmp_path, local_path)

                log.info("Eliminando archivo remoto %s", fname)
                smbclient.remove(remote_path)

                log.info("Sincronizado exitosamente: %s → %s", fname, local_path)

            except Exception:
                log.exception("Error procesando archivo remoto %s", fname)
                # Limpieza parcial
                if local_path.exists() and str(local_path).endswith(f"_{fname}"):
                    try:
                        local_path.unlink()
                    except OSError:
                        pass
                tmp_path = LOCAL_DIR / f".{fname}.tmp"
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                continue

        return True

    finally:
        try:
            smbclient.delete_session(host)
        except Exception:
            pass

# ========================
# Main loop
# ========================

def main():
    try:
        import smbclient
    except ImportError:
        log.critical("La librería 'smbprotocol' no está instalada. "
                     "Ejecutá: pip install smbprotocol")
        sys.exit(1)

    ensure_local_dir()
    env = load_env(ENV_FILE)
    host, port, username, password, share, smb_path = get_smb_config(env)

    log.info("Iniciando sincronización SMB: %s/%s/%s → %s", host, share, smb_path, LOCAL_DIR)

    backoff = INITIAL_BACKOFF

    while not _shutdown_requested:
        try:
            ok = sync_cycle(smbclient, host, port, username, password, share, smb_path)
            if ok:
                if backoff != INITIAL_BACKOFF:
                    log.info("Conexión restablecida. Backoff reseteado.")
                backoff = INITIAL_BACKOFF
            else:
                log.warning("No se pudo sincronizar. Reintentando en %ss", backoff)
        except Exception as e:
            log.error("Error inesperado en ciclo de sincronización: %s", e)
            log.warning("Reintentando en %ss", backoff)

        # Esperar con posibilidad de interrupción por señal
        for _ in range(backoff):
            if _shutdown_requested:
                break
            time.sleep(1)

        backoff = min(backoff * 2, MAX_BACKOFF)

    log.info("Servicio de sincronización finalizado.")

# ========================
# Entrypoint
# ========================

if __name__ == "__main__":
    main()
