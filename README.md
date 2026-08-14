# PIDVN25006 Vision Runtime

Runtime package for Panasonic PIDVN AGV Vision.

The production runtime is intentionally small:

- `mainProcess.py`: central backend for camera ingest, YOLO inference, zone reasoning, state tracking, runtime snapshot export, HIK RCS sync, callback API, and auto-dispatch.
- `mainCCTV.py`: PyQt6 monitoring frontend. It reads backend snapshots and preview/debug frames from `outputs/runtime`.
- `tools/run_forever.py`: watchdog supervisor for backend and frontend.
- `tools/roi_designer.py`: retained commissioning tool for drawing ROI when factory layout changes.
- `core/`: runtime modules imported by `mainProcess.py` and `mainCCTV.py`.
- `configs/`: camera, rule, runtime, GUI, HIK RCS, AMR/FMR auto-dispatch, and ROI zone configuration.
- `weights/best.pt`: production slot detector.
- `weights_elevatorbase/best.pt`: production elevator floor classifier.
- `weights_elevatorgate/best.pt`: expected future elevator gate classifier path. The code already supports it; if the file is missing, gate state is reported as `unknown`.

## Run

Windows:

```bat
run_forever.cmd
```

Linux:

```bash
./run_forever.sh
```

The supervisor starts both:

- backend: `mainProcess.py`
- frontend: `mainCCTV.py`

For backend-only maintenance:

```bash
./run_forever.sh --no-frontend
```

## Systemd

The production service is:

```text
deploy/systemd/pidvn25006.service
```

It starts `run_forever.sh` without `--no-frontend`, so the intended factory runtime includes both backend and CCTV frontend. On Linux, the supervisor still checks `DISPLAY` or `WAYLAND_DISPLAY`; if no graphical session is available, it keeps backend running and skips the frontend.

## Runtime Data Flow

```text
RTSP cameras
  -> core.camera_reader.FrameStore
  -> mainProcess batch inference via core.model_registry
  -> core.zone_reasoner / core.state_tracker
  -> outputs/runtime/process_latest.json
  -> outputs/runtime/agv_latest.json
  -> outputs/runtime/cameras/*.json
  -> outputs/runtime/preview/*.jpg
  -> outputs/runtime/debug/*.jpg when selected by frontend
  -> core.hik_rcs_bridge
  -> independent AMR/FMR lanes in core.auto_dispatcher
```

`mainCCTV.py` never performs inference. It only reads exported runtime state and images.

## Required Runtime Files

```text
assets/rtc_logo.png
configs/*.json
core/*.py
app/detail_window.py
mainProcess.py
mainCCTV.py
requirements.txt
run_forever.cmd
run_forever.sh
tools/run_forever.py
tools/roi_designer.py
weights/best.pt
weights_elevatorbase/best.pt
```

## ROI Tool

Use the ROI designer only during commissioning or when the physical layout changes:

```bash
python tools/roi_designer.py --source reference.jpg --output configs/zones_cam5.json --target-object pallet
```

## Config Reference

Operational documents:

- `docs/technical_operation_logic_vi.md`: full Vision AMR/FMR technical logic.
- `docs/site_operation_guide_vi.md`: short site operation guide.
- `docs/vision_auto_dispatch_api_contract_vi.md`: PDA/App Caller API contract.

`configs/ingest.json` controls camera input:

- `stream_profile`: RTSP channel profile, usually `main`.
- `latest_frame_only`: drop old buffered frames and process the newest frame.
- `reader_output_fps`: target decoded frame rate published to backend.
- `buffer_size`: OpenCV capture buffer size.
- `reconnect_delay_sec`: initial reconnect delay when a camera is offline.
- `rtsp_transport`: FFmpeg RTSP transport, usually `tcp`.
- `open_timeout_msec`: camera open timeout.
- `read_timeout_msec`: camera read timeout.
- `skip_sleep_ms`: short sleep while throttling frame publish rate.

`configs/rules.json` controls detection-to-zone state:

- `spatial_method`: how a detection box is matched to a zone polygon.
- `enter_window` / `enter_count`: how many recent positive observations are required before a zone becomes `occupied`.
- `exit_window` / `exit_count`: how many recent negative observations are required before a zone becomes `empty`.
- `enter_confirm_sec`: extra time confirmation before accepting `occupied`.
- `exit_confirm_sec`: extra time confirmation before accepting `empty`.
- `occupied_hold_sec`: minimum hold time before an occupied zone can become empty.
- `unknown_timeout_sec`: stale observation timeout before state becomes `unknown`.
- `conf_threshold`: YOLO/classifier confidence threshold.
- `img_size`: YOLO inference image size for slot cameras.
- `batch_size`: maximum number of due cameras inferred per scheduler loop.

`configs/runtime.json` controls backend/frontend runtime cadence:

- `slot_infer_fps_default`: inference target FPS for normal zone cameras.
- `selected_infer_fps`: inference target FPS for cameras opened in detail view.
- `grid_display_fps`: preview export FPS and frontend grid polling FPS.
- `detail_display_fps`: frontend detail-window polling FPS.
- `export_interval_ms`: JSON snapshot export and HIK sync interval.
- `debug_export_fps`: processed/debug image export FPS for selected cameras.
- `history_log_max_mb`: max size of each history log file.
- `history_log_backup_count`: number of rotated history logs kept.
- `occupied_session_break_sec`: delay before clearing the displayed occupied-since timestamp after a zone becomes empty.
- `log_cleanup_enabled`: enable output log cleanup.
- `log_cleanup_interval_sec`: cleanup check interval.
- `log_retention_hours`: age limit for stale runtime logs.
- `schedule_sleep_ms`: backend loop sleep time.
- `selected_priority_boost`: scheduler priority boost for selected/detail cameras.
- `offline_priority_penalty`: scheduler priority penalty for offline cameras.
- `preview_width` / `preview_height`: preview image size exported for CCTV grid.

## Runtime Boundary

Replay apps, experimental processors, old detector schedulers, manual HIK CLI tools, dataset samples, training run artifacts, and stale commissioning documents have been removed from this runtime package.

If a new capability is needed later, add it only when it is wired into either:

- `mainProcess.py` for backend behavior, or
- `mainCCTV.py` / `app/detail_window.py` for operator UI behavior.
