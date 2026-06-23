from presidio_analyzer import EntityRecognizer

from backend.presidio.recognizers.account import ACCOUNT_RECOGNIZER
from backend.presidio.recognizers.anumber import A_NUMBER_RECOGNIZER
from backend.presidio.recognizers.case_id import CASE_ID_RECOGNIZER
from backend.presidio.recognizers.case_number import CASE_NUMBER_RECOGNIZER
from backend.presidio.recognizers.dob import DOB_RECOGNIZER
from backend.presidio.recognizers.email import EMAIL_RECOGNIZER
from backend.presidio.recognizers.eoir_id import EOIR_ID_RECOGNIZER
from backend.presidio.recognizers.government_id import GOVERNMENT_ID_RECOGNIZER
from backend.presidio.recognizers.hearing_access_code import HEARING_ACCESS_CODE_RECOGNIZER
from backend.presidio.recognizers.hearing_number import HEARING_NUMBER_RECOGNIZER
from backend.presidio.recognizers.i94_number import I94_NUMBER_RECOGNIZER
from backend.presidio.recognizers.passport_number import PASSPORT_NUMBER_RECOGNIZER
from backend.presidio.recognizers.phone_number import PHONE_NUMBER_RECOGNIZER
from backend.presidio.recognizers.school_id import SCHOOL_ID_RECOGNIZER
from backend.presidio.recognizers.us_address import US_ADDRESS_RECOGNIZER
from backend.presidio.recognizers.uscis_receipt import USCIS_RECEIPT_RECOGNIZER


def get_custom_recognizers() -> list[EntityRecognizer]:
    return [
        EMAIL_RECOGNIZER,
        PHONE_NUMBER_RECOGNIZER,
        ACCOUNT_RECOGNIZER,
        CASE_ID_RECOGNIZER,
        CASE_NUMBER_RECOGNIZER,
        A_NUMBER_RECOGNIZER,
        DOB_RECOGNIZER,
        US_ADDRESS_RECOGNIZER,
        USCIS_RECEIPT_RECOGNIZER,
        EOIR_ID_RECOGNIZER,
        I94_NUMBER_RECOGNIZER,
        PASSPORT_NUMBER_RECOGNIZER,
        HEARING_NUMBER_RECOGNIZER,
        HEARING_ACCESS_CODE_RECOGNIZER,
        SCHOOL_ID_RECOGNIZER,
        GOVERNMENT_ID_RECOGNIZER,
    ]
