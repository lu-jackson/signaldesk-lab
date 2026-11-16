"""領域錯誤 → HTTP 狀態碼。400 輸入錯、404 不存在、409 狀態衝突、422 schema、502/503 依賴失敗。"""


class DomainError(Exception):
    status = 400
    code = "bad_request"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFound(DomainError):
    status = 404
    code = "not_found"


class Conflict(DomainError):
    status = 409
    code = "conflict"


class DependencyError(DomainError):
    status = 502
    code = "dependency_failed"


class NotConfigured(DomainError):
    status = 503
    code = "not_configured"
