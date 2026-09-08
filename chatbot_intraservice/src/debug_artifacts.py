# -*- coding: utf-8 -*-
"""Управление отладочными артефактами: пути для _analysis_*, _probe_* и других временных файлов."""
from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
DEBUG_DIR = PKG / "debug"


def ensure_debug_dir() -> Path:
    """Создать папку debug/ если не существует и вернуть путь."""
    DEBUG_DIR.mkdir(exist_ok=True)
    return DEBUG_DIR


def analysis_path(task_id: str | int) -> Path:
    """Путь к файлу _analysis_{task_id}.json в debug/."""
    ensure_debug_dir()
    return DEBUG_DIR / f"_analysis_{task_id}.json"


def analysis_summary_path(task_id: str | int) -> Path:
    """Путь к файлу _analysis_{task_id}_summary.json в debug/."""
    ensure_debug_dir()
    return DEBUG_DIR / f"_analysis_{task_id}_summary.json"


def debug_file_path(filename: str) -> Path:
    """Общий путь к отладочному файлу в debug/."""
    ensure_debug_dir()
    return DEBUG_DIR / filename


def legacy_analysis_path(task_id: str | int) -> Path:
    """Старый путь к _analysis_*.json в корне (для обратной совместимости при чтении)."""
    return PKG / f"_analysis_{task_id}.json"


def find_analysis(task_id: str | int) -> Path | None:
    """Найти файл анализа: сначала в debug/, затем в корне (legacy)."""
    new_path = analysis_path(task_id)
    if new_path.is_file():
        return new_path
    old_path = legacy_analysis_path(task_id)
    if old_path.is_file():
        return old_path
    return None
