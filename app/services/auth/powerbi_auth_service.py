from app.clients.powerbi_client import PowerBIClient


class PowerBIAuthService:
    def __init__(self) -> None:
        self.client = PowerBIClient()

    async def validate(
        self,
        access_token: str,
    ) -> bool:
        return await self.client.validate_connection(
            access_token=access_token,
        )
