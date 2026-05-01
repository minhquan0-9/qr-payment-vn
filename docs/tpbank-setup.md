# Setup TPBank cho worker

> **Cảnh báo**: TPBank không cung cấp API public cho retail. Adapter này gọi
> trực tiếp internet banking endpoint (`ebank.tpb.vn/gateway/api/...`) sau khi
> đăng nhập với username/password/deviceId. Việc này KHÔNG được TPBank
> endorse. Dùng tài khoản riêng cho web bán hàng, không phải tài khoản chính.

## Yêu cầu

- 1 tài khoản TPBank (cá nhân, đã kích hoạt eBank).
- 1 trình duyệt Chrome/Firefox để lấy `deviceId` lần đầu.

## Bước 1 — Lấy `deviceId` (1 lần đầu)

`deviceId` là giá trị TPBank dùng để đánh dấu thiết bị đã verify khuôn mặt
(face ID). Nếu thiếu nó, mỗi lần login sẽ bắt verify khuôn mặt → automation
không chạy được.

1. Mở Chrome, vào https://ebank.tpb.vn/retail/vX/
2. Đăng nhập bình thường. Nếu được hỏi xác minh khuôn mặt, làm theo hướng dẫn
   trên app TPBank Mobile để xác nhận.
3. Sau khi đăng nhập thành công: bấm **F12** → tab **Console**.
4. Paste lệnh sau, nhấn Enter:
   ```js
   localStorage.deviceId
   ```
5. Copy giá trị string trả về (ví dụ: `"abc123def456..."`) — đây là `deviceId`.

> **Lưu ý**: deviceId này gắn với trình duyệt này. Đừng xoá cookies/localStorage
> của tab này (nếu xoá, phải verify khuôn mặt lại để lấy deviceId mới).

## Bước 2 — Lấy `accountId`

`accountId` chính là **số tài khoản TPBank** anh muốn track (ví dụ
`0123456789`). Có thể tìm trong app TPBank Mobile hoặc trong trang chủ
ebank sau khi đăng nhập.

## Bước 3 — Cấu hình `.env`

```env
BANK_TYPE=tpb
TPB_USERNAME=your_tpb_username
TPB_PASSWORD=your_tpb_password
TPB_DEVICE_ID=<giá trị copy từ console>
TPB_ACCOUNT_ID=<số TK TPBank>

# Cập nhật BIN cho VietQR sinh QR thanh toán đúng NH
BANK_BIN=970423
BANK_ACCOUNT_NUMBER=<số TK TPBank>
BANK_ACCOUNT_NAME=<TÊN CHỦ TK TPBank>
```

## Bước 4 — Chạy

```bash
docker compose --profile tpb up --build
```

## Verify

```bash
curl -X POST 'http://localhost:8000/api/bank/test-login?bank_type=tpb' | jq
```

Trả `{"ok": true, "bank_code": "TPB", "recent_incoming_count": ...}` là OK.

## Khắc phục lỗi thường gặp

### Lỗi "TPB login failed 401"

- Sai username/password, HOẶC
- `deviceId` đã hết hạn / bị TPBank revoke (xảy ra nếu lâu không dùng web banking).
- Giải pháp: làm lại bước 1 để lấy `deviceId` mới.

### Lỗi "Failed to get transactions: 401" lặp đi lặp lại

- Token hết hạn nhưng login lại fail → kiểm tra `deviceId`.

### Bị TPBank block IP

- TPBank có rate-limit / IP block khi poll quá nhanh.
- Giải pháp:
  1. Tăng `POLL_INTERVAL_SECONDS` lên 15-30s.
  2. Dùng VPS có IP residential (không phải datacenter), hoặc dùng proxy xoay.
  3. Adapter hiện tại chưa hỗ trợ proxy — cần thêm tham số `proxies=` vào
     `httpx.AsyncClient` trong `app/services/banking/tpbank_client.py` nếu cần.

## Cách `deviceId` được sinh ra (tham khảo)

`deviceId` được TPBank sinh tự động lúc đăng ký trình duyệt mới và lưu vào
`localStorage`. Quy trình verify: web banking gửi 1 challenge → TPBank Mobile
app nhận push notification → user xác minh khuôn mặt trên app → web banking
nhận response → trình duyệt được "trust" và gắn deviceId.

Logic implementation lấy từ [chuanghiduoc/api_tpbank_free](https://github.com/chuanghiduoc/api_tpbank_free).
