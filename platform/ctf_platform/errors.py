from __future__ import annotations


class ApiError(Exception):
    """Exception that can be serialized as the platform error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        http_status: int,
        description: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.description = description or message


def bad_request(message: str, description: str | None = None, status: int = 400) -> ApiError:
    return ApiError("bad_request", message, status, description)


def unauthorized(message: str = "missing or invalid X-Agent-Key") -> ApiError:
    return ApiError("unauthorized", message, 401, "Missing or invalid team Agent Key.")


def not_found(message: str = "resource not found") -> ApiError:
    return ApiError("not_found", message, 404, "The requested API, challenge, file, or env does not exist.")


def env_not_running(message: str = "dynamic env is not running") -> ApiError:
    return ApiError("env_not_running", message, 409, "The dynamic challenge env is not running.")
