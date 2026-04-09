# Tich Hop Trolley Vision -> HIK RCS-2000

## 1. Ket luan tu tai lieu HIK
Tai lieu chinh hang `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1)` xac nhan 3 API bind lien quan:

- `bindPodAndBerth`
- `bindPodAndMat`
- `bindCtnrAndBin`

Voi chu trinh trolley, API dung huong uu tien la:

- `bindPodAndBerth` khi RCS quan ly trolley/rack tai mot vi tri
- `bindPodAndMat` khi trolley business object gan voi `materialLot`

Khong nen ep trolley vao `bindCtnrAndBin` neu tren RCS doi tuong nghiep vu cua no dang la rack/pod.

## 2. Tu duy nghiep vu dung
Vision chi xac nhan:

- zone co trolley hay khong
- zone dang `occupied`, `empty`, hoac `unknown`

RCS can hieu zone do la business object nao:

- `positionCode`
- `podCode`
- hoac `materialLot`

Do do, trolley rollout co 2 tang:

1. Tang Vision:
   - detect trolley
   - zone state
   - dispatch `bind/unbind`
2. Tang business mapping:
   - AGV/RCS cap ma nghiep vu that

## 3. Chuong trinh hien tai da ho tro gi
Bridge trong code da ho tro day du:

- `bindPodAndBerth`
- `bindPodAndMat`
- `lockPosition`

Tuc la ve mat chuong trinh, trolley flow da san sang. Phan con thieu de live la mapping nghiep vu that.

## 4. Mapping toi thieu cho trolley
Moi zone trolley can chot:

- `camera_id`
- `zone_id`
- `method`
- `position_code`
- `pod_code`
- `pod_dir` neu site yeu cau
- `material_lot` neu site dung `bindPodAndMat`
- `unknown_action`

### Mau `bindPodAndBerth`
```json
{
  "enabled": true,
  "camera_id": "cam1",
  "zone_id": "A1",
  "method": "bindPodAndBerth",
  "position_code": "TR_A1",
  "pod_code": "TROLLEY_001",
  "pod_dir": "0",
  "unknown_action": "lockPosition"
}
```

### Mau `bindPodAndMat`
```json
{
  "enabled": true,
  "camera_id": "cam1",
  "zone_id": "A1",
  "method": "bindPodAndMat",
  "pod_code": "TROLLEY_001",
  "material_lot": "LOT_001",
  "position_code": "TR_A1",
  "unknown_action": "lockPosition"
}
```

## 5. Cac camera trolley hien co trong project
Project hien dang co:

- `cam1`
- `cam2`
- `cam3`
- `cam8`

Zone ROI hien co trong repo:

- `cam1`: `A1`, `A2`, `A3`, `B1`, `B2`, `B3`
- `cam2`: `A5`
- `cam3`: `A3`, `A4`, `A5`
- `cam8`: `A1`, `A2`, `A3`, `B1`, `B2`, `B3`, `C1`, `C2`, `C3`

Canh bao:

- bo zone trolley hien tai chua dong deu va co kha nang la bo ROI dang o trang thai tam
- truoc khi live trolley, can audit lai zone list va quy uoc ten zone

## 6. File template va file runtime de dien mapping
Da bo sung:

- `configs/hik_rcs_trolley_template.json`
- `configs/hik_rcs.json`

Muc dich:

- khong anh huong runtime production hien tai
- cho phep dien business mapping trolley mot cach tach biet voi pallet
- dong thoi da mirror san cac trolley mappings `enabled=false` vao `configs/hik_rcs.json` de co the van hanh pallet+trolley chung mot runtime khi business code da duoc chot

Quy trinh dung:

1. Lay template
2. Dien `position_code`, `pod_code`, `material_lot` neu can
3. Copy hoac doi chieu cac dong da chot vao `configs/hik_rcs.json`
4. Bat `enabled=true`
5. Test `dry_run=true`
6. Sau khi pass moi chuyen `dry_run=false`

## 7. Cac response dung khi test trolley
Neu request da den duoc RCS, nhung mapping sai, ban se gap business error kieu:

- `Map code ... not exist`
- `point code is not exist`
- `rack ... unbound storage`

Day la dau hieu:

- giao thuc da dung
- chi sai business mapping

Neu thong so bi thieu o code, bridge se tra:

- `CONFIG_ERROR`

Neu network/auth sai, ban se gap:

- `HTTP_ERROR`
- `IP NOT IN ALLOW LIST`

## 8. Chot huong rollout
Cho trolley, huong triên khai dung la:

1. Xac nhan doi tuong nghiep vu tren RCS la rack/pod hay rack+lot
2. Chon `bindPodAndBerth` hoac `bindPodAndMat`
3. Chot business mapping tu RCS
4. Dien vao `hik_rcs.json`
5. Test CLI
6. Test live 1 zone
7. Moi bat toan bo trolley cameras
