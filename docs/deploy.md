# Triển khai lên server (môi trường dev)

Bản triển khai đang chạy: **https://vegastar.themeshub.net** (Ubuntu 22.04, 2 vCPU, 4 GB RAM).

Server này còn chạy nhiều dịch vụ khác và RAM còn ít, nên bản này **không dùng Docker**: API chạy bằng systemd
trong virtualenv, dùng PostgreSQL có sẵn của máy, giao diện là file tĩnh do nginx phục vụ. Cách chạy bằng Docker
Compose (mô tả trong [README](../README.md)) vẫn giữ nguyên cho máy cá nhân và máy của người chấm.

## Kiến trúc trên server

```
Internet ──► nginx (443, SSL Let's Encrypt)
               ├── /            → /var/www/vegastar        (giao diện đã build)
               ├── /pitch/      → bản trình bày 6 slide (trang tĩnh riêng)
               ├── /api/        → 127.0.0.1:8011           (FastAPI, systemd: vegastar-api)
               │                   /api/docs mở cho người đánh giá, /api/metrics bị chặn
               └── /metrics, /docs (đường dẫn gốc) → 403

PostgreSQL 14 của hệ thống: database `vessel` (PostGIS 3.2, pgvector 0.8, pg_trgm)
```

| Thành phần | Vị trí |
|---|---|
| Mã nguồn + virtualenv | `/opt/vegastar` (user `vegastar`) |
| Cấu hình | `/opt/vegastar/.env` (quyền 600, **không nằm trong git**) |
| Dữ liệu CSV | `/opt/vegastar/data` |
| Giao diện đã build | `/var/www/vegastar` (gồm `/pitch/` và `VegaStar-Tong-quan.pdf`) |
| Service | `/etc/systemd/system/vegastar-api.service` |
| nginx | `/etc/nginx/sites-available/vegastar.themeshub.net` (bản trong repo: [deploy/nginx/](../deploy/nginx/vegastar.themeshub.net.conf)) |
| Service (bản trong repo) | [deploy/vegastar-api.service](../deploy/vegastar-api.service) |
| Chứng chỉ | `/etc/letsencrypt/live/vegastar.themeshub.net` (certbot tự gia hạn) |

## Các bước đã làm

```bash
# 1. Gói cần thêm trên server
apt-get install -y postgresql-14-postgis-3 python3.12-venv

# 2. Database riêng
sudo -u postgres createdb -O vessel vessel        # role `vessel` có mật khẩu riêng
sudo -u postgres psql -d vessel -c 'CREATE EXTENSION postgis; CREATE EXTENSION vector; CREATE EXTENSION pg_trgm;'

# 3. Mã nguồn (từ máy dev)
git archive --format=tar HEAD | gzip > code.tar.gz
tar -czf data.tar.gz data                          # CSV của đề, không nằm trong git
scp code.tar.gz data.tar.gz root@server:/tmp/
ssh root@server 'mkdir -p /opt/vegastar && cd /opt/vegastar && tar xzf /tmp/code.tar.gz && tar xzf /tmp/data.tar.gz'

# 4. Môi trường Python và nạp dữ liệu
cd /opt/vegastar && python3.12 -m venv .venv && .venv/bin/pip install .
.venv/bin/python scripts/load_data.py              # ~26 giây: 1.000 tàu, 171.073 điểm AIS

# 5. Giao diện: build trên máy dev rồi tải lên (tránh cài Node trên server)
cd frontend && VITE_API_BASE_URL=https://vegastar.themeshub.net/api \
  VITE_SITE_URL=https://vegastar.themeshub.net npm run build
scp -r dist/* root@server:/var/www/vegastar/   # prebuild tự chép PDF tổng quan và ảnh cho trang pitch

# 6. Service + nginx + SSL
systemctl enable --now vegastar-api
certbot certonly --webroot -w /var/www/vegastar-acme -d vegastar.themeshub.net
```

Kho tri thức (RAG) tự đồng bộ khi API khởi động. Lịch sử hội thoại từ máy dev được chuyển sang bằng
`pg_dump --data-only -t conversations -t messages -t memory_chunks -t map_data` rồi `psql -f`.

## Cấu hình khác với máy cá nhân

| Biến | Giá trị trên server | Vì sao |
|---|---|---|
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8011` | Chỉ nginx gọi được; không mở cổng ra Internet |
| `CORS_ORIGINS` | `https://vegastar.themeshub.net` | Chỉ tên miền thật được gọi API từ trình duyệt |
| `TRUST_PROXY_HEADERS` | `true` | Rate limit tính theo IP thật qua `X-Forwarded-For` |
| `AUTH_USERS` | `demo:demo` | Tài khoản dùng thử; nên đổi hoặc dùng chuỗi băm khi public lâu dài |
| `SESSION_SECRET` | chuỗi ngẫu nhiên 32 byte | Không đổi khi khởi động lại nên người dùng không bị đăng xuất |
| `DATA_DIR`, `KNOWLEDGE_DIR`, `EVAL_REPORT_PATH` | đường dẫn tuyệt đối trong `/opt/vegastar` | systemd chạy với `ProtectSystem=strict` |

Service chạy user `vegastar` (không phải root), `NoNewPrivileges`, `ProtectSystem=strict`, `ProtectHome`,
chỉ ghi được `/opt/vegastar/results`, và `MemoryMax=900M` để không ảnh hưởng các dịch vụ khác trên máy.

## Cập nhật phiên bản mới

```bash
# Trên máy dev
git archive --format=tar HEAD | gzip > code.tar.gz
cd frontend && npm run build           # với các biến VITE_* của tên miền thật

# Trên server
tar xzf /tmp/code.tar.gz -C /opt/vegastar          # .env và data/ giữ nguyên
/opt/vegastar/.venv/bin/pip install /opt/vegastar  # khi pyproject đổi
rsync -a --delete dist/ /var/www/vegastar/
chown -R vegastar:vegastar /opt/vegastar
systemctl restart vegastar-api
```

Kiểm tra sau khi cập nhật:

```bash
curl -s https://vegastar.themeshub.net/api/health
journalctl -u vegastar-api -n 30 --no-pager
```

## Những chỗ dễ sai

- **Build giao diện phải truyền biến môi trường của tên miền**, nếu không bundle sẽ trỏ API về `localhost`:
  `VITE_API_BASE_URL=https://vegastar.themeshub.net/api VITE_SITE_URL=https://vegastar.themeshub.net npm run build`.
  Kiểm tra nhanh sau khi deploy: `grep -rl "vegastar.themeshub.net/api" /var/www/vegastar/assets`.
- **`try_files $uri $uri/ /index.html`**: thiếu `$uri/` thì `/pitch/` rơi về ứng dụng React thay vì trang tĩnh.
- **Chặn `/api/metrics`**: endpoint Prometheus không có xác thực và lộ lưu lượng, chi phí.
- **CSP phải cho phép máy chủ ảnh vệ tinh** (`https://server.arcgisonline.com`) nếu muốn dùng nút nền "Vệ tinh".

## Vận hành

- **Log:** `journalctl -u vegastar-api -f` (JSON một dòng mỗi lượt: tool, độ trễ, token, chi phí);
  nginx: `/var/log/nginx/vegastar.{access,error}.log`.
- **Số liệu:** trang **Thống kê** (`/#/thong-ke`) hoặc `curl` `/api/stats` với token đăng nhập.
  `/metrics` bị chặn ở nginx, xem từ trong máy: `curl localhost:8011/metrics`.
- **SSL:** certbot tự gia hạn; hook `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh` nạp lại nginx.
- **Sao lưu:** `pg_dump vessel | gzip > vessel-$(date +%F).sql.gz` (73 MB, chủ yếu là điểm AIS).

## Việc nên làm tiếp nếu chạy lâu dài

- Đổi mật khẩu tài khoản `demo` (hoặc dùng `scripts/hash_password.py`) và mật khẩu root của server; chuyển sang SSH key.
- Bật `ufw` chỉ mở 22, 80, 443.
- Đặt giới hạn chi tiêu và cảnh báo trên tài khoản OpenAI.
- Thêm sao lưu định kỳ database và giám sát dung lượng đĩa (máy đang dùng 74%).
