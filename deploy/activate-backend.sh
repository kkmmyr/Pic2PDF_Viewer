#!/bin/bash
# Linux productionでbackend source・common・venvを一体の世代として安全にactive化する。
set -Eeuo pipefail

APP_ROOT=${PIC2PDF_APP_ROOT:-/opt/pic2pdf-viewer}
ACTIVE_BACKEND="${APP_ROOT}/backend"
ACTIVE_COMMON="${APP_ROOT}/common/llm"
ACTIVE_ENV="${ACTIVE_BACKEND}/.venv"
UV_BIN=${PIC2PDF_UV_BIN:-/home/amashio/.local/bin/uv}
PYTHON_BIN=${PIC2PDF_PYTHON_BIN:-/usr/bin/python3.12}
SERVICE_NAME=${PIC2PDF_SERVICE_NAME:-pic2pdf-viewer}
BACKUP_LOCK="${APP_ROOT}/.backup.lock"

LABEL=${1:-$(date +%Y-%m-%d_%H%M%S)_pre-deploy}
NEXT_BACKEND=${2:-}
NEXT_COMMON=${3:-}
WORKSPACE_ROOT=${4:-}
NEXT_ENV="${NEXT_BACKEND}/.venv"
GENERATION="$(date +%Y%m%d%H%M%S)-$$"

APP_PID=""
APP_FROZEN=0
PREVIOUS_BACKEND=""
PREVIOUS_COMMON=""
BACKEND_SWITCHED=0
COMMON_SWITCHED=0

log() {
  printf '%s\n' "$*"
}

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  return 1
}

resume_app() {
  if [ "$APP_FROZEN" -eq 1 ]; then
    if kill -0 "$APP_PID" 2>/dev/null; then
      kill -CONT "$APP_PID" || true
      log "Resumed ${SERVICE_NAME} process (PID ${APP_PID})."
    fi
    APP_FROZEN=0
  fi
}

set_active_link() {
  link_path=$1
  target=$2
  temporary_link="${link_path}.next-$$"
  if [ -e "$temporary_link" ] || [ -L "$temporary_link" ]; then
    fail "temporary active link already exists: ${temporary_link}"
    return
  fi
  ln -s "$target" "$temporary_link"
  mv -Tf "$temporary_link" "$link_path"
}

remove_temporary_links() {
  for link_path in "$ACTIVE_BACKEND" "$ACTIVE_COMMON"; do
    temporary_link="${link_path}.next-$$"
    if [ -L "$temporary_link" ]; then
      unlink "$temporary_link"
    fi
  done
}

restore_previous_release() {
  restore_failed=0
  if [ "$BACKEND_SWITCHED" -eq 1 ]; then
    if [ -d "$PREVIOUS_BACKEND" ] && set_active_link "$ACTIVE_BACKEND" "$PREVIOUS_BACKEND"; then
      BACKEND_SWITCHED=0
    else
      printf 'ERROR: failed to restore previous backend: %s\n' "$PREVIOUS_BACKEND" >&2
      restore_failed=1
    fi
  fi
  if [ "$COMMON_SWITCHED" -eq 1 ]; then
    if [ -n "$PREVIOUS_COMMON" ]; then
      if [ -d "$PREVIOUS_COMMON" ] && set_active_link "$ACTIVE_COMMON" "$PREVIOUS_COMMON"; then
        COMMON_SWITCHED=0
      else
        printf 'ERROR: failed to restore previous common package: %s\n' "$PREVIOUS_COMMON" >&2
        restore_failed=1
      fi
    elif [ -L "$ACTIVE_COMMON" ]; then
      unlink "$ACTIVE_COMMON"
      COMMON_SWITCHED=0
    elif [ ! -e "$ACTIVE_COMMON" ]; then
      COMMON_SWITCHED=0
    else
      printf 'ERROR: active common path cannot be removed safely: %s\n' "$ACTIVE_COMMON" >&2
      restore_failed=1
    fi
  fi
  return "$restore_failed"
}

cleanup() {
  status=$?
  trap - EXIT
  set +e
  remove_temporary_links
  rollback_needed=0
  if [ "$BACKEND_SWITCHED" -eq 1 ] || [ "$COMMON_SWITCHED" -eq 1 ]; then
    rollback_needed=1
    log "Interrupted activation; restoring the previous backend release."
    restore_previous_release
  fi
  resume_app
  if [ "$rollback_needed" -eq 1 ]; then
    sudo systemctl restart "$SERVICE_NAME"
  fi
  exit "$status"
}

assert_unit_inactive() {
  unit=$1
  state=$(systemctl is-active "$unit" 2>/dev/null || true)
  case "$state" in
    active|activating|deactivating)
      fail "${unit} is ${state}; retry after it becomes inactive."
      ;;
  esac
}

assert_no_appledouble_files() {
  contaminated_path=$(find \
    "$NEXT_BACKEND" \
    "$NEXT_COMMON" \
    "$WORKSPACE_ROOT" \
    -type f -name '._*' -print -quit)
  if [ -n "$contaminated_path" ]; then
    fail "AppleDouble metadata is not allowed in staged release: ${contaminated_path}"
  fi
}

assert_no_novel_writers() {
  (
    cd "$ACTIVE_BACKEND"
    "${ACTIVE_ENV}/bin/python" - <<'PY'
import sqlite3
from pathlib import Path

import config

path = Path(config.NOVEL_DB_PATH)
if not path.is_file():
    raise SystemExit(f"novel database not found: {path}")

connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=30.0)
try:
    tables = {
        str(row[0])
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    required = {"rebuild_jobs", "ocr_runs"}
    missing = sorted(required - tables)
    if missing:
        raise SystemExit(f"novel writer tables are missing: {', '.join(missing)}")
    rebuild_count = int(
        connection.execute(
            "SELECT COUNT(*) FROM rebuild_jobs WHERE state IN ('queued', 'running')"
        ).fetchone()[0]
    )
    ocr_count = int(
        connection.execute("SELECT COUNT(*) FROM ocr_runs WHERE state='running'").fetchone()[0]
    )
finally:
    connection.close()

print(f"Novel writer check: rebuild_jobs={rebuild_count}, ocr_runs={ocr_count}")
if rebuild_count or ocr_count:
    raise SystemExit("queued or running Novel writers must reach zero before deployment")
PY
  )
}

freeze_app() {
  APP_PID=$(systemctl show "$SERVICE_NAME" --property MainPID --value)
  if ! [[ "$APP_PID" =~ ^[0-9]+$ ]] || [ "$APP_PID" -le 1 ]; then
    fail "could not resolve a running ${SERVICE_NAME} MainPID"
    return
  fi
  kill -STOP "$APP_PID"
  APP_FROZEN=1
  state=$(ps -o stat= -p "$APP_PID" | tr -d ' ')
  case "$state" in
    *T*) log "Paused ${SERVICE_NAME} process (PID ${APP_PID}) for a consistent operation." ;;
    *) fail "${SERVICE_NAME} process did not enter a stopped state" ;;
  esac
}

smoke_next_release() {
  cd "$NEXT_BACKEND"
  PIC2PDF_EXPECTED_APP_ROOT="$APP_ROOT" \
    PIC2PDF_EXPECTED_BACKEND="$NEXT_BACKEND" \
    PIC2PDF_EXPECTED_COMMON="$NEXT_COMMON" \
    "${NEXT_ENV}/bin/python" - <<'PY'
import os
import sqlite3
from importlib.metadata import version
from pathlib import Path

import config
import lancedb
import local_llm
import main
from services.novel_db.page_fts import PAGE_FTS_INDEX_CONFIG, search_page_fts
from services.novel_db.search_scope import Scope

lance_version = version("lancedb")
parts = tuple(int(part) for part in lance_version.split(".")[:2])
if parts != (0, 34):
    raise SystemExit(f"unexpected LanceDB version: {lance_version}")

expected_common = Path(os.environ["PIC2PDF_EXPECTED_COMMON"]).resolve()
common_file = Path(local_llm.__file__).resolve()
if not common_file.is_relative_to(expected_common):
    raise SystemExit(f"qwen-common is not loaded from the staged generation: {common_file}")
app_root = Path(os.environ["PIC2PDF_EXPECTED_APP_ROOT"]).resolve()
expected_backend = Path(os.environ["PIC2PDF_EXPECTED_BACKEND"]).resolve()
lance_path = Path(config.NOVEL_DB_LANCE_PATH).resolve()
try:
    lance_relative = lance_path.relative_to(app_root)
except ValueError:
    lance_relative = None
if lance_path.is_relative_to(expected_backend) or (
    lance_relative is not None
    and lance_relative.parts
    and (
        lance_relative.parts[0] == "backend"
        or lance_relative.parts[0].startswith("backend-")
    )
):
    raise SystemExit(f"LanceDB path is scoped to a backend release: {lance_path}")
if PAGE_FTS_INDEX_CONFIG.get("base_tokenizer") != "icu":
    raise SystemExit("page FTS ICU configuration could not be imported")
if main.app is None:
    raise SystemExit("FastAPI application import failed")

novel_db = Path(config.NOVEL_DB_PATH)
connection = sqlite3.connect(f"file:{novel_db.as_posix()}?mode=ro", uri=True, timeout=30.0)
try:
    has_fts = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='pages_fts'"
    ).fetchone()
    if has_fts is None:
        raise SystemExit("existing pages_fts table is missing")
    connection.execute(
        "SELECT rowid FROM pages_fts WHERE pages_fts MATCH ? LIMIT 1",
        ('"pic2pdf_deploy_smoke_no_match"',),
    ).fetchall()
    page_icu_status = "not-required"
    if config.NOVEL_DB_LEXICAL_BACKEND in {"shadow", "lance_icu"}:
        if not lance_path.is_dir():
            raise SystemExit(f"configured LanceDB directory is missing: {lance_path}")
        connection.execute("PRAGMA query_only = ON")
        probe = search_page_fts(
            connection,
            "zzpic2pdfdeploysmokeqzjx",
            Scope("all"),
            top=1,
        )
        if probe:
            raise SystemExit("page ICU no-match smoke unexpectedly returned a row")
        page_icu_status = "verified"
finally:
    connection.close()

print(
    "Release smoke passed: "
    f"lancedb={getattr(lancedb, '__version__', lance_version)}, "
    f"qwen_common={common_file}, lexical={config.NOVEL_DB_LEXICAL_BACKEND}, "
    f"page_icu={page_icu_status}, lance_path={lance_path}"
)
PY
}

install_rollback_compatible_migrations() {
  source_dir="${NEXT_BACKEND}/alembic/versions"
  target_dir="${ACTIVE_BACKEND}/alembic/versions"
  if [ ! -d "$source_dir" ] || [ ! -d "$target_dir" ]; then
    fail "Alembic versions directory is missing"
    return
  fi
  copied=0
  while IFS= read -r -d '' migration; do
    migration_name=$(basename "$migration")
    target="${target_dir}/${migration_name}"
    if [ ! -e "$target" ]; then
      if [ "$migration_name" != "0014_novel_search_index_state.py" ]; then
        fail "migration is not approved for backward-compatible rollout: ${migration_name}"
        return
      fi
      cp -p "$migration" "$target"
      copied=$((copied + 1))
      log "Installed rollback-compatible migration: ${migration_name}"
    elif ! cmp -s "$migration" "$target"; then
      fail "migration differs between active and staged releases: ${migration_name}"
      return
    fi
  done < <(find "$source_dir" -maxdepth 1 -type f -name '*.py' -print0)
  log "Rollback migration compatibility check passed; copied=${copied}."
}

upgrade_and_verify_schema() {
  cd "$ACTIVE_BACKEND"
  "${ACTIVE_ENV}/bin/python" - <<'PY'
import sqlite3
from pathlib import Path

import config
from alembic.config import Config
from alembic.script import ScriptDirectory
from services.novel_db.migrations import upgrade_head

alembic_ini = Path("alembic.ini").resolve()
alembic_config = Config(str(alembic_ini))
expected_revision = ScriptDirectory.from_config(alembic_config).get_current_head()
upgrade_head()

database = Path(config.NOVEL_DB_PATH)
connection = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=30.0)
try:
    actual_revision = str(connection.execute("SELECT version_num FROM alembic_version").fetchone()[0])
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    page_state = connection.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name='novel_search_index_state'"
    ).fetchone()
finally:
    connection.close()

if actual_revision != expected_revision:
    raise SystemExit(
        f"Alembic revision mismatch: expected={expected_revision}, actual={actual_revision}"
    )
if integrity != "ok":
    raise SystemExit(f"novel.db integrity check failed after migration: {integrity}")
if page_state is None:
    raise SystemExit("novel_search_index_state table is missing after migration")
print(f"Schema migration passed: revision={actual_revision}, integrity={integrity}")
PY
}

capture_previous_release() {
  if [ -L "$ACTIVE_BACKEND" ]; then
    PREVIOUS_BACKEND=$(readlink -f "$ACTIVE_BACKEND")
  elif [ -d "$ACTIVE_BACKEND" ]; then
    PREVIOUS_BACKEND="${APP_ROOT}/backend-pre-release-${GENERATION}"
    if [ -e "$PREVIOUS_BACKEND" ] || [ -L "$PREVIOUS_BACKEND" ]; then
      fail "previous backend retention path already exists: ${PREVIOUS_BACKEND}"
      return
    fi
    mv "$ACTIVE_BACKEND" "$PREVIOUS_BACKEND"
  else
    fail "active backend is neither a symlink nor a directory: ${ACTIVE_BACKEND}"
    return
  fi
  if [ ! -d "$PREVIOUS_BACKEND" ]; then
    fail "previous backend target is not a directory: ${PREVIOUS_BACKEND}"
    return
  fi
  BACKEND_SWITCHED=1

  if [ -L "$ACTIVE_COMMON" ]; then
    PREVIOUS_COMMON=$(readlink -f "$ACTIVE_COMMON")
  elif [ -d "$ACTIVE_COMMON" ]; then
    PREVIOUS_COMMON="${APP_ROOT}/common/llm-pre-release-${GENERATION}"
    if [ -e "$PREVIOUS_COMMON" ] || [ -L "$PREVIOUS_COMMON" ]; then
      fail "previous common retention path already exists: ${PREVIOUS_COMMON}"
      return
    fi
    mv "$ACTIVE_COMMON" "$PREVIOUS_COMMON"
  elif [ -e "$ACTIVE_COMMON" ]; then
    fail "active common path is not a directory or symlink: ${ACTIVE_COMMON}"
    return
  fi
  COMMON_SWITCHED=1
}

probe_service() {
  if ! sudo systemctl restart "$SERVICE_NAME"; then
    return 1
  fi
  for attempt in $(seq 1 30); do
    if systemctl is-active --quiet "$SERVICE_NAME" \
      && curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8091/ >/dev/null \
      && curl --fail --silent --show-error --max-time 15 http://127.0.0.1:8091/api/novel_db/books >/dev/null; then
      log "Service and HTTP probes passed on attempt ${attempt}."
      return 0
    fi
    sleep 1
  done
  return 1
}

rollback_release() {
  log "Activation failed; restoring previous backend release: ${PREVIOUS_BACKEND}"
  if ! restore_previous_release; then
    fail "release symlink rollback failed; inspect ${SERVICE_NAME} immediately"
    return
  fi
  if ! probe_service; then
    fail "rollback restart or HTTP probe failed; inspect ${SERVICE_NAME} immediately"
    return
  fi
  log "Rollback completed. Failed generation retained for diagnosis: ${NEXT_BACKEND}"
}

trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if ! [[ "$LABEL" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
  fail "backup label contains unsupported characters: ${LABEL}"
fi
case "$NEXT_BACKEND" in
  "${APP_ROOT}"/backend-*) ;;
  *) fail "staged backend must be an immediate generation under ${APP_ROOT}" ;;
esac
case "$NEXT_COMMON" in
  "${APP_ROOT}"/common/llm-*) ;;
  *) fail "staged common package must be a versioned path under ${APP_ROOT}/common" ;;
esac
case "$WORKSPACE_ROOT" in
  "${APP_ROOT}"/.deploy-workspace-*) ;;
  *) fail "staged workspace must be a versioned path under ${APP_ROOT}" ;;
esac

for path in \
  "$APP_ROOT/pyproject.toml" \
  "$APP_ROOT/uv.lock" \
  "$NEXT_BACKEND/pyproject.toml" \
  "$NEXT_COMMON/pyproject.toml" \
  "$WORKSPACE_ROOT/pyproject.toml" \
  "$WORKSPACE_ROOT/uv.lock" \
  "$UV_BIN" \
  "$PYTHON_BIN" \
  "$ACTIVE_ENV/bin/python"; do
  if [ ! -e "$path" ]; then
    fail "required deployment input is missing: ${path}"
  fi
done
if [ "$(readlink -f "$WORKSPACE_ROOT/backend")" != "$(readlink -f "$NEXT_BACKEND")" ]; then
  fail "staged workspace backend does not resolve to the requested generation"
fi
if [ "$(readlink -f "$WORKSPACE_ROOT/common/llm")" != "$(readlink -f "$NEXT_COMMON")" ]; then
  fail "staged workspace common package does not resolve to the requested generation"
fi
if [ -e "$NEXT_ENV" ] || [ -L "$NEXT_ENV" ]; then
  fail "new environment path already exists: ${NEXT_ENV}"
fi
assert_no_appledouble_files
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  fail "${SERVICE_NAME} must be active before deployment"
fi

assert_unit_inactive backup-meta.service
assert_unit_inactive backup-restore-test.service
assert_no_novel_writers

freeze_app
assert_unit_inactive backup-meta.service
assert_unit_inactive backup-restore-test.service
assert_no_novel_writers

exec 9>"$BACKUP_LOCK"
if ! flock -n 9; then
  fail "another database backup or restore check holds ${BACKUP_LOCK}"
fi

log "Creating and restoring verified pre-deploy backup: ${LABEL}"
cd "$ACTIVE_BACKEND"
"${ACTIVE_ENV}/bin/python" -m tools.server_backup backup --label "$LABEL"
"${ACTIVE_ENV}/bin/python" -m tools.server_backup verify-latest
flock -u 9
exec 9>&-
resume_app

log "Building locked backend release: ${NEXT_BACKEND}"
cd "$WORKSPACE_ROOT"
UV_PROJECT_ENVIRONMENT="$NEXT_ENV" "$UV_BIN" sync \
  --locked \
  --package pic2pdf-viewer-backend \
  --no-dev \
  --python "$PYTHON_BIN"

smoke_next_release
assert_no_novel_writers

freeze_app
assert_unit_inactive backup-meta.service
assert_unit_inactive backup-restore-test.service
assert_no_novel_writers
install_rollback_compatible_migrations
upgrade_and_verify_schema

capture_previous_release
set_active_link "$ACTIVE_COMMON" "$NEXT_COMMON"
set_active_link "$ACTIVE_BACKEND" "$NEXT_BACKEND"
log "Activated backend release: ${NEXT_BACKEND}"
resume_app

if ! probe_service; then
  rollback_release
  exit 1
fi

BACKEND_SWITCHED=0
COMMON_SWITCHED=0
sudo systemctl status "$SERVICE_NAME"
log "Backend activation complete. Previous release retained: ${PREVIOUS_BACKEND}"
