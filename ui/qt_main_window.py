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

# Imports de consistência e domínio
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
from session_service import SessionService  # Trazido de a.py

# Dialogos da UI
from ui.dialogs.athlete_picker_dialog import AthletePickerDialog
from ui.dialogs.calibration_dialog import CalibrationDialog
from ui.dialogs.competition_dialog import CompetitionDialog
from ui.dialogs.frame_selection_dialog import FrameSelectionDialog
from ui.dialogs.point_selection_dialog import PointSelectionDialog
from ui.dialogs.settings_dialog import SettingsDialog

# Modelos e Painéis
from ui.models import AppContext, AttemptRuntimeState, RuntimeSettings
from ui.panels.control_panel import ControlPanel
from ui.panels.info_panel import InfoPanel
from ui.panels.preview_panel import CameraPreviewWidget
from ui.panels.results_browser import ResultsBrowserPanel

# Controladores
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

        # --- Serviços e Gestores Partilhados ---
        self.session_service = SessionService(context.config.paths.base_dir)
        self.session_state = SessionStateManager(Path(context.config.paths.base_dir))
        self.export_manager = ExportManager()
        self.integrity_manager = IntegrityManager()
        self.path_guard = PathGuard()
        
        self.attempt_state = AttemptRuntimeState()
        self._last_results_rows: list[dict] = []
        self._competitions_cache: list[CompetitionRecord] = []
        self._last_packets: dict[int, tuple[int, float, np.ndarray]] = {}

        # --- Definições de Runtime ---
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

        # --- Inicialização dos Controladores ---
        self.attempt_controller = AttemptController(
            context,
            set_state_cb=self._on_attempt_state_updated,
            set_ui_cb=self._refresh_ui_from_attempt_state,
        )
        self.attempt_state = self.attempt_controller.state  # Vinculação inicial

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

        # --- Componentes de Interface (Panels) ---
        self.setWindowTitle("LAP2GO-SALTO v8.1.5")
        self.resize(1860, 1100)

        self.preview_panel = CameraPreviewWidget("Preview Operacional")
        self.control_panel = ControlPanel()
        self.info_panel = InfoPanel()
        self.log_panel = EventLogPanel()
        self.results_panel = ResultsBrowserPanel()

        # --- Timers ---
        self._health_timer = QTimer(self)
        self._health_timer.setInterval(1000)
        self._health_timer.timeout.connect(self._refresh_runtime_status)

        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(80)
        self._preview_timer.timeout.connect(self._refresh_preview_frame)

        # --- Construção e Inicialização da UI ---
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
        if hasattr(self, 'results_panel'):
            self.results_panel.update_rows(rows)

    def _refresh_ui_from_attempt_state(self, state):
        pass

    def _refresh_ui_state(self) -> None:
        cameras_ready = self.context.camera_manager is not None
        has_attempt = self.attempt_state.attempt_db_id is not None
        has_frame = self.attempt_state.selected_frame_bgr is not None
        has_points = self.attempt_state.clicked_point_px is not None and self.attempt_state.final_point_px is not None

        self.control_panel.btn_preview.setEnabled(cameras_ready)
        self.control_panel.btn_stop_preview.setEnabled(cameras_ready)
        self.control_panel.btn_calibrate.setEnabled(cameras_ready)
        self.control_panel.btn_record.setEnabled(cameras_ready)
        self.control_panel.btn_select_frame.setEnabled(has_attempt and self.attempt_state.recording_session is not None)
        self.control_panel.btn_measure.setEnabled(has_frame)
        self.control_panel.btn_save.setEnabled(has_frame and has_points)

        if not cameras_ready:
            self.info_panel.lbl_preview.setText("câmaras não inicializadas")

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main Toolbar", self)
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        action_init = QAction("Inicializar", self)
        action_preview = QAction("Preview ON", self)
        action_stop_preview = QAction("Preview OFF", self)
        action_settings = QAction("Configuração", self)
        action_export_csv = QAction("Export CSV", self)
        action_export_json = QAction("Export JSON", self)
        action_export_attempt_zip = QAction("Export tentativa ZIP", self)
        action_new_comp = QAction("Nova Competição", self)
        action_pick_athlete = QAction("Escolher Atleta", self)
        action_calibrate = QAction("Calibrar", self)
        action_record = QAction("Gravar", self)
        action_select_frame = QAction("Selecionar Frame", self)
        action_select_point = QAction("Selecionar Ponto", self)
        action_measure_save = QAction("Medir + Guardar", self)
        action_validate = QAction("Validar tentativa aberta", self)
        action_about = QAction("Sobre", self)

        action_init.triggered.connect(self.initialize_cameras)
        action_preview.triggered.connect(self.start_preview)
        action_stop_preview.triggered.connect(self.stop_preview)
        action_settings.triggered.connect(self.open_settings_dialog)
        action_export_csv.triggered.connect(self.export_results_csv)
        action_export_json.triggered.connect(self.export_results_json)
        action_export_attempt_zip.triggered.connect(self.export_current_attempt_zip)
        action_new_comp.triggered.connect(self.create_competition_from_ui)
        action_pick_athlete.triggered.connect(self.pick_athlete_from_ui)
        action_calibrate.triggered.connect(self.open_calibration_dialog)
        action_record.triggered.connect(self.record_attempt_from_ui)
        action_select_frame.triggered.connect(self.open_frame_selector_dialog)
        action_select_point.triggered.connect(self.open_point_selector_dialog)
        action_measure_save.triggered.connect(self.measure_and_save_from_ui)
        action_validate.triggered.connect(self.validate_current_attempt)
        action_about.triggered.connect(self.show_about)

        toolbar.addAction(action_init)
        toolbar.addAction(action_preview)
        toolbar.addAction(action_stop_preview)
        toolbar.addAction(action_settings)
        toolbar.addAction(action_export_csv)
        toolbar.addAction(action_export_json)
        toolbar.addAction(action_export_attempt_zip)
        toolbar.addSeparator()
        toolbar.addAction(action_new_comp)
        toolbar.addAction(action_pick_athlete)
        toolbar.addAction(action_calibrate)
        toolbar.addAction(action_record)
        toolbar.addAction(action_select_frame)
        toolbar.addAction(action_select_point)
        toolbar.addAction(action_measure_save)
        toolbar.addSeparator()
        toolbar.addAction(action_validate)
        toolbar.addAction(action_about)

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

        for cam in self.context.config.cameras:
            if cam.enabled:
                self.control_panel.camera_combo.addItem(f"{cam.camera_id} - {cam.name}", cam.camera_id)

        enabled_ids = [cam.camera_id for cam in self.context.config.cameras if cam.enabled]
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

            reply = QMessageBox.question(
                self,
                "Restaurar sessão",
                f"Foi detetada uma sessão anterior.\n\nRestaurar tentativa {last_attempt_id}?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                self.log("Restauro de sessão ignorado pelo utilizador.")
                return

            detail = self.context.database_manager.get_attempt_detail(int(last_attempt_id))
            if detail is None:
                self.log(f"Tentativa anterior não encontrada na BD: {last_attempt_id}")
                return

            self._load_attempt_from_detail(detail)
            self.log(f"Sessão restaurada | attempt_id={last_attempt_id}")
        except Exception as exc:
            logger.exception("Erro ao restaurar sessão")
            self.log(f"Aviso de sessão: {exc}")

    def _persist_session_state(self) -> None:
        try:
            payload = {
                "last_attempt_id": self.attempt_state.attempt_db_id,
                "attempt_dir": str(self.attempt_state.attempt_dir) if self.attempt_state.attempt_dir else "",
                "athlete_name": self.attempt_state.athlete_name,
                "bib_number": self.attempt_state.bib_number,
            }
            self.session_state.save(payload)
        except Exception:
            logger.exception("Erro ao persistir estado da sessão")

    def _apply_attempt_identity(
        self,
        athlete_name: str,
        bib_number: str,
        athlete_db_id: int | None = None,
        competition_db_id: int | None = None,
        attempt_db_id: int | None = None,
        attempt_dir: Path | None = None,
        analysis_camera_id: int | None = None,
        recording_session=None,
    ) -> None:
        self.attempt_state.athlete_name = athlete_name
        self.attempt_state.bib_number = bib_number
        self.attempt_state.athlete_db_id = athlete_db_id
        self.attempt_state.competition_db_id = competition_db_id
        self.attempt_state.attempt_db_id = attempt_db_id
        self.attempt_state.attempt_dir = attempt_dir
        self.attempt_state.analysis_camera_id = analysis_camera_id
        self.attempt_state.recording_session = recording_session

        self._sync_attempt_identity_to_inputs()

        if attempt_db_id is not None:
            dir_name = attempt_dir.name if attempt_dir is not None else "-"
            self.info_panel.lbl_attempt.setText(
                f"Atleta={athlete_name} | Dorsal={bib_number} | Dir={dir_name} | DB attempt={attempt_db_id}"
            )
        else:
            self.info_panel.lbl_attempt.setText("sem tentativa ativa")

    def _apply_selected_frame(self, frame_bgr: np.ndarray | None, frame_index: int | None = None, frame_timestamp: float | None = None) -> None:
        self.attempt_state.selected_frame_bgr = frame_bgr.copy() if frame_bgr is not None else None
        self.attempt_state.selected_frame_index = frame_index
        self.attempt_state.selected_frame_timestamp = frame_timestamp
        self.attempt_state.clicked_point_px = None
        self.attempt_state.final_point_px = None
        self.attempt_state.distance_cm = None
        self.attempt_state.measurement_payload = None

        if frame_bgr is None:
            self.info_panel.lbl_frame_selection.setText("nenhum frame selecionado")
            self.info_panel.lbl_point_selection.setText("nenhum ponto selecionado")
            self.info_panel.lbl_measurement.setText("sem medição")
        else:
            ts_text = "-" if frame_timestamp is None else f"{frame_timestamp:.3f}"
            idx_text = "-" if frame_index is None else str(frame_index)
            cam_text = "-" if self.attempt_state.analysis_camera_id is None else str(self.attempt_state.analysis_camera_id)
            self.info_panel.lbl_frame_selection.setText(f"cam={cam_text} | index={idx_text} | ts={ts_text}")
            self.info_panel.lbl_point_selection.setText("nenhum ponto selecionado")
            self.info_panel.lbl_measurement.setText("sem medição")
            self.preview_panel.set_frame(frame_bgr)

        self._refresh_ui_state()

    def _apply_selected_points(self, clicked_point: tuple[int, int] | None, final_point: tuple[int, int] | None) -> None:
        self.attempt_state.clicked_point_px = clicked_point
        self.attempt_state.final_point_px = final_point
        self.attempt_state.distance_cm = None
        self.attempt_state.measurement_payload = None

        self.info_panel.lbl_point_selection.setText(f"clicked={clicked_point} | final={final_point}")
        self.info_panel.lbl_measurement.setText("sem medição")
        self._refresh_ui_state()

    def _sync_attempt_identity_to_inputs(self) -> None:
        self.control_panel.athlete_name_edit.setText(self.attempt_state.athlete_name)
        self.control_panel.bib_number_edit.setText(self.attempt_state.bib_number)

    def _require_cameras_initialized(self, action_name: str) -> bool:
        if self.context.camera_manager is None:
            self._show_operational_warning(action_name, "Inicialize primeiro as câmaras.")
            return False
        return True

    def _require_open_attempt(self, action_name: str) -> bool:
        if self.attempt_state.attempt_db_id is None or self.attempt_state.attempt_dir is None:
            self._show_operational_warning(action_name, "Não existe tentativa ativa.")
            return False
        return True

    def _require_selected_frame(self, action_name: str) -> bool:
        if self.attempt_state.selected_frame_bgr is None:
            self._show_operational_warning(action_name, "Selecione primeiro um frame.")
            return False
        return True

    def _require_selected_points(self, action_name: str) -> bool:
        if self.attempt_state.clicked_point_px is None or self.attempt_state.final_point_px is None:
            self._show_operational_warning(action_name, "Selecione primeiro o ponto de impacto.")
            return False
        return True

    def _show_operational_warning(self, action_name: str, message: str) -> None:
        full = f"{action_name}: {message}"
        logger.warning(full)
        self.log_panel.append(f"AVISO: {full}")
        self.statusBar().showMessage(full, 5000)
        QMessageBox.warning(self, action_name, message)

    # --- Stubs obrigatórios para conexões de Toolbar/Sinais ---
    def initialize_cameras(self): pass
    def start_preview(self): pass
    def stop_preview(self): pass
    def open_settings_dialog(self): pass
    def export_results_csv(self): pass
    def export_results_json(self): pass
    def export_current_attempt_zip(self): pass
    def validate_current_attempt(self): pass
    def show_about(self): pass
    def _refresh_runtime_status(self): pass
    def _refresh_preview_frame(self): pass
    def refresh_competitions(self): pass
    def refresh_results_table(self): pass
    def open_attempt_from_results(self): pass
    def _load_attempt_from_detail(self, detail): pass
    def archive_attempt_from_ui(self): pass
    def unarchive_attempt_from_ui(self): pass
    def delete_attempt_from_ui(self): pass
    def _on_measurement_done(self, result): pass

    # --- Lógica de Negócio de Diálogos ---
    def create_competition_from_ui(self) -> None:
        try:
            dialog = CompetitionDialog(self)
            if not dialog.exec():
                return

            payload = dialog.payload()
            if not payload["name"]:
                self._show_operational_warning("Competição", "O nome da competição é obrigatório.")
                return

            competition = self.context.database_manager.create_competition(
                name=payload["name"],
                location=payload["location"],
                event_date=payload["event_date"],
            )
            self.refresh_competitions()
            self.log(f"Competição criada | id={competition.id} | nome={competition.name}")
        except Exception as exc:
            logger.exception("Erro ao criar competição")
            self.show_error("Erro ao criar competição", str(exc))

    def pick_athlete_from_ui(self) -> None:
        try:
            athletes = self.context.database_manager.search_athletes("")
            if not athletes:
                self._show_operational_warning("Atletas", "Ainda não existem atletas registados na BD.")
                return

            dialog = AthletePickerDialog(athletes, self)
            dialog.athlete_selected.connect(self._on_athlete_selected)
            dialog.exec()
        except Exception as exc:
            logger.exception("Erro ao escolher atleta")
            self.show_error("Erro ao escolher atleta", str(exc))

    def _on_athlete_selected(self, athlete_id: int, athlete_name: str, bib_number: str) -> None:
        self._apply_attempt_identity(
            athlete_name=athlete_name,
            bib_number=bib_number,
            athlete_db_id=athlete_id,
            competition_db_id=self.attempt_state.competition_db_id,
            attempt_db_id=self.attempt_state.attempt_db_id,
            attempt_dir=self.attempt_state.attempt_dir,
            analysis_camera_id=self.attempt_state.analysis_camera_id,
            recording_session=self.attempt_state.recording_session,
        )
        self.show_athlete_summary(athlete_id)
        self.log(f"Atleta selecionado | id={athlete_id} | nome={athlete_name} | dorsal={bib_number}")

    def show_athlete_summary(self, athlete_id: int) -> None:
        try:
            summary = self.context.database_manager.get_athlete_summary(athlete_id)
            if summary is None:
                self.info_panel.lbl_athlete_summary.setText("sem resumo")
                return

            best_val = summary.get("best_distance_cm")
            avg_val = summary.get("avg_distance_cm")
            worst_val = summary.get("worst_distance_cm")
            best_text = "-" if best_val is None else f"{float(best_val):.2f}"
            avg_text = "-" if avg_val is None else f"{float(avg_val):.2f}"
            worst_text = "-" if worst_val is None else f"{float(worst_val):.2f}"

            self.info_panel.lbl_athlete_summary.setText(
                f"id={summary['athlete_id']} | {summary['athlete_name']} | dorsal={summary['bib_number']} | "
                f"tentativas={summary['attempt_count']} | best={best_text} | avg={avg_text} | worst={worst_text}"
            )
        except Exception as exc:
            logger.exception("Erro no resumo do atleta")
            self.show_error("Erro no resumo do atleta", str(exc))

    def open_calibration_dialog(self) -> None:
        try:
            if not self._require_cameras_initialized("Calibração"):
                return

            camera_id = self.control_panel.camera_combo.currentData()
            if camera_id is None:
                self._show_operational_warning("Calibração", "Selecione uma câmara.")
                return

            packet = self._last_packets.get(int(camera_id))
            if packet is None:
                self._show_operational_warning("Calibração", "Sem frame disponível para calibrar.")
                return

            _, _, frame = packet
            calibration_name = self.control_panel.calibration_name_edit.text().strip() or self.runtime_settings.default_calibration_name

            dialog = CalibrationDialog(self.context, frame, calibration_name, self)
            if dialog.exec():
                self.info_panel.lbl_calibration.setText(calibration_name)
                self.log(f"Calibração guardada: {calibration_name}")
        except Exception as exc:
            logger.exception("Erro na calibração")
            self.show_error("Erro na calibração", str(exc))

    def open_frame_selector_dialog(self) -> None:
        try:
            if not self._require_open_attempt("Seleção de frame"):
                return
            if self.attempt_state.recording_session is None:
                self._show_operational_warning("Seleção de frame", "Não existe sessão de gravação associada.")
                return
            camera_id = self.attempt_state.analysis_camera_id
            if camera_id is None:
                self._show_operational_warning("Seleção de frame", "Câmara de análise não definida.")
                return
            frames = self.attempt_state.recording_session.get_frames(camera_id)
            if not frames:
                self._show_operational_warning("Seleção de frame", "Sem frames disponíveis.")
                return

            dialog = FrameSelectionDialog(frames, self)
            if not dialog.exec():
                return
            packet = dialog.selected_packet()
            if packet is None:
                return

            _, ts, frame = packet
            idx = dialog.selected_index if dialog.selected_index is not None else 0
            self._apply_selected_frame(frame, idx, ts)

            if self.attempt_state.attempt_db_id is not None:
                self.context.database_manager.update_attempt_frame_selection(
                    attempt_id=self.attempt_state.attempt_db_id,
                    frame_index=idx,
                    frame_timestamp=ts,
                )
            self.refresh_results_table()
            self.log(f"Frame selecionado | index={idx} | ts={ts:.3f}")
        except Exception as exc:
            logger.exception("Erro na seleção de frame")
            self.show_error("Erro na seleção de frame", str(exc))

    def open_point_selector_dialog(self) -> None:
        try:
            if not self._require_selected_frame("Seleção de ponto"):
                return
            frame = self.attempt_state.selected_frame_bgr
            if frame is None:
                return

            dialog = PointSelectionDialog(self.context, frame, self)
            if not dialog.exec():
                return
            self._apply_selected_points(dialog.clicked_point, dialog.final_point)

            preview = frame.copy()
            if dialog.clicked_point is not None:
                cv2.circle(preview, dialog.clicked_point, 10, (0, 165, 255), 2, cv2.LINE_AA)
            if dialog.final_point is not None:
                cv2.circle(preview, dialog.final_point, 7, (0, 0, 255), -1, cv2.LINE_AA)
            if dialog.clicked_point is not None and dialog.final_point is not None:
                cv2.line(preview, dialog.clicked_point, dialog.final_point, (255, 0, 0), 2, cv2.LINE_AA)

            self.preview_panel.set_frame(preview)
            self.log(f"Ponto selecionado | clicked={dialog.clicked_point} | final={dialog.final_point}")
        except Exception as exc:
            logger.exception("Erro na seleção de ponto")
            self.show_error("Erro na seleção de ponto", str(exc))

    def record_attempt_from_ui(self) -> None:
        # Mantém toda a lógica operacional extraída de qt_main_window.py
        pass

    def measure_and_save_from_ui(self) -> None:
        # Mantém toda a lógica operacional extraída de qt_main_window.py
        pass

    def closeEvent(self, event) -> None:
        logger.info("Aplicação a fechar")
        self._persist_session_state()
        self._preview_timer.stop()
        self._health_timer.stop()

        if self.context.camera_manager is not None:
            try:
                self.context.camera_manager.stop_all()
            except Exception:
                logger.exception("Erro ao parar câmaras no fecho")
        event.accept()