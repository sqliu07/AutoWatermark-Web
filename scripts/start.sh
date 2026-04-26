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

requirements_ready() {
  "${PYTHON}" - <<'PY' >/dev/null 2>&1
import flask
import flask_limiter
import PIL
import piexif
PY
}

if [[ "${SKIP_PIP_INSTALL:-0}" == "1" ]]; then
  echo "Skipping dependency installation because SKIP_PIP_INSTALL=1"
elif requirements_ready; then
  touch "${VENV_DIR}/.requirements-installed"
elif [[ ! -f "${VENV_DIR}/.requirements-installed" ]] || [[ requirements.txt -nt "${VENV_DIR}/.requirements-installed" ]]; then
  echo "Installing Python dependencies"
  "${PIP}" install --upgrade pip
  "${PIP}" install -r requirements.txt
  touch "${VENV_DIR}/.requirements-installed"
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

mkdir -p "${UPLOAD_FOLDER:-${ROOT_DIR}/upload}" "${ROOT_DIR}/logs"

echo "Starting AutoWatermark Web at http://127.0.0.1:5000"
exec "${PYTHON}" app.py
