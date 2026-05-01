from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ----- VietQR (sinh QR thanh toán) -----
    bank_bin: str = Field(default="970422")  # 970422 = MB Bank
    bank_account_number: str = Field(default="YOUR_ACCOUNT_NUMBER")
    bank_account_name: str = Field(default="YOUR_NAME")
    # Mã viết tắt NH cho SMS parser (chỉ dùng khi bật ENABLE_SMS_WEBHOOK).
    # Một trong: VCB, MB, BIDV, VTB, ACB, TCB, TPB, STB, AGR, GENERIC.
    bank_code: str = Field(default="MB")

    # ----- MB Bank private API (poller) -----
    mb_username: str = Field(default="", description="Username/SĐT đăng nhập app MB Bank")
    mb_password: str = Field(default="", description="Mật khẩu app MB Bank")
    # Số tài khoản MB Bank cần track. Nếu để rỗng sẽ track tất cả tài khoản trong account list.
    mb_account_no: str = Field(default="")
    # Số giây giữa mỗi lần poll
    poll_interval_seconds: int = Field(default=10, ge=2)
    # Số phút lùi về quá khứ khi poll lần đầu (tránh miss giao dịch lúc khởi động)
    poll_lookback_minutes: int = Field(default=30, ge=1)

    # ----- Database / app -----
    database_url: str = Field(default="sqlite+aiosqlite:///./payments.db")
    webhook_secret: str = Field(default="change_me_in_production")

    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    order_expires_minutes: int = Field(default=15)
    cors_origins: str = Field(default="*")

    # ----- Feature flags -----
    # Bật webhook SMS (fallback / kết hợp). Mặc định tắt vì hướng chính là MB poller.
    enable_sms_webhook: bool = Field(default=False)
    # Bật worker poll MB Bank (chạy trong cùng FastAPI process khi không tách worker).
    enable_in_process_poller: bool = Field(default=False)

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
