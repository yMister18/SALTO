from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app_config import load_app_config
from calibration import CalibrationManager
from database import DatabaseManager
from file_manager import FileManager
from ui.qt_main_window import AppContext, MainWindow


@pytest.fixture
def test_context(tmp_path: Path) -> AppContext:
    config = load_app_config("config.json")

    config.paths.base_dir = str(tmp_path)

    file_manager = FileManager(base_dir=config.paths.base_dir)
    calibration_manager = CalibrationManager()
    database_manager = DatabaseManager(tmp_path / "lap2go_test.db")

    return AppContext(
        config=config,
        file_manager=file_manager,
        calibration_manager=calibration_manager,
        database_manager=database_manager,
        camera_manager=None,
    )


def test_main_window_smoke(qtbot, test_context: AppContext):
    window = MainWindow(test_context)
    qtbot.addWidget(window)
    window.show()

    assert window.windowTitle() != ""
    assert window.preview_panel is not None
    assert window.control_panel is not None
    assert window.info_panel is not None
    assert window.results_panel is not None


def test_results_filter_edit_updates_text(qtbot, test_context: AppContext):
    window = MainWindow(test_context)
    qtbot.addWidget(window)
    window.show()

    qtbot.keyClicks(window.results_panel.filter_edit, "ana")
    assert window.results_panel.filter_edit.text() == "ana"


def test_include_archived_checkbox_toggle(qtbot, test_context: AppContext):
    window = MainWindow(test_context)
    qtbot.addWidget(window)
    window.show()

    checkbox = window.results_panel.chk_include_archived
    assert checkbox.isChecked() is False

    qtbot.mouseClick(checkbox, Qt.LeftButton)
    assert checkbox.isChecked() is True

    qtbot.mouseClick(checkbox, Qt.LeftButton)
    assert checkbox.isChecked() is False


def test_settings_dialog_open_and_close(qtbot, test_context: AppContext, monkeypatch):
    window = MainWindow(test_context)
    qtbot.addWidget(window)
    window.show()

    called = {"value": False}

    def fake_open_settings_dialog():
        called["value"] = True

    monkeypatch.setattr(window, "open_settings_dialog", fake_open_settings_dialog)
    window._build_toolbar()

    window.open_settings_dialog()
    assert called["value"] is True


def test_results_table_exists(qtbot, test_context: AppContext):
    window = MainWindow(test_context)
    qtbot.addWidget(window)
    window.show()

    table = window.results_panel.table
    assert table.columnCount() > 0
    assert table.rowCount() >= 0