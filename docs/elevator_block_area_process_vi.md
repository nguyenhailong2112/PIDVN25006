# Cam6 AMR Pallet Elevator - Block Area Process

## 1. Muc tieu

Tai lieu nay mo ta mode moi cho elevator AMR pallet:

- `lockPosition` duoc OFF cho chu trinh elevator
- `blockArea` duoc ON thay the de chan/mo vung cho Waiting Point
- Vision van giu fail-safe neu cabin stale/unknown

## 2. Y nghia API

Theo tai lieu `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1)`:

- `lockPosition`: enable/disable mot position cu the
- `blockArea`: empty/unblock mot area

Voi elevator, `blockArea` hop vai tro hon vi muon chan ca vung waiting/entry thay vi chi mot point.

`indBind` cua `blockArea`:

- `1` = empty / block area
- `0` = unblock area

Voi elevator:

- `occupied` hoac `unknown` -> block area -> `indBind="1"`
- `empty` on dinh -> unblock area -> `indBind="0"`

## 3. Cau hinh

Trong `configs/hik_rcs.json`, elevator mappings (`cam6`, `cam7`) dung:

```json
{
  "method": "blockArea",
  "position_code": "WTPF1",
  "matter_area": "WTPF1",
  "control_mod": "-1",
  "pause": "0",
  "notice_third": "0",
  "unknown_action": "none"
}
```

Neu RCS site dung area ID khac `position_code`, team onsite co the doi:

- `matter_area`
- `block_area_code` neu muon dung ten khac
- `control_mod`
- `target_area` khi `control_mod=2`

## 4. Payload blockArea

Bridge nay goi HIK theo payload co ban:

```json
{
  "reqCode": "PID",
  "matterArea": "WTPF1",
  "indBind": "1",
  "pause": "0",
  "controlMod": "-1",
  "noticeThird": "0"
}
```

Neu site can mode `controlMod=2`, them:

```json
{
  "targetArea": "BLK1"
}
```

## 5. Luong van hanh

### 5.1 Cabin occupied

1. Camera cam6/cam7 thay cabin `occupied`.
2. Vision gui `blockArea(indBind="1")`.
3. RCS block area, AMR ben ngoai khong duoc vao vung nay.

### 5.2 Cabin empty

1. Camera thay cabin `empty` on dinh.
2. Vision gui `blockArea(indBind="0")`.
3. RCS unblock area, AMR duoc phep tiep can Waiting Point.

### 5.3 Camera unknown/stale

1. Camera mat health, stale stream, hoac ROI khong tin cay.
2. Vision fail-safe = block area.
3. Gui `blockArea(indBind="1")`.

## 6. Manual test

Test payload block/unblock truc tiep bang CLI:

```bash
python tools/hik_rcs_cli.py block-area --matter-area WTPF1 --action block
python tools/hik_rcs_cli.py block-area --matter-area WTPF1 --action unblock
```

Neu muon mo phong dung payload AGV sample:

```bash
python tools/hik_rcs_cli.py block-area --matter-area BLK1 --action block --control-mod 2 --target-area BLK1
```

## 7. Checklist nghiem thu

1. Xac nhan area ID cho elevator tren RCS.
2. Dien dung `matter_area` cho tung mapping.
3. Neu dung blocking mode thi giu `control_mod=-1`.
4. Neu site muon sample team AGV, chot lai `control_mod` va `target_area`.
5. Test occupied -> block.
6. Test empty -> unblock.
7. Test unknown/stale -> block fail-safe.
8. Kiem tra log HTTP `blockArea` trong `outputs/runtime/hik_rcs/http_exchange.jsonl`.
