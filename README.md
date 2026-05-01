# Payment QR Backend

Backend FastAPI tự động xác nhận thanh toán cho web bán hàng VN bằng cách **đăng nhập tự động vào ngân hàng** (private API) trong worker container, **poll lịch sử giao dịch theo chu kỳ**, và bắn realtime event về web khi có giao dịch trùng `order_code`.

**Hỗ trợ 3 NH ngay (mỗi NH = 1 worker container)**: MB Bank, ACB, TPBank.
Có thể chạy nhiều NH song song để gom tiền vào cùng 1 hệ thống order.

> **Cảnh báo**: tất cả lib NH dùng (`mbbank-lib`, `makky-acb-api`, port từ `tpbank-api`) đều **unofficial**. Việc tự động hoá đăng nhập app banking có thể vi phạm ToS của NH. Hãy dùng tài khoản NH **riêng** dành cho web bán hàng, không phải tài khoản chính.

## Kiến trúc

```
┌─────────────────────────────────────────────────────────────────────┐
│ docker compose --profile mb --profile acb --profile tpb up          │
│                                                                     │
│  ┌──────────────┐   ┌─────────────────────┐                         │
│  │  postgres    │   │  app (FastAPI)      │                         │
│  │  :5432       │◄──┤  /api/orders        │                         │
│  │              │   │  /api/orders/{code} │                         │
│  │              │   │  /api/orders/{code}/│                         │
│  │              │   │     stream (SSE)    │                         │
│  │              │   │  /api/bank/health   │                         │
│  └──────┬───────┘   └─────────┬───────────┘                         │
│         │                     │                                     │
│         │       shared event bus + DB                               │
│         │                     │                                     │
│  ┌──────┴────┐   ┌────────────┴────┐   ┌──────────────────┐         │
│  │ worker-mb │   │ worker-acb      │   │ worker-tpb       │         │
│  │ poll MB   │   │ poll ACB        │   │ poll TPBank      │         │
│  │ mỗi 10s   │   │ mỗi 10s         │   │ mỗi 10s          │         │
│  └───────────┘   └─────────────────┘   └──────────────────┘         │
└─────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTPS
                       ┌──────┴──────┐
                       │  Web bán    │
                       │  hàng       │
                       └─────────────┘
```

**Flow 1 đơn hàng**:
1. Web bán hàng `POST /api/orders {amount, description}` → backend sinh `order_code` 8-10 ký tự + URL ảnh QR (chuẩn VietQR) chứa `order_code` ở phần *Nội dung CK*.
2. Khách scan QR + chuyển tiền với nội dung CK = `order_code`.
3. Worker container của NH tương ứng (đang đăng nhập NH) poll lịch sử giao dịch mỗi N giây → thấy giao dịch `creditAmount > 0` và `description` chứa `order_code` → khớp → cập nhật order = `paid`.
4. Backend bắn SSE event `paid` về web bán hàng đang lắng nghe → web hiển thị "✓ Đã thanh toán" tức thời.

## Yêu cầu

- Docker + Docker Compose (chạy production).
- Python 3.11+ (chạy local dev không Docker).
- 1 trong các NH sau (cá nhân, đã kích hoạt e/m-banking):
  - **MB Bank** (dễ nhất — lib `mbbank-lib` ổn định) — xem [docs/mbbank-setup.md](docs/mbbank-setup.md)
  - **ACB** (dùng lib `makky-acb-api`) — xem [docs/acb-setup.md](docs/acb-setup.md)
  - **TPBank** (port từ npm `tpbank-api`, cần lấy `deviceId` 1 lần đầu) — xem [docs/tpbank-setup.md](docs/tpbank-setup.md)

## Cách chạy

### Cách 1 — Docker Compose (khuyến nghị)

```bash
unzip payment-qr-backend.zip && cd payment-qr-backend
cp .env.example .env
# Sửa .env theo NH anh dùng (xem docs/<bank>-setup.md)
# Quan trọng: BANK_BIN + BANK_ACCOUNT_NUMBER + BANK_ACCOUNT_NAME phải khớp với NH anh dùng

# Chạy chỉ MB:
docker compose --profile mb up --build

# Chạy nhiều NH (gom tiền vào cùng 1 hệ thống order):
docker compose --profile mb --profile acb --profile tpb up --build

# Hoặc dùng alias "all" để bật tất cả:
docker compose --profile all up --build
```

Container chạy:
- `postgres`: DB lưu order + lịch sử transaction (luôn chạy)
- `app`: FastAPI server cổng 8000 (luôn chạy)
- `worker-mb` / `worker-acb` / `worker-tpb`: chỉ chạy nếu profile được bật

Mở `http://localhost:8000` để dùng frontend demo, hoặc `http://localhost:8000/docs` để xem Swagger.

### Cách 2 — Local dev (SQLite, không Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Sửa .env, ví dụ:
#   DATABASE_URL=sqlite+aiosqlite:///./payments.db
#   BANK_TYPE=mb        # hoặc acb / tpb
#   ENABLE_IN_PROCESS_POLLER=true   # poll trong cùng FastAPI process

uvicorn app.main:app --reload   # chạy app + poller (nếu bật flag) cùng 1 process
```

Hoặc chạy worker riêng ở terminal thứ 2:
```bash
BANK_TYPE=mb python -m app.worker
```

## Verify NH credentials

Sau khi setup, test login từng NH:

```bash
# Trạng thái config (không gọi NH thật)
curl http://localhost:8000/api/bank/health | jq

# Test login MB
curl -X POST 'http://localhost:8000/api/bank/test-login?bank_type=mb' | jq

# Test login ACB
curl -X POST 'http://localhost:8000/api/bank/test-login?bank_type=acb' | jq

# Test login TPB
curl -X POST 'http://localhost:8000/api/bank/test-login?bank_type=tpb' | jq
```

Trả `{"ok": true, "bank_code": "...", "recent_incoming_count": ...}` là OK.

Nếu lỗi 502 → check log container worker tương ứng:
```bash
docker compose logs worker-mb
docker compose logs worker-acb
docker compose logs worker-tpb
```

## Endpoints

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/orders` | Tạo đơn, trả về `order_code` + `qr_url` |
| GET | `/api/orders/{code}` | Lấy trạng thái đơn (poll fallback) |
| GET | `/api/orders/{code}/stream` | **SSE realtime**: nhận event `paid`/`expired`/`canceled` |
| POST | `/api/orders/{code}/cancel` | Huỷ đơn pending |
| GET | `/api/bank/health` | Trạng thái config NH (không gọi NH thật) |
| POST | `/api/bank/test-login?bank_type=mb\|acb\|tpb` | Verify NH login + lấy 30p giao dịch gần nhất (debug, **đừng public**) |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI |

### Tích hợp web bán hàng

```js
// 1. Tạo đơn
const r = await fetch('https://your-backend/api/orders', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({amount: 25000, description: 'Đơn #1234'}),
});
const order = await r.json();

// 2. Hiển thị QR
document.querySelector('#qr-img').src = order.qr_url;

// 3. Lắng nghe realtime
const es = new EventSource(`https://your-backend/api/orders/${order.order_code}/stream`);
es.addEventListener('paid', (e) => {
  alert('Đã thanh toán!');
  // gọi tiếp logic confirm đơn của anh...
});
```

## Tests

```bash
pytest -q
```

Bao phủ:
- `tests/test_parsers.py` — SMS parser cho 9 NH VN (cho đường fallback SMS, optional)
- `tests/test_matcher.py` — matching engine: happy path, thiếu/dư tiền, hết hạn, content có dấu tiếng Việt
- `tests/test_mbbank_helpers.py` — parse `creditAmount` / `postingDate` từ format MB
- `tests/test_acb_client.py` — ACB adapter: filter outgoing, dedupe, account discovery
- `tests/test_tpbank_client.py` — TPBank adapter: login flow, token refresh on 401, parse các format date
- `tests/test_banking_factory.py` — factory `build_client_from_settings`
- `tests/test_poller.py` — `BankPoller` với fake bank client: ingest, dedupe, không match, publish event
- `tests/test_api.py` — e2e qua HTTP: tạo đơn, OpenAPI, SMS webhook fallback

Tổng 51 tests pass.

## Cấu hình quan trọng (`.env`)

| Biến | Mô tả | Default |
|---|---|---|
| `BANK_BIN` | BIN của NH dùng để sinh QR (970422=MB, 970416=ACB, 970423=TPB) | `970422` |
| `BANK_ACCOUNT_NUMBER` | STK nhận tiền (in trên QR) | `YOUR_ACCOUNT_NUMBER` |
| `BANK_ACCOUNT_NAME` | Tên chủ TK (in trên QR) | `YOUR_NAME` |
| `BANK_TYPE` | NH worker dùng (mb/acb/tpb) — set qua docker-compose profile | `mb` |
| **MB Bank** | | |
| `MB_USERNAME` | Username/SĐT đăng nhập MB | rỗng |
| `MB_PASSWORD` | Password MB | rỗng |
| `MB_ACCOUNT_NO` | STK MB cần track (rỗng = auto-discover) | rỗng |
| **ACB** | | |
| `ACB_USERNAME` | Username ACB ONE | rỗng |
| `ACB_PASSWORD` | Password ACB ONE | rỗng |
| `ACB_ACCOUNT_NO` | STK ACB (rỗng = auto-discover) | rỗng |
| **TPBank** | | |
| `TPB_USERNAME` | Username eBank TPB | rỗng |
| `TPB_PASSWORD` | Password eBank TPB | rỗng |
| `TPB_DEVICE_ID` | Device ID lấy từ browser (xem [docs/tpbank-setup.md](docs/tpbank-setup.md)) | rỗng |
| `TPB_ACCOUNT_ID` | STK TPBank cần track | rỗng |
| **Poller / app** | | |
| `POLL_INTERVAL_SECONDS` | Giây giữa mỗi lần poll. <5s dễ bị NH block | `10` |
| `POLL_LOOKBACK_MINUTES` | Cửa sổ lùi quá khứ ở lần poll đầu (chống miss tx khi worker restart) | `30` |
| `DATABASE_URL` | DSN SQLAlchemy | postgres trong compose |
| `ENABLE_IN_PROCESS_POLLER` | Chạy poller bên trong FastAPI process (thay vì worker container) | `false` |
| `ENABLE_SMS_WEBHOOK` | Bật `/webhooks/sms` làm fallback (xem [docs/android-sms-forwarder.md](docs/android-sms-forwarder.md)) | `false` |
| `WEBHOOK_SECRET` | Secret cho `/webhooks/sms` (chỉ khi bật SMS) | placeholder |
| `ORDER_EXPIRES_MINUTES` | TTL đơn pending | `15` |
| `CORS_ORIGINS` | Comma-separated origins, `*` = all | `*` |

## Mở rộng / thay nguồn dữ liệu

Đã thiết kế `BankClient` interface (`app/services/banking/base.py`). Để thêm NH mới (ví dụ Sepay/Casso/Vietcombank):

1. Tạo class kế thừa `BankClient`, implement `fetch_incoming_transactions(since, until)`.
2. Đăng ký trong `app/services/banking/__init__.py:build_client_from_settings`.
3. Thêm config vào `app/config.py` + `.env.example`.
4. Thêm service `worker-<bank>` trong `docker-compose.yml` với `BANK_TYPE` tương ứng.

Phần order/QR/SSE/matching/dedup giữ nguyên.

## Troubleshooting

### MB Bank
- **`test-login` báo 502 `MB login/fetch failed`**:
  - Sai username/password → check lại bằng cách đăng nhập app MB Bank thường
  - MB tạm khoá vì login nhiều lần fail / nghi automation → đợi 1-2h, thử lại từ IP khác
  - Captcha OCR fail → thử restart container, lib sẽ retry
- Khi MB đổi captcha/WASM: chờ tác giả [`mbbank-lib`](https://github.com/thedtvn/MBBank) update, hoặc fallback sang ACB/TPB

### ACB
- **`test-login` báo 502** → username/password sai hoặc ACB đổi `clientId`/`apikey`. Update `makky-acb-api`: `pip install -U makky-acb-api`
- Xem [docs/acb-setup.md](docs/acb-setup.md) phần "Khi break"

### TPBank
- **`TPB_DEVICE_ID chưa cấu hình`**: chưa lấy deviceId từ browser. Xem [docs/tpbank-setup.md](docs/tpbank-setup.md)
- **`TPB login failed 401`**: deviceId hết hạn / bị TPBank revoke → lấy lại deviceId mới từ browser
- TPBank rate-limit IP → tăng `POLL_INTERVAL_SECONDS` lên 15-30s

### Common
- **Worker không match được giao dịch dù tiền đã vào**: check log worker container xem có "Ingested tx" không. Nếu có nhưng không match → so sánh `description` log với `order_code`; có thể format khác mong đợi → điều chỉnh `app/services/matcher.py:normalize`
- **Order chưa kịp `paid` thì khách đã đóng web** — không sao, web bán hàng chỉ cần poll `/api/orders/{code}` lại lúc khách quay lại; trạng thái lưu trên DB
- **Muốn match số tiền tuyệt đối** (không cho trả dư): sửa điều kiện ở `app/services/matcher.py` từ `>=` thành `==`

## License

Code này MIT.

Các thư viện ngân hàng (đều unofficial, KHÔNG endorsed bởi NH tương ứng):
- [`mbbank-lib`](https://github.com/thedtvn/MBBank) — MIT, by The DT
- [`makky-acb-api`](https://github.com/Makky/ACB-API) — bởi Makky
- TPBank logic port từ [`api_tpbank_free`](https://github.com/chuanghiduoc/api_tpbank_free) — MIT
