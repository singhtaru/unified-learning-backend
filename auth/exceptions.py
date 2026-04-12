class AuthError(Exception):
    """Raised for auth failures; handled into a standard JSON envelope."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(message)
