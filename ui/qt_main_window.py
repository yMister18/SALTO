from __future__ import annotations

import json
import logging
import shutil
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from camera_manager import CameraManager, CameraSourceConfig
from consistency_checks import validate_attempt_dir_minimal, validate_attempt_state_payload
from database import CompetitionRecord
from export_manager import ExportManager
from file_manager import MeasurementRecord
from geometry import Line2D
from image_quality import ImageQualityAnalyzer
from integrity_manager import IntegrityManager
from merge_analyzer import ImpactAnalyzer
from path_guard import PathGuard
from recording_manager import RecordingConfig, RecordingSession
from reporting import ReportingManager
from session_state import SessionStateManager
from session_service import SessionService

from ui.dialogs.athlete_picker_dialog import AthletePickerDialog
from ui.dialogs.calibration_dialog import CalibrationDialog
from ui.dialogs.competition_dialog import CompetitionDialog
from ui.dialogs.frame_selection_dialog import FrameSelectionDialog
from ui.dialogs.point_selection_dialog import PointSelectionDialog
from ui.dialogs.settings_dialog import SettingsDialog

from ui.models import AppContext, AttemptRuntimeState, RuntimeSettings
from ui.panels.control_panel import ControlPanel
from ui.panels.info_panel import InfoPanel
from ui.panels.preview_panel import CameraPreviewWidget
from ui.panels.results_browser import ResultsBrowserPanel

from attempt_controller import AttemptController
from results_controller import ResultsController
from measurement_controller import MeasurementController

logger = logging.getLogger(__name__)


class EventLogPanel(QWidget):
    """Painel de registo de eventos integrado na Interface."""

    def __init__(self) -> None:
        super().__init__()
        from PySide6.QtWidgets import QGroupBox, QPlainTextEdit, QVBoxLayout

        box = QGroupBox("Eventos")
        self.log_edit = QPlainTextEdit()
        self.log_edit.setReadOnly(True)

        box_layout = QVBoxLayout(box)
        box_layout.addWidget(self.log_edit)

        layout = QVBoxLayout(self)
        layout.addWidget(box)

    def append(self, message: str) -> None:
        self.log_edit.appendPlainText(message)


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.context = context

        self.session_service = SessionService(context.config.paths.base_dir)
        self.session_state = SessionStateManager(Path(context.config.paths.base_dir))
        self.export_manager = ExportManager()
        self.integrity_manager = IntegrityManager()
        self.path_guard = PathGuard()

        self.attempt_state = AttemptRuntimeState()
        self._last_results_rows: list[dict] = []
        self._competitions_cache: list[CompetitionRecord] = []
        self._last_packets: dict[int, tuple[int, float, np.ndarray]] = {}

        analysis = self.context.config.analysis
        self.runtime_settings = RuntimeSettings(
            duration_seconds=float(context.config.recording.duration_seconds_default),
            pre_buffer_seconds=float(context.config.recording.pre_buffer_seconds_default),
            default_calibration_name=str(analysis.default_calibration_name),
            distance_precision_decimals=int(analysis.distance_precision_decimals),
            default_call_line_world_cm=(
                tuple(analysis.default_call_line_world_cm[0]),
                tuple(analysis.default_call_line_world_cm[1]),
            ),
        )

        self.attempt_controller = AttemptController(
            context,
            set_state_cb=self._on_attempt_state_updated,
            set_ui_cb=self._refresh_ui_from_attempt_state,
        )
        self.attempt_state = self.attempt_controller.state

        self.preview_panel = CameraPreviewWidget("Preview Operacional")
        self.control_panel = ControlPanel()
        self.info_panel = InfoPanel()
        self.log_panel = EventLogPanel()
        self.results_panel = ResultsBrowserPanel()

        self.results_controller = ResultsController(
            self.context.database_manager,
            self.export_manager,
            state_updated_cb=self.on_results_updated,
        )

        self.measurement_controller = MeasurementController(
            context=self.context,
            runtime_settings=self.runtime_settings,
            attempt_state_getter=lambda: self.attempt_controller.state,
            file_manager=self.context.file_manager,
            database_manager=self.context.database_manager,
            measurement_done_cb=self._on_measurement_done,
            preview_update_cb=lambda img: self.preview_panel.set_frame(img),
            error_cb=lambda msg: self.show_error("Medição", msg),
        )

        self.setWindowTitle("LAP2GO-SALTO v8.1.5")
        self.resize(1860, 1100)

        self._health_timer = QTimer(self)
        self._health_timer.setInterval(1000)
        self._health_timer.timeout.connect(self._refresh_runtime_status)

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(120)  # menos carga na UI
        self._preview_timer.timeout.connect(self._refresh_preview_frame)

        self._build_toolbar()
        self._build_statusbar()
        self._build_layout()
        self._connect_signals()

        self._load_initial_state()
        self.refresh_competitions()
        self.refresh_results_table()
        self._restore_last_session_if_available()
        self._refresh_ui_state()
        self._run_state_consistency_check("startup")

        logger.info("MainWindow inicializada com sucesso na versão v8.1.5")

    def log(self, message: str) -> None:
        logger.info(message)
        self.log_panel.append(message)
        self.statusBar().showMessage(message, 5000)

    def show_error(self, title: str, message: str):
        logger.error("%s: %s", title, message)
        self.log_panel.append(f"ERRO: {message}")
        QMessageBox.critical(self, title, message)

    def _run_state_consistency_check(self, source: str) -> None:
        issues = []
        issues.extend(validate_attempt_state_payload(self.attempt_state))
        issues.extend(validate_attempt_dir_minimal(self.attempt_state.attempt_dir))

        if issues:
            logger.warning("State consistency issues at %s: %s", source, issues)
            self.log_panel.append(f"AVISO CONSISTÊNCIA [{source}]")
            for issue in issues:
                self.log_panel.append(f"- {issue}")

    def _on_attempt_state_updated(self, state):
        self.attempt_state = state

    def on_results_updated(self, rows):
        self._last_results_rows = rows
        if hasattr(self, "results_panel"):
            self.results_panel.update_rows(rows)

    def _refresh_ui_from_attempt_state(self, state):
        self.attempt_state = state
        self._refresh_ui_state()

    def _refresh_ui_state(self) -> None:
        cameras_ready = self.context.camera_manager is not None
        has_attempt = self.attempt_state.attempt_db_id is not None
        has_frame = self.attempt_state.selected_frame_bgr is not None
        has_points = (
            self.attempt_state.clicked_point_px is not None
            and self.attempt_state.final_point_px is not None
        )

        self.control_panel.btn_preview.setEnabled(cameras_ready)
        self.control_panel.btn_stop_preview.setEnabled(cameras_ready)
        self.control_panel.btn_calibrate.setEnabled(cameras_ready)
        self.control_panel.btn_record.setEnabled(cameras_ready)
        self.control_panel.btn_select_frame.setEnabled(
            has_attempt and self.attempt_state.recording_session is not None
        )
        self.control_panel.btn_measure.setEnabled(has_frame)
        self.control_panel.btn_save.setEnabled(has_frame and has_points)

        if not cameras_ready:
            self.info_panel.lbl_preview.setText("câmaras não inicializadas")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        actions = [
            ("Inicializar", self.initialize_cameras),
            ("Preview ON", self.start_preview),
            ("Preview OFF", self.stop_preview),
            ("Configuração", self.open_settings_dialog),
            ("Export CSV", self.export_results_csv),
            ("Export JSON", self.export_results_json),
            ("Export tentativa ZIP", self.export_current_attempt_zip),
            ("Nova Competição", self.create_competition_from_ui),
            ("Escolher Atleta", self.pick_athlete_from_ui),
            ("Calibrar", self.open_calibration_dialog),
            ("Gravar", self.record_attempt_from_ui),
            ("Selecionar Frame", self.open_frame_selector_dialog),
            ("Selecionar Ponto", self.open_point_selector_dialog),
            ("Medir + Guardar", self.measure_and_save_from_ui),
            ("Validar tentativa aberta", self.validate_current_attempt),
            ("Sobre", self.show_about),
        ]

        for text, callback in actions:
            action = QAction(text, self)
            action.triggered.connect(callback)
            toolbar.addAction(action)

    def _build_statusbar(self) -> None:
        status = QStatusBar(self)
        status.showMessage("Aplicação pronta.")
        self.setStatusBar(status)

    def _build_layout(self) -> None:
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(self.control_panel)
        left_layout.addWidget(self.info_panel)
        left_layout.addWidget(self.log_panel, stretch=1)

        right_top_widget = QWidget()
        right_top_layout = QVBoxLayout(right_top_widget)
        right_top_layout.addWidget(self.preview_panel)

        right_bottom_widget = QWidget()
        right_bottom_layout = QVBoxLayout(right_bottom_widget)
        right_bottom_layout.addWidget(self.results_panel)

        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(right_top_widget)
        right_splitter.addWidget(right_bottom_widget)
        right_splitter.setSizes([560, 380])

        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([560, 1300])

        container = QWidget()
        root_layout = QHBoxLayout(container)
        root_layout.addWidget(main_splitter)
        self.setCentralWidget(container)

    def _connect_signals(self) -> None:
        self.control_panel.btn_initialize.clicked.connect(self.initialize_cameras)
        self.control_panel.btn_preview.clicked.connect(self.start_preview)
        self.control_panel.btn_stop_preview.clicked.connect(self.stop_preview)
        self.control_panel.btn_calibrate.clicked.connect(self.open_calibration_dialog)
        self.control_panel.btn_record.clicked.connect(self.record_attempt_from_ui)
        self.control_panel.btn_select_frame.clicked.connect(self.open_frame_selector_dialog)
        self.control_panel.btn_measure.clicked.connect(self.open_point_selector_dialog)
        self.control_panel.btn_save.clicked.connect(self.measure_and_save_from_ui)
        self.control_panel.competition_create_requested.connect(self.create_competition_from_ui)
        self.control_panel.competition_refresh_requested.connect(self.refresh_competitions)
        self.control_panel.athlete_pick_requested.connect(self.pick_athlete_from_ui)

        self.results_panel.btn_refresh.clicked.connect(self.refresh_results_table)
        self.results_panel.filter_edit.textChanged.connect(self.refresh_results_table)
        self.results_panel.competition_filter_combo.currentIndexChanged.connect(self.refresh_results_table)
        self.results_panel.sort_combo.currentIndexChanged.connect(self.refresh_results_table)
        self.results_panel.chk_include_archived.toggled.connect(self.refresh_results_table)
        self.results_panel.open_attempt_requested.connect(self.open_attempt_from_results)
        self.results_panel.athlete_summary_requested.connect(self.show_athlete_summary)
        self.results_panel.archive_attempt_requested.connect(self.archive_attempt_from_ui)
        self.results_panel.unarchive_attempt_requested.connect(self.unarchive_attempt_from_ui)
        self.results_panel.delete_attempt_requested.connect(self.delete_attempt_from_ui)

    def _load_initial_state(self) -> None:
        self.control_panel.calibration_name_edit.setText(self.runtime_settings.default_calibration_name)
        self.info_panel.lbl_config.setText("config.json carregado com sucesso")
        self.info_panel.lbl_competition.setText("sem competição activa")
        self.info_panel.lbl_calibration.setText(self.runtime_settings.default_calibration_name)
        self.info_panel.lbl_database.setText(str(self.context.database_manager.db_path))
        self.info_panel.lbl_athlete_summary.setText("sem resumo")
        self._reset_attempt_ui_labels()

        enabled_ids = []
        for cam in self.context.config.cameras:
            cam_id = cam["camera_id"] if isinstance(cam, dict) else cam.camera_id
            enabled = cam["enabled"] if isinstance(cam, dict) else cam.enabled
            name = cam["name"] if isinstance(cam, dict) else cam.name
            if enabled:
                self.control_panel.camera_combo.addItem(f"{cam_id} - {name}", cam_id)
                enabled_ids.append(cam_id)

        self.info_panel.lbl_cameras.setText(str(enabled_ids))
        self.info_panel.lbl_health.setText("não inicializado")
        self.log("UI Qt iniciada.")
        self.log(f"Câmaras configuradas: {enabled_ids}")
        self.log(f"BD inicializada: {self.context.database_manager.db_path}")

    def _reset_attempt_ui_labels(self) -> None:
        self.info_panel.lbl_preview.setText("parado")
        self.info_panel.lbl_recording.setText("sem gravação ativa")
        self.info_panel.lbl_frame_selection.setText("nenhum frame selecionado")
        self.info_panel.lbl_point_selection.setText("nenhum ponto selecionado")
        self.info_panel.lbl_measurement.setText("sem medição")
        self.info_panel.lbl_attempt.setText("sem tentativa ativa")

    def initialize_cameras(self):
        print("Inicializar câmaras chamado!")
        try:
            config_cameras = [
                CameraSourceConfig(**cam) if isinstance(cam, dict) else cam
                for cam in self.context.config.cameras
            ]

            if self.context.camera_manager is not None:
                try:
                    self.context.camera_manager.stop_all()
                except Exception:
                    logger.exception("Erro ao parar instância anterior do CameraManager")

            self.context.camera_manager = CameraManager(config_cameras)
            self.context.camera_manager.start_all()

            self._health_timer.start()
            self._refresh_runtime_status()
            self._refresh_ui_state()

            print("Câmaras inicializadas!")
            self.log("Câmaras inicializadas com sucesso.")
        except Exception as e:
            print("Erro na inicialização das câmaras:", e)
            self.log(f"Erro ao inicializar câmaras: {e}")
            self.info_panel.lbl_health.setText("erro")

    def start_preview(self):
        print("DEBUG: Iniciar Preview.")
        if self.context.camera_manager is None:
            self.info_panel.lbl_preview.setText("câmaras não inicializadas")
            self.preview_panel.set_message("Preview multi-câmara indisponível")
            self.log("Preview não iniciado: câmaras não inicializadas.")
            return

        self._preview_timer.start()
        self.info_panel.lbl_preview.setText("ativo")
        self.log("Preview iniciado.")

    def stop_preview(self):
        print("DEBUG: Parar Preview.")
        self._preview_timer.stop()
        self.info_panel.lbl_preview.setText("parado")
        self.preview_panel.set_message("Preview multi-câmara indisponível")
        self.log("Preview parado.")

    def _refresh_runtime_status(self):
        if self.context.camera_manager is None:
            self.info_panel.lbl_health.setText("não inicializado")
            self.info_panel.lbl_preview.setText("câmaras não inicializadas")
            return

        try:
            summary = self.context.camera_manager.health_summary()
            if not summary:
                self.info_panel.lbl_health.setText("sem sinal")
                return

            states = list(summary.values())
            if any(state == "healthy" for state in states):
                self.info_panel.lbl_health.setText("healthy")
            elif any(state == "degraded" for state in states):
                self.info_panel.lbl_health.setText("degraded")
            elif any(state == "recovering" for state in states):
                self.info_panel.lbl_health.setText("recovering")
            else:
                self.info_panel.lbl_health.setText(", ".join(states))
        except Exception as exc:
            self.info_panel.lbl_health.setText("erro")
            self.log(f"Erro ao atualizar saúde das câmaras: {exc}")

    def _refresh_preview_frame(self):
        try:
            if self.context.camera_manager is None:
                self.preview_panel.set_message("Preview multi-câmara indisponível")
                return

            camera_id = self.control_panel.camera_combo.currentData()
            frame = None

            latest = self.context.camera_manager.latest_packets()

            if camera_id in latest:
                frame = latest[camera_id][2]
            elif latest:
                frame = next(iter(latest.values()))[2]

            if frame is None or frame.size == 0:
                self.preview_panel.set_message("Preview multi-câmara indisponível")
                return

            h, w = frame.shape[:2]
            if w > 960:
                new_h = int(h * (960 / w))
                frame = cv2.resize(frame, (960, new_h), interpolation=cv2.INTER_AREA)

            self.preview_panel.set_frame(frame)
        except Exception as e:
            self.preview_panel.set_message("Erro no preview")
            self.log(f"Erro ao refrescar preview: {e}")

    def refresh_competitions(self): pass
    def refresh_results_table(self): pass
    def open_attempt_from_results(self): pass
    def _load_attempt_from_detail(self, detail): pass
    def archive_attempt_from_ui(self): pass
    def unarchive_attempt_from_ui(self): pass
    def delete_attempt_from_ui(self): pass
    def _on_measurement_done(self, result): pass
    def open_settings_dialog(self): pass
    def export_results_csv(self): pass
    def export_results_json(self): pass
    def export_current_attempt_zip(self): pass
    def validate_current_attempt(self): pass
    def show_about(self): pass

    def create_competition_from_ui(self) -> None:
        pass

    def pick_athlete_from_ui(self) -> None:
        pass

    def show_athlete_summary(self, athlete_id: int) -> None:
        pass

    def open_calibration_dialog(self) -> None:
        pass

    def open_frame_selector_dialog(self) -> None:
        pass

    def open_point_selector_dialog(self) -> None:
        pass

    def record_attempt_from_ui(self) -> None:
        pass

    def measure_and_save_from_ui(self) -> None:
        pass

    def _restore_last_session_if_available(self) -> None:
        try:
            payload = self.session_state.load()
            if not payload:
                self.log("Sem sessão anterior para restaurar.")
                return

            last_attempt_id = payload.get("last_attempt_id")
            if last_attempt_id is None:
                self.log("Sessão anterior sem tentativa associada.")
                return

            self.log("Sessão anterior sem tentativa associada.")
        except Exception as exc:
            logger.exception("Erro ao restaurar sessão")
            self.log(f"Aviso de sessão: {exc}")

    def closeEvent(self, event) -> None:
        logger.info("Aplicação a fechar")
        self._preview_timer.stop()
        self._health_timer.stop()

        if self.context.camera_manager is not None:
            try:
                self.context.camera_manager.stop_all()
            except Exception:
                logger.exception("Erro ao parar câmaras no fecho")
        event.accept()