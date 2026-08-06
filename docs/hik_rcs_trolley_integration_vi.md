# Tich Hop FMR Trolley Vision -> HIK RCS-2000

## 1. Ket luan trien khai

Chu trinh FMR trolley hien tai da duoc quy chuan theo cung mot pipeline voi AMR pallet:

- API runtime: `bindCtnrAndBin`
- Policy: `hybrid_canonical`
- Owner canonical rieng: `canonical_trolley`
- Callback bat buoc: `bindNotify`

Khong su dung `bindPodAndBerth` hoac `bindPodAndMat` cho mapping trolley hien tai, vi mapping ma site dang cung cap va chu trinh can dong bo deu di theo container/bin.

## 2. Vai tro cua Vision

Vision chi lam cac viec sau:

- Detect trolley trong ROI.
- On dinh trang thai ROI thanh `OCCUPIED`, `EMPTY`, hoac `UNKNOWN`.
- Goi `bindCtnrAndBin` theo mapping Vision-RCS trong `configs/hik_rcs.json`.
- Nhan `bindNotify` tu RCS de biet actual `ctnrCode` dang nam o slot.
- Canonical hoa slot ve static `ctnr_code` cua chinh slot khi can.

Vision khong dieu phoi FMR trong tai lieu nay va khong can biet toan bo task graph cua RCS.

## 3. Cac khu vuc trolley

| Camera | Khu vuc | Zone can check | Ghi chu |
|---|---|---|---|
| `cam2` | Coil | `A1` -> `A5` | 5 diem |
| `cam3` | Warehouse | `A1`, `A2`, `B1`, `B2` | 4 diem |
| `cam8` | 3T | `A1` -> `A9` | 9 diem, gom 3 cot FILO |
| `cam11` | Coil | `A1` -> `A7` | 7 diem |
| `cam7` | Thang may | lift zone | Khong thuoc bind/unbind trolley, cho AGV chot de bat `blockArea` |

Tong diem bind/unbind trolley dang quan ly: 25.

## 4. Vi sao can hybrid_canonical

Trong van hanh song song FMR va con nguoi, RCS co the bind `ctnrCode` theo doi tuong duoc FMR mang tu diem pick sang diem put. Neu giu nguyen actual code nay tai diem put, diem pick co the khong bind lai duoc khi co trolley moi, vi `ctnrCode` cu van dang bi RCS xem la da nam o diem put.

`hybrid_canonical` giai quyet bang cach:

1. Cho phep Vision hoc actual `ctnrCode` tu `bindNotify`.
2. Unbind dung actual code neu actual code khac static code cua slot.
3. Bind lai static code cua slot.
4. Khi slot EMPTY, unbind theo actual/static code ma session dang quan ly.

Nhu vay moi slot trolley se tro ve quy uoc de kiem soat truc quan:

```text
COIL_FF10 -> COIL_FF10
WH_A1     -> WH_A1
3T_A1     -> 3T_A1
COIL_AA1  -> COIL_AA1
```

## 5. Yeu cau RCS

Can team AGV/RCS xac nhan:

- Tat ca `position_code`, `stg_bin_code`, `ctnr_code`, `ctnr_typ` trong `configs/hik_rcs.json` dung voi RCS.
- RCS da bat Task Notify `bindCtnrAndBin`.
- Notification path tro ve Vision la `/bindNotify`.
- Base path Vision la `/service/rest`.
- RCS gui du thong tin `ctnrCode`, `ctnrType` hoac `ctnrTyp`, va `stgBinCode` hoac `positionCode` trong notify.

Endpoint:

```text
http://<VISION_IP>:2112/service/rest/bindNotify
```

## 6. Test onsite toi thieu

### Test 1 - Manual trolley

1. Dat trolley thu cong vao mot slot trolley.
2. Vision phai bind static `ctnr_code` cua slot.
3. Lay trolley ra.
4. Vision phai unbind thanh cong dung code cua slot.

### Test 2 - FMR mang trolley tu slot khac den

1. Cho FMR thuc hien task pick/put trolley.
2. Kiem tra RCS gui `bindNotify` ve Vision.
3. Neu RCS bind actual code khac static code cua slot put, Vision phai canonical hoa ve static code cua slot put.
4. Kiem tra diem pick co the bind lai trolley moi binh thuong.

### Test 3 - Locked/incomplete task

1. Trong luc FMR dang lam task, khong ep Vision sua bind/unbind tai diem dang bi RCS lock.
2. Vision phai log loi business va giu session can reconcile.
3. Sau khi task ket thuc, Vision xu ly lai theo trang thai ROI on dinh.

## 7. File can xem khi debug

- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- `outputs/runtime/hik_rcs/bridge_state.json`
- `outputs/runtime/hik_rcs/callbacks/bindNotify_latest.json`
- `outputs/runtime/hik_rcs/callbacks/bindNotify.jsonl`

## 8. Ket luan

FMR trolley da san sang chay chung runtime voi AMR pallet theo co che canonical. Dieu kien ngoai Vision can dam bao la RCS mapping dung va `bindNotify` that su ve du truong du lieu. Khi hai dieu kien nay dat, Vision co du co so de bind/unbind va sua xung dot actual/static `ctnrCode` cho toan bo diem trolley.
