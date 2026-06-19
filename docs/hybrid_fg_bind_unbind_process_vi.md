# Hybrid FG Canonical Bind/Unbind Process

## 1. Ket luan

FG dang dung policy:

```json
"dispatch_policy": "hybrid_fg_canonical"
```

Muc tieu cua policy nay:

- Cong nhan dua pallet vao FG -> Vision bind static theo slot FG, vi du `FG_AA2 = FG_AA2`.
- AMR/RCS Record dua pallet tu PK xuong FG -> RCS co the bind tam thoi actual `ctnrCode` tu PK, vi du `FG_BB5 = PK_CC3`.
- Sau khi Vision biet actual `ctnrCode` dang nam o FG, Vision chuan hoa lai Storage Bin Management ve ma tinh cua FG:

```text
FG_BB5 = FG_BB5
```

Quy tac nay tranh loi trung identity: `PK_CC3` khong bi giu duoi FG, nen khi cong nhan dat pallet moi vao `PK_CC3`, Vision/RCS van bind PK bin binh thuong.

## 2. Co so API trong HIK document

Tai lieu `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1)` cung cap du co so:

- `bindCtnrAndBin`: bind/unbind container va bin, bat buoc co `ctnrCode`, `ctnrTyp`, va mot trong `stgBinCode` / `positionCode`.
- `bindNotify`: RCS notify thao tac bind/unbind, co `method=bindCtnrAndBin`, `indBind`, va `bindParam` gom `ctnrCode`, `ctnrType`, `stgBinCode`.
- `agvCallback`: co the cung cap them `taskCode`, `stgBinCode`, `ctnrCode`, `ctnrTyp`.

Tai lieu khong co API "rename/update ctnrCode" truc tiep. Vi vay cach chuan la mot transaction logic gom 2 lenh:

1. `bindCtnrAndBin(indBind="0")` de unbind actual ctnr dang nam trong FG.
2. `bindCtnrAndBin(indBind="1")` de bind static ctnr cua chinh slot FG.

## 3. Callback RCS can cau hinh

RCS Application Registration cho Vision:

```text
Name: VISION
Generated Code: VISIONRTC
Type: MES System/device access control service (WCS)
IP: 192.168.10.44
Port: 2112
Base Path: /service/rest
Invoke Type: REST method
Protocol: http
Enable Encryption: OFF
Task Notify -> bindCtnrAndBin -> Notification Path: /bindNotify
```

URL cuoi cung RCS goi ve Vision:

```text
http://192.168.10.44:2112/service/rest/bindNotify
```

Code callback server van chap nhan them duong legacy:

```text
/service/rest/agvCallbackService/bindNotify
```

## 4. State machine tung slot FG

Moi mapping FG co state rieng trong:

```text
outputs/runtime/hik_rcs/bridge_state.json
```

Field chinh:

- `observed_state`: Vision thay `occupied` / `empty`.
- `dispatch_policy`: `hybrid_fg_canonical`.
- `hybrid_session.owner`: `canonical_fg`, `rcs_record`, `rcs_record_pending`, hoac rong.
- `hybrid_session.actual_ctnr_code`: actual ctnr dang nam trong bin neu biet.
- `hybrid_session.canonical_source_ctnr_code`: ma PK/RCS dang can go khoi FG.
- `hybrid_session.canonical_target_ctnr_code`: ma FG static can bind lai.
- `hybrid_session.needs_reconcile`: can doi chieu neu transaction chua hoan thanh.

## 5. Logic FG EMPTY -> OCCUPIED

### 5.1 Cong nhan dua pallet vao FG

Khong co callback Record cho FG slot. Vision gui static bind:

```json
{
  "stgBinCode": "FG001103501013",
  "positionCode": "FG_BB5",
  "ctnrCode": "FG_BB5",
  "ctnrTyp": "2",
  "indBind": "1"
}
```

Ket qua:

```text
FG_BB5 = FG_BB5
```

### 5.2 AMR/RCS Record dua pallet tu PK xuong FG

Vi du AMR lay `PK_CC3` va tra vao `FG_BB5`.

RCS Record co the bind truoc:

```text
FG_BB5 = PK_CC3
```

Vision nhan biet actual `ctnrCode=PK_CC3` qua `bindNotify`, `agvCallback`, hoac response cua RCS. Sau do Vision thuc hien canonical transaction:

```json
{
  "stgBinCode": "FG001103501013",
  "positionCode": "FG_BB5",
  "ctnrCode": "PK_CC3",
  "ctnrTyp": "2",
  "indBind": "0"
}
```

roi:

```json
{
  "stgBinCode": "FG001103501013",
  "positionCode": "FG_BB5",
  "ctnrCode": "FG_BB5",
  "ctnrTyp": "2",
  "indBind": "1"
}
```

Ket qua cuoi:

```text
FG_BB5 = FG_BB5
PK_CC3 duoc giai phong de bind lai tai khu PK khi co pallet moi
```

Neu RCS tra `has been locked` / `has incomplete task`, Vision khong ket luan fail cuoi. Bridge se retry sau `retry_interval_sec` vi day thuong la giai doan AMR/task chua ket thuc.

## 6. Logic FG OCCUPIED -> EMPTY

Vision unbind ma dang biet gan nhat:

- neu FG da canonical -> unbind `FG_xx`.
- neu chua canonical va dang biet actual `PK_xx` -> unbind `PK_xx`.
- neu khong biet ma nao -> ghi state can reconcile, khong unbind mu.

Quy tac nay tranh viec gui unbind sai container.

## 7. Vi du van hanh mong muon

1. AMR mang `PK_AA4` xuong `FG_AA1`
   - RCS co the bind tam `FG_AA1 = PK_AA4`
   - Vision canonicalize thanh `FG_AA1 = FG_AA1`

2. Cong nhan mang pallet xuong `FG_AA2`
   - Vision bind static `FG_AA2`

3. Cong nhan mang pallet xuong `FG_AA3`
   - Vision bind static `FG_AA3`

4. AMR mang `PK_AA1` xuong `FG_AA4`
   - RCS co the bind tam `FG_AA4 = PK_AA1`
   - Vision canonicalize thanh `FG_AA4 = FG_AA4`

5. Cong nhan mang pallet xuong `FG_AA5`
   - Vision bind static `FG_AA5`

Ket qua Storage Bin Management sau khi Vision canonicalize:

```text
FG_AA1 = FG_AA1
FG_AA2 = FG_AA2
FG_AA3 = FG_AA3
FG_AA4 = FG_AA4
FG_AA5 = FG_AA5
```

## 8. Checklist nghiem thu

1. RCS bat Application Registration cho Vision voi Base Path `/service/rest`.
2. RCS bat Task Notify `bindCtnrAndBin` -> `/bindNotify`.
3. Vision PC mo firewall inbound TCP `2112`.
4. Xac nhan callback sinh file:
   - `outputs/runtime/hik_rcs/callbacks/bindNotify_latest.json`
   - `outputs/runtime/hik_rcs/callbacks/bindNotify.jsonl`
5. Dat pallet thu cong vao mot FG empty, xac nhan RCS Storage Bin Management hien `FG_xx = FG_xx`.
6. Tao task AMR tra pallet PK vao FG, xac nhan co thoi diem RCS Record bind `FG_xx = PK_xx`.
7. Doi Vision canonicalize, xac nhan RCS Storage Bin Management quay ve `FG_xx = FG_xx`.
8. Dat pallet moi vao lai vi tri PK vua duoc AMR lay, xac nhan PK bind lai thanh cong, khong bi loi `ctnrCode PK_xx has been bind`.
9. Lay pallet ra khoi FG, xac nhan Vision unbind dung ctnr hien hanh.
10. Neu `needs_reconcile=true`, doi chieu `bridge_state.json`, `http_exchange.jsonl`, `bindNotify.jsonl` va RCS Storage Bin Management.

## 9. Fail-safe

- Vision khong invent ma container moi. FG chi canonical ve ma tinh da cau hinh trong `hik_rcs.json`.
- Vision khong unbind mu khi khong biet ctnrCode.
- Transaction unbind-source/bind-static khong atomic o muc RCS API, nen bridge luu state va retry.
- Neu RCS dang lock bin do active task, bridge retry thay vi coi la loi cau hinh.

## 10. Ket luan cam ket

Hang muc nay thuc hien duoc tren co so API HIK vi tai lieu co du:

- API ghi bind/unbind: `bindCtnrAndBin`.
- Callback bind/unbind co actual ctnr: `bindNotify`.
- Callback task co the bo sung actual ctnr: `agvCallback`.

Dieu kien nghiem thu tot nhat la RCS bat `bindNotify` cho `bindCtnrAndBin` ve callback server cua Vision.
