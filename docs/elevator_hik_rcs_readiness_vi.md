# Elevator Vision - HIK RCS Readiness

## 1. Muc tieu

Tai lieu nay chot lai chu trinh camera thang may trong project PIDVN25006 va cac dieu kien can co de tich hop voi AGV/RCS.

Trang thai hien tai:

- code workflow elevator da san sang
- HIK mapping cho thang may da duoc khai bao trong `configs/hik_rcs.json`
- tat ca lift workflow va HIK elevator mappings dang de `enabled=false`
- chi bat lai sau khi team AGV/RCS chot du command, position code va quy tac callback

## 2. Chu trinh thang may dang lam gi

Camera thang may khong chi bao "co vat / khong co vat". Chu trinh elevator bien ket qua Vision thanh mot workflow cap quyen an toan:

1. Camera doc frame va model detect object trong ROI thang may.
2. `ZoneReasoner` ket luan ROI co object muc tieu hay khong.
3. `StateTracker` lam on dinh `empty / occupied / unknown`.
4. `ElevatorRuntime` doc zone state va command tu AGV/RCS.
5. `ElevatorStateMachine` quyet dinh lift dang:
   - `IDLE_BLOCKED`
   - `IDLE_CLEAR`
   - `ENTRY_ARMED`
   - `TASK_ACTIVE`
   - `INTRUSION_ALARM`
   - `TASK_RELEASE`
   - `FAULT_UNKNOWN`
6. `mainProcess` chuyen lift state thanh payload control cho HIK:
   - `IDLE_CLEAR` -> `empty` -> `lockPosition(enable)`
   - fault -> `unknown` -> `lockPosition(disable)`
   - cac state con lai -> `occupied` -> `lockPosition(disable)`

Y nghia nghiep vu:

- chi khi cabin thang may clear on dinh thi AGV/FMR moi duoc cap quyen vao
- khi da authorize/task active/release/fault thi vi tri phai bi khoa
- neu camera stale/offline/unknown thi fail-safe ve disabled, khong suy doan cabin empty

## 3. File va config lien quan

- `configs/elevator.json`: cau hinh workflow lift, hien dang `enabled=false`
- `configs/hik_rcs.json`: mapping `lockPosition` cho `cam6:LIFT_1` va `cam7:LIFT_2`, hien dang `enabled=false`
- `core/elevator_state_machine.py`: state machine cap quyen
- `core/elevator_runtime.py`: doc command, build observation, xuat snapshot
- `mainProcess.py`: chuyen elevator snapshot thanh control payload cho HIK/RCS
- `tools/elevator_cmd.py`: tool test command local

## 4. Command AGV/RCS can gui cho Vision

Vision hien dang nhan command qua:

- `outputs/runtime/elevator_commands.json`

Danh sach command:

- `authorize`: xin cap quyen cho mot task/vehicle vao cabin
- `entry_complete`: AGV/FMR da vao cabin, task bat dau active
- `release`: task da duoc phep roi cabin
- `continue`: tiep tuc sau intrusion alarm
- `cancel`: huy token workflow hien tai

Moi command can co:

- `sequence`: so tang dan, bat buoc de chong xu ly lap
- `camera_id`: `cam6` hoac `cam7`
- `command`
- `task_id`: bat buoc voi `authorize`, va phai khop khi `entry_complete/release/continue`
- `vehicle_id`
- `expected_load_type`: `pallet` cho AMR, `trolley` cho FMR
- `timestamp`

## 5. Thong tin can chot voi team AGV/RCS

Can chot ro cac diem sau truoc khi bat `enabled=true`:

1. RCS position code dung de khoa/mo cua tung cabin:
   - `cam6:LIFT_1` -> `position_code` nao
   - `cam7:LIFT_2` -> `position_code` nao
2. AGV/RCS se gui command vao Vision bang cach nao:
   - ghi file JSON noi bo
   - HTTP endpoint moi trong Vision
   - hoac callback adapter rieng
3. `task_id` nao duoc xem la source of truth:
   - task code tu RCS
   - PDA task id
   - hay id noi bo cua adapter
4. Khi nao AGV gui:
   - `authorize`
   - `entry_complete`
   - `release`
   - `cancel`
5. Class nao duoc phep trong cabin:
   - AMR pallet: `pallet`, co cho phep `person` hay khong
   - FMR trolley: `trolley`, co cho phep `person` hay khong
6. Chinh sach khi intrusion:
   - AGV dung tai cho
   - RCS cancel task
   - hay operator xu ly roi gui `continue`

## 6. RCS can cau hinh gi

Tren RCS can dam bao:

- co position code thang may de `lockPosition` enable/disable
- endpoint callback cua Vision duoc allowlist neu RCS can goi nguoc
- network tu Vision toi RCS port RPC 8182 thong
- `clientCode` va `tokenCode` neu site bat authentication
- thoi gian retry/timeout phu hop voi chu trinh thang may

## 7. Checklist commissioning

Thu tu bat live khuyen nghi:

1. Dien `position_code` cho mapping thang may trong `configs/hik_rcs.json`.
2. Bat `dry_run=true`.
3. Bat tung lift trong `configs/elevator.json`.
4. Gui command bang `tools/elevator_cmd.py`.
5. Xac nhan snapshot:
   - `outputs/runtime/elevator_latest.json`
   - `outputs/runtime/agv_latest.json`
   - `outputs/runtime/hik_rcs/http_exchange.jsonl`
6. Xac nhan `IDLE_CLEAR` moi sinh enable.
7. Xac nhan `ENTRY_ARMED/TASK_ACTIVE/TASK_RELEASE/FAULT_UNKNOWN` deu sinh disable.
8. Chuyen `dry_run=false` va test voi RCS that.
9. Sau khi pass moi de AGV/RCS adapter gui command that.

## 8. Ket luan

Chu trinh elevator hien tai dung ve kien truc: Vision la lop cam bien va safety gate, AGV/RCS la lop dieu phoi task. De live chinh xac, dieu con thieu khong nam o model hay core state machine, ma nam o viec chot ma `position_code`, command timing va handshake voi team AGV/RCS.
