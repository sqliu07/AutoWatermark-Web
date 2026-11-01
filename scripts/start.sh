#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${VENV_DIR:-${ROOT_DIR}/.venv}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
ENV_FILE="${ENV_FILE:-${ROOT_DIR}/.env.local}"

cd "${ROOT_DIR}"

if [[ ! -x "${VENV_DIR}/bin/python" ]]; then
  echo "Creating virtual environment: ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

PYTHON="${VENV_DIR}/bin/python"
PIP="${VENV_DIR}/bin/pip"

if [[ "${SKIP_PIP_INSTALL:-0}" == "1" ]]; then
  echo "Skipping dependency installation because SKIP_PIP_INSTALL=1"
else
  REQUIREMENTS_HASH="$("${PYTHON}" - <<'PY'
import hashlib
from pathlib import Path
print(hashlib.sha256(Path("requirements.txt").read_bytes()).hexdigest())
PY
)"
  REQUIREMENTS_MARKER="${VENV_DIR}/.requirements-installed"
  INSTALLED_REQUIREMENTS_HASH=""
  if [[ -f "${REQUIREMENTS_MARKER}" ]]; then
    INSTALLED_REQUIREMENTS_HASH="$(cat "${REQUIREMENTS_MARKER}")"
  fi
  if [[ "${INSTALLED_REQUIREMENTS_HASH}" != "${REQUIREMENTS_HASH}" ]]; then
    echo "Installing Python dependencies"
    "${PIP}" install --upgrade pip
    "${PIP}" install --upgrade --upgrade-strategy eager -r requirements.txt
    printf '%s\n' "${REQUIREMENTS_HASH}" > "${REQUIREMENTS_MARKER}"
  fi
fi

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${DOWNLOAD_TOKEN_SECRET:-}" ]] || [[ "${DOWNLOAD_TOKEN_SECRET}" == "__CHANGE_ME__" ]]; then
  DOWNLOAD_TOKEN_SECRET="$("${PYTHON}" - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
  printf 'DOWNLOAD_TOKEN_SECRET=%q\n' "${DOWNLOAD_TOKEN_SECRET}" > "${ENV_FILE}"
  chmod 600 "${ENV_FILE}"
  export DOWNLOAD_TOKEN_SECRET
  echo "Generated DOWNLOAD_TOKEN_SECRET and saved it to ${ENV_FILE}"
else
  export DOWNLOAD_TOKEN_SECRET
fi

export FLASK_RUN_HOST="${FLASK_RUN_HOST:-127.0.0.1}"
export FLASK_RUN_PORT="${FLASK_RUN_PORT:-5000}"
export FLASK_DEBUG="${FLASK_DEBUG:-0}"

mkdir -p "${UPLOAD_FOLDER:-${ROOT_DIR}/upload}" "${ROOT_DIR}/logs"

echo "Starting AutoWatermark Web at http://${FLASK_RUN_HOST}:${FLASK_RUN_PORT}"
exec "${PYTHON}" app.py
