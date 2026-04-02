# PIDVN25006 - AGV Vision CCTV Runtime

Tác giả dự án: Nguyễn Hải Long - RTC Computer Vision

## 1. Mục tiêu hệ thống

Hệ thống này dùng camera CCTV công nghiệp để xác nhận trạng thái hàng tại các vị trí làm việc với AGV/AMR:

- `occupied` / `bind` / `1`: vị trí đang có hàng
- `empty` / `unbind` / `0`: vị trí đang trống
- `unknown`: chưa đủ chắc chắn hoặc camera/runtime đang không ổn định

Mục tiêu cuối cùng của phần mềm là:

1. Nhận hình từ camera/video.
2. Suy luận trạng thái zone/ROI theo từng camera.
3. Hiển thị giám sát cho người vận hành.
4. Xuất trạng thái zone cho hệ thống AGV/AMR.
5. Tùy chọn đồng bộ trực tiếp sang HIK RCS-2000 bằng REST API.

---

## 2. Kiến trúc hệ thống hiện tại

Kiến trúc khuyến nghị hiện tại là V2, tách backend và frontend:

### 2.1 Backend - `mainProcess.py`

Đây là tiến trình trung tâm của hệ thống, chịu trách nhiệm:

- mở camera RTSP hoặc video replay
- giữ `latest frame` cho từng camera
- chọn camera đến hạn infer
- gom batch inference xuống GPU
- suy luận trạng thái zone
- ghi history thay đổi trạng thái
- xuất preview/debug cho giao diện
- xuất snapshot runtime cho AGV
- tùy chọn bridge sang HIK RCS

### 2.2 Frontend - `mainCCTV.py`

Đây là giao diện giám sát nhẹ:

- không tự mở camera
- chỉ đọc dữ liệu do backend export
- hiển thị grid camera
- mở cửa sổ detail camera
- chọn camera ưu tiên để backend tăng nhịp infer

### 2.3 Các chế độ main khác

- `main.py`: phiên bản V1/legacy, vẫn hữu ích làm code tham chiếu
- `main_origin_monitor_gui.py`: monitor kiểu origin/processed từ giai đoạn trước
- `app/main_runtime.py`, `app/main_replay.py`, `app/main_replay_multi.py`: các luồng chạy thử nghiệm/replay

Trong triển khai thật, ưu tiên:

- backend: `python mainProcess.py`
- frontend: `python mainCCTV.py`

---

## 3. Luồng dữ liệu tổng thể

Luồng xử lý chuẩn của hệ thống:

`Camera/Video -> CameraReader/VideoFileReader -> FrameStore -> Scheduler -> YOLO batch inference -> ZoneReasoner -> StateTracker -> Runtime Export -> GUI / AGV / HIK RCS`

Giải thích ngắn:

1. Camera/video được đọc liên tục.
2. Hệ thống chỉ giữ frame mới nhất để giảm độ trễ.
3. Backend chọn camera nào cần infer theo mức ưu tiên và FPS mục tiêu.
4. YOLO chạy batch để tận dụng GPU tốt hơn.
5. Detections được quy đổi sang zone observation.
6. `StateTracker` áp dụng hysteresis để tránh flicker.
7. Nếu dữ liệu stale quá ngưỡng, trạng thái bị ép về `unknown`.
8. Kết quả được xuất sang file runtime, GUI, AGV và bridge HIK.

---

## 4. Cấu trúc thư mục quan trọng

### 4.1 Entrypoint

- `mainProcess.py`: backend chính
- `mainCCTV.py`: frontend chính
- `main.py`: runtime V1
- `main_origin_monitor_gui.py`: monitor thử nghiệm/legacy

### 4.2 Thư mục cấu hình

- `configs/cameras.json`: danh sách camera, nguồn, model, zone config
- `configs/rules.json`: luật enter/exit/unknown, threshold, batch size
- `configs/ingest.json`: cấu hình RTSP/video ingest
- `configs/runtime.json`: nhịp decode/infer/export/preview
- `configs/gui.json`: cấu hình giao diện
- `configs/hik_rcs.json`: cấu hình bridge HIK RCS-2000
- `configs/zones_*.json`: polygon zone theo từng camera

### 4.3 Core modules

- `core/camera_reader.py`: đọc RTSP/live
- `core/video_file_reader.py`: đọc file replay
- `core/model_registry.py`: quản lý cache model YOLO
- `core/zone_reasoner.py`: map detection -> zone observation
- `core/state_tracker.py`: state machine occupied/empty/unknown
- `core/runtime_bridge.py`: file bridge giữa backend và frontend
- `core/hik_rcs_client.py`: HTTP client gọi HIK RCS
- `core/hik_rcs_bridge.py`: chuyển zone state sang action RCS
- `core/hik_callback_server.py`: nhận callback từ RCS

### 4.4 Output runtime

Hệ thống dùng `outputs/runtime/` làm bridge dữ liệu:

- `outputs/runtime/process_latest.json`: snapshot runtime toàn hệ
- `outputs/runtime/agv_latest.json`: snapshot gọn cho AGV
- `outputs/runtime/selected_cameras.json`: camera đang được chọn từ UI
- `outputs/runtime/cameras/<camera_id>.json`: snapshot từng camera
- `outputs/runtime/preview/<camera_id>.jpg`: ảnh preview cho grid
- `outputs/runtime/debug/<camera_id>.jpg`: ảnh debug detail
- `outputs/runtime/hik_rcs/`: request/response/state/callback của bridge HIK

### 4.5 Output khác

- `outputs/history/*.jsonl`: log thay đổi trạng thái zone

---

## 5. Ý nghĩa trạng thái zone

Trạng thái zone là đầu ra nghiệp vụ quan trọng nhất của dự án.

### 5.1 Trạng thái logic

- `occupied`: hệ thống tin rằng vị trí đang có hàng
- `empty`: hệ thống tin rằng vị trí đang trống
- `unknown`: chưa thể kết luận an toàn

### 5.2 Quy đổi đầu ra

- `occupied` -> `value=1`, `binding=bind`
- `empty` -> `value=0`, `binding=unbind`
- `unknown` -> `value=null`, `binding=unknown`

### 5.3 Ý nghĩa vận hành

- `occupied`: AGV không nên coi vị trí là trống
- `empty`: AGV có thể coi vị trí là trống
- `unknown`: cần fail-safe, không được suy diễn bừa thành `empty`

---

## 6. Cách hệ thống suy luận trạng thái

### 6.1 Detections -> Zone

Mỗi zone có:

- `zone_id`
- `target_object`
- polygon chuẩn hóa

Một zone chỉ quan tâm object đúng class của nó.

### 6.2 Spatial method

Trong `configs/rules.json`, hệ thống hỗ trợ:

- `bbox_center`
- `bbox_all_corners`

Khuyến nghị bài toán công nghiệp:

- dùng `bbox_all_corners` để chỉ coi là `occupied` khi bbox nằm gọn trong ROI

### 6.3 Hysteresis

`StateTracker` dùng:

- `enter_window`, `enter_count`
- `exit_window`, `exit_count`

Mục tiêu:

- tránh flicker
- tránh flip trạng thái khi detection drop ngắn hạn

### 6.4 Unknown timeout

Nếu camera hoặc pipeline không cập nhật đủ mới:

- trạng thái sẽ bị ép về `unknown`
- tuyệt đối không tự suy diễn sang `empty`

---

## 7. Cách chạy hệ thống

### 7.1 Chạy tiêu chuẩn

Mở 2 terminal:

### Terminal 1 - Backend

```bash
python mainProcess.py
```

### Terminal 2 - Frontend

```bash
python mainCCTV.py
```

### 7.1.1 Chay mot cham va tu restart khi crash

Tren Ubuntu Desktop/Server, khuyen nghi uu tien chay bang supervisor:

```bash
chmod +x run_forever.sh
./run_forever.sh
```

Neu dang o Windows moi dung:

```bat
run_forever.cmd
```

Hoac goi truc tiep supervisor:

```bash
python tools/run_forever.py
```

Supervisor se:

- tu dong mo `mainProcess.py`
- tu dong mo `mainCCTV.py`
- theo doi 2 tien trinh nay lien tuc
- tien trinh nao exit bat thuong se duoc khoi dong lai
- ghi log watchdog tai `outputs/runtime/supervisor/supervisor.log`

Co the chay chi backend:

```bash
./run_forever.sh --no-frontend
```

Luu y quan trong:

- supervisor chi hoat dong khi may tinh va user session van con hoat dong
- neu may shutdown hoac user session ket thuc, tat ca process trong session deu dung
- tren Ubuntu, neu muon tu dong chay lai sau reboot, can dang ky them `systemd`
- tren Windows, neu muon tu dong chay lai sau reboot/logon, can dang ky them Task Scheduler hoac service Windows

### 7.1.2 Ubuntu Server voi `systemd`

Neu may la Ubuntu Server hoac ban muon he thong tu len lai sau reboot, hay dung file mau:

- `deploy/systemd/pidvn25006.service`

Quy trinh khuyen nghi:

1. copy project vao duong dan on dinh, vi du `/opt/PIDVN25006`
2. sua `User`, `WorkingDirectory`, `ExecStart` trong file service cho dung may that
3. copy file service vao:

```bash
sudo cp deploy/systemd/pidvn25006.service /etc/systemd/system/
```

4. nap lai `systemd`:

```bash
sudo systemctl daemon-reload
```

5. bat auto-start:

```bash
sudo systemctl enable pidvn25006.service
```

6. start service:

```bash
sudo systemctl start pidvn25006.service
```

7. xem trang thai:

```bash
sudo systemctl status pidvn25006.service
```

Khuyen nghi cho Ubuntu Server:

- dung `ExecStart=/opt/PIDVN25006/run_forever.sh --no-frontend`
- frontend neu can thi mo rieng tren Ubuntu Desktop hoac may monitor

### 7.2 Chạy chỉ backend

Hữu ích khi:

- test inference
- test AGV snapshot
- test bridge HIK
- debug hiệu năng

```bash
python mainProcess.py
```

### 7.2.1 Tham so supervisor

Supervisor ho tro mot so tham so:

```bash
./run_forever.sh --frontend-delay-sec 5 --restart-delay-sec 3 --crash-backoff-sec 10
```

Y nghia:

- `--frontend-delay-sec`: doi bao lau roi moi mo giao dien sau khi backend da start
- `--restart-delay-sec`: do tre restart thong thuong
- `--crash-backoff-sec`: do tre restart khi process crash qua nhanh
- `--poll-interval-sec`: chu ky watchdog kiem tra child process
- `--no-frontend`: chi giu backend song

Neu dang o Ubuntu Server hoac may khong co giao dien:

- chay `--no-frontend`
- giu backend sinh output runtime va HIK bridge
- neu can auto-start sau reboot, uu tien `systemd`

Luu y:

- `tools/run_forever.py` hien tai tu kiem tra `DISPLAY`/`WAYLAND_DISPLAY`
- neu chay tren Linux headless ma ban quen `--no-frontend`, supervisor se canh bao va tu dong chay backend-only thay vi crash-loop frontend

### 7.3 Chạy callback server HIK riêng

```bash
python tools/hik_rcs_cli.py serve-callbacks
```

### 7.3.1 Thu muc log cua supervisor

Khi chay bang `run_forever.sh`, `run_forever.cmd` hoac `tools/run_forever.py`, can theo doi them:

- `outputs/runtime/supervisor/supervisor.log`

File nay dung de truy vet:

- backend da duoc start luc nao
- frontend da duoc start luc nao
- process nao crash
- code exit cua child process la gi
- watchdog da restart lai bao nhieu lan

### 7.4 Chạy test bridge HIK ở chế độ giả lập

```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam1 --zone-id A1 --state occupied --dry-run
```

---

## 8. Cấu hình chi tiết

### 8.1 `configs/cameras.json`

Mỗi camera gồm:

- `camera_id`
- `camera_type`
- `name`
- `source_type`: `video`, `rtsp`, `live`
- `source_path`
- `model_path`
- `zone_config`
- `infer_every_n_frames`
- `enabled`

### 8.1.1 `camera_type`

Các loại chính:

- `trolley_slot`
- `pallet_slot`
- `general_monitoring`

### 8.1.2 Khi sửa file này

Cần đảm bảo:

- đường dẫn model đúng
- đường dẫn video/RTSP đúng
- camera slot có `zone_config`
- `enabled=true` cho camera muốn chạy

### 8.2 `configs/rules.json`

Thông số quan trọng:

- `spatial_method`
- `enter_window`
- `enter_count`
- `exit_window`
- `exit_count`
- `unknown_timeout_sec`
- `conf_threshold`
- `img_size`
- `batch_size`

### Gợi ý chỉnh

- tăng `enter_count` nếu muốn chống false positive mạnh hơn
- tăng `exit_count` nếu muốn chống false empty mạnh hơn
- giảm `img_size` để giảm tải GPU
- giảm `batch_size` nếu VRAM không đủ

### 8.3 `configs/ingest.json`

Thông số chính:

- `stream_profile`
- `latest_frame_only`
- `reader_output_fps`
- `expected_source_fps`
- `buffer_size`
- `reconnect_delay_sec`
- `rtsp_transport`
- `open_timeout_msec`
- `read_timeout_msec`

### Gợi ý chỉnh

- mạng yếu: tăng `read_timeout_msec`
- muốn giảm delay: giữ `latest_frame_only=true`, `buffer_size=1`
- camera HIK sub-stream: `stream_profile=sub`

### 8.4 `configs/runtime.json`

Thông số backend quan trọng:

- `decode_fps_default`
- `slot_infer_fps_default`
- `general_infer_fps_default`
- `selected_infer_fps`
- `detail_infer_fps`
- `grid_display_fps`
- `detail_display_fps`
- `export_interval_ms`
- `debug_export_fps`
- `selected_priority_boost`

### Gợi ý chỉnh

- GPU yếu: giảm `slot_infer_fps_default`, `general_infer_fps_default`
- UI giật: giảm `grid_display_fps`
- cần detail mượt hơn: tăng `detail_infer_fps`

### 8.5 `configs/gui.json`

Thông số giao diện:

- số hàng/cột grid
- kích thước tile
- khoảng cách tile
- `tile_view_mode`

### 8.6 `configs/hik_rcs.json`

Đây là cấu hình tích hợp HIK RCS-2000.

Các trường chính:

- `enabled`
- `dry_run`
- `host`
- `rpc_port`
- `dps_port`
- `client_code`
- `token_code`
- `callback_server`
- `mappings`

### 8.6.1 Ý nghĩa `mappings`

Mỗi mapping là một quy tắc:

- camera nào
- zone nào
- gọi API HIK nào
- mã nghiệp vụ HIK tương ứng là gì

Ví dụ:

- `bindPodAndBerth`
- `bindPodAndMat`
- `bindCtnrAndBin`

### 8.6.2 Lưu ý rất quan trọng

Bridge HIK không thể tự bịa ra `positionCode`, `podCode`, `materialLot`, `ctnrCode`.

Bạn bắt buộc phải được HIK/WMS/AGV xác nhận:

- zone nào ứng với mã nào trong RCS
- loại đối tượng nào đang được quản lý
- `unknown` sẽ được xử lý bằng `lockPosition` hay cách khác

### 8.6.3 Chế độ an toàn

Khuyến nghị:

- để `dry_run=true` khi test lần đầu
- chỉ `enabled=true` sau khi mapping thật đã được xác nhận

---

## 9. Tích hợp HIK RCS-2000

### 9.1 Điều bridge đang làm

Bridge đọc kết quả zone từ backend và xử lý:

- `occupied` -> bind
- `empty` -> unbind
- `unknown` -> lockPosition nếu mapping yêu cầu

Bridge chỉ dispatch khi:

- trạng thái thay đổi
- hoặc request trước đó thất bại và đến kỳ retry

### 9.2 Callback từ RCS

Bridge hỗ trợ nhận:

- `agvCallback`
- `warnCallback`
- `bindNotify`

Dữ liệu callback được lưu vào:

- `outputs/runtime/hik_rcs/callbacks/`

### 9.3 Log giao tiếp HIK

Request/response được lưu tại:

- `outputs/runtime/hik_rcs/http_exchange.jsonl`

State bridge được lưu tại:

- `outputs/runtime/hik_rcs/bridge_state.json`

### 9.4 CLI hỗ trợ

Ví dụ:

```bash
python tools/hik_rcs_cli.py query-agv --map-short-name test
python tools/hik_rcs_cli.py query-task --task-code TASK-001
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action disable
python tools/hik_rcs_cli.py call-rpc genAgvSchedulingTask payload.json
```

---

## 10. Quy trình vận hành chuẩn

### 10.1 Trước khi chạy

Kiểm tra:

- camera online
- model đúng đường dẫn
- zone config đúng camera
- GPU/driver ổn
- `configs/hik_rcs.json` đúng nếu dùng HIK bridge
- neu chay production lien tuc tren Ubuntu, uu tien dung `run_forever.sh` thay vi mo tay 2 terminal

### 10.2 Trong khi chạy

Theo dõi:

- grid camera có hình không
- detail camera có zone đúng không
- `outputs/runtime/agv_latest.json` có cập nhật không
- log backend có lỗi reconnect/model/config không
- `outputs/runtime/supervisor/supervisor.log` co ghi nhan restart bat thuong khong

### 10.3 Khi đóng hệ thống

Thứ tự khuyến nghị:

1. đóng `mainCCTV.py`
2. đóng `mainProcess.py`

Neu dang chay bang supervisor:

1. nhan `Ctrl+C` tai cua so supervisor
2. cho watchdog dong backend/frontend co kiem soat

---

## 11. Debug nhanh

### 11.1 Frontend mở nhưng không có hình

Kiểm tra:

- backend có đang chạy không
- `outputs/runtime/preview/` có ảnh không
- `outputs/runtime/cameras/<camera_id>.json` có được cập nhật không

### 11.2 Zone sai

Kiểm tra:

- `configs/zones_*.json`
- `target_object`
- `spatial_method`
- model có detect đúng class không

### 11.3 Zone bị nhấp nháy

Kiểm tra và chỉnh:

- `enter_window`, `enter_count`
- `exit_window`, `exit_count`
- `unknown_timeout_sec`

### 11.4 Camera RTSP hay offline

Kiểm tra:

- URL RTSP
- tài khoản mật khẩu
- `stream_profile`
- timeout trong `configs/ingest.json`

### 11.5 GPU quá tải

Giảm:

- `slot_infer_fps_default`
- `general_infer_fps_default`
- `img_size`
- `batch_size`

### 11.6 HIK bridge không gửi request

Kiểm tra:

- `configs/hik_rcs.json` có `enabled=true` chưa
- mapping đã `enabled=true` chưa
- `dry_run` có đang bật không
- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- zone hiện tại có đang `unknown` vì health/score không đủ không

### 11.7 HIK bridge gửi request nhưng AGV không phản ứng

Kiểm tra:

- `positionCode`/`podCode`/`materialLot`/`ctnrCode` có đúng mã thật trong RCS không
- `client_code` và `token_code` có đúng không
- RCS có nhận callback hay không
- phía HIK có đang kỳ vọng API khác với use-case hiện tại không

---

## 12. Mở rộng hệ thống

Các hướng mở rộng rõ ràng nhất:

- thêm camera mới bằng `configs/cameras.json`
- thêm zone mới bằng `configs/zones_*.json`
- thêm loại mapping HIK mới trong `core/hik_rcs_bridge.py`
- thêm API HIK mới trong `core/hik_rcs_client.py`
- thêm dashboard giám sát runtime
- thêm persistence/DB thay cho file bridge nếu cần scale

---

## 13. Checklist triển khai tại nhà máy

### 13.1 Checklist phần cứng

- camera đúng vị trí
- ánh sáng ổn định
- mạng nội bộ ổn
- GPU đủ tải

### 13.2 Checklist phần mềm

- môi trường Python đầy đủ
- model đúng version
- config camera đúng
- config zone đúng
- config runtime phù hợp hiệu năng máy

### 13.3 Checklist tích hợp AGV

- xác nhận API HIK cần dùng
- xác nhận `positionCode`
- xác nhận `podCode/materialLot/ctnrCode`
- xác nhận `client_code`, `token_code`
- xác nhận callback URL
- test `dry_run`
- test request thật
- test callback thật
- test fail-safe `unknown`

---

## 14. Giới hạn hiện tại cần hiểu đúng

Đây là điểm rất quan trọng.

Code hiện tại đã hoàn chỉnh về mặt luồng phần mềm, nhưng để chạy production 100% thì vẫn cần đầu vào nghiệp vụ đúng:

- mã HIK RCS thật
- token thật
- host/port thật
- test live với server RCS thật

Nếu Vision chỉ biết có hàng hay không có hàng, mà chưa biết ID đối tượng nghiệp vụ, thì bridge chưa thể tự động gọi bind/unbind đúng nghĩa nếu chưa có mapping phù hợp.

---

## 15. File tài liệu liên quan

- `docs/hik_rcs_vision_integration_vi.md`: hướng dẫn bridge HIK chi tiết
- `docs/hik_rcs_commissioning_step_by_step_vi.md`: hướng dẫn triển khai cầm tay chỉ việc Vision -> HIK RCS
- `USER_MANUAL.md`: tài liệu cho công nhân vận hành

---

## 16. Kết luận

Phiên bản hiện tại của dự án đã có:

- pipeline Vision hoàn chỉnh
- GUI giám sát
- snapshot cho AGV
- bridge tích hợp HIK RCS
- tài liệu vận hành và debug

Khi cần triển khai thực tế, hãy luôn làm theo thứ tự:

1. xác nhận config camera/model/zone
2. chạy backend
3. kiểm tra GUI và snapshot
4. bật HIK bridge ở `dry_run`
5. xác nhận mapping thật
6. mới chuyển sang request thật
