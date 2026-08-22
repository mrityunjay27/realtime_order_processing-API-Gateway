from app.clients.base import GatewayClient
from app.config import AUTH_SERVICE_URL


class AuthClient(GatewayClient):
    def __init__(self):
        super().__init__(base_url=AUTH_SERVICE_URL, prefix="/api/auth")
