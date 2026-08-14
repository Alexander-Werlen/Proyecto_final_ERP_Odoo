import json
import logging
import os
import shutil
import time
import uuid
from tempfile import NamedTemporaryFile

import requests


REMOTE_DIR = os.environ.get("REMOTE_DIR", "/app/remote")
BASE_DIR = os.environ.get("BASE_DIR", "/app/data/facturas")

HEALTH_FILE = os.path.join(BASE_DIR, ".health")
INCOMING = os.path.join(BASE_DIR, "incoming")
PROCESSING = os.path.join(BASE_DIR, "processing")
SUCCESS = os.path.join(BASE_DIR, "exitosas")
FAILED = os.path.join(BASE_DIR, "fallos")
RETRY_FILE = os.path.join(BASE_DIR, ".retry_queue.json")

ODOO_URL = os.environ["ODOO_URL"]
API_KEY = os.environ["ODOO_API_KEY"]
ENABLE_REMOTE_SYNC = os.environ.get("ENABLE_REMOTE_SYNC", "true").lower() == "true"

POLL_INTERVAL = float(os.environ.get("WATCHER_POLL_INTERVAL", "2"))
MAX_RETRIES = int(os.environ.get("WATCHER_MAX_RETRIES", "3"))
FILE_STABILITY_WAIT = float(os.environ.get("WATCHER_STABILITY_WAIT", "1"))
FILE_MIN_AGE = float(os.environ.get("WATCHER_MIN_AGE", "3"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("invoice-watcher")

retry_queue = {}


def ensure_dirs():
    for directory in (INCOMING, PROCESSING, SUCCESS, FAILED):
        os.makedirs(directory, exist_ok=True)


def is_stable_file(path):
    try:
        if time.time() - os.path.getmtime(path) < FILE_MIN_AGE:
            return False

        size_before = os.path.getsize(path)
        time.sleep(FILE_STABILITY_WAIT)
        size_after = os.path.getsize(path)
    except (FileNotFoundError, OSError):
        return False

    return size_before == size_after


def atomic_write_json(path, data):
    directory = os.path.dirname(path)
    with NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=directory) as temporary:
        json.dump(data, temporary, ensure_ascii=True)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_name = temporary.name
    os.replace(temporary_name, path)


def load_retry_queue():
    global retry_queue

    if not os.path.exists(RETRY_FILE):
        retry_queue = {}
        return

    try:
        with open(RETRY_FILE, encoding="utf-8") as retry_file:
            retry_queue = json.load(retry_file)
        log.info("Loaded retry queue (%s items)", len(retry_queue))
    except (OSError, ValueError):
        log.exception("Could not load retry queue; starting with an empty queue")
        retry_queue = {}


def save_retry_queue():
    atomic_write_json(RETRY_FILE, retry_queue)


def available_path(directory, filename):
    destination = os.path.join(directory, filename)
    if not os.path.exists(destination):
        return destination, filename

    unique_filename = f"{uuid.uuid4()}_{filename}"
    return os.path.join(directory, unique_filename), unique_filename


def call_odoo(filename, path, attempt, correlation_id):
    response = requests.post(
        ODOO_URL,
        json={
            "jsonrpc": "2.0",
            "method": "call",
            "params": {
                "api_key": API_KEY,
                "filename": filename,
                "path": path,
                "attempt": attempt,
                "correlation_id": correlation_id,
            },
        },
        timeout=10,
    )
    response.raise_for_status()
    payload = response.json()
    return payload.get("result", {})


def process_file(filename, path, attempt, correlation_id):
    log.info("[%s] processing %s (attempt %s)", correlation_id, filename, attempt)

    try:
        return call_odoo(filename, path, attempt, correlation_id)
    except Exception as error:
        log.exception("[%s] Odoo request failed", correlation_id)
        return {
            "status": "retry",
            "retry_after": 60,
            "reason": str(error),
        }


def move_to_result(path, directory, filename):
    destination, _ = available_path(directory, filename)
    shutil.move(path, destination)


def handle_result(filename, path, result, attempt, correlation_id):
    status = result.get("status")

    if status == "ok":
        move_to_result(path, SUCCESS, filename)
        retry_queue.pop(filename, None)
        save_retry_queue()
        log.info("[%s] success", correlation_id)
        return

    if status == "retry" and attempt < MAX_RETRIES:
        retry_after = max(0, int(result.get("retry_after", 60)))
        retry_queue[filename] = {
            "path": path,
            "attempt": attempt + 1,
            "correlation_id": correlation_id,
            "next_attempt_at": time.time() + retry_after,
        }
        save_retry_queue()
        log.warning(
            "[%s] retry scheduled in %ss (attempt %s)",
            correlation_id,
            retry_after,
            attempt + 1,
        )
        return

    if os.path.exists(path):
        move_to_result(path, FAILED, filename)
    retry_queue.pop(filename, None)
    save_retry_queue()
    log.error("[%s] failed permanently: %s", correlation_id, result.get("reason", status))


def process_retry_queue():
    now = time.time()

    for filename, data in list(retry_queue.items()):
        try:
            if now < data["next_attempt_at"]:
                continue

            path = data["path"]
            if not os.path.exists(path):
                log.error("[%s] retry file no longer exists: %s", data["correlation_id"], path)
                retry_queue.pop(filename, None)
                save_retry_queue()
                continue

            result = process_file(
                filename=filename,
                path=path,
                attempt=data["attempt"],
                correlation_id=data["correlation_id"],
            )
            handle_result(
                filename=filename,
                path=path,
                result=result,
                attempt=data["attempt"],
                correlation_id=data["correlation_id"],
            )
        except Exception:
            log.exception("Retry queue error for %s", filename)


def process_incoming():
    try:
        filenames = os.listdir(INCOMING)
    except OSError:
        log.exception("Could not list incoming directory")
        return

    for original_filename in filenames:
        if not original_filename.lower().endswith(".csv"):
            continue

        source = os.path.join(INCOMING, original_filename)
        if not os.path.isfile(source) or not is_stable_file(source):
            continue

        try:
            path, filename = available_path(PROCESSING, original_filename)
            shutil.move(source, path)
            correlation_id = str(uuid.uuid4())
            log.info("[%s] claimed %s", correlation_id, filename)

            result = process_file(
                filename=filename,
                path=path,
                attempt=1,
                correlation_id=correlation_id,
            )
            handle_result(
                filename=filename,
                path=path,
                result=result,
                attempt=1,
                correlation_id=correlation_id,
            )
        except Exception:
            log.exception("Incoming processing error for %s", original_filename)


def sync_remote():
    if not ENABLE_REMOTE_SYNC:
        return

    if not os.path.isdir(REMOTE_DIR):
        log.warning("REMOTE_DIR does not exist (%s)", REMOTE_DIR)
        return

    try:
        filenames = os.listdir(REMOTE_DIR)
    except OSError:
        log.exception("Could not list remote directory")
        return

    for original_filename in filenames:
        if not original_filename.lower().endswith(".csv"):
            continue

        source = os.path.join(REMOTE_DIR, original_filename)
        if not os.path.isfile(source) or not is_stable_file(source):
            continue

        try:
            destination, filename = available_path(INCOMING, original_filename)
            shutil.move(source, destination)
            log.info("Moved from remote to incoming: %s", filename)
        except Exception:
            log.exception("Remote sync error for %s", original_filename)


def update_health():
    with open(HEALTH_FILE, "w", encoding="utf-8") as health_file:
        health_file.write(str(time.time()))


def main():
    ensure_dirs()
    load_retry_queue()
    log.info("Watcher started, polling every %ss", POLL_INTERVAL)

    while True:
        sync_remote()
        process_retry_queue()
        process_incoming()
        update_health()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
