# MB Bank — Setup & Operational Notes

## Tài khoản dùng cho automation

- **Mở 1 tài khoản MB Bank riêng** chỉ để nhận thanh toán cho web bán hàng. Không dùng tài khoản chính có nhiều tiền hoặc đăng ký dịch vụ doanh nghiệp.
- Đăng nhập app MB Bank trên 1 thiết bị bình thường ít nhất 1 lần để hoàn tất verify số điện thoại / OTP / smartOTP. Sau đó mới chạy automation.
- Tắt SmartOTP (nếu đã bật) cho thao tác xem lịch sử giao dịch — endpoint `getTransactionAccountHistory` không yêu cầu OTP, chỉ cần session.

## Bật / tắt automation

Trong `.env`:

```ini
MB_USERNAME=09xxxxxxxx        # SĐT/username đăng nhập app MB
MB_PASSWORD=your_password
MB_ACCOUNT_NO=                # để rỗng nếu chỉ có 1 TK; điền nếu có nhiều
POLL_INTERVAL_SECONDS=10      # 10s là an toàn; 3-5s dễ bị MB rate-limit
POLL_LOOKBACK_MINUTES=30      # đủ rộng để lúc worker restart không miss tx
```

## Verify

```bash
curl -X POST http://localhost:8000/api/bank/test-login | jq
```

Response thành công:
```json
{
  "ok": true,
  "accounts": ["0123456789"],
  "recent_incoming_count": 0,
  "recent": []
}
```

Response lỗi → check log container `app`:
```bash
docker compose logs -f app
```

Lỗi phổ biến:
| Symptom | Nguyên nhân | Cách xử lý |
|---|---|---|
| `LoginError` / 401 | Sai pass; hoặc MB tạm chặn IP | Đổi pass; đợi 1-2h |
| `CryptoVerifyError` | MB đổi cơ chế WASM/captcha | Update `mbbank-lib` (`pip install -U mbbank-lib` rồi rebuild image) |
| `CapchaError` sau retry | OCR fail liên tục | Tăng `retry_times` trong code, hoặc đợi MB cập nhật captcha |
| `MBBankAPIError 428` | MB yêu cầu xác minh thêm | Đăng nhập app trên điện thoại 1 lần để clear flag |

## Bảo vệ credentials

- Đặt `.env` ngoài git (có sẵn `.gitignore`).
- Trong production, dùng secret manager (AWS Secrets Manager, Vault, Doppler, ...) thay vì lưu plain trong `.env`.
- KHÔNG expose `/api/bank/test-login` ra public (chứa raw credentials trong log nếu fail). Sau khi verify xong, anh có thể xoá file `app/api/bank.py` hoặc bảo vệ bằng auth.

## Vận hành

- Worker container có `restart: unless-stopped` → tự khởi động lại nếu crash.
- Mỗi lần worker khởi động sẽ re-login MB và poll lại với `POLL_LOOKBACK_MINUTES`. Vì có dedupe theo `refNo`, không lo trùng.
- Thời gian "thấy" 1 giao dịch mới: tối đa = `POLL_INTERVAL_SECONDS` + thời gian MB cập nhật vào lịch sử (~3-5s sau khi tiền vào). Tổng độ trễ ~10-20s với default config.

## Khi nào cân nhắc bỏ MB private API

Nếu MB siết security (bind device, ép SmartOTP cho mọi GET), giải pháp này sẽ break liên tục. Lúc đó:
- **Dùng Sepay (sepay.vn)**: free tier, có webhook, ổn định. Cách swap: thêm 1 file `app/services/banking/sepay_client.py` implement `BankClient`, trỏ worker dùng client mới.
- **Hoặc fallback SMS forwarder** (đã có sẵn router `/webhooks/sms`, bật bằng `ENABLE_SMS_WEBHOOK=true`). Xem `docs/android-sms-forwarder.md`.
