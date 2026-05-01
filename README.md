# Payment QR Backend

Backend FastAPI tự động xác nhận thanh toán cho web bán hàng VN qua **biến động số dư SMS** từ ngân hàng — không cần đăng ký dịch vụ trung gian, không cần API ngân hàng doanh nghiệp.

## Cách hoạt động

```
[Web bán hàng]
    │ POST /api/orders {amount, description}
    │   ← {order_code, qr_url, status:"pending", expires_at}
    │ GET  /api/orders/{code}/stream   (SSE realtime)
    ▼
[FastAPI backend]  ← POST /webhooks/sms ← [Android phone forwarder]
    │                                       (nhận SMS biến động, forward HTTP)
    ▼
[PostgreSQL: orders, bank_transactions]
```

1. Web bán hàng gọi `POST /api/orders` để tạo đơn → backend sinh `order_code` duy nhất + URL ảnh QR (chuẩn VietQR) chứa `order_code` ở phần nội dung CK.
2. Khách quét QR, chuyển tiền với nội dung CK = `order_code`.
3. Điện thoại Android (cắm sạc 24/7) nhận SMS biến động số dư từ ngân hàng → app forwarder POST nội dung SMS về `/webhooks/sms`.
4. Backend parse SMS, tìm `order_code` + match số tiền → chuyển order sang `paid` + bắn SSE event về web bán hàng.

## Yêu cầu

- Python 3.11+
- PostgreSQL 14+ (dev có thể chạy SQLite)
- 1 điện thoại Android có SIM nhận SMS từ ngân hàng + 1 app forwarder (xem [docs/android-sms-forwarder.md](docs/android-sms-forwarder.md))

## Cài đặt nhanh (dev với SQLite)

```bash
# 1. Cài deps (khuyên dùng uv hoặc venv)
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 2. Sao .env.example -> .env và sửa thông tin tài khoản nhận tiền
cp .env.example .env
# Mở .env, sửa BANK_BIN / BANK_ACCOUNT_NUMBER / BANK_ACCOUNT_NAME / WEBHOOK_SECRET

# 3. Chạy server (lần đầu sẽ tự tạo bảng SQLite)
uvicorn app.main:app --reload

# 4. Mở http://localhost:8000 -> điền số tiền -> được chuyển sang trang QR
```

## Chạy với Postgres (production-like)

```bash
docker compose up -d postgres
export DATABASE_URL=postgresql+asyncpg://payment:payment@localhost:5432/payments
alembic upgrade head
uvicorn app.main:app --reload
```

Hoặc chạy cả app + postgres bằng compose:

```bash
docker compose up --build
```

## Endpoints

| Method | Path | Mô tả |
|---|---|---|
| POST | `/api/orders` | Tạo đơn, trả về `order_code` + `qr_url` |
| GET | `/api/orders/{code}` | Lấy trạng thái đơn (poll fallback) |
| GET | `/api/orders/{code}/stream` | SSE realtime: nhận event `paid`/`expired`/`canceled` |
| POST | `/api/orders/{code}/cancel` | Huỷ đơn pending |
| POST | `/webhooks/sms` | Endpoint cho Android forwarder (cần header `X-Webhook-Secret`) |
| GET | `/health` | Health check |
| GET | `/docs` | Swagger UI auto-gen |

### Ví dụ tạo đơn

```bash
curl -X POST http://localhost:8000/api/orders \
  -H 'Content-Type: application/json' \
  -d '{"amount": 25000, "description": "Áo thun size L"}'
```

```json
{
  "order_code": "PAY3F7K2X9A",
  "amount": 25000,
  "description": "Áo thun size L",
  "status": "pending",
  "qr_url": "https://img.vietqr.io/image/970436-0123456789-compact2.png?amount=25000&addInfo=PAY3F7K2X9A&accountName=YOUR_NAME",
  "created_at": "2025-01-01T00:00:00Z",
  "expires_at": "2025-01-01T00:15:00Z",
  "paid_at": null
}
```

### Ví dụ giả lập 1 SMS biến động (dev/test)

```bash
curl -X POST http://localhost:8000/webhooks/sms \
  -H 'Content-Type: application/json' \
  -H 'X-Webhook-Secret: <your-WEBHOOK_SECRET>' \
  -d '{
    "message": "VCB 18/04 12:34 TK 0123 +25,000VND. SD: 100,000 VND. ND: PAY3F7K2X9A thanh toan",
    "sender": "Vietcombank"
  }'
```

## Setup Android SMS Forwarder

Xem chi tiết [docs/android-sms-forwarder.md](docs/android-sms-forwarder.md).

## Tích hợp vào web bán hàng

Phía web bán hàng (bất kỳ framework nào):

```js
// 1. Khi user bấm "Thanh toán", gọi backend
const r = await fetch('https://your-backend/api/orders', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({amount: 25000, description: 'Đơn #1234'}),
});
const order = await r.json();

// 2. Hiển thị QR
document.querySelector('img#qr').src = order.qr_url;

// 3. Lắng nghe realtime
const es = new EventSource(`https://your-backend/api/orders/${order.order_code}/stream`);
es.addEventListener('paid', () => {
  alert('Đã thanh toán thành công!');
  // gọi tiếp API tạo đơn nội bộ / chuyển trang...
});
```

## Test

```bash
pytest -q
```

Bao phủ:
- Parser SMS cho 9 NH VN phổ biến (VCB, MB, BIDV, VTB, ACB, TCB, TPB, STB, AGR) + format generic.
- Matching engine: happy path, thiếu tiền (không match), trả dư (vẫn match), order hết hạn, content có dấu tiếng Việt + ký tự đặc biệt.
- End-to-end qua HTTP: tạo đơn → webhook → kiểm tra đã chuyển paid; xác thực secret; idempotent.

## Lint

```bash
ruff check .
ruff format .
```

## Lưu ý bảo mật

- Bảo vệ `/webhooks/sms` bằng `WEBHOOK_SECRET`. Dùng giá trị random ≥ 32 ký tự.
- KHÔNG để cổng webhook public không TLS — proxy qua Cloudflare Tunnel / ngrok / Caddy với HTTPS.
- Nếu host trong nhà, cấu hình SMS forwarder app gửi qua Cloudflare Tunnel public URL.
- Match số tiền: code mặc định cho phép khách trả **bằng hoặc nhiều hơn** số order. Nếu cần khớp tuyệt đối, sửa điều kiện trong `app/services/matcher.py`.

## Mở rộng: thay nguồn dữ liệu

Nếu sau này muốn chuyển sang Sepay/Casso (ổn định hơn parse SMS), chỉ cần thêm 1 router webhook mới (vd `app/api/sepay_webhook.py`) gọi cùng hàm `find_and_match_order(...)`. Logic order/SSE giữ nguyên.
