class ApiError(Exception):
    def __init__(self, status_code: int, code: str, detail: str | None = None) -> None:
        self.status_code = status_code
        self.code = code
        self.detail = detail
        super().__init__(code)
