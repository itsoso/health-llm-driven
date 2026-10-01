"""Default-off, stateless Streamable HTTP MCP with first-party consent."""
import json
import logging
import re
import contextvars
from contextlib import asynccontextmanager
from datetime import date
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, AnyHttpUrl
from starlette.responses import JSONResponse
from starlette.routing import Route
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import ProviderTokenVerifier
from mcp.server.auth.provider import construct_redirect_uri
from mcp.server.auth.routes import create_auth_routes
from mcp.server.auth.settings import AuthSettings, ClientRegistrationOptions, RevocationOptions
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from app.api.deps import get_current_user_required, bind_authenticated_tenant
from app.services.remote_health_oauth import RemoteHealthOAuth, RemoteHealthConfig, PREFIX, SCOPE
from app.services.remote_health_queries import query_health

logger = logging.getLogger(__name__)
_private_sdk_request = contextvars.ContextVar("remote_health_private_sdk_request", default=False)


def _install_sdk_log_privacy():
    """SDK diagnostics can echo arguments; keep only severity within this request scope."""
    previous = logging.getLogRecordFactory()
    if getattr(previous, "_remote_health_privacy", False):
        return
    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        if _private_sdk_request.get() and (record.name.startswith("mcp.") or record.name == "root"):
            record.msg = "remote_health_sdk_event"
            record.args = ()
            record.exc_info = None
            record.exc_text = None
            record.stack_info = None
        return record
    factory._remote_health_privacy = True
    logging.setLogRecordFactory(factory)


class ConsentBody(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request: str = Field(min_length=43, max_length=43, pattern=r"^[A-Za-z0-9_-]+$")
    expected_user_id: int
    approved: bool


class RemoteBoundary:
    """Bound request sizes, authenticate OAuth resource indicators, and suppress reflected errors."""
    def __init__(self, app, provider):
        self.app, self.provider = app, provider

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        if not scope["path"].startswith(PREFIX + "/"):
            return await self.app(scope, receive, send)
        request = Request(scope, receive)
        if not self.provider.rate_limit("ingress", 600) or not self.provider.rate_limit("ip:" + (request.client.host if request.client else "unknown"), 120):
            return await JSONResponse({"error": "rate_limited"}, 429, headers={"Retry-After": "60"})(scope, receive, send)
        if request.headers.get("host") != urlsplit(self.provider.config.origin).netloc:
            return await JSONResponse({"error": "invalid_host"}, 400)(scope, receive, send)
        origin = request.headers.get("origin")
        if origin and origin != self.provider.config.origin:
            return await JSONResponse({"error": "invalid_origin"}, 403)(scope, receive, send)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16384:
                return await JSONResponse({"error": "request_too_large"}, 413)(scope, receive, send)
        delivered = False
        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        check_request = Request(scope, replay)
        path = scope["path"]
        if path.endswith("/token") or path.endswith("/authorize"):
            data = check_request.query_params if request.method == "GET" else await check_request.form()
            if any(len(data.getlist(k)) != 1 for k in data):
                return await JSONResponse({"error": "invalid_request"}, 400)(scope, receive, send)
            if data.get("resource") != self.provider.config.resource:
                return await JSONResponse({"error": "invalid_target"}, 400)(scope, receive, send)
            if path.endswith("/authorize") and data.get("code_challenge_method") != "S256":
                return await JSONResponse({"error": "invalid_request"}, 400)(scope, receive, send)
            if data.get("grant_type") == "authorization_code" and not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", str(data.get("code_verifier", ""))):
                return await JSONResponse({"error": "invalid_request"}, 400)(scope, receive, send)
        delivered = False
        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers += [(b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer"),
                            (b"x-content-type-options", b"nosniff")]
                if path.endswith("/authorize"):
                    for index, (name, value) in enumerate(headers):
                        if name.lower() == b"location" and any(value.decode().startswith(uri + "?")
                                for c in self.provider.config.clients for uri in c.redirect_uris):
                            headers[index] = (name, construct_redirect_uri(value.decode(), iss=self.provider.config.issuer).encode())
                message = {**message, "headers": headers}
            await send(message)
        privacy = _private_sdk_request.set(True)
        try:
            await self.app(scope, replay, private_send)
        finally:
            _private_sdk_request.reset(privacy)


def install_remote_health(app, config: RemoteHealthConfig, session_factory):
    """Install only after explicit enablement; no grants or secrets are generated at startup."""
    from starlette.applications import Starlette
    _install_sdk_log_privacy()
    provider = RemoteHealthOAuth(config, session_factory)
    mcp = FastMCP("Reva read-only health", token_verifier=ProviderTokenVerifier(provider),
        auth=AuthSettings(issuer_url=AnyHttpUrl(config.issuer), resource_server_url=AnyHttpUrl(config.resource),
                          required_scopes=[SCOPE], validate_token_resource=True),
        stateless_http=True, json_response=True, max_request_body_size=16384,
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=[urlsplit(config.origin).netloc], allowed_origins=[config.origin]),
        instructions="Read only the consenting user's sleep, diet and exercise. Missing records mean unknown, not zero. "
                     "Preserve source/date semantics; do not sum overlapping sources or infer medical diagnoses.")

    def query(kind, start_date, end_date, timezone):
        token = get_access_token()
        if token is None or token.scopes != [SCOPE] or token.resource != config.resource or not token.subject:
            raise ValueError("Read-only authorization required")
        if not provider.rate_limit("user:" + token.subject, 60):
            raise ValueError("Query rate limit reached; retry in one minute")
        try:
            with provider.session() as db:
                bind_authenticated_tenant(db, int(token.subject))
                result = query_health(db, int(token.subject), kind, start_date, end_date, timezone)
            if len(json.dumps(result, ensure_ascii=False).encode()) > 100000:
                raise ValueError("Result too large; request a shorter date range")
            logger.info("remote_health query_ok grant=%s tool=%s", token.claims["grant_id"], kind)
            return result
        except ValueError:
            raise
        except Exception:
            logger.error("remote_health query_failed tool=%s", kind)
            raise ValueError("Health query unavailable") from None

    annotations = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
    @mcp.tool(annotations=annotations, meta={"securitySchemes": [{"type": "oauth2", "scopes": [SCOPE]}]})
    def get_sleep(start_date: date, end_date: date, timezone: str) -> dict:
        """Read own sleep observations; inclusive ISO dates, explicit IANA timezone, max 31 days."""
        return query("sleep", start_date, end_date, timezone)

    @mcp.tool(annotations=annotations, meta={"securitySchemes": [{"type": "oauth2", "scopes": [SCOPE]}]})
    def get_diet(start_date: date, end_date: date, timezone: str) -> dict:
        """Read own diet nutrients without photos or free text; include missingness and sources."""
        return query("diet", start_date, end_date, timezone)

    @mcp.tool(annotations=annotations, meta={"securitySchemes": [{"type": "oauth2", "scopes": [SCOPE]}]})
    def get_exercise(start_date: date, end_date: date, timezone: str) -> dict:
        """Read own exercise observations without GPS; do not sum overlapping sources."""
        return query("exercise", start_date, end_date, timezone)

    router = APIRouter(prefix=PREFIX)
    async def owner(request: Request, user=Depends(get_current_user_required)):
        if request.state.auth_type != "cookie" or getattr(request.state, "is_proxy_mode", False):
            raise HTTPException(403, "Consent requires the account owner's website login")
        if request.method != "GET" and request.headers.get("origin") != config.origin:
            raise HTTPException(403, "Consent origin mismatch")
        return user

    @router.get("/consent")
    async def preview(request: Request, user=Depends(owner)):
        raw = request.query_params.get("request", "")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", raw):
            raise HTTPException(400, "Invalid authorization request")
        try:
            return JSONResponse({**provider.preview(raw), "user_id": user.id}, headers={"Cache-Control": "no-store"})
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @router.post("/consent")
    async def consent(body: ConsentBody, user=Depends(owner)):
        try:
            redirect = provider.consent(body.request, user.id, body.expected_user_id, body.approved)
            return JSONResponse({"redirect_uri": redirect}, headers={"Cache-Control": "no-store"})
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @router.get("/connections")
    async def connections(user=Depends(owner)):
        return JSONResponse(provider.grants(user.id), headers={"Cache-Control": "no-store"})

    @router.delete("/connections/{grant_id}")
    async def disconnect(grant_id: str, user=Depends(owner)):
        provider.revoke_grant(user.id, grant_id)
        return JSONResponse({"revoked": True}, headers={"Cache-Control": "no-store"})

    app.include_router(router)
    sdk_routes = create_auth_routes(provider, AnyHttpUrl(config.issuer),
        client_registration_options=ClientRegistrationOptions(enabled=False, valid_scopes=[SCOPE], default_scopes=[SCOPE]),
        revocation_options=RevocationOptions(enabled=True))

    async def metadata(request):
        return JSONResponse({"issuer": config.issuer, "authorization_endpoint": config.issuer + "/authorize",
            "token_endpoint": config.issuer + "/token", "revocation_endpoint": config.issuer + "/revoke",
            "response_types_supported": ["code"], "grant_types_supported": ["authorization_code", "refresh_token"],
            "scopes_supported": [SCOPE], "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"], "revocation_endpoint_auth_methods_supported": ["none"],
            "authorization_response_iss_parameter_supported": True}, headers={"Cache-Control": "no-store"})

    async def resource_metadata(request):
        return JSONResponse({"resource": config.resource, "authorization_servers": [config.issuer],
            "scopes_supported": [SCOPE], "bearer_methods_supported": ["header"]})

    app.router.routes.append(Route("/.well-known/oauth-authorization-server" + PREFIX, metadata))
    app.router.routes.append(Route("/.well-known/oauth-protected-resource" + PREFIX + "/mcp", resource_metadata))
    mcp_app = mcp.streamable_http_app()
    async def revoke(request):
        # SDK 1.30 requires an optional client_secret field even for public clients.
        # RFC 7009 public-client requests contain only client_id and token.
        data = await request.form()
        if any(len(data.getlist(k)) != 1 for k in data) or not isinstance(data.get("token"), str):
            return JSONResponse({"error": "invalid_request"}, 400)
        client = await provider.get_client(str(data.get("client_id", "")))
        if client is None:
            return JSONResponse({"error": "invalid_client"}, 401)
        raw = data["token"]
        if len(raw) > 128:
            return JSONResponse({}, 200)
        token = await provider.load_access_token(raw)
        if token is None:
            token = await provider.load_refresh_token(client, raw)
        if token is not None and token.client_id == client.client_id:
            await provider.revoke_token(token)
        return JSONResponse({}, 200)

    routes = [r for r in sdk_routes if r.path not in {"/.well-known/oauth-authorization-server", "/revoke"}]
    routes.append(Route("/revoke", revoke, methods=["POST"]))
    routes.append(Route("/.well-known/oauth-authorization-server", metadata))
    routes.extend(mcp_app.routes)
    remote = Starlette(routes=routes, middleware=mcp_app.user_middleware)
    app.mount(PREFIX, remote)
    app.add_middleware(RemoteBoundary, provider=provider)
    old_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with old_lifespan(application):
            async with mcp.session_manager.run():
                yield
    app.router.lifespan_context = lifespan
    return provider
