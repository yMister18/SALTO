from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from app_config import ApplicationConfig, CalibrationPreset, load_app_config
from calibration import CalibrationData, CalibrationManager
from camera_manager import CameraManager
from file_manager import FileManager, MeasurementRecord
from frame_selector import FrameSelectionCancelled, FrameSelector
from geometry import Line2D
from image_quality import ImageQualityAnalyzer
from merge_analyzer import ImpactAnalyzer
from recording_manager import RecordingConfig, RecordingSession
from reporting import ReportingManager
from ui_manager import CalibrationCancelled, CalibrationUI, PointSelectionCancelled, ZoomPointSelector


LOG = logging.getLogger("lap2go")


class AppError(RuntimeError):
    pass


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LAP2GO-SALTO")
    parser.add_argument(
        "--config",
        default="config.json",
        help="Caminho para o config.json",
    )
    parser.add_argument(
        "--mode",
        choices=["run", "calibrate", "record", "measure"],
        default="run",
        help="Modo de operação",
    )
    return parser


def configure_logging(logs_dir: Path) -> Path:
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "lap2go.log"

    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    LOG.addHandler(file_handler)
    LOG.addHandler(stream_handler)
    return log_path


def prompt_text(prompt: str, allow_empty: bool = False) -> str:
    while True:
        value = input(prompt).strip()
        if value or allow_empty:
            return value
        print("Valor obrigatório.")


def prompt_yes_no(prompt: str, default_yes: bool = True) -> bool:
    suffix = " [Y/n]: " if default_yes else " [y/N]: "
    raw = input(prompt + suffix).strip().lower()
    if not raw:
        return default_yes
    return raw in {"y", "yes", "s", "sim"}


def choose_analysis_camera_id(config: ApplicationConfig, camera_manager: CameraManager) -> int:
    enabled = camera_manager.enabled_camera_ids()
    default_id = config.analysis.default_analysis_camera_id

    print("Câmaras disponíveis:", enabled)
    print("Estado atual:", camera_manager.health_summary())

    while True:
        raw = input(f"Escolha a câmara para análise [{default_id}]: ").strip()
        if not raw:
            return default_id
        try:
            camera_id = int(raw)
            if camera_id in enabled:
                return camera_id
        except Exception:
            pass
        print("camera_id inválido.")


def resolve_calibration_preset(
    config: ApplicationConfig,
    preset_name: str,
) -> CalibrationPreset:
    for preset in config.calibration.presets:
        if preset.name == preset_name:
            return preset
    raise AppError(f"Preset de calibração não encontrado: {preset_name}")


def prompt_world_points(required_points: int) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    print(f"Introduza {required_points} pontos reais em centímetros no formato x,y")
    for idx in range(required_points):
        while True:
            raw = input(f"Ponto real #{idx + 1}: ").strip()
            try:
                x_str, y_str = raw.split(",")
                points.append((float(x_str), float(y_str)))
                break
            except Exception:
                print("Formato inválido. Use x,y")
    return points


def prompt_call_line(default_line: tuple[tuple[float, float], tuple[float, float]]) -> Line2D:
    print("Defina a linha de chamada no plano real (cm).")
    print(f"Default: {default_line[0][0]},{default_line[0][1]} e {default_line[1][0]},{default_line[1][1]}")

    use_default = prompt_yes_no("Usar linha por omissão?", default_yes=True)
    if use_default:
        return Line2D(default_line[0], default_line[1])

    while True:
        try:
            p1_raw = input("Linha ponto 1 (x,y): ").strip()
            p2_raw = input("Linha ponto 2 (x,y): ").strip()
            x1, y1 = [float(v) for v in p1_raw.split(",")]
            x2, y2 = [float(v) for v in p2_raw.split(",")]
            return Line2D((x1, y1), (x2, y2))
        except Exception:
            print("Valores inválidos. Tente novamente.")


def preview_live(camera_manager: CameraManager, seconds: float = 2.0) -> None:
    end_time = time.time() + seconds
    cv2.namedWindow("LAP2GO - Preview", cv2.WINDOW_NORMAL)

    while time.time() < end_time:
        packets = camera_manager.latest_packets()
        stats_map = {stat.camera_id: stat for stat in camera_manager.stats()}
        previews = []

        # Garante que iteramos pelas câmaras ativas de forma dinâmica
        for camera_id in sorted(camera_manager.enabled_camera_ids()):
            packet = packets.get(camera_id) if packets else None
            stat = stats_map.get(camera_id)
            status = stat.health_status if stat else "unknown"

            # Se o pacote não existir ou o frame for inválido, cria uma imagem de standby
            if packet is None or len(packet) < 3 or packet[2] is None:
                blank = np.zeros((540, 960, 3), dtype=np.uint8)
                cv2.putText(blank, f"CAM {camera_id}", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2, cv2.LINE_AA)
                cv2.putText(blank, f"A CARREGAR / ERRO | {status}", (30, 120), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2, cv2.LINE_AA)
                previews.append(blank)
                continue

            # Se o frame for válido, processa-o em segurança
            _, ts, frame = packet
            try:
                view = cv2.resize(frame, (960, 540))
                
                color = (0, 200, 0)
                if status == "degraded":
                    color = (0, 165, 255)
                elif status in {"down", "no_signal"}:
                    color = (0, 0, 255)
                elif status == "recovering":
                    color = (255, 255, 0)

                cv2.putText(view, f"CAM {camera_id} | {ts:.3f}", (24, 42), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2, cv2.LINE_AA)
                cv2.putText(view, f"{status} | reconnects={stat.reconnect_count}", (24, 82), cv2.FONT_HERSHEY_SIMPLEX, 0.75, color, 2, cv2.LINE_AA)
                previews.append(view)
            except Exception:
                # Backup extra caso o resize falhe por frame corrompido
                blank = np.zeros((540, 960, 3), dtype=np.uint8)
                cv2.putText(blank, f"CAM {camera_id} - Erro Frame", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 2, cv2.LINE_AA)
                previews.append(blank)

        # Junta os painéis no mosaico final com base nas imagens recolhidas
        if previews:
            if len(previews) == 1:
                mosaic = previews[0]
            elif len(previews) == 2:
                mosaic = cv2.hconcat(previews)
            elif len(previews) == 3:
                blank = np.zeros_like(previews[0])
                mosaic = cv2.vconcat([cv2.hconcat(previews[:2]), cv2.hconcat([previews[2], blank])])
            else:
                mosaic = cv2.vconcat([cv2.hconcat(previews[:2]), cv2.hconcat(previews[2:4])])

            cv2.imshow("LAP2GO - Preview", mosaic)
        
        if cv2.waitKey(30) == 27: # Aumentado para 30ms para dar tempo ao Windows de renderizar a janela
            break

    cv2.destroyWindow("LAP2GO - Preview")


def build_file_manager_from_config(config: ApplicationConfig) -> FileManager:
    return FileManager(base_dir=config.paths.base_dir)


def acquire_calibration(
    config: ApplicationConfig,
    calibration_manager: CalibrationManager,
    file_manager: FileManager,
    camera_manager: CameraManager,
    calibration_name: str,
    analysis_camera_id: int,
) -> CalibrationData:
    calibration_path = file_manager.calibration_path(calibration_name)

    if calibration_path.exists() and prompt_yes_no(
        f"Usar calibração existente '{calibration_path.name}'?",
        default_yes=True,
    ):
        data = calibration_manager.load(calibration_path)
        LOG.info("Calibração carregada de %s", calibration_path)
        return data

    packet = camera_manager.stream(analysis_camera_id).get_latest_packet()
    if packet is None:
        raise AppError("Sem frame disponível para calibração.")

    _, _, frame = packet

    print("Modo de calibração: selecione os pontos da sandbox no frame.")
    calib_ui = CalibrationUI()
    image_points = calib_ui.collect_points(
        frame,
        required_points=config.calibration.min_points,
    )

    print(f"Preset por omissão: {config.calibration.default_preset_name}")
    use_default_preset = prompt_yes_no("Usar preset por omissão?", default_yes=True)

    if use_default_preset:
        preset = resolve_calibration_preset(config, config.calibration.default_preset_name)
        world_points = preset.world_points_cm
    else:
        world_points = prompt_world_points(len(image_points))

    data = calibration_manager.calibrate(
        image_points=image_points,
        world_points_cm=world_points,
        sandbox_name=calibration_name,
    )
    calibration_manager.save(data, calibration_path)
    LOG.info(
        "Calibração guardada em %s | erro médio=%.3f px | erro máximo=%.3f px",
        calibration_path,
        data.quality.mean_reprojection_error_px,
        data.quality.max_reprojection_error_px,
    )
    return data


def validate_selected_frame_quality(frame: np.ndarray) -> tuple[bool, dict]:
    analyzer = ImageQualityAnalyzer()
    result = analyzer.analyze(frame)

    print("\nQualidade do frame selecionado:")
    print(f"- sharpness_variance: {result.sharpness_variance:.2f}")
    print(f"- contrast_std: {result.contrast_std:.2f}")
    print(f"- brightness_mean: {result.brightness_mean:.2f}")
    print(f"- dynamic_range: {result.dynamic_range:.2f}")
    print(
        f"- flags: blurry={result.is_blurry}, dark={result.is_too_dark}, "
        f"bright={result.is_too_bright}, low_contrast={result.is_low_contrast}"
    )

    quality_payload = asdict(result)

    if result.passed:
        return True, quality_payload

    print("Aviso: o frame tem problemas de qualidade.")
    proceed = prompt_yes_no("Pretende continuar mesmo assim?", default_yes=False)
    return proceed, quality_payload


def calibrate_mode(
    config: ApplicationConfig,
    camera_manager: CameraManager,
    file_manager: FileManager,
    calibration_manager: CalibrationManager,
) -> None:
    analysis_camera_id = choose_analysis_camera_id(config, camera_manager)
    calibration_name = (
        prompt_text(
            f"Nome da calibração [{config.analysis.default_calibration_name}]: ",
            allow_empty=True,
        )
        or config.analysis.default_calibration_name
    )

    data = acquire_calibration(
        config=config,
        calibration_manager=calibration_manager,
        file_manager=file_manager,
        camera_manager=camera_manager,
        calibration_name=calibration_name,
        analysis_camera_id=analysis_camera_id,
    )
    print("Calibração concluída.")
    print(f"Ficheiro: {file_manager.calibration_path(calibration_name)}")
    print(f"Erro médio: {data.quality.mean_reprojection_error_px:.3f} px")
    print(f"Erro máximo: {data.quality.max_reprojection_error_px:.3f} px")


def record_mode(
    config: ApplicationConfig,
    camera_manager: CameraManager,
    file_manager: FileManager,
) -> None:
    athlete_name = prompt_text("Nome do atleta: ")
    bib_number = prompt_text("Dorsal: ")
    attempt_dir = file_manager.create_attempt_dir(athlete_name, bib_number)

    duration_seconds = float(
        prompt_text(
            f"Duração de gravação em segundos [{config.recording.duration_seconds_default}]: ",
            allow_empty=True,
        ) or str(config.recording.duration_seconds_default)
    )

    pre_buffer_seconds = float(
        prompt_text(
            f"Pre-buffer em segundos [{config.recording.pre_buffer_seconds_default}]: ",
            allow_empty=True,
        ) or str(config.recording.pre_buffer_seconds_default)
    )

    recording = RecordingSession(
        RecordingConfig(
            output_dir=attempt_dir / "video",
            session_fps=config.recording.session_fps,
            sync_tolerance_ms=config.recording.sync_tolerance_ms,
            min_required_cameras=config.recording.min_required_cameras,
            poll_interval_seconds=config.recording.poll_interval_seconds,
            video_codec=config.recording.video_codec,
            file_extension=config.recording.file_extension,
            write_timestamp_overlay=config.recording.write_timestamp_overlay,
        )
    )

    input("Prima ENTER para iniciar gravação...")
    recording.record_for_duration(
        camera_manager=camera_manager,
        duration_seconds=duration_seconds,
        include_pre_buffer_seconds=pre_buffer_seconds,
    )
    video_paths = recording.export_videos()
    print("Vídeos exportados:", video_paths)


def measure_mode(
    config: ApplicationConfig,
    camera_manager: CameraManager,
    file_manager: FileManager,
    calibration_manager: CalibrationManager,
) -> None:
    run_attempt(config, camera_manager, file_manager, calibration_manager)


def run_attempt(
    config: ApplicationConfig,
    camera_manager: CameraManager,
    file_manager: FileManager,
    calibration_manager: CalibrationManager,
) -> None:
    athlete_name = prompt_text("Nome do atleta: ")
    bib_number = prompt_text("Dorsal: ")
    attempt_dir = file_manager.create_attempt_dir(athlete_name, bib_number)

    LOG.info("Nova tentativa criada em %s", attempt_dir)

    analysis_camera_id = choose_analysis_camera_id(config, camera_manager)

    camera_health = camera_manager.stream(analysis_camera_id).get_health_status()
    if camera_health not in {"healthy", "degraded", "recovering"}:
        raise AppError(
            f"A câmara de análise {analysis_camera_id} não está operacional: {camera_health}"
        )

    calibration_name = (
        prompt_text(
            f"Nome da calibração [{config.analysis.default_calibration_name}]: ",
            allow_empty=True,
        )
        or config.analysis.default_calibration_name
    )

    calibration_data = acquire_calibration(
        config=config,
        calibration_manager=calibration_manager,
        file_manager=file_manager,
        camera_manager=camera_manager,
        calibration_name=calibration_name,
        analysis_camera_id=analysis_camera_id,
    )

    call_line = prompt_call_line(config.analysis.default_call_line_world_cm)

    print("Preview rápido das câmaras...")
    preview_live(camera_manager, seconds=2.0)

    duration_seconds = float(
        prompt_text(
            f"Duração de gravação em segundos [{config.recording.duration_seconds_default}]: ",
            allow_empty=True,
        ) or str(config.recording.duration_seconds_default)
    )

    pre_buffer_seconds = float(
        prompt_text(
            f"Pre-buffer em segundos [{config.recording.pre_buffer_seconds_default}]: ",
            allow_empty=True,
        ) or str(config.recording.pre_buffer_seconds_default)
    )

    recording = RecordingSession(
        RecordingConfig(
            output_dir=attempt_dir / "video",
            session_fps=config.recording.session_fps,
            sync_tolerance_ms=config.recording.sync_tolerance_ms,
            min_required_cameras=config.recording.min_required_cameras,
            poll_interval_seconds=config.recording.poll_interval_seconds,
            video_codec=config.recording.video_codec,
            file_extension=config.recording.file_extension,
            write_timestamp_overlay=config.recording.write_timestamp_overlay,
        )
    )

    input("Prima ENTER para iniciar gravação...")
    LOG.info(
        "Gravação iniciada | duração=%.2fs | pre_buffer=%.2fs | health=%s",
        duration_seconds,
        pre_buffer_seconds,
        camera_manager.health_summary(),
    )

    recording.record_for_duration(
        camera_manager=camera_manager,
        duration_seconds=duration_seconds,
        include_pre_buffer_seconds=pre_buffer_seconds,
    )

    video_paths = recording.export_videos()
    LOG.info("Vídeos exportados: %s", video_paths)
    LOG.info("Health pós-gravação: %s", camera_manager.health_summary())

    frames = recording.get_frames(analysis_camera_id)
    if not frames:
        raise AppError(f"Sem frames gravados para a câmara {analysis_camera_id}")

    frame_result = FrameSelector().select_frame(frames)
    LOG.info(
        "Frame selecionado | cam=%d | index=%d | ts=%.3f",
        frame_result.camera_id,
        frame_result.frame_index,
        frame_result.timestamp,
    )

    proceed, quality_payload = validate_selected_frame_quality(frame_result.frame)
    if not proceed:
        raise AppError("Operação cancelada devido à qualidade insuficiente do frame.")

    analyzer = ImpactAnalyzer(calibration_manager)
    point_selector = ZoomPointSelector()

    point_result = point_selector.select_point(
        frame_result.frame,
        snap_callback=lambda frame, point: analyzer.smart_snap(frame, point),
    )

    measurement = analyzer.compute_measurement(
        frame=frame_result.frame,
        clicked_point_px=point_result.final_point,
        call_line_world=call_line,
        auto_snap=False,
    )

    annotated = analyzer.draw_measurement_overlay(frame_result.frame, measurement)

    quality_analyzer = ImageQualityAnalyzer()
    quality_overlay = quality_analyzer.draw_overlay(annotated, quality_analyzer.analyze(frame_result.frame))

    original_frame_path = file_manager.save_image(attempt_dir / "frame_original.png", frame_result.frame)
    annotated_frame_path = file_manager.save_image(attempt_dir / "frame_annotated.png", quality_overlay)

    calibration_path = file_manager.calibration_path(calibration_name)

    measurement_payload = {
        "attempt_dir": str(attempt_dir),
        "attempt_id": attempt_dir.name,
        "athlete_name": athlete_name,
        "bib_number": bib_number,
        "analysis_camera_id": analysis_camera_id,
        "frame_index": frame_result.frame_index,
        "frame_timestamp": frame_result.timestamp,
        "clicked_point_px": point_result.clicked_point,
        "final_point_px": point_result.final_point,
        "world_point_cm": measurement.world_point_cm,
        "distance_cm": round(
            measurement.distance_cm,
            config.analysis.distance_precision_decimals,
        ),
        "projection_on_call_line_cm": measurement.projection_on_call_line_cm,
        "snap_debug": asdict(measurement.debug),
        "image_quality": quality_payload,
        "calibration": {
            "file": str(calibration_path),
            "sandbox_name": calibration_data.sandbox_name,
            "quality": asdict(calibration_data.quality),
        },
        "videos": {str(k): str(v) for k, v in video_paths.items()},
        "files": {
            "original_frame": str(original_frame_path),
            "annotated_frame": str(annotated_frame_path),
        },
        "camera_health": camera_manager.health_summary(),
        "camera_stats": [asdict(stat) for stat in camera_manager.stats()],
    }

    measurement_json_path = file_manager.save_json(
        attempt_dir / "measurement.json",
        measurement_payload,
    )

    csv_record = MeasurementRecord(
        attempt_id=attempt_dir.name,
        athlete_name=athlete_name,
        bib_number=bib_number,
        camera_id=analysis_camera_id,
        frame_index=frame_result.frame_index,
        timestamp_iso=file_manager.utc_now_iso(),
        clicked_point_px=point_result.clicked_point,
        snapped_point_px=point_result.final_point,
        world_point_cm=measurement.world_point_cm,
        distance_cm=round(
            measurement.distance_cm,
            config.analysis.distance_precision_decimals,
        ),
        calibration_file=str(calibration_path),
        original_frame_file=str(original_frame_path),
        annotated_frame_file=str(annotated_frame_path),
    )
    csv_path = file_manager.append_csv(file_manager.measurement_csv_path(), [csv_record])

    reporting = ReportingManager()

    manifest_payload = {
        "attempt_id": attempt_dir.name,
        "attempt_dir": str(attempt_dir),
        "files": {
            "measurement_json": str(measurement_json_path),
            "original_frame": str(original_frame_path),
            "annotated_frame": str(annotated_frame_path),
            "attempt_report": str(attempt_dir / "attempt_report.txt"),
        },
        "videos": {str(k): str(v) for k, v in video_paths.items()},
    }
    manifest_path = reporting.save_manifest(
        attempt_dir / "manifest.json",
        manifest_payload,
    )

    report_text = reporting.build_attempt_report_text(measurement_payload)
    report_path = reporting.save_attempt_report(
        attempt_dir / "attempt_report.txt",
        report_text,
    )

    athlete_history_path = file_manager.athlete_history_path(athlete_name, bib_number)
    athlete_history_entry = {
        "attempt_id": attempt_dir.name,
        "athlete_name": athlete_name,
        "bib_number": bib_number,
        "timestamp_iso": file_manager.utc_now_iso(),
        "distance_cm": round(
            measurement.distance_cm,
            config.analysis.distance_precision_decimals,
        ),
        "measurement_json": str(measurement_json_path),
        "annotated_frame_file": str(annotated_frame_path),
    }
    athlete_history_saved = reporting.append_athlete_history(
        athlete_history_path,
        athlete_history_entry,
    )

    LOG.info("Medição final: %.2f cm", measurement.distance_cm)
    LOG.info("image_quality: %s", quality_payload)
    LOG.info("measurement.json: %s", measurement_json_path)
    LOG.info("measurements.csv: %s", csv_path)
    LOG.info("manifest.json: %s", manifest_path)
    LOG.info("attempt_report.txt: %s", report_path)
    LOG.info("athlete_history: %s", athlete_history_saved)

    print(f"\nMedição final: {measurement.distance_cm:.2f} cm")
    print(f"Frame original: {original_frame_path}")
    print(f"Frame anotado: {annotated_frame_path}")
    print(f"JSON: {measurement_json_path}")
    print(f"CSV: {csv_path}")
    print(f"Manifest: {manifest_path}")
    print(f"Relatório: {report_path}")
    print(f"Histórico atleta: {athlete_history_saved}")

    preview = cv2.resize(quality_overlay, (1280, 720))
    cv2.imshow("LAP2GO - Resultado", preview)
    cv2.waitKey(0)
    cv2.destroyWindow("LAP2GO - Resultado")


def run_mode(
    config: ApplicationConfig,
    camera_manager: CameraManager,
    file_manager: FileManager,
    calibration_manager: CalibrationManager,
) -> None:
    while True:
        try:
            run_attempt(
                config=config,
                camera_manager=camera_manager,
                file_manager=file_manager,
                calibration_manager=calibration_manager,
            )
        except FrameSelectionCancelled as exc:
            LOG.warning(str(exc))
            print("Seleção de frame cancelada.")
        except PointSelectionCancelled as exc:
            LOG.warning(str(exc))
            print("Seleção do ponto cancelada.")
        except CalibrationCancelled as exc:
            LOG.warning(str(exc))
            print("Calibração cancelada.")
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            LOG.exception("Erro durante a tentativa: %s", exc)
            print(f"Erro na tentativa: {exc}")

        again = prompt_yes_no("\nPretende processar nova tentativa?", default_yes=True)
        if not again:
            break


def main() -> None:
    args = build_arg_parser().parse_args()

    config = load_app_config(args.config)
    file_manager = build_file_manager_from_config(config)

    log_path = configure_logging(Path(config.paths.logs_dir))
    LOG.info("Aplicação iniciada | log=%s | mode=%s", log_path, args.mode)

    camera_manager: Optional[CameraManager] = None

    try:
        camera_manager = CameraManager(config.cameras)
        camera_manager.start_all()

        if not camera_manager.wait_until_ready(
            min_cameras=config.recording.min_required_cameras,
            timeout_seconds=15.0,
        ):
            raise AppError(
                f"Número insuficiente de câmaras prontas. health={camera_manager.health_summary()}"
            )

        LOG.info("Câmaras prontas: %s", camera_manager.enabled_camera_ids())
        LOG.info("Health inicial: %s", camera_manager.health_summary())

        calibration_manager = CalibrationManager()

        if args.mode == "run":
            run_mode(config, camera_manager, file_manager, calibration_manager)
        elif args.mode == "calibrate":
            calibrate_mode(config, camera_manager, file_manager, calibration_manager)
        elif args.mode == "record":
            record_mode(config, camera_manager, file_manager)
        elif args.mode == "measure":
            measure_mode(config, camera_manager, file_manager, calibration_manager)
        else:
            raise AppError(f"Modo não suportado: {args.mode}")

    except KeyboardInterrupt:
        LOG.info("Aplicação interrompida pelo utilizador.")
        print("\nAplicação terminada pelo utilizador.")
    except Exception as exc:
        LOG.exception("Erro fatal: %s", exc)
        print(f"Erro fatal: {exc}")
    finally:
        if camera_manager is not None:
            camera_manager.stop_all()
        cv2.destroyAllWindows()
        LOG.info("Aplicação terminada.")


if __name__ == "__main__":
    main()