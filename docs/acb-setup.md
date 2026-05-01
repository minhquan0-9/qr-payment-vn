# Setup ACB cho worker

> **Cảnh báo**: thư viện `makky-acb-api` là *unofficial*, đứng tên bên thứ ba
> reverse-engineer mobile API của ACB (`apiapp.acb.com.vn`). Việc tự động hoá
> đăng nhập có thể vi phạm ToS của ACB và dẫn tới khoá tài khoản. Khuyến nghị:
> - Dùng 1 tài khoản ACB riêng dành cho hệ thống nhận tiền của web bán hàng,
>   KHÔNG dùng tài khoản chính.
> - Đặt poll interval ≥ 10 giây để tránh bị rate-limit.

## Yêu cầu

- 1 tài khoản ACB (cá nhân, đã kích hoạt ACB ONE).
- Username + password đăng nhập ACB ONE.

## Cấu hình `.env`

```env
BANK_TYPE=acb
ACB_USERNAME=your_acb_username
ACB_PASSWORD=your_acb_password
# Để rỗng = auto-discover từ list tài khoản; có thể set cụ thể nếu nhiều TK:
ACB_ACCOUNT_NO=

# Cập nhật BIN cho VietQR sinh QR thanh toán đúng NH
BANK_BIN=970416
BANK_ACCOUNT_NUMBER=<số TK ACB>
BANK_ACCOUNT_NAME=<TÊN CHỦ TK ACB>
```

## Chạy

```bash
docker compose --profile acb up --build
```

## Verify

Sau khi `worker-acb` start, gọi endpoint debug:

```bash
curl -X POST 'http://localhost:8000/api/bank/test-login?bank_type=acb' | jq
```

Trả `{"ok": true, "bank_code": "ACB", "recent_incoming_count": ...}` là OK.

## Khi break

ACB có thể đổi `clientId`, `apikey`, hoặc thay đổi schema response bất kỳ lúc
nào. Khi đó:

1. Update `makky-acb-api` lên phiên bản mới: `pip install -U makky-acb-api`.
2. Nếu chưa có bản fix: kiểm tra
   [GitHub issues của lib](https://github.com/Makky/ACB-API/issues).
3. Hoặc fork lib và update `DEFAULT_CLIENT_ID` / `DEFAULT_API_KEY` lấy được
   từ traffic mobile app.

## Cách lấy `clientId` mới (khi cần)

ACB mobile app dùng `clientId` cố định nhúng trong APK. Lấy bằng cách:

1. Cài [mitmproxy](https://mitmproxy.org/) trên máy tính.
2. Cài cert mitm vào điện thoại Android.
3. Set proxy của điện thoại trỏ về máy tính.
4. Mở app ACB ONE, đăng nhập → mitmproxy log lại request `POST /mb/v2/auth/tokens`.
5. Copy `clientId` từ body request, update lib.

Việc này nâng cao và ngoài phạm vi setup chuẩn — chỉ cần khi lib bị outdated.
