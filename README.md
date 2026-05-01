# Payment QR Backend

Backend FastAPI tự động xác nhận thanh toán cho web bán hàng VN bằng cách **đăng nhập tự động vào MB Bank** (private API) trong 1 worker container, **poll lịch sử giao dịch theo chu kỳ**, và bắn realtime event về web khi có giao dịch trùng `order_code`.

> **Cảnh báo**: lib MB Bank dùng (`mbbank-lib`) là *unofficial*. Việc tự động hoá đăng nhập app banking có thể vi phạm ToS của MB. Hãy dùng tài khoản MB riêng dành cho web bán hàng, không dùng tài khoản chính. Anh đã nắm rủi ro này.

## Kiến trúc

```
┌─────────────────────────────────────────────────────────────────────┐
│ docker compose up                                                   │
│                                                                     │
│  ┌──────────────┐   ┌─────────────────────┐   ┌──────────────────┐  │
│  │  postgres    │   │  app (FastAPI)      │   │  worker          │  │
│  │  :5432       │◄──┤  /api/orders        │   │  (poll MB API)   │  │
│  │              │   │  /api/orders/{code} │   │                  │  │
│  │              │   │  /api/orders/{code}/│   │  every Ns:       │  │
│  │              │   │     stream (SSE)    │   │   1) login MB    │  │
│  │              │   │  /api/bank/health   │◄──┤   2) get tx hist │  │
│  │              │   │  /api/bank/test-... │   │   3) match order │  │
│  └──────────────┘   └─────────────────────┘   │   4) publish     │  │
│         ▲                     ▲               │      "paid" evt  │  │
│         │                     │               └──────────────────┘  │
│         │                     │                       │             │
│         │                     │   shared event bus    │             │
│         └─────────────────────┴───────────────────────┘             │
└─────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ HTTPS
                              │
                       ┌──────┴──────┐
                       │  Web bán    │
                       │  hàng       │
                       └─────────────┘
```

**Flow 1 đơn hàng**:
1. Web bán hàng `POST /api/orders {amount, description}` → backend sinh `order_code` 8-10 ký tự + URL ảnh QR (chuẩn VietQR) chứa `order_code` ở phần *Nội dung CK*.
2. Khách scan QR + chuyển tiền với nội dung CK = `order_code`.
3. Worker container (đang đăng nhập MB Bank) poll endpoint `getTransactionAccountHistory` mỗi N giây → thấy giao dịch mới có `creditAmount > 0` và `description` chứa `order_code` → khớp → cập nhật order = `paid`.
4. Backend bắn SSE event `paid` về web bán hàng đang lắng nghe → web hiển thị "✓ Đã thanh toán" tức thời.

## Yêu cầu

- Docker + Docker Compose (chạy production).
- Python 3.11+ (chạy local dev không Docker).
- 1 tài khoản **MB Bank cá nhân** (mở được app MB trên điện thoại thường, không phải MB Pro/MBBiz).

## Cách chạy

### Cách 1 — Docker Compose (khuyến nghị)

```bash
unzip payment-qr-backend.zip && cd payment-qr-backend
cp .env.example .env
# Sửa .env: BANK_BIN, BANK_ACCOUNT_NUMBER, BANK_ACCOUNT_NAME, MB_USERNAME, MB_PASSWORD
docker compose up --build
```

3 container sẽ start:
- `postgres`: DB lưu order + lịch sử transaction
- `app`: FastAPI server cổng 8000
- `worker`: poll MB Bank → match order

Mở `http://localhost:8000` để dùng frontend demo, hoặc `http://localhost:8000/docs` để xem Swagger.

### Cách 2 — Local dev (SQLite, không Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# Sửa .env theo nhu cầu, ví dụ:
#   DATABASE_URL=sqlite+aiosqlite:///./payments.db
#   ENABLE_IN_PROCESS_POLLER=true   # poll trong cùng FastAPI process

uvicorn app.main:app --reload   # chạy app + poller (nếu bật flag) cùng 1 process
```

Hoặc chạy worker riêng ở terminal thứ 2:
```bash
python -m app.worker
```

## Verify MB credentials

Sau khi setup, gọi để kiểm tra:

```bash
curl http://localhost:8000/api/bank/health
# {"mb_username_configured": true, "mb_password_configured": true, ...}

curl -X POST http://localhost:8000/api/bank/test-login
# {"ok": true, "accounts": ["0123456789"], "recent_incoming_count": 0, "recent": []}
```

Nếu `test-login` lỗi 502 → check log container `app` (`docker compose logs app`) để biết MB trả về gì (sai password / captcha fail / MB block / ...).

## Endpoints

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/orders` | Tạo đơn, trả về `order_code` + `qr_url` |
| GET | `/api/orders/{code}` | Lấy trạng thái đơn (poll fallback) |
| GET | `/api/orders/{code}/stream` | **SSE realtime**: nhận event `paid`/`expired`/`canceled` |
| POST | `/api/orders/{code}/cancel` | Huỷ đơn pending |
| GET | `/api/bank/health` | Trạng thái config MB |
| POST | `/api/bank/test-login` | Verify MB login + lấy 5p giao dịch gần nhất (debug, **đừng public**) |
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
- `tests/test_parsers.py` — SMS parser cho 9 NH VN (cho đường fallback SMS, optional).
- `tests/test_matcher.py` — matching engine: happy path, thiếu/dư tiền, hết hạn, content có dấu tiếng Việt.
- `tests/test_mbbank_helpers.py` — parse `creditAmount` / `postingDate` từ format MB.
- `tests/test_poller.py` — `BankPoller` với fake bank client: ingest, dedupe, không match, publish event.
- `tests/test_api.py` — e2e qua HTTP: tạo đơn, OpenAPI, SMS webhook fallback.

Tổng 36 tests pass.

## Cấu hình quan trọng (`.env`)

| Biến | Mô tả | Default |
|---|---|---|
| `BANK_BIN` | BIN của NH (970422 = MB) | `970422` |
| `BANK_ACCOUNT_NUMBER` | STK nhận tiền | `YOUR_ACCOUNT_NUMBER` |
| `BANK_ACCOUNT_NAME` | Tên chủ TK (in trên QR) | `YOUR_NAME` |
| `MB_USERNAME` | Username/SĐT đăng nhập MB | rỗng |
| `MB_PASSWORD` | Password MB | rỗng |
| `MB_ACCOUNT_NO` | STK MB cần track. Rỗng = auto từ tài khoản đăng nhập | rỗng |
| `POLL_INTERVAL_SECONDS` | Giây giữa mỗi lần poll. <5s dễ bị MB block | `10` |
| `POLL_LOOKBACK_MINUTES` | Cửa sổ lùi quá khứ ở lần poll đầu (chống miss tx khi worker restart) | `30` |
| `DATABASE_URL` | DSN SQLAlchemy | postgres trong compose |
| `ENABLE_IN_PROCESS_POLLER` | Chạy poller bên trong FastAPI process (thay vì worker container riêng) | `false` |
| `ENABLE_SMS_WEBHOOK` | Bật `/webhooks/sms` làm fallback (xem [docs/sms-fallback.md](docs/android-sms-forwarder.md)) | `false` |
| `WEBHOOK_SECRET` | Secret cho `/webhooks/sms` (chỉ khi bật SMS) | placeholder |
| `ORDER_EXPIRES_MINUTES` | TTL đơn pending | `15` |
| `CORS_ORIGINS` | Comma-separated origins, `*` = all | `*` |

## Mở rộng / thay nguồn dữ liệu

Đã thiết kế `BankClient` interface (`app/services/banking/base.py`). Để chuyển sang Sepay/Casso/NH khác:
1. Tạo class kế thừa `BankClient`, implement `fetch_incoming_transactions(since, until)`.
2. Trỏ `app/worker.py` dùng client mới.

Phần order/QR/SSE/matching giữ nguyên.

## Troubleshooting

- **`test-login` báo 502 `MB login/fetch failed`**:
  - Sai username/password → check lại bằng cách đăng nhập app MB Bank thường.
  - MB tạm khoá vì login nhiều lần fail / nghi automation → đợi 1-2h, thử lại từ IP khác.
  - Captcha OCR fail → thử restart container, lib sẽ retry.
- **Worker không match được giao dịch dù tiền đã vào**:
  - Check log `docker compose logs worker` xem có "Ingested tx" không. Nếu có nhưng không match → so sánh `description` log với `order_code`: format `description` MB trả khác mong đợi → cần điều chỉnh `app/services/matcher.py:normalize`.
- **Order chưa kịp `paid` thì khách đã đóng web** — không sao, web bán hàng chỉ cần poll `/api/orders/{code}` lại lúc khách quay lại; trạng thái lưu trên DB.
- **Muốn match số tiền tuyệt đối** (không cho trả dư): sửa điều kiện ở `app/services/matcher.py:46` từ `>=` thành `==`.

## License

Code này MIT. Lib `mbbank-lib` (https://github.com/thedtvn/MBBank) là MIT của tác giả The DT, không endorsed bởi MB Bank.
