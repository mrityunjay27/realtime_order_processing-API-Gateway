from app.clients.auth_client import AuthClient
from app.routes.proxy import make_proxy_router

router = make_proxy_router(AuthClient(), prefix="/api/auth", tag="auth")
