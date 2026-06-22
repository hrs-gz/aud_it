from fastapi import APIRouter

from backend.presidio.analyzer import get_analyzer_status
from backend.schemas import PresidioStatusResponse, RecognizerCatalogResponse
from backend.services.presidio import list_recognizers

router = APIRouter(prefix="/api/presidio", tags=["presidio"])


@router.get("/status", response_model=PresidioStatusResponse)
def get_presidio_status():
    return PresidioStatusResponse(**get_analyzer_status())


@router.get("/recognizers", response_model=RecognizerCatalogResponse)
def get_recognizers():
    return RecognizerCatalogResponse(recognizers=list_recognizers())
