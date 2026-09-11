from pydantic import BaseModel


class GatewayPublicKey(BaseModel):
    exponent: str | None = None
    modulus: str | None = None


class Gateway(BaseModel):
    id: str
    name: str
    type: str

    gateway_annotation: str | None = None
    gateway_status: str | None = None
    public_key: GatewayPublicKey | None = None


class GatewayListResponse(BaseModel):
    gateways: list[Gateway]
    count: int


class GatewayDatasourceCredentialDetails(BaseModel):
    use_end_user_oauth2_credentials: bool | None = None


class GatewayDatasource(BaseModel):
    id: str
    gateway_id: str

    datasource_type: str | None = None
    datasource_name: str | None = None
    connection_details: str | None = None
    credential_type: str | None = None
    credential_details: GatewayDatasourceCredentialDetails | None = None
    # Detects Microsoft Entra ID SSO passthrough only (OAuth2-credentialed
    # connectors). Kerberos/SAML AD-SSO is not observable via this API and is
    # never reported here; None means "not applicable or unknown", not "off".
    sso_enabled: bool | None = None


class GatewayDatasourceListResponse(BaseModel):
    gateway_id: str
    datasources: list[GatewayDatasource]
    count: int
