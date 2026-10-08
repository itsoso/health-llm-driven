"""Private, non-persistent share-place lookups. Never echo validation input."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from app.api.deps import get_current_user_required
from app.models.user import User
from app.schemas.share_location import NearbyRequest, SearchRequest, LocationResults, LocationAvailability
from app.services import share_location


class PrivateLookupRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def private_handler(request):
            try:
                response = await handler(request)
            except RequestValidationError:
                response = JSONResponse({"detail": "地点查询参数无效，请重新定位或填写"}, status_code=422)
            except HTTPException as exc:
                response = JSONResponse({"detail": exc.detail}, status_code=exc.status_code, headers=exc.headers)
            except Exception:
                response = JSONResponse({"detail": "地点查询暂不可用，请手动填写"}, status_code=503)
            response.headers["Cache-Control"] = "no-store"
            return response

        return private_handler


router = APIRouter(prefix="/share-location", tags=["share-location"], route_class=PrivateLookupRoute)


@router.get("/availability", response_model=LocationAvailability)
def availability(user: User = Depends(get_current_user_required)):
    return LocationAvailability(enabled=share_location.is_available())


@router.post("/nearby", response_model=LocationResults)
def nearby(payload: NearbyRequest, user: User = Depends(get_current_user_required)):
    with share_location.audited_lookup(user.id, "nearby"):
        return share_location.nearby(payload)


@router.post("/search", response_model=LocationResults)
def search(payload: SearchRequest, user: User = Depends(get_current_user_required)):
    with share_location.audited_lookup(user.id, "search"):
        return share_location.search(payload)
