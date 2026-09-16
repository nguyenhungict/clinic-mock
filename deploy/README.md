# Deploy clinic-mock lên AWS — Runbook

**Mục tiêu:** một instance clinic mock dùng chung cho team, chạy tại base URL đã đăng ký với
chương trình (tên miền riêng, HTTPS), giữ nguyên URL đó suốt batch kể cả khi đổi sang image
chính thức. Thời gian làm lần đầu: ~45 phút, phần lớn là đợi DNS và tạo máy.

Thư mục `deploy/` chỉ chứa hạ tầng chạy mock; **không sửa file nào ngoài thư mục này**.

## Ràng buộc từ contract (AIHR-PC-001 rev 1.1) và cách đáp ứng

| Điều khoản | Cách deploy này đáp ứng |
|---|---|
| §4.2.1 — chạy image nguyên bản; không đặt gì giữa harness và mock làm đổi hành vi | Image build từ `Dockerfile` gốc, không sửa. Dockerfile chỉ `COPY` `pyproject.toml`, `uv.lock`, `README.md`, `src/` nên thư mục `deploy/` **không bao giờ lọt vào image** — digest không phụ thuộc vào các file ở đây. Caddy chỉ terminate TLS và forward thẳng: không rewrite, không cache, không nén, không đổi header |
| §4.1.1 — base URL đăng ký trước ngày 3 tuần 1, đóng băng | Elastic IP + bản ghi DNS trỏ một lần. Mọi lần deploy lại đều trên cùng máy, cùng IP, cùng tên miền |
| §4.2.1 — harness đọc `/_harness/version` trước mỗi lần chấm; chương trình có thể audit bất kỳ lúc nào | Khi có image chính thức: pin theo **digest** trong compose, đối chiếu `/_harness/version` với digest công bố (mục 7). Bản mentor hiện chưa có endpoint này |
| §4.2.4 — bot không gọi `/_harness/*` | Không chặn ở proxy (harness cần gọi). Client trong bot không được biết đến nhóm endpoint này |
| §5 — độ trễ p95 chiếm 15% điểm | Region Singapore, cùng region với bot nếu bot cũng trên AWS |

Mock lưu dữ liệu **in-memory, một process** (`db = Store()` trong `src/clinic_mock/store.py`):
restart container = mất dữ liệu; **hai container = hai bộ dữ liệu khác nhau**. Vì vậy luôn chạy
**đúng một container**, không auto-scale, không load-balance nhiều bản. Mất dữ liệu khi restart
là chấp nhận được: harness luôn `reset` + `seed` trước mỗi case (Hình 2 trong contract).

---

## 0. Chuẩn bị

- Tài khoản AWS có quyền tạo EC2, Elastic IP, Security Group.
- Quyền sửa DNS của tên miền đã đăng ký (Route 53, Cloudflare, hoặc nhà cung cấp tên miền).
- Máy local có `ssh` (Git Bash trên Windows là đủ).
- Repo này đã push lên một remote mà server clone được (GitHub của team). Ghi lại URL.

Chọn **region `ap-southeast-1` (Singapore)** — gần Việt Nam nhất. Nếu bot cũng deploy trên AWS,
đặt **cùng region** để độ trễ bot → mock không đội p95 lên.

---

## 1. Tạo EC2

AWS Console → EC2 → **Launch instance**:

| Mục | Giá trị | Lý do |
|---|---|---|
| Name | `clinic-mock` | |
| AMI | **Ubuntu Server 24.04 LTS**, 64-bit x86 | Docker CE hỗ trợ chính thức, vá bảo mật 5 năm |
| Instance type | **t3.micro** (free tier 12 tháng đầu) hoặc t3.small | Mock dùng ~100 MB RAM. t3.micro build image hơi chậm; thêm swap ở bước 4 là đủ |
| Key pair | Tạo mới `clinic-mock-key`, ED25519, định dạng `.pem` | Tải về; `chmod 400 clinic-mock-key.pem` |
| Network settings | VPC mặc định; **Auto-assign public IP: Enable** | |
| Firewall (security group) | Tạo mới `clinic-mock-sg`, 3 rule inbound: <br>• SSH · TCP 22 · **My IP** <br>• HTTP · TCP 80 · 0.0.0.0/0 <br>• HTTPS · TCP 443 · 0.0.0.0/0 | Port 80 cần để Let's Encrypt xác thực và để redirect → https. Port **8000 không mở**: mock chỉ nghe trong mạng Docker |
| Storage | 20 GiB, **gp3** | Đủ cho image + log; gp3 rẻ và nhanh hơn gp2 |
| Advanced details → Credit specification | Standard | Tránh phí burst bất ngờ với dòng t3 |

Launch → đợi *Instance state: Running* và *Status check: 2/2 checks passed*.

> **Tùy chọn tốt hơn SSH:** Advanced details → IAM instance profile → tạo role có policy
> `AmazonSSMManagedInstanceCore`. Sau đó dùng *Connect → Session Manager* trong console, không
> cần mở port 22, không quản lý file key. Nếu chọn cách này, bỏ rule SSH trong security group.

---

## 2. Elastic IP — khoá IP vĩnh viễn

EC2 → **Elastic IPs** → *Allocate Elastic IP address* → *Allocate*. Chọn IP vừa tạo →
*Actions → Associate Elastic IP address* → Instance: `clinic-mock` → *Associate*.

Từ đây IP không đổi khi stop/start. Nếu phải dựng máy mới, chỉ gắn lại EIP — DNS không cần chạm.

EIP **miễn phí khi đang gắn vào instance đang chạy**; bị tính ~$3.6/tháng nếu để trống hoặc máy
đang stop. Không cấp phát rồi bỏ đó; hết batch thì *Release*.

---

## 3. DNS — trỏ tên miền đã đăng ký về EIP

Ở nơi quản lý DNS, thêm bản ghi:

| Type | Name | Value | TTL |
|---|---|---|---|
| A | `<tên miền đã đăng ký>` | `<Elastic IP>` | 300 |

Nếu DNS ở **Cloudflare**: để **DNS only** (đám mây xám), không bật proxy (đám mây cam). Proxy
Cloudflare là "thứ đứng giữa harness và mock" theo §4.2.1 — nó đổi header, có timeout riêng
(100 s) và có thể cache.

Kiểm tra từ máy local, phải ra đúng Elastic IP:

```bash
nslookup <tên miền đã đăng ký>
```

**Đợi DNS resolve đúng trước khi làm bước 6.** Nếu chưa, Let's Encrypt cấp chứng chỉ thất bại
và sau vài lần sẽ bị rate-limit ~1 giờ.

---

## 4. Cài đặt server

```bash
ssh -i clinic-mock-key.pem ubuntu@<Elastic IP>
```

Chạy lần lượt trên server:

```bash
# OS: cập nhật + bật tự vá bảo mật
sudo apt-get update && sudo apt-get -y upgrade
sudo apt-get -y install unattended-upgrades git curl
sudo dpkg-reconfigure -plow unattended-upgrades

# Docker CE từ repo chính thức (kèm compose plugin)
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker ubuntu
```

Đăng xuất rồi đăng nhập lại (để nhóm `docker` có hiệu lực), kiểm tra:

```bash
docker compose version
```

Swap 1 GB — **bắt buộc với t3.micro** để build image không bị OOM:

```bash
sudo fallocate -l 1G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## 5. Clone repo và cấu hình

```bash
sudo mkdir -p /opt/clinic-mock && sudo chown ubuntu:ubuntu /opt/clinic-mock
git clone <URL repo của team> /opt/clinic-mock
cd /opt/clinic-mock/deploy

cp .env.example .env
chmod 600 .env

# Sinh key — mỗi key PHẢI bắt đầu bằng sk_ (gạch dưới)
for n in grading alice bob; do echo "sk_${n}_$(openssl rand -hex 12)"; done

nano .env    # điền MOCK_DOMAIN, ACME_EMAIL, MOCK_API_KEYS
```

Quy ước key trong `MOCK_API_KEYS`:

| Key | Ai dùng | Ghi chú |
|---|---|---|
| `sk_grading_…` | **Bot khi chấm điểm** và **harness** | Harness ghi/đọc trong scope của key nó dùng; bot phải dùng cùng key thì bước 4–5 của Hình 2 mới thấy đúng dữ liệu. Gửi key này cho chương trình nếu được yêu cầu |
| `sk_<tên>_…` | Mỗi thành viên một key để dev | Dữ liệu canonical (`apt_00417`, `pt_3391`, `slot_91d2`) hiện ra với mọi key; lịch hẹn mới tạo chỉ key tạo mới thấy |

**`POST /_harness/reset` xóa dữ liệu của mọi key** (`Store.reset()` khởi tạo lại toàn bộ) — giữ
quy ước "báo trên kênh team trước khi reset". `.env` không vào git (đã có trong `.gitignore`);
lưu bản sao trong password manager của team.

---

## 6. Khởi chạy

```bash
cd /opt/clinic-mock/deploy
./deploy.sh
```

Script kiểm tra `.env`, build image từ `Dockerfile` gốc, `docker compose up -d`, đợi healthcheck
và in digest image đang chạy. Lần đầu build trên t3.micro mất 2–4 phút.

Theo dõi Caddy xin chứng chỉ (10–30 giây):

```bash
docker compose logs -f caddy    # tìm "certificate obtained successfully", Ctrl-C để thoát
```

Kiểm tra từ máy local (hoặc ngay trên server):

```bash
./smoke.sh https://<tên miền đã đăng ký> sk_grading_xxx
```

Bước 1–6 phải `OK`. Bước 7 (`/_harness/version`) `WARN` là bình thường với bản mentor. Mở
`https://<tên miền>/docs` để xem Swagger.

**Cấu hình phía bot** (mỗi thành viên, trong `.env` của repo callbot):

```env
CLINIC_MOCK_BASE_URL=https://<tên miền đã đăng ký>/v1
CLINIC_MOCK_API_KEY=sk_<tên>_xxx
```

---

## 7. Vận hành

### Lệnh hằng ngày

```bash
cd /opt/clinic-mock/deploy
docker compose ps                     # trạng thái + health
docker compose logs -f clinic-mock    # log mock (JSON)
docker compose logs -f caddy          # access log
docker compose restart clinic-mock    # restart — mất dữ liệu in-memory, vô hại
```

### Cập nhật khi repo có commit mới

```bash
PULL=1 ./deploy.sh
```

Downtime 10–20 giây khi container mới thay container cũ. Báo team trước.

### Đổi sang image chính thức (khi `#residency-batch03` công bố)

1. Trong `docker-compose.yml`, service `clinic-mock`: xóa khối `build:`, thêm
   `image: <registry>/clinic-mock@sha256:<digest công bố>`. **Pin theo digest, không dùng tag.**
2. Commit, push, rồi trên server `PULL=1 ./deploy.sh` — script thấy không còn `build:` sẽ `pull`.
3. Đối chiếu:
   ```bash
   curl -s https://<tên miền>/_harness/version -H "Authorization: Bearer sk_grading_…"
   ```
   Digest trả về phải trùng digest công bố. Ghi lại trong doc team.
4. Tên miền, IP, key: **không đổi**.

### Máy stop/start hoặc dựng lại

- Stop/start: EIP giữ IP; `restart: unless-stopped` tự kéo container lên. Chạy `smoke.sh`.
- Dựng máy mới: làm lại bước 4–6, rồi *Associate* EIP sang máy mới. DNS không cần sửa; Caddy
  tự xin lại chứng chỉ.

### Giám sát tối thiểu

- EC2 → instance → tab *Monitoring* → **CloudWatch alarm** `StatusCheckFailed ≥ 1` trong 2 kỳ
  1 phút → SNS topic gửi email cho team. (10 alarm đầu miễn phí.)
- Uptime ngoài AWS: một dịch vụ ping `https://<tên miền>/health` mỗi 5 phút (Healthchecks.io,
  UptimeRobot — gói free đủ dùng).

### Checklist trước mỗi lần chấm điểm

1. `./smoke.sh https://<tên miền> sk_grading_…` — bước 1–6 OK.
2. Khi đã dùng image chính thức: `/_harness/version` trùng digest công bố.
3. Không ai trong team đang test trên instance chung — xác nhận trên kênh team.
4. `docker compose ps` — cả hai container `running`/`healthy`.

---

## 8. Bảo mật

- Chỉ 80/443 mở ra internet; 22 chỉ từ IP của bạn (hoặc dùng SSM và không mở 22). Port 8000
  không bao giờ publish ra host.
- Key `sk_…` chỉ nằm trong `deploy/.env` trên server (mode 600) và password manager. Nếu lộ:
  sửa `.env` → `docker compose up -d` (mock đọc key lúc khởi động).
- Caddy tự gia hạn chứng chỉ Let's Encrypt (90 ngày). Không cần cron.
- `unattended-upgrades` vá OS tự động. Image mock chỉ đổi khi bạn chủ động deploy — đúng tinh
  thần "digest đóng băng".
- **Không** thêm CORS, rate-limit, auth bổ sung, WAF, CDN hay proxy khác trước mock — đều là
  "thứ đứng giữa harness và mock" theo §4.2.1.

---

## 9. Chi phí ước tính (ap-southeast-1)

| Hạng mục | Mỗi tháng |
|---|---|
| t3.micro on-demand | ~$9.5 (miễn phí 750 giờ/tháng trong 12 tháng đầu free tier) |
| EBS 20 GiB gp3 | ~$1.9 |
| Elastic IP (đang gắn) | $0 |
| Data transfer | không đáng kể — JSON nhỏ, 100 GB đầu miễn phí |
| **Tổng** | **~$11/tháng**, hoặc ~$2 nếu còn free tier |

Hết batch: *Terminate* instance rồi **Release** Elastic IP.

---

## 10. Sự cố thường gặp

| Triệu chứng | Nguyên nhân / xử lý |
|---|---|
| `curl https://…` lỗi TLS; Caddy log "challenge failed" | DNS chưa trỏ đúng EIP, hoặc port 80 bị chặn ở security group. Sửa xong: `docker compose restart caddy` |
| Caddy log "rate limited" / "too many failed authorizations" | Xin cert thất bại nhiều lần. Đợi 1 giờ, đảm bảo DNS đúng rồi mới restart |
| `/health` OK nhưng mọi `/v1/*` trả 401 | Key trong `.env` không bắt đầu `sk_` (gạch dưới), hoặc bot chưa gửi `Authorization: Bearer` |
| Bot nhận 404 ở mọi request | Base URL của bot thiếu `/v1` |
| Build image bị kill hoặc treo | Thiếu RAM — chưa thêm swap (bước 4) |
| Dữ liệu "biến mất" | Ai đó `reset`, hoặc container vừa restart (in-memory). Bình thường — `POST /_harness/seed` lại |
| Sau stop/start không truy cập được | Chưa gắn EIP nên IP đổi → gắn EIP. Hoặc `docker compose ps` xem container có lên không |
| `deploy.sh` báo "vẫn còn CHANGE_ME" | Chưa điền hết `.env` |
