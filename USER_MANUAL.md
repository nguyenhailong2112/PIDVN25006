# Hướng dẫn sử dụng chương trình cho công nhân vận hành nhà máy

## 1. Mục đích
Chương trình dùng để:
- xem hình ảnh CCTV tại các vị trí trong nhà máy
- xem trạng thái có hàng / không có hàng tại từng vị trí trolley/pallet
- hỗ trợ hệ thống AGV lấy/trả hàng đúng vị trí

## 2. Trước khi chạy
Đảm bảo máy tính đã bật và hệ thống camera đang hoạt động.

## 3. Cách mở chương trình
### Bước 1: mở chương trình xử lý
Chạy:
```bash
python mainProcess.py
```

### Bước 2: mở chương trình giám sát hình ảnh
Chạy:
```bash
python mainCCTV.py
```

## 4. Cách hiểu màn hình
### Màn hình lưới camera
- mỗi ô là một camera
- nếu có hình nghĩa là backend đang nhận được dữ liệu từ camera đó
- nếu hiện `No Signal` nghĩa là camera chưa có hình hoặc backend chưa xuất preview

### Màn hình chi tiết camera
Khi bấm vào 1 camera:
- bên trái: ảnh gốc
- bên phải: ảnh đã xử lý
- bên dưới: thông tin trạng thái zone

## 5. Ý nghĩa trạng thái
- `occupied` / `1` / `bind`: vị trí đang có hàng
- `empty` / `0` / `unbind`: vị trí đang trống
- `unknown`: hệ thống chưa chắc chắn hoặc camera đang không ổn định

## 6. Cách thao tác cơ bản
1. Mở `mainProcess.py` trước.
2. Mở `mainCCTV.py` sau.
3. Quan sát lưới camera.
4. Bấm vào camera cần xem chi tiết.
5. Đọc trạng thái zone trên màn hình chi tiết.

## 7. Khi nào cần báo kỹ thuật viên
- camera không có hình lâu
- trạng thái `unknown` xuất hiện kéo dài bất thường
- hình ảnh bị đứng lâu
- chương trình không mở được
- AGV không nhận được trạng thái đúng với thực tế

## 8. Lưu ý vận hành
- Không tự ý sửa file cấu hình.
- Không đóng `mainProcess.py` khi đang sử dụng hệ thống.
- Nếu chỉ mở `mainCCTV.py` mà không mở `mainProcess.py`, màn hình có thể không có dữ liệu.
- Khi cần kiểm tra kỹ một camera, bấm vào camera đó để mở màn hình chi tiết.

## 9. Khởi động lại khi có lỗi nhẹ
1. Tắt `mainCCTV.py`.
2. Tắt `mainProcess.py`.
3. Mở lại `mainProcess.py`.
4. Mở lại `mainCCTV.py`.

## 10. Mục tiêu cuối cùng của hệ thống
Hệ thống này dùng để trả lời câu hỏi đơn giản nhất cho AGV:
- vị trí đang chọn có hàng hay không?
- nếu có thì trả `1 / occupied / bind`
- nếu không có thì trả `0 / empty / unbind`
- nếu chưa chắc chắn thì trả `unknown`