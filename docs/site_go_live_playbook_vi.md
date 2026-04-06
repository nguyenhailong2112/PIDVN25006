# Playbook Trien Khai Site Vision -> HIK RCS

Tai lieu nay la ban huong dan onsite ngan gon nhung day du de dua he thong Vision pallet vao commissioning tai nha may.

## 1. Muc tieu go-live

Phan onsite hien tai chi tap trung vao chu trinh pallet:

- `cam4`, `cam5`: khu Packing
- `cam9`, `cam10`: khu FG

Logic zone da duoc chot:

- neu bbox pallet cham ROI thi zone = `occupied`
- neu khong co pallet trong ROI thi zone = `empty`
- neu camera/runtime khong du tin cay thi zone = `unknown`

Spatial rule mac dinh cua he thong da duoc doi sang:

- `bbox_intersects`

## 2. Quy uoc mapping da chot

### 2.1 Packing

- `cam4` dung zone runtime: `A1` -> `C4`
- `cam5` dung zone runtime: `D1` -> `F4`
- `position_code` va `ctnr_code` theo quy uoc:
  - `PK_A1`, `PK_A2`, ..., `PK_F4`

### 2.2 FG

- `cam9` dung zone runtime: `A1` -> `A7`
- `cam10` dung zone runtime: `B1` -> `B6`
- `position_code` va `ctnr_code` theo quy uoc:
  - `FG_A1`, `FG_A2`, ..., `FG_B6`

### 2.3 Business method

Toan bo pallet zones hien tai deu dung:

- `method = bindCtnrAndBin`
- `ctnr_typ = 1`
- `unknown_action = lockPosition`

### 2.4 Truong bat buoc onsite phai dien

Onsite phai dien dung:

- `host`
- `stg_bin_code` cho tung zone
- `client_code` / `token_code` neu site bat buoc auth

## 3. File can sua onsite

### 3.1 RCS bridge config

File:

- [configs/hik_rcs.json](C:\Users\longn\PycharmProjects\PIDVN25006\configs\hik_rcs.json)

Onsite can sua:

1. `host`
2. `rpc_port` neu site khac `8182`
3. `dps_port` neu site khac `8083`
4. `client_code`, `token_code` neu AGV team cap
5. `stg_bin_code` cua tung zone
6. `dry_run`

### 3.2 ROI

Files ROI pallet:

- [configs/zones_cam4.json](C:\Users\longn\PycharmProjects\PIDVN25006\configs\zones_cam4.json)
- [configs/zones_cam5.json](C:\Users\longn\PycharmProjects\PIDVN25006\configs\zones_cam5.json)
- [configs/zones_cam9.json](C:\Users\longn\PycharmProjects\PIDVN25006\configs\zones_cam9.json)
- [configs/zones_cam10.json](C:\Users\longn\PycharmProjects\PIDVN25006\configs\zones_cam10.json)

Luu y audit:

- `cam9` hien tai co `A6` va `A7` dang trung polygon, can check va sua ROI onsite

## 4. Trinh tu onsite dung

1. Kiem tra IP may Vision.
2. Gui IP may Vision cho team AGV/RCS de whitelist.
3. Xac nhan server RCS va port API.
4. Dien `host` va `stg_bin_code` vao `hik_rcs.json`.
5. Giu `dry_run = true`.
6. Test logic bang CLI:

```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam4 --zone-id A1 --state occupied --dry-run
python tools/hik_rcs_cli.py bind-zone --camera-id cam4 --zone-id A1 --state empty --dry-run
```

7. Test request that:

```bash
python tools/hik_rcs_cli.py probe-bin --ctnr-typ 1 --stg-bin-code <STG_BIN_CODE_THAT>
```

8. Doc log:

- [outputs/runtime/hik_rcs/http_exchange.jsonl](C:\Users\longn\PycharmProjects\PIDVN25006\outputs\runtime\hik_rcs\http_exchange.jsonl)

9. Kiem tra tren RCS:

- `Operation -> Log -> Interface Call Log`

10. Khi request that pass, doi:

```json
"dry_run": false
```

11. Test live mot zone duy nhat:

```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam4 --zone-id A1 --state occupied
python tools/hik_rcs_cli.py bind-zone --camera-id cam4 --zone-id A1 --state empty
```

12. Neu live CLI pass, moi chay backend:

```bash
python mainProcess.py
```

## 5. Cach ket luan dung/sai

### Truyen thong dung khi:

- request toi dung `host:port`
- RCS tra JSON business response that
- log local co request/response
- `Interface Call Log` tren RCS co record moi

### Chua dung khi:

- `404 no found`: sai endpoint
- `IP NOT IN ALLOW LIST`: chua duoc whitelist
- `401/403`: auth chua dung
- timeout: mang/service chua thong

## 6. Nhung diem co y khong live ngay

- `cam6`, `cam7` thang may van de `enabled = false`
- Ly do: can team AGV chot xu ly task elevator active truoc khi bat interlock live

## 7. Cau chot

Code hien tai da du de di commissioning onsite.

Onsite khong con la bai toan "viet them giao thuc", ma la bai toan:

- dien dung IP server
- dien dung `stg_bin_code`
- duoc whitelist
- test theo dung trinh tu
