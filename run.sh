#!/bin/bash
# .venv が無ければ作って依存を入れる
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv && .venv/bin/pip install -r requirements.lock || exit 1
fi
exec .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 7860
