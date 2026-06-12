from presidio_analyzer import EntityRecognizer

from backend.presidio.recognizers.account import ACCOUNT_RECOGNIZER
from backend.presidio.recognizers.anumber import A_NUMBER_RECOGNIZER
from backend.presidio.recognizers.case_id import CASE_ID_RECOGNIZER
from backend.presidio.recognizers.dob import DOB_RECOGNIZER
from backend.presidio.recognizers.mrn import MRN_RECOGNIZER


def get_custom_recognizers() -> list[EntityRecognizer]:
    return [
        MRN_RECOGNIZER,
        ACCOUNT_RECOGNIZER,
        CASE_ID_RECOGNIZER,
        A_NUMBER_RECOGNIZER,
        DOB_RECOGNIZER,
    ]
