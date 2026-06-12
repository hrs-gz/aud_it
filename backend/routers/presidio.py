from fastapi import APIRouter

from backend.schemas import RecognizerCatalogResponse
from backend.services.presidio import list_recognizers

router = APIRouter(prefix="/api/presidio", tags=["presidio"])


@router.get("/recognizers", response_model=RecognizerCatalogResponse)
def get_recognizers():
    return RecognizerCatalogResponse(recognizers=list_recognizers())
