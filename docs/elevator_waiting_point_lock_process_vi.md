# Cam6 AMR Pallet Elevator - Waiting Point Lock Process

## 1. Ket luan thiet ke

Voi rang buoc hien tai, Vision khong nhan duoc callback authorize/task/elevator tu RCS. Vision chi co the truyen trang thai sang RCS bang `lockPosition` tren cac diem `Waiting Point`.

Do do process cam6 dung de live la:

- Camera 6 quan sat ROI cabin `LIFT_1`
- neu cabin `occupied` hoac `unknown` -> lock cac Waiting Point
- neu cabin `empty` on dinh -> unlock cac Waiting Point
- AMR chi co the di toi Waiting Point khi Waiting Point duoc unlock
- khi AMR toi Waiting Point, logic goi thang may va dieu khien AGV Mode van do team AGV/RCS xu ly

Vision khong goi thang may, khong doc log thang may, khong goi `continueTask`, va khong dieu khien AMR truc tiep trong process nay.

## 2. Mapping da chuan bi

Trong `configs/hik_rcs.json` da co 2 mapping cho cam6:

```json
{
  "enabled": false,
  "mapping_id": "cam6_lift1_waiting_floor1",
  "camera_id": "cam6",
  "zone_id": "LIFT_1",
  "method": "lockPosition",
  "position_code": "WTP1FA",
  "unknown_action": "lockPosition"
}
```

```json
{
  "enabled": false,
  "mapping_id": "cam6_lift1_waiting_floor2",
  "camera_id": "cam6",
  "zone_id": "LIFT_1",
  "method": "lockPosition",
  "position_code": "WTP2FA",
  "unknown_action": "lockPosition"
}
```

Khi chot dung ma RCS:

- doi `position_code` neu ma that khac `WTP1FA` / `WTP2FA`
- doi `enabled=true` cho tung mapping can live
- nen test voi `dry_run=true` truoc khi `dry_run=false`

## 3. Logic lockPosition

HIK `lockPosition` dung `indBind` nhu sau:

- `indBind="1"`: enable vi tri
- `indBind="0"`: disable vi tri

Bridge cua Vision dang map:

- zone `occupied` -> desired lock state `disabled` -> `lockPosition(indBind="0")`
- zone `empty` -> desired lock state `enabled` -> `lockPosition(indBind="1")`
- zone `unknown` -> fail-safe `disabled` -> `lockPosition(indBind="0")`

Y nghia:

- cabin co vat, camera mat tin cay, hoac state khong chac chan -> AMR khong duoc di toi Waiting Point
- cabin empty on dinh -> AMR duoc di toi Waiting Point de goi thang may

## 4. Chu trinh van hanh thuc te

### 4.1 AMR tu tang 1 len tang 2, chua mang pallet

1. AMR o diem sac tang 1.
2. Vision quan sat `LIFT_1`.
3. Neu `LIFT_1=occupied/unknown`, Vision lock `WTP1FA` va `WTP2FA`.
4. AMR khong vao duoc Waiting Point tang 1, nen khong goi thang.
5. Khi `LIFT_1=empty` on dinh, Vision unlock `WTP1FA` va `WTP2FA`.
6. AMR di toi Waiting Point tang 1.
7. RCS/AGV goi thang, chuyen AGV Mode, mo cua.
8. AMR di vao cabin va len tang 2.

### 4.2 AMR tu tang 2 xuong tang 1, co pallet

1. AMR lay pallet tai PK.
2. AMR can di toi Waiting Point tang 2.
3. Vision tiep tuc quan sat `LIFT_1`.
4. Neu cabin dang co pallet/person/obstacle/trolley hoac unknown -> lock `WTP1FA`, `WTP2FA`.
5. Neu cabin empty on dinh -> unlock `WTP1FA`, `WTP2FA`.
6. AMR di toi Waiting Point tang 2, goi thang va vao cabin.
7. Vi AMR mang pallet, camera co the detect `pallet`; cabin se thanh `occupied` va Vision lock cac Waiting Point trong khi cabin dang bi su dung.
8. Khi AMR ra khoi cabin va cabin empty on dinh, Vision unlock lai cac Waiting Point.

### 4.3 Cac chuyen pallet FG -> PK va PK -> FG tiep theo

Khong can reset mode bang tay. Vision la reactive gate:

- cabin empty -> unlock
- cabin occupied/unknown -> lock

Chu trinh lap lai lien tuc.

## 5. Co can reset lockPosition sau khi AMR ra khoi thang may khong?

Khong can reset rieng neu camera thay duoc trang thai cabin dung.

Sau khi AMR ra khoi cabin:

- neu ROI khong con object -> `empty` -> Vision gui enable Waiting Point
- neu con pallet/person/obstacle/trolley -> `occupied` -> tiep tuc lock
- neu camera stale/offline/unknown -> tiep tuc lock

Day la reset theo state, khong phai reset theo event.

## 6. Co can continueTask sau khi unlock Waiting Point khong?

Vision khong nen tu goi `continueTask` trong mode hien tai, vi Vision khong co `taskCode` va khong nhan callback task tu RCS.

Can chot voi team AGV/RCS:

- neu task AMR dang cho vi Waiting Point bi lock, khi Vision unlock point thi RCS co tu tiep tuc task khong?
- neu task bi fail/cancel khi point lock, AGV/RCS se tao lai task hay can operator thao tac?
- RCS co the dam bao Waiting Point lock chi lam task pending, khong lam task failed khong?

Neu RCS yeu cau `continueTask`, team AGV phai cung cap cho Vision/adapter it nhat:

- `taskCode`
- thoi diem can continue
- rule retry/fail-safe

Khong co cac thong tin nay thi Vision khong goi `continueTask`.

## 7. Gioi han hien tai: model khong detect AMR

Model hien co 4 class:

- `pallet`
- `trolley`
- `person`
- `obstacle`

Khong co class `AMR`.

He qua:

- khi AMR vao cabin ma khong mang pallet, Vision co the van thay cabin `empty`
- neu he thong chi co mot AMR va RCS quan ly task active duy nhat, rui ro nay co the chap nhan trong giai doan pilot
- neu co nhieu AMR hoac can safety interlock nghiem ngat, phai co them mot trong cac tin hieu sau:
  - train them class `AMR`
  - AGV/RCS gui signal AMR entered/exited cabin
  - them virtual point/sensor/PLC signal bao cabin dang bi AMR su dung
  - camera/logic rieng nhan dien than AMR

Day la gioi han vat ly cua bai toan, khong the khac phuc hoan hao chi bang `lockPosition` neu Vision khong nhin thay AMR va khong nhan event tu RCS.

## 8. Person co duoc tinh la occupied khong?

Config cam6 hien tai dung:

```json
"target_object": "*"
```

Nghia la bat ky class nao trong ROI cung lam cabin `occupied`, bao gom `person`.

Day la fail-safe mac dinh. Neu site quyet dinh person duoc phep o trong cabin khi AMR su dung, nhung person khong duoc lam khoa Waiting Point, co the doi target object thanh danh sach tinh, vi du:

```json
"target_object": "pallet,trolley,obstacle"
```

Tuy nhien khong khuyen nghi doi tru khi da co danh gia safety, vi person o cabin truoc khi AMR goi thang se khong con chan AMR.

## 9. Checklist cau hinh truoc live

1. Xac nhan ROI `LIFT_1` tren cam6 bao tron dung vung cabin.
2. Xac nhan `target_object`:
   - fail-safe: `*`
   - cho phep person khong chan AMR: `pallet,trolley,obstacle`
3. Xac nhan Waiting Point RCS:
   - tang 1: `WTP1FA` hay ma khac
   - tang 2: `WTP2FA` hay ma khac
4. Dien dung `position_code` trong `configs/hik_rcs.json`.
5. Bat `enabled=true` cho mapping cam6 can test.
6. De `dry_run=true`.
7. Chay runtime va xem log dry-run.
8. Test cabin empty -> phai sinh `lockPosition(indBind="1")`.
9. Test cabin co pallet/person/obstacle -> phai sinh `lockPosition(indBind="0")`.
10. Rut camera/lam stale stream -> phai sinh hoac giu disabled.
11. Chuyen `dry_run=false` khi dry-run pass.
12. Test voi RCS real tung Waiting Point.

## 10. Checklist nghiem thu voi AGV/RCS

### Case A - Cabin dang empty

- Vision state: `LIFT_1=empty`
- RCS point `WTP1FA/WTP2FA`: enabled
- AMR di duoc toi Waiting Point
- AMR goi thang theo logic AGV

### Case B - Cabin co pallet/object

- Vision state: `LIFT_1=occupied`
- RCS point `WTP1FA/WTP2FA`: disabled
- AMR khong di duoc toi Waiting Point
- AMR khong goi thang

### Case C - Camera mat tin cay

- Tat stream/rut camera/lam stale input
- Vision/RCS phai fail-safe ve disabled
- AMR khong duoc vao Waiting Point

### Case D - Unlock xong AMR co tiep tuc task khong

- Tao task khi Waiting Point dang bi lock
- Sau do lam cabin empty de Vision unlock
- Xac nhan RCS co tu tiep tuc task hay can tao lai/continue
- Ghi lai ket qua nay thanh rule van hanh

### Case E - AMR khong mang pallet

- AMR vao cabin khong co pallet
- Xac nhan co rui ro Vision khong nhin thay AMR hay khong
- Neu rui ro khong chap nhan, phai them AMR detection hoac event tu AGV/RCS

## 11. Ket luan

Phuong an dung cho dieu kien hien tai la Waiting Point lock gate:

- Vision khong dieu khien thang may
- Vision khong dieu khien AMR
- Vision chi khoa/mo cac Waiting Point bang `lockPosition`
- RCS/AGV chi duoc goi thang khi Waiting Point duoc Vision mo

Day la phuong an gon nhat, dung vai tro cua Vision, va co the live nhanh neu team AGV xac nhan `positionCode` va co che task pending khi Waiting Point bi lock.
