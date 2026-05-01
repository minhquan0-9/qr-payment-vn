from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ----- VietQR (sinh QR thanh toán) -----
    bank_bin: str = Field(default="970422")  # 970422 = MB; 970416 = ACB; 970423 = TPB
    bank_account_number: str = Field(default="YOUR_ACCOUNT_NUMBER")
    bank_account_name: str = Field(default="YOUR_NAME")
    # Mã viết tắt NH cho SMS parser (chỉ dùng khi bật ENABLE_SMS_WEBHOOK).
    bank_code: str = Field(default="MB")

    # ----- Worker bank type (chọn 1 NH cho mỗi worker container) -----
    # Một trong: "mb", "acb", "tpb". Worker container đọc env này khi khởi động.
    bank_type: str = Field(default="mb")

    # ----- MB Bank private API -----
    mb_username: str = Field(default="")
    mb_password: str = Field(default="")
    mb_account_no: str = Field(default="")

    # ----- ACB (apiapp.acb.com.vn private mobile API) -----
    acb_username: str = Field(default="")
    acb_password: str = Field(default="")
    acb_account_no: str = Field(default="")

    # ----- TPBank (ebank.tpb.vn web banking) -----
    tpb_username: str = Field(default="")
    tpb_password: str = Field(default="")
    # deviceId lấy từ localStorage trong browser sau khi đăng nhập web banking
    # (xem docs/tpbank-setup.md). Bắt buộc để tránh re-verify khuôn mặt mỗi lần.
    tpb_device_id: str = Field(default="")
    # Số tài khoản TPBank cần track giao dịch
    tpb_account_id: str = Field(default="")

    # ----- Poller -----
    poll_interval_seconds: int = Field(default=10, ge=2)
    poll_lookback_minutes: int = Field(default=30, ge=1)

    # ----- Database / app -----
    database_url: str = Field(default="sqlite+aiosqlite:///./payments.db")
    webhook_secret: str = Field(default="change_me_in_production")
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)
    order_expires_minutes: int = Field(default=15)
    cors_origins: str = Field(default="*")

    # ----- Feature flags -----
    enable_sms_webhook: bool = Field(default=False)
    enable_in_process_poller: bool = Field(default=False)

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
