from fastapi import status


def _provider_label(provider: str) -> str:
    labels = {
        "powerbi": "Power BI",
        "fabric": "Fabric",
        "snowflake": "Snowflake",
    }

    return labels.get(provider, provider)


class AppException(Exception):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int,
        provider: str | None = None,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message)

        self.code = code
        self.message = message
        self.status_code = status_code
        self.provider = provider
        self.retry_after = retry_after


class InvalidAccessTokenError(AppException):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="AUTH_TOKEN_INVALID",
            message=(
                f"The supplied {_provider_label(provider)} "
                "access token is invalid or expired."
            ),
            status_code=status.HTTP_401_UNAUTHORIZED,
            provider=provider,
        )


class InsufficientPermissionsError(AppException):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="AUTH_INSUFFICIENT_PERMISSIONS",
            message=(
                f"The supplied {_provider_label(provider)} token "
                "does not have the required permissions."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
            provider=provider,
        )


class UpstreamRateLimitError(AppException):
    def __init__(
        self,
        provider: str,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(
            code="UPSTREAM_RATE_LIMITED",
            message=(
                f"{_provider_label(provider)} is currently rate limiting requests."
            ),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            provider=provider,
            retry_after=retry_after,
        )


class UpstreamTimeoutError(AppException):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="UPSTREAM_TIMEOUT",
            message=(
                f"{_provider_label(provider)} did not respond within the allowed time."
            ),
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            provider=provider,
        )


class UpstreamUnavailableError(AppException):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="UPSTREAM_SERVICE_UNAVAILABLE",
            message=(f"{_provider_label(provider)} is currently unavailable."),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            provider=provider,
        )


class UpstreamRequestError(AppException):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="UPSTREAM_REQUEST_FAILED",
            message=(
                f"The request to {_provider_label(provider)} could not be completed."
            ),
            status_code=status.HTTP_502_BAD_GATEWAY,
            provider=provider,
        )
