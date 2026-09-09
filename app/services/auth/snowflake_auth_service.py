from app.clients.snowflake_client import SnowflakeClient
from app.schemas.snowflake_lineage import SnowflakeLineageSnapshot
from app.services.snowflake_lineage_service import SnowflakeLineageService


class SnowflakeAuthService:
    async def discover_lineage(
        self,
        *,
        account_identifier: str,
        access_token: str,
        warehouse: str | None = None,
        role: str | None = None,
        token_type: str = "OAUTH",
    ) -> SnowflakeLineageSnapshot:
        client = SnowflakeClient(
            account_identifier,
            token_type=token_type,
        )
        rows = await client.get_object_dependencies(
            access_token=access_token,
            warehouse=warehouse,
            role=role,
        )
        return SnowflakeLineageService().normalize_rows(
            account_identifier=account_identifier,
            rows=rows,
        )
