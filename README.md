# PIDVN25006 - Vision System V2

## 1. Mục tiêu hệ thống
Hệ thống này giám sát camera CCTV công nghiệp để xác định trạng thái ROI/zone cho trolley hoặc pallet và trả kết quả cho AGV/AMR.

Output quan trọng nhất của hệ thống là trạng thái zone:
- `1` / `occupied` / `bind`: có hàng trong ROI.
- `0` / `empty` / `unbind`: không có hàng trong ROI.
- `unknown`: chưa đủ tin cậy hoặc camera/lồng xử lý đang không ổn định.

## 2. Kiến trúc V2
Hệ thống V2 được chia thành 2 tiến trình đơn giản:

### `mainProcess.py`
Backend duy nhất của hệ thống:
- mở camera/video
- giữ latest frame của từng camera
- chọn camera đến hạn infer
- gom batch inference xuống GPU
- tính trạng thái zone
- xuất kết quả ROI cho AGV
- xuất preview/debug frame cho giao diện

### `mainCCTV.py`
Frontend nhẹ:
- không tự mở camera nữa
- chỉ đọc preview/debug do backend xuất ra
- hiển thị lưới CCTV
- mở detail camera
- gửi danh sách camera đang được chọn để backend ưu tiên infer

## 3. Các file cấu hình chính
- `configs/cameras.json`: danh sách camera, loại camera, model, zone config.
- `configs/rules.json`: rule occupancy/empty/unknown và batch inference.
- `configs/ingest.json`: cấu hình ingest camera/video.
- `configs/gui.json`: cấu hình lưới hiển thị GUI.
- `configs/runtime.json`: nhịp decode, infer, preview, priority boost.

## 4. Output quan trọng cho AGV
Backend luôn cập nhật file:
- `outputs/runtime/agv_latest.json`

Đây là file đơn giản nhất để tích hợp cho Version 3 với HIK Server/AGV.
Mỗi camera có danh sách `zones`, và mỗi zone có:
- `zone_id`
- `value`: `1`, `0`, hoặc `null`
- `binding`: `bind`, `unbind`, hoặc `unknown`
- `state`: `occupied`, `empty`, hoặc `unknown`
- `health`
- `score`

## 5. Cách chạy hệ thống
Mở 2 terminal:

### Terminal 1 - Backend
```bash
python mainProcess.py
```

### Terminal 2 - Frontend
```bash
python mainCCTV.py
```

`main.py` hiện chỉ là alias để mở frontend.

## 6. Luồng vận hành
1. Backend chạy trước.
2. Backend mở toàn bộ camera/video.
3. Backend infer và xuất trạng thái zone.
4. Frontend đọc preview/debug từ backend để hiển thị.
5. Khi người vận hành chọn camera trên GUI, frontend ghi camera đó vào runtime bridge.
6. Backend đọc danh sách camera được chọn và tăng priority infer cho camera đó.
7. AGV có thể đọc `outputs/runtime/agv_latest.json` để lấy câu trả lời zone ROI hiện tại.

## 7. Runtime bridge
Các file giao tiếp nhẹ giữa backend và frontend nằm ở `outputs/runtime/`:
- `selected_cameras.json`: camera đang được chọn trên UI.
- `process_latest.json`: tổng snapshot runtime.
- `agv_latest.json`: output ROI đơn giản cho AGV.
- `cameras/<camera_id>.json`: snapshot riêng cho từng camera.
- `preview/<camera_id>.jpg`: ảnh raw preview cho grid/detail.
- `debug/<camera_id>.jpg`: ảnh processed/debug cho detail camera được chọn.

## 8. Debug nhanh
### Nếu frontend mở nhưng không có hình
- kiểm tra backend đã chạy chưa.
- kiểm tra thư mục `outputs/runtime/preview` có ảnh hay chưa.
- kiểm tra `outputs/runtime/cameras/<camera_id>.json` có được cập nhật hay chưa.

### Nếu AGV chưa có output đúng
- kiểm tra `outputs/runtime/agv_latest.json`.
- kiểm tra camera đó có zone config đúng không.
- kiểm tra model/path camera trong `configs/cameras.json`.

### Nếu camera yếu hoặc chậm
- giảm `slot_infer_fps_default` / `general_infer_fps_default` trong `configs/runtime.json`.
- giảm `decode_fps_default`.
- giảm `img_size` trong `configs/rules.json`.
- giảm `grid_display_fps` nếu UI chưa đủ mượt.

## 9. Hướng mở rộng cho Version 3
Version 2 đã chừa sẵn chỗ cho tích hợp HIK Server/AGV:
- AGV chỉ cần gửi camera/zone đang quan tâm.
- Vision backend đã luôn duy trì trạng thái ROI hiện tại.
- Version 3 chỉ cần thêm adapter/API để đọc hoặc trả lời từ `agv_latest.json` hoặc state memory tương đương.