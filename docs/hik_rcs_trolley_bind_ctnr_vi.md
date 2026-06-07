# FMR Trolley - bindCtnrAndBin Integration

## 1. Muc tieu

Tai lieu nay chot huong truyen thong Vision -> HIK RCS cho chu trinh FMR trolley theo quyet dinh dung `bindCtnrAndBin`, dong bo voi cach mapping hien tai cua AMR pallet.

Trang thai da trien khai:

- da bo sung mapping trolley vao `configs/hik_rcs.json`
- tat ca mapping trolley dang `enabled=false`
- cac tham so business de trong de team AGV/RCS dien onsite
- khong anh huong cac mapping pallet dang chay

## 2. Co so API HIK

Theo `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1)`:

- `bindCtnrAndBin` dung de bind/unbind container va bin
- API nay ap dung cho CTU va FMR task
- `indBind="1"` la bind
- `indBind="0"` la unbind
- `ctnrCode` va `ctnrTyp` la bat buoc
- it nhat mot trong `stgBinCode` hoac `positionCode` phai co
- `characterValue` la trait value cho FMR roadway neu site can

## 3. Mapping da them vao hik_rcs.json

Da them cac camera/zone trolley:

- `cam1`: `A1`, `A2`, `A3`, `B1`, `B2`, `B3`
- `cam2`: `A5`
- `cam3`: `A3`, `A4`, `A5`
- `cam8`: `A1`, `A2`, `A3`, `B1`, `B2`, `B3`, `C1`, `C2`, `C3`

Moi mapping co dang:

```json
{
  "enabled": false,
  "camera_id": "cam1",
  "zone_id": "A1",
  "method": "bindCtnrAndBin",
  "position_code": "",
  "stg_bin_code": "",
  "ctnr_code": "",
  "ctnr_typ": "",
  "unknown_action": "lockPosition"
}
```

## 4. Tham so can team AGV/RCS cung cap

Moi vi tri trolley can chot:

- `camera_id`
- `zone_id`
- RCS `position_code` neu bind theo virtual rack/bin position
- RCS `stg_bin_code` neu bind theo storage bin
- `ctnr_code`: ma trolley/container RCS su dung cho vi tri/doi tuong do
- `ctnr_typ`: container type cua trolley trong RCS
- `bin_name` neu site bat custom bin ID
- `character_value` neu FMR roadway can trait value
- `lock_position_code` neu muon lockPosition bang ma khac `position_code`

Luu y quan trong:

- Neu chi dien `stg_bin_code` ma de trong `position_code`, `unknown_action=lockPosition` se can them `lock_position_code`.
- Neu `position_code` duoc dien dung, bridge co the dung chinh `position_code` de lock/unlock khi zone unknown.
- Khi chua chot du mapping, giu `enabled=false`.

## 5. Luong runtime

Luong xu ly trolley giong pallet:

1. Model detect `trolley`.
2. ROI state qua `StateTracker` thanh `occupied / empty / unknown`.
3. HIK bridge doc mapping trong `hik_rcs.json`.
4. Neu state `occupied` hop le:
   - goi `bindCtnrAndBin(indBind="1")`.
5. Neu state `empty` hop le:
   - goi `bindCtnrAndBin(indBind="0")`.
6. Neu state `unknown`:
   - neu `unknown_action="lockPosition"` thi khoa vi tri bang `lockPosition(indBind="0")`.

## 6. Quy trinh test

1. Dien mapping cho 1 zone trolley duy nhat.
2. Giu `dry_run=true`.
3. Bat `enabled=true` cho mapping do.
4. Dat trolley vao ROI, xac nhan log sinh `indBind=1`.
5. Keo trolley ra khoi ROI, xac nhan log sinh `indBind=0`.
6. Che camera/lam stale input, xac nhan sinh lock disable neu co `position_code`.
7. Doi `dry_run=false` va test voi RCS that.
8. Sau khi 1 zone pass moi nhan rong toan bo trolley zones.

## 7. Dieu kien acceptance

Trolley integration duoc xem la pass khi:

- `occupied` on dinh moi bind
- trolley di ngang qua ROI khong bind sai
- che khuat ngan/trung han khong unbind sai
- `empty` on dinh moi unbind
- `unknown` khong bao gio bi suy ra empty
- RCS response `code="0"` duoc log day du
- mapping sai tra business error ro rang, khong retry vo han voi loi non-retryable

## 8. Ket luan

Ve mat code, FMR trolley da duoc dua vao cung pipeline HIK voi pallet. Phan con lai la business mapping cua RCS: ma bin/position/container type/container code. Khi cac ma nay duoc dien va test tung zone, runtime co the bind/unbind trolley bang `bindCtnrAndBin` nhu pallet.
