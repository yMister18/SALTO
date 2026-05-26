from __future__ import annotations

import logging
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from app_config import load_app_config
from calibration import CalibrationManager
from database import DatabaseManager
from file_manager import FileManager
from logging_config import setup_logging
from ui.models import AppContext
from ui.qt_main_window import MainWindow


logger = logging.getLogger(__name__)


def build_context(config_path: str = "config.json") -> AppContext:
    config = load_app_config(config_path)
    file_manager = FileManager(base_dir=config.paths.base_dir)
    calibration_manager = CalibrationManager()
    database_manager = DatabaseManager(Path(config.paths.base_dir) / "lap2go.db")

    return AppContext(
        config=config,
        file_manager=file_manager,
        calibration_manager=calibration_manager,
        database_manager=database_manager,
        camera_manager=None,
    )


def main() -> int:
    config_path = "config.json"
    if len(sys.argv) > 1:
        config_path = sys.argv[1]

    config = load_app_config(config_path)
    log_file = setup_logging(config.paths.base_dir)

    logger.info("Aplicação a arrancar com config=%s", config_path)
    logger.info("Ficheiro de log ativo: %s", log_file)

    app = QApplication(sys.argv)
    context = build_context(config_path)
    window = MainWindow(context)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())