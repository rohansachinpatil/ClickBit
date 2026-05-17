from enum import Enum

class InterventionReason(Enum):
    CAPTCHA_DETECTED = "captcha_detected"
    AUTH_REQUIRED = "auth_required"
    PERMISSION_POPUP = "permission_popup"
    MODAL_BLOCKING_FLOW = "modal_blocking_flow"
    CLOUD_FLARE_VERIFICATION = "cloudflare_verification"
