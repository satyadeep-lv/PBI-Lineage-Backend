from typing import Annotated, Literal

from pydantic import BaseModel, Field, SecretStr

SnowflakeAuthenticationMethod = Literal[
    "password",
    "key_pair",
    "external_browser",
    "oauth",
]


class SnowflakeConnectionOptions(BaseModel):
    account_identifier: str = Field(min_length=1, max_length=255)
    user: str = Field(min_length=1, max_length=255)
    warehouse: str | None = Field(default=None, max_length=255)
    database: str | None = Field(default=None, max_length=255)
    schema_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)


class SnowflakePasswordAuthenticationRequest(SnowflakeConnectionOptions):
    authentication_method: Literal["password"]
    password: SecretStr = Field(min_length=1, max_length=1024)
    authenticator: Literal["snowflake", "username_password_mfa"] = "snowflake"
    passcode: SecretStr | None = Field(default=None, max_length=32)
    passcode_in_password: bool = False


class SnowflakeKeyPairAuthenticationRequest(SnowflakeConnectionOptions):
    authentication_method: Literal["key_pair"]
    private_key_pem: SecretStr = Field(min_length=1, max_length=65536)
    private_key_passphrase: SecretStr | None = Field(
        default=None,
        max_length=1024,
    )


class SnowflakeExternalBrowserAuthenticationRequest(SnowflakeConnectionOptions):
    authentication_method: Literal["external_browser"]


class SnowflakeOAuthAuthenticationRequest(SnowflakeConnectionOptions):
    authentication_method: Literal["oauth"]
    token: SecretStr = Field(min_length=1, max_length=16384)


SnowflakeAuthenticationRequest = Annotated[
    SnowflakePasswordAuthenticationRequest
    | SnowflakeKeyPairAuthenticationRequest
    | SnowflakeExternalBrowserAuthenticationRequest
    | SnowflakeOAuthAuthenticationRequest,
    Field(discriminator="authentication_method"),
]


class SnowflakeAuthenticationResponse(BaseModel):
    session_id: str
    status: Literal["authenticated"] = "authenticated"
    authentication_method: SnowflakeAuthenticationMethod
    account_identifier: str
    user: str
    current_account: str | None = None
    current_user: str | None = None
    current_role: str | None = None
    current_warehouse: str | None = None
    current_database: str | None = None
    current_schema: str | None = None
    expires_in: int
    message: str = "Snowflake authentication successful."


class SnowflakeAuthenticationStatusResponse(BaseModel):
    status: Literal["authenticated"] = "authenticated"
    authentication_method: SnowflakeAuthenticationMethod
    account_identifier: str
    user: str
    current_account: str | None = None
    current_user: str | None = None
    current_role: str | None = None
    current_warehouse: str | None = None
    current_database: str | None = None
    current_schema: str | None = None
    expires_in: int
