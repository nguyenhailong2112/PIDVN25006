# RCS Record Managed Bind Conflict Resolution

## 1. Ket luan xu ly

Bug bind/unbind tai FG khong phai la loi detection. Day la xung dot ownership du lieu giua:

- Vision: nhin thay ROI `occupied` / `empty`
- RCS Record: quan ly container/pallet dang duoc AMR van chuyen tu PK xuong FG

Huong xu ly da trien khai:

- PK giu policy mac dinh `vision_managed_static`
- FG chuyen sang `dispatch_policy = rcs_record_managed`
- Vision khong gui `bindCtnrAndBin` tinh cho FG nua
- RCS Record la owner cua `ctnrCode` tai FG khi pallet duoc AMR tra xuong

## 2. Nguyen nhan goc

`positionCode` va `stgBinCode` la dinh danh vi tri/bin.

`ctnrCode` la dinh danh container/pallet.

Khi AMR lay hang tu `PK_BB4` va tra xuong `FG_AA3`, container dang di chuyen van la `PK_BB4`. Neu RCS Record bind `FG_AA3` voi `ctnrCode = PK_BB4` thi day la logic dung theo task carry-over cua RCS.

Neu Vision tiep tuc thay `FG_AA3 = occupied` va gui:

```json
{
  "stgBinCode": "FG000303501013",
  "ctnrCode": "FG_AA3",
  "ctnrTyp": "2",
  "indBind": "1"
}
```

thi Vision dang tranh quyen voi RCS Record. Day la ly do sinh loi dang gap tai hien truong.

## 3. Dispatch policy

Bridge HIK da ho tro `dispatch_policy` cho tung mapping:

| Policy | Y nghia | Co gui bind/unbind chinh khong |
| --- | --- | --- |
| `vision_managed_static` | Vision quan ly bind/unbind bang `ctnr_code` tinh trong config | Co |
| `rcs_record_managed` | RCS Record quan ly `ctnrCode`; Vision chi quan sat ROI | Khong |
| `observe_only` | Vision chi quan sat ROI, khong quan ly bind/unbind | Khong |

Neu mapping khong khai bao `dispatch_policy`, bridge mac dinh la `vision_managed_static` de khong pha hanh vi cu.

## 4. Cau hinh hien tai

### PK

PK van dung `vision_managed_static`.

Ly do:

- cong nhan dat pallet thu cong tai PK
- Vision can bind vi tri PK de RCS biet diem nao co pallet cho AMR lay
- `ctnrCode` tai PK dang duoc quy uoc bang ma diem PK, vi du `PK_BB4`

### FG

12 vi tri FG da chuyen sang:

```json
"dispatch_policy": "rcs_record_managed"
```

Ly do:

- pallet tai FG co the den tu bat ky vi tri PK
- `ctnrCode` tai FG phai la container/pallet AMR mang xuong
- RCS Record la lop biet source/destination cua task, Vision khong nen bind tinh `FG_AA*` / `FG_BB*`

## 5. Hanh vi runtime ky vong

### PK occupied

Vision gui `bindCtnrAndBin(indBind="1")` theo static `ctnr_code` PK.

Vi du:

```json
{
  "stgBinCode": "B0000403501013",
  "ctnrCode": "PK_BB4",
  "ctnrTyp": "2",
  "indBind": "1"
}
```

### PK empty

Vision gui `bindCtnrAndBin(indBind="0")` de unbind PK neu can. Neu RCS Record da unbind truoc khi AMR lay hang, loi already-unbound/not-bound co the duoc xem la ket qua khong nghiem trong trong qua trinh commissioning.

### FG occupied do AMR tra hang

Vision chi ghi nhan `observed_state = occupied`.

Vision khong gui:

```json
"ctnrCode": "FG_AA3"
```

RCS Record tu bind FG voi `ctnrCode` that cua pallet, vi du `PK_BB4`.

### FG empty do cong nhan lay hang ra

Vision chi ghi nhan `observed_state = empty`.

Vision khong tu unbind vi tri FG neu khong biet `ctnrCode` that dang duoc RCS bind trong bin do.

Neu site can Vision unbind FG sau khi cong nhan lay hang ra, bat buoc can them mot trong cac nguon du lieu sau:

- API query `stgBinCode -> ctnrCode` tu RCS
- callback/task event tu RCS tra ve `ctnrCode` thuc te
- task ledger do Vision tao khi trien khai auto dispatch

Khong co nguon du lieu nay thi Vision khong the unbind chinh xac mot `ctnrCode` dong ma no khong biet.

## 6. Checklist test sau khi cap nhat

1. Bat RCS Record cho chu trinh AMR PK -> FG.
2. Xoa/clean cac bind loi cu tren FG neu RCS dang con stale container.
3. Chay runtime Vision.
4. Dat pallet vao PK, xac nhan Vision van gui bind PK.
5. Tao task AMR lay pallet PK va tra xuong FG.
6. Khi FG thanh `occupied`, xac nhan log Vision khong con request `bindCtnrAndBin` voi `ctnrCode = FG_AA*` hoac `FG_BB*`.
7. Kiem tra RCS Storage Bin Management: FG duoc bind voi `ctnrCode` cua pallet tu PK, vi du `PK_BB4`.
8. Lay pallet ra khoi FG, xac nhan Vision khong spam unbind sai `FG_AA*` / `FG_BB*`.
9. Kiem tra `outputs/runtime/hik_rcs/bridge_state.json`: FG co `dispatch_policy = rcs_record_managed`, `main_binding_suppressed = true`.
10. Kiem tra PK van co request bind/unbind binh thuong.

## 7. Quy tac van hanh

Trong Phase 1 Manual:

- PK do Vision bind/unbind.
- FG do RCS Record bind/unbind khi pallet duoc AMR van chuyen.
- Khong tron mode AMR-delivery va manual-FG-static-binding tren cung mot cau hinh FG.

Neu can cho cong nhan dat pallet thu cong vao FG va muon Vision bind static FG, phai co mode rieng:

- tam dung AMR task lien quan FG
- tat RCS Record hoac tach bin/manual workflow ro rang
- doi FG policy ve `vision_managed_static` chi trong mode manual duoc kiem soat

Khong nen bat static FG binding song song voi RCS Record trong cung mot chu trinh live.
