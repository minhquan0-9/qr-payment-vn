# Setup Android SMS Forwarder

Mục tiêu: mỗi khi điện thoại Android nhận SMS biến động số dư từ ngân hàng, app sẽ tự động POST nội dung SMS về backend của bạn.

## Phần cứng đề xuất

- 1 điện thoại Android (Android 6+ là đủ; dùng máy cũ cũng được).
- Cắm sạc 24/7 và để chế độ "tắt tối ưu hoá pin" cho app forwarder (nếu không Android sẽ kill app sau vài giờ).
- SIM số đăng ký nhận SMS biến động số dư của tài khoản nhận tiền.

## Lựa chọn 1 — App `SMS Forwarder` mã nguồn mở

App **SMS Forwarder** (https://github.com/bogkonstantin/android_income_sms_gateway_webhook) hoặc tương đương.

1. Cài app từ APK (có sẵn trên GitHub) hoặc Play Store.
2. Thêm 1 webhook endpoint trỏ về `https://<backend-public-host>/webhooks/sms`.
3. Method: `POST`, Content-Type: `application/json`.
4. Header: `X-Webhook-Secret: <giá trị WEBHOOK_SECRET trong .env>`.
5. Body template (JSON):
   ```json
   {
     "message": "%text%",
     "sender": "%from%",
     "received_at": "%sentStamp%"
   }
   ```
   (Thay placeholder `%text%` / `%from%` theo cú pháp của app bạn dùng.)
6. Lọc theo người gửi (sender filter) để chỉ forward SMS từ ngân hàng:
   - Vietcombank → `Vietcombank` / `VCB`
   - MB Bank → `MBBank` / `MB`
   - Techcombank → `Techcombank` / `TCB`
   - BIDV → `BIDV`
   - VietinBank → `VietinBank`
   - ACB → `ACB`
   - ...
7. Test: gửi 1 SMS test (có thể tự gửi từ máy khác) → check log trên backend.

## Lựa chọn 2 — Macrodroid (no-code)

1. Cài Macrodroid (free version đủ dùng).
2. Tạo macro:
   - Trigger: `SMS Received` → filter sender chứa `Vietcombank` (hoặc tên NH của bạn).
   - Action: `HTTP Request (POST)`
     - URL: `https://<backend-public-host>/webhooks/sms`
     - Headers: `X-Webhook-Secret: <WEBHOOK_SECRET>`, `Content-Type: application/json`
     - Body: `{"message": "[sms]", "sender": "[sender]"}`
3. Cho phép Macrodroid chạy nền + tắt tối ưu pin.

## Mở port public

Backend chạy ở mạng nội bộ → cần expose ra Internet để điện thoại gọi vào:

- **Cloudflare Tunnel** (khuyên dùng, free, có HTTPS sẵn): `cloudflared tunnel --url http://localhost:8000`
- **ngrok**: `ngrok http 8000` (URL đổi mỗi lần chạy ở plan free; trả phí để cố định)
- **VPS công khai**: deploy trực tiếp trên VPS có domain + cert (Caddy/Nginx + Let's Encrypt)

## Kiểm tra

Sau khi cấu hình:

1. Chuyển 1 khoản nhỏ (vd 1.000đ) vào tài khoản với nội dung là `order_code` của 1 đơn pending.
2. Trong vài giây, đơn phải chuyển sang `paid` ở `/api/orders/{code}` và web bán hàng (đang lắng nghe SSE) sẽ thấy event `paid`.
3. Nếu không match: kiểm tra
   - Log backend (uvicorn): xem SMS có đến webhook không, parser có decode được số tiền + nội dung không.
   - Format SMS có thay đổi (NH thỉnh thoảng đổi format) → cập nhật regex trong `app/services/parsers/base.py`.
