# Hybrid FG Bind/Unbind Process

## 1. Ket luan

FG khong duoc khoa cung theo mot mode duy nhat.

Trong van hanh thuc te, AMR va cong nhan co the cung dua pallet tu PK xuong FG. Vi vay Vision dung policy:

```json
"dispatch_policy": "hybrid_fg_managed"
```

Policy nay quyet dinh owner theo tung lan pallet vao/ra tung slot FG:

- AMR/RCS task dua pallet vao FG -> owner la `rcs_record`
- cong nhan dua pallet vao FG -> owner la `manual_vision`
- neu RCS dang lock bin/active task -> owner tam thoi la `rcs_record_pending`
- neu khong biet actual `ctnrCode` khi can unbind -> dua vao `needs_reconcile`

## 2. Co so API trong HIK document

Tai lieu `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1)` cung cap du co so:

- `bindCtnrAndBin`: bind/unbind container va bin, bat buoc co `ctnrCode`, `ctnrTyp`, va mot trong `stgBinCode` / `positionCode`.
- `agvCallback`: RCS goi ve third-party platform, co cac field `method`, `currentPositionCode`, `stgBinCode`, `taskCode`, `ctnrCode`, `ctnrTyp`.
- `bindNotify`: RCS notify thao tac bind/unbind, co `method=bindCtnrAndBin`, `indBind`, va `bindParam` gom `ctnrCode`, `ctnrType`, `stgBinCode`.
- `queryTaskStatus`: co the dung lam polling backup theo `taskCodes` hoac `agvCode`, nhung khong thay the `bindNotify` trong bai toan biet actual `ctnrCode` cua FG.

Vi vay huong chuan la yeu cau team AGV/RCS bat callback:

- `/service/rest/agvCallbackService/agvCallback`
- `/service/rest/agvCallbackService/bindNotify`

Code hien tai da co callback server nhan va luu cac route nay.

## 3. State machine tung slot FG

Moi mapping FG co state rieng trong:

```text
outputs/runtime/hik_rcs/bridge_state.json
```

Field chinh:

- `observed_state`: Vision thay `occupied` / `empty`
- `dispatch_policy`: `hybrid_fg_managed`
- `hybrid_session.owner`: `manual_vision`, `rcs_record`, `rcs_record_pending`, hoac rong
- `hybrid_session.actual_ctnr_code`: actual ctnr dang nam trong bin neu biet
- `hybrid_session.needs_reconcile`: can doi chieu RCS neu Vision khong du thong tin unbind an toan

## 4. Logic khi FG EMPTY -> OCCUPIED

### 4.1 Co callback RCS/Record

Neu Vision doc duoc `bindNotify`/`agvCallback` gan day cho dung `stgBinCode` hoac `positionCode`:

- lay `ctnrCode` that tu callback, vi du `PK_AA4`
- set owner `rcs_record`
- khong gui static bind `FG_AA1`

Ket qua:

```text
FG_AA1 = PK_AA4
```

### 4.2 Khong co callback, Vision thu static bind

Vision gui `bindCtnrAndBin(indBind="1")` voi static code cua FG, vi du:

```json
{
  "stgBinCode": "FG000203501013",
  "positionCode": "FG_AA2",
  "ctnrCode": "FG_AA2",
  "ctnrTyp": "2",
  "indBind": "1"
}
```

Neu RCS tra success:

- owner `manual_vision`
- session actual `FG_AA2`

Neu RCS tra bin da bind container khac, vi du `PK_AA4`:

- Vision chap nhan day la RCS-managed
- owner `rcs_record`
- actual `PK_AA4`
- khong retry static bind `FG_AA1`

Neu RCS tra `has been locked` / `has incomplete task`:

- owner `rcs_record_pending`
- khong spam retry
- doi callback/doi state sau do reconcile

## 5. Logic khi FG OCCUPIED -> EMPTY

Vision chi unbind khi biet `ctnrCode` can unbind:

- owner `manual_vision` -> unbind static FG code, vi du `FG_AA2`
- owner `rcs_record` va biet actual `PK_AA4` -> unbind `PK_AA4`
- khong biet actual ctnr -> khong unbind mu, set `needs_reconcile=true`

Quy tac nay tranh bug cu: Vision khong bao gio unbind sai `FG_AA1` neu bin dang that su bind `PK_AA4`.

## 6. Vi du van hanh mong muon

1. AMR mang `PK_AA4` xuong `FG_AA1`
   - RCS Record/bindNotify bao `ctnrCode=PK_AA4`
   - Vision set `FG_AA1 = PK_AA4`

2. Cong nhan mang pallet xuong `FG_AA2`
   - khong co callback RCS cho FG_AA2
   - Vision bind static `FG_AA2`

3. Cong nhan mang pallet xuong `FG_AA3`
   - Vision bind static `FG_AA3`

4. AMR mang `PK_AA1` xuong `FG_AA4`
   - RCS Record/bindNotify bao `ctnrCode=PK_AA1`
   - Vision set `FG_AA4 = PK_AA1`

5. Cong nhan mang pallet xuong `FG_AA5`
   - Vision bind static `FG_AA5`

Ket qua Storage Bin Management:

```text
FG_AA1 = PK_AA4
FG_AA2 = FG_AA2
FG_AA3 = FG_AA3
FG_AA4 = PK_AA1
FG_AA5 = FG_AA5
```

## 7. Checklist nghiem thu

1. Bat callback server cua Vision.
2. Yeu cau RCS cau hinh callback `agvCallback` va `bindNotify` ve Vision PC.
3. Dat pallet thu cong vao mot FG empty, xac nhan Vision bind static `FG_xx`.
4. Tao task AMR tra pallet vao mot FG empty, xac nhan RCS/bindNotify co actual `PK_xx`.
5. Xac nhan Vision khong gui static bind `FG_xx` de ghi de task AMR.
6. Lay pallet manual ra khoi FG, xac nhan Vision unbind static `FG_xx`.
7. Lay pallet AMR-delivered ra khoi FG, xac nhan Vision unbind actual `PK_xx` neu callback/response da cho biet.
8. Neu `needs_reconcile=true`, dung RCS Storage Bin Management hoac callback log de doi chieu actual ctnr.

## 8. Ket luan cam ket

Hang muc hybrid nay thuc hien duoc tren co so API HIK vi tai lieu co:

- API ghi bind/unbind: `bindCtnrAndBin`
- callback task co `stgBinCode`, `ctnrCode`: `agvCallback`
- callback bind/unbind truc tiep co `bindParam.ctnrCode`, `bindParam.stgBinCode`: `bindNotify`

Dieu kien de dat muc chac chan cao nhat la team AGV/RCS bat `bindNotify` cho `bindCtnrAndBin`. Neu chua bat, bridge van co fallback bang response cua `bindCtnrAndBin`, nhung callback la duong chuan de nghiem thu nha may.
