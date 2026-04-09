# Xu Ly Hien Tuong Giat Xam Khung Hinh tren mainCCTV / Detail Window

## 1. Dau hieu
Trieu chung da duoc ghi nhan:

- khung hinh raw hoac process bi xam tung phan
- co luc xam nua khung, co luc xam full khung
- luong process bi nang hon luong raw
- xay ra theo chu ky rat ngan, gan nhu frame nao cung co the bi

## 2. Nguyen nhan ky thuat co kha nang cao nhat
Trong phien ban cu, backend ghi de truc tiep cac file:

- `outputs/runtime/preview/*.jpg`
- `outputs/runtime/debug/*.jpg`
- `outputs/runtime/cameras/*.json`
- `outputs/runtime/process_latest.json`
- `outputs/runtime/agv_latest.json`

Trong khi do GUI doc lai chinh cac file nay theo chu ky cao.

Neu GUI doc dung luc backend dang `cv2.imwrite`, ket qua co the la:

- anh JPG chua ghi xong
- decoder doc duoc frame bi rach du lieu
- xuat hien khung xam, khung mo, khung vo

## 3. Ban va da duoc sua trong code
Da doi sang co che ghi atomic:

- ghi file tam
- `replace()` file dich sau khi ghi xong

File da sua:

- `mainProcess.py`
- `core/runtime_bridge.py`
- `mainCCTV.py`

Huong sua:

1. Anh preview/debug duoc encode ra bo nho, ghi vao file tam, roi moi replace file dich
2. JSON snapshot cung duoc ghi atomic
3. GUI giu lai frame tot gan nhat neu mot lan doc anh that bai

## 4. Neu van con giat sau khi da cap nhat code
Luc do uu tien nghi den tai qua ingest / infer / export:

- RTSP source khong on dinh
- FPS infer qua cao
- FPS display qua cao
- may dang qua tai CPU/GPU/IO

## 5. Cac tham so nen ha truoc
Trong `configs/runtime.json`, uu tien ha theo thu tu:

1. `grid_display_fps`
2. `detail_display_fps`
3. `slot_infer_fps_default`
4. `general_infer_fps_default`
5. `selected_infer_fps`
6. `detail_infer_fps`

Profile an toan de thu nghiem:

```json
{
  "grid_display_fps": 12.0,
  "detail_display_fps": 12.0,
  "slot_infer_fps_default": 12.0,
  "general_infer_fps_default": 8.0,
  "selected_infer_fps": 15.0,
  "detail_infer_fps": 15.0,
  "debug_export_fps": 6.0,
  "export_interval_ms": 120
}
```

## 6. Cach xac nhan da het loi
Sau khi cap nhat code:

1. chay `mainProcess.py`
2. chay `mainCCTV.py`
3. mo detail window cua 1 camera pallet va 1 camera trolley
4. quan sat lien tuc it nhat 2-3 phut

Ky vong:

- khong con xam nua khung / full khung theo chu ky
- neu co mat frame hiem hoi do RTSP, raw va process se cung mat ngat quang, khong phai chi process bi xam lien tuc

## 7. Ket luan
Neu trieu chung giam manh hoac bien mat sau ban sua atomic write, nguyen nhan chinh la race condition file IO giua backend va GUI.
