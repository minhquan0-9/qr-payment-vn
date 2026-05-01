from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    amount: int = Field(..., gt=0, description="Số tiền VND, > 0")
    description: str | None = Field(default=None, max_length=255)


class OrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_code: str
    amount: int
    description: str | None
    status: str
    qr_url: str | None
    created_at: datetime
    expires_at: datetime
    paid_at: datetime | None


class SMSPayload(BaseModel):
    """Payload mà Android SMS Forwarder app post về.

    Hầu hết các app forwarder (sms-forwarder, Macrodroid, SMS Gateway) đều có thể
    cấu hình gửi JSON tuỳ ý. Format dưới đây dùng các tên trường phổ biến.
    """

    message: str = Field(..., description="Nội dung SMS gốc")
    sender: str | None = Field(
        default=None, description="Tên/số người gửi (ví dụ 'Vietcombank', '+84...')"
    )
    received_at: datetime | None = Field(default=None)
    bank_code: str | None = Field(
        default=None, description="Override mã ngân hàng (VCB/MB/BIDV/...)"
    )


class SMSWebhookResult(BaseModel):
    accepted: bool
    parsed: bool
    matched_order_code: str | None = None
    amount: int | None = None
    content: str | None = None
    reason: str | None = None
