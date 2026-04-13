# UBUNTU DESKTOP RUNBOOK - PIDVN25006

Tai lieu nay la huong dan cầm tay chi viec de dua `PIDVN25006` len may Ubuntu Desktop va van hanh ngoai hien truong.

Muc tieu:

1. Cai dat dung moi truong Python va dependency.
2. Chay he thong dung cach cho Ubuntu Desktop.
3. Giu backend + frontend tu dong song bang watchdog.
4. Tu dong khoi dong lai sau login cua Ubuntu Desktop.
5. Biet cach check log, check trang thai va xu ly su co.

Tai lieu nay duoc viet cho Ubuntu Desktop, khong phai Ubuntu Server.
Neu may la Ubuntu Server headless, uu tien xem them:

- `deploy/systemd/pidvn25006.service`
- `docs/hik_rcs_commissioning_step_by_step_vi.md`

---

## 1. Muc tieu van hanh tren Ubuntu Desktop

Khi may Ubuntu Desktop duoc bat len va nguoi van hanh login:

- watchdog duoc mo
- backend `mainProcess.py` duoc chay
- frontend `mainCCTV.py` duoc chay
- neu backend hoac frontend crash, watchdog tu dong start lai
- Vision tiep tuc xuat runtime va bridge sang HIK RCS neu config cho phep

Kien truc van hanh:

`run_forever.sh -> tools/run_forever.py -> mainProcess.py + mainCCTV.py`

Trong thuc te:

- `run_forever.sh` la launcher Linux
- `tools/run_forever.py` la supervisor/watchdog
- `mainProcess.py` la backend xu ly va bridge HIK
- `mainCCTV.py` la giao dien giam sat

---

## 2. Gia dinh va dieu kien truoc khi bat dau

Tai lieu nay gia dinh:

- he dieu hanh: Ubuntu Desktop
- user chay he thong: user van hanh hoac user ky thuat
- project da duoc copy day du vao may Ubuntu
- camera/RTSP da o cung mang voi may Ubuntu
- GPU/driver da duoc cai neu site dung GPU

Ban can co:

- quyen shell tren Ubuntu
- quyen sua file trong thu muc project
- thong tin HIK/RCS neu co bat bridge

---

## 3. Chon thu muc dat du an

Khuyen nghi dat project o mot duong dan co dinh, vi du:

```bash
/opt/PIDVN25006
```

Hoac neu khong muon dat o `/opt`, co the dat trong home:

```bash
/home/<username>/PIDVN25006
```

Khuyen nghi thuc te:

- dat o duong dan co dinh
- khong dat trong thu muc tam
- khong doi ten folder lung tung sau khi da cau hinh autostart

Trong tai lieu nay, vi du se dung:

```bash
/opt/PIDVN25006
```

Neu may cua ban dat duong dan khac, hay thay tat ca duong dan theo may that.

---

## 4. Kiem tra he thong Ubuntu truoc khi cai

Mo terminal va chay:

```bash
uname -a
lsb_release -a
whoami
pwd
```

Muc dich:

- xac nhan dung Ubuntu
- xac nhan user dang login
- xac nhan duong dan hien tai

Neu muon check desktop session:

```bash
echo "$XDG_CURRENT_DESKTOP"
echo "$DISPLAY"
echo "$WAYLAND_DISPLAY"
```

Ky vong:

- Ubuntu Desktop co `DISPLAY` hoac `WAYLAND_DISPLAY`
- neu 2 bien nay rong, frontend co the khong mo duoc

---

## 5. Cai Python va virtual environment

### 5.1 Kiem tra Python

```bash
python3 --version
which python3
```

Khuyen nghi:

- Python 3.10+ hoac 3.11

### 5.2 Cai `venv` neu chua co

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 5.3 Tao virtualenv

```bash
cd /opt/PIDVN25006
python3 -m venv .venv
```

### 5.4 Kich hoat virtualenv

```bash
source .venv/bin/activate
```

Sau khi kich hoat, prompt thuong se hien:

```bash
(.venv)
```

### 5.5 Nang cap pip

```bash
pip install --upgrade pip setuptools wheel
```

### 5.6 Cai dependency

```bash
pip install -r requirements.txt
```

Neu site dung GPU, ban can cai dung ban PyTorch/CUDA phu hop.
Buoc nay phai theo dung driver va version CUDA cua may.

Neu chua co GPU hoac chua xac nhan CUDA, co the test bang CPU truoc.

---

## 6. Kiem tra tai nguyen va camera truoc khi chay

### 6.1 Kiem tra model

```bash
ls -lh weights/
```

### 6.2 Kiem tra config camera

```bash
cat configs/cameras.json
```

Can xac nhan:

- `camera_id` dung
- `source_type` dung
- `source_path` dung
- `zone_config` dung
- `model_path` dung

### 6.3 Kiem tra config HIK

```bash
cat configs/hik_rcs.json
```

Can xac nhan:

- `enabled`
- `dry_run`
- `host`
- `rpc_port`
- `dps_port`
- `client_code`
- `token_code`
- `mappings`

### 6.4 Kiem tra ket noi toi camera/HIK

Neu can ping:

```bash
ping -c 4 <camera_ip>
ping -c 4 <hik_rcs_ip>
```

Neu site chan ping, khong sao, nhung phai co cach xac nhan route mang.

---

## 7. Chay thu backend va frontend bang tay mot lan

Khuyen nghi chay thu bang tay 1 lan truoc khi chuyen sang watchdog.

### 7.1 Chay backend

Terminal 1:

```bash
cd /opt/PIDVN25006
source .venv/bin/activate
python3 mainProcess.py
```

### 7.2 Chay frontend

Terminal 2:

```bash
cd /opt/PIDVN25006
source .venv/bin/activate
python3 mainCCTV.py
```

### 7.3 Kiem tra

Can xac nhan:

- frontend mo duoc
- co grid camera
- output runtime duoc tao

Kiem tra file:

```bash
ls outputs/runtime/
ls outputs/runtime/cameras/
ls outputs/runtime/preview/
```

Neu chay duoc bang tay, moi chuyen sang watchdog.

---

## 8. Chuan bi launcher Linux

Tai root project da co file:

```bash
run_forever.sh
```

Cap quyen thuc thi:

```bash
cd /opt/PIDVN25006
chmod +x run_forever.sh
```

Co the mo file de xem:

```bash
cat run_forever.sh
```

Y nghia:

- tu tim `.venv/bin/python`
- neu khong co thi tim `python3`
- sau do goi `tools/run_forever.py`

---

## 9. Chay watchdog tren Ubuntu Desktop

Chay:

```bash
cd /opt/PIDVN25006
./run_forever.sh
```

Ky vong:

- console hien thong bao start supervisor
- backend duoc mo
- sau vai giay frontend duoc mo
- neu 1 trong 2 process tat bat thuong, watchdog tu restart

File log can theo doi:

```bash
outputs/runtime/supervisor/supervisor.log
```

Co the xem live:

```bash
tail -f outputs/runtime/supervisor/supervisor.log
```

---

## 10. Chay watchdog khi muon chi giu backend

Neu vi ly do nao do ban muon:

- frontend mo bang tay rieng
- hoac test backend/HIK
- hoac debug camera

Thi chay:

```bash
./run_forever.sh --no-frontend
```

Luu y:

- tren Ubuntu Desktop thong thuong ban se muon co frontend
- `--no-frontend` chu yeu dung cho debug hoac cho may gan monitor khac

---

## 11. Cach stop he thong dung cach

Neu dang chay trong terminal:

1. quay lai cua so terminal dang chay `run_forever.sh`
2. nhan `Ctrl+C`

Ky vong:

- supervisor nhan signal stop
- supervisor terminate backend/frontend co kiem soat
- log ghi nhan dong he thong

Khong khuyen nghi:

- kill tung child process roi de supervisor mo lai
- dong ngang terminal bang cach bat thuong neu chua can

---

## 12. Tu dong chay sau khi login Ubuntu Desktop

Voi Ubuntu Desktop, cach than thien nhat la auto-start sau login bang `~/.config/autostart`.

### 12.1 Tao script wrapper cho autostart

Khuyen nghi tao them script:

```bash
mkdir -p ~/bin
nano ~/bin/pidvn25006_start.sh
```

Noi dung:

```bash
#!/usr/bin/env bash
cd /opt/PIDVN25006
./run_forever.sh >> /opt/PIDVN25006/outputs/runtime/supervisor/autostart_stdout.log 2>> /opt/PIDVN25006/outputs/runtime/supervisor/autostart_stderr.log
```

Cap quyen:

```bash
chmod +x ~/bin/pidvn25006_start.sh
```

### 12.2 Tao file desktop autostart

```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/pidvn25006.desktop
```

Noi dung:

```ini
[Desktop Entry]
Type=Application
Name=PIDVN25006
Exec=/home/<username>/bin/pidvn25006_start.sh
X-GNOME-Autostart-enabled=true
Terminal=true
```

Phai sua:

- `<username>` thanh user that

### 12.3 Test autostart

Dang xuat va login lai.

Ky vong:

- watchdog tu mo
- backend tu start
- frontend tu start

Neu khong muon cua so terminal hien len, co the doi:

```ini
Terminal=false
```

Nhung khuyen nghi thuc te:

- giai doan commissioning nen de `Terminal=true`
- sau khi on dinh moi can nhac `Terminal=false`

---

## 13. Cach kiem tra he thong sau khi login

Sau khi login Ubuntu Desktop, kiem tra theo thu tu:

### 13.1 Kiem tra cua so watchdog

Can co:

- cua so terminal cua `run_forever.sh`

### 13.2 Kiem tra frontend

Can co:

- cua so `mainCCTV.py`
- grid camera hien len

### 13.3 Kiem tra output runtime

```bash
ls outputs/runtime/
ls outputs/runtime/cameras/
```

### 13.4 Kiem tra log watchdog

```bash
tail -n 50 outputs/runtime/supervisor/supervisor.log
```

### 13.5 Kiem tra bridge HIK neu dang bat

```bash
ls outputs/runtime/hik_rcs/
```

Neu dang gui that:

```bash
tail -f outputs/runtime/hik_rcs/http_exchange.jsonl
```

---

## 14. Checklist dau ca van hanh

Moi khi vao ca, nguoi van hanh/ky thuat vien check:

1. may Ubuntu da login chua
2. watchdog co dang chay khong
3. frontend co mo khong
4. tat ca camera can thiet co hinh khong
5. `outputs/runtime/agv_latest.json` co cap nhat khong
6. neu dang dung HIK bridge, `http_exchange.jsonl` co log bat thuong khong
7. co qua nhieu zone `unknown` khong

Neu co bat thuong, xu ly truoc khi cho he thong vao ca san xuat.

---

## 15. Checklist cuoi ca

Neu khong tat may:

- co the de he thong chay lien tuc

Neu can dong he thong:

1. quay lai terminal watchdog
2. nhan `Ctrl+C`
3. xac nhan backend/frontend da dong
4. backup log neu co su co trong ca

---

## 16. Xu ly su co thong dung

### 16.1 Frontend khong mo

Kiem tra:

```bash
echo "$DISPLAY"
echo "$WAYLAND_DISPLAY"
tail -n 50 outputs/runtime/supervisor/supervisor.log
```

Neu `DISPLAY` va `WAYLAND_DISPLAY` rong:

- frontend co the khong mo duoc
- can xac nhan ban dang login vao desktop session that

### 16.2 Backend crash lien tuc

Kiem tra:

```bash
tail -n 100 outputs/runtime/supervisor/supervisor.log
```

Can xem:

- crash code la gi
- crash xay ra sau bao nhieu giay
- watchdog co dang backoff khong

### 16.3 Camera khong co hinh

Kiem tra:

- `configs/cameras.json`
- duong dan RTSP
- ket noi mang
- co camera nao offline khong

### 16.4 HIK bridge khong gui request

Kiem tra:

```bash
cat configs/hik_rcs.json
tail -f outputs/runtime/hik_rcs/http_exchange.jsonl
cat outputs/runtime/hik_rcs/bridge_state.json
```

Can xem:

- `enabled=true` chua
- `dry_run=false` chua
- mapping da `enabled=true` chua
- zone co dang `unknown` khong

### 16.5 Frontend bi dong bat thuong

Neu watchdog dang chay:

- doi vai giay
- frontend se duoc mo lai

Neu khong duoc mo lai:

```bash
tail -n 100 outputs/runtime/supervisor/supervisor.log
```

### 16.6 Sau login khong tu chay

Kiem tra:

```bash
ls ~/.config/autostart/
cat ~/.config/autostart/pidvn25006.desktop
cat ~/bin/pidvn25006_start.sh
```

Can xem:

- duong dan `Exec=` dung chua
- script da `chmod +x` chua
- project root dung chua

---

## 17. Cach cap nhat code sau nay

Moi khi cap nhat code:

1. backup `configs/`
2. backup `outputs/runtime/supervisor/supervisor.log` neu can
3. stop watchdog
4. cap nhat source code
5. kich hoat lai `.venv`
6. `pip install -r requirements.txt` neu co thay doi dependency
7. test bang tay 1 lan
8. start lai `run_forever.sh`

Khong khuyen nghi:

- cap nhat code giua ca san xuat khi chua duoc phep

---

## 18. Khuyen nghi cho commissioning tai nha may

Trong giai doan commissioning:

- de cua so watchdog mo
- de frontend mo
- de terminal hien log
- de `dry_run=true` truoc
- test tung zone
- ghi bien ban test

Sau khi on dinh:

- moi chuyen sang request that
- moi can nhac auto-start sau login

Thu tu khuyen nghi:

1. test bang tay
2. test watchdog
3. test autostart login
4. test HIK dry-run
5. test HIK request that
6. test AGV phan ung that

---

## 19. Tieu chi de duoc coi la san sang van hanh

He thong Ubuntu Desktop duoc coi la san sang khi:

1. `run_forever.sh` chay on dinh
2. backend va frontend tu start duoc
3. backend/frontend crash thi watchdog tu restart
4. output runtime duoc cap nhat lien tuc
5. autostart sau login da test pass
6. neu dung HIK bridge thi dry-run pass
7. neu gui that thi request/response/callback pass
8. nguoi van hanh da biet cach xem log watchdog va xu ly loi co ban

---

## 20. Lenh tong hop nhanh nhat

### Cai lan dau

```bash
cd /opt/PIDVN25006
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
chmod +x run_forever.sh
```

### Chay he thong

```bash
cd /opt/PIDVN25006
./run_forever.sh
```

### Chay chi backend

```bash
cd /opt/PIDVN25006
./run_forever.sh --no-frontend
```

### Xem log watchdog

```bash
tail -f /opt/PIDVN25006/outputs/runtime/supervisor/supervisor.log
```

### Stop he thong

```bash
Ctrl+C
```

---

## 21. Ket luan thuc te nhat

Voi Ubuntu Desktop, cach van hanh de hieu va than thien nhat cho du an nay la:

- login vao desktop
- chay `run_forever.sh`
- de watchdog giu backend/frontend song
- theo doi frontend va log watchdog

Neu ban di dung thu tu cua tai lieu nay, thi ban se co mot he thong van hanh de tiep can, de su dung, de debug va de mang ra commissioning ngoai hien truong theo mot quy trinh ro rang, khong bo sot buoc.
