from app.clients.fabric_client import FabricClient


class FabricAuthService:
    def __init__(self) -> None:
        self.client = FabricClient()

    async def validate(
        self,
        access_token: str,
    ) -> bool:
        return await self.client.validate_connection(
            access_token=access_token,
        )
