from fastapi import status


def _provider_label(provider: str) -> str:
    labels = {
        "powerbi": "Power BI",
        "fabric": "Fabric",
        "xmla": "XMLA",
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
    def __init__(
        self,
        provider: str,
        detail: str | None = None,
    ) -> None:
        message = f"The request to {_provider_label(provider)} could not be completed."

        if detail:
            message = f"{message} {detail}"

        super().__init__(
            code="UPSTREAM_REQUEST_FAILED",
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            provider=provider,
        )


class ProviderIntegrationNotConfiguredError(AppException):
    def __init__(
        self,
        provider: str,
        detail: str | None = None,
    ) -> None:
        message = f"{_provider_label(provider)} integration is not configured."

        if detail:
            message = f"{message} {detail}"

        super().__init__(
            code=("PROVIDER_INTEGRATION_NOT_CONFIGURED"),
            message=message,
            status_code=(status.HTTP_501_NOT_IMPLEMENTED),
            provider=provider,
        )


class MissingAuthenticationCredentialsError(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_CREDENTIALS_REQUIRED",
            message=("Authentication credentials are required."),
            status_code=(status.HTTP_401_UNAUTHORIZED),
        )


class InvalidAuthenticationSchemeError(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_SCHEME_INVALID",
            message=("Bearer authentication is required."),
            status_code=(status.HTTP_401_UNAUTHORIZED),
        )


class UpstreamInvalidResponseError(AppException):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="UPSTREAM_INVALID_RESPONSE",
            message=(f"{_provider_label(provider)} returned an invalid response."),
            status_code=status.HTTP_502_BAD_GATEWAY,
            provider=provider,
        )


class ProviderAuthenticationRequiredError(AppException):
    def __init__(
        self,
        provider: str,
    ) -> None:
        super().__init__(
            code="AUTH_PROVIDER_REQUIRED",
            message=(f"{_provider_label(provider)} authentication is required."),
            status_code=(status.HTTP_401_UNAUTHORIZED),
            provider=provider,
        )


class AuthenticationSessionRequiredError(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_SESSION_REQUIRED",
            message=("A valid authentication session is required."),
            status_code=(status.HTTP_401_UNAUTHORIZED),
        )


class AuthenticationSessionExpiredError(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="AUTH_SESSION_EXPIRED",
            message=("The authentication session has expired."),
            status_code=(status.HTTP_401_UNAUTHORIZED),
        )


class ProviderResourceNotFoundError(AppException):
    def __init__(
        self,
        provider: str,
        resource: str,
    ) -> None:
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=(f"{_provider_label(provider)} {resource} was not found."),
            status_code=status.HTTP_404_NOT_FOUND,
            provider=provider,
        )


class ProviderAuthenticationFailedError(AppException):
    def __init__(self, provider: str) -> None:
        super().__init__(
            code="AUTH_PROVIDER_FAILED",
            message=(
                f"{_provider_label(provider)} authentication failed. "
                "Verify the account, identity, authenticator, and assigned role."
            ),
            status_code=status.HTTP_401_UNAUTHORIZED,
            provider=provider,
        )


class ResourceNotFoundError(AppException):
    def __init__(self, resource: str) -> None:
        super().__init__(
            code="RESOURCE_NOT_FOUND",
            message=f"The requested {resource} was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )


class InvalidLineageRequestError(AppException):
    def __init__(self, message: str) -> None:
        super().__init__(
            code="LINEAGE_REQUEST_INVALID",
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
        )


class LineageApiKeyRequiredError(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="LINEAGE_API_KEY_REQUIRED",
            message="A lineage administration API key is required.",
            status_code=status.HTTP_401_UNAUTHORIZED,
        )


class LineageApiKeyInvalidError(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="LINEAGE_API_KEY_INVALID",
            message="The lineage administration API key is invalid.",
            status_code=status.HTTP_403_FORBIDDEN,
        )
