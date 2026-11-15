"""Сохранение имени игрока и последних адресов между запусками."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "monopoly" / "settings.json"


def load_settings() -> dict[str, Any]:
    try:
        data = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(values: dict[str, Any]) -> None:
    current = load_settings()
    current.update(values)
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        # Настройки — не критичная часть: молча игнорируем ошибки записи.
        pass
