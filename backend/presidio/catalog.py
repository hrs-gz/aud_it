from pydantic import BaseModel

from backend.presidio.recognizers import get_custom_recognizers


class RecognizerCatalogEntry(BaseModel):
    entity_type: str
    label: str
    description: str
    group: str
    custom: bool
    default_enabled: bool


CUSTOM_CATALOG: list[RecognizerCatalogEntry] = [
    RecognizerCatalogEntry(
        entity_type="MEDICAL_RECORD_NUMBER",
        label="Medical Record Number",
        description="Hospital MRN identifiers (e.g. MRN-00048192)",
        group="custom",
        custom=True,
        default_enabled=True,
    ),
    RecognizerCatalogEntry(
        entity_type="ACCOUNT_NUMBER",
        label="Account Number",
        description="Financial account IDs (e.g. ACCT-9842-7710-5531)",
        group="custom",
        custom=True,
        default_enabled=True,
    ),
    RecognizerCatalogEntry(
        entity_type="CASE_ID",
        label="Case ID",
        description="Case reference numbers (e.g. CASE-2026-01984)",
        group="custom",
        custom=True,
        default_enabled=True,
    ),
    RecognizerCatalogEntry(
        entity_type="A_NUMBER",
        label="A-Number",
        description="Alien registration numbers (e.g. A123456789)",
        group="custom",
        custom=True,
        default_enabled=True,
    ),
    RecognizerCatalogEntry(
        entity_type="DOB",
        label="Date of Birth",
        description="Dates near birth-related context (DOB, born, birthdate)",
        group="custom",
        custom=True,
        default_enabled=True,
    ),
]

BUILTIN_LABELS: dict[str, tuple[str, str]] = {
    "EMAIL_ADDRESS": ("Email Address", "Email addresses"),
    "PHONE_NUMBER": ("Phone Number", "Phone and fax numbers"),
    "US_SSN": ("US SSN", "US Social Security numbers"),
    "US_PASSPORT": ("US Passport", "US passport numbers"),
    "US_DRIVER_LICENSE": ("US Driver License", "US driver license numbers"),
    "CREDIT_CARD": ("Credit Card", "Credit card numbers"),
    "IBAN_CODE": ("IBAN", "International bank account numbers"),
    "IP_ADDRESS": ("IP Address", "IPv4 and IPv6 addresses"),
    "DATE_TIME": ("Date/Time", "Dates and times"),
    "PERSON": ("Person Name", "Person names detected by NLP"),
    "LOCATION": ("Location", "Locations and addresses detected by NLP"),
    "ORGANIZATION": ("Organization", "Organization names detected by NLP"),
    "NRP": ("Nationality/Religion/Political", "Nationality, religion, or political group"),
    "MEDICAL_LICENSE": ("Medical License", "Medical license numbers"),
    "URL": ("URL", "Web URLs"),
    "CRYPTO": ("Crypto Wallet", "Cryptocurrency wallet addresses"),
}


def get_custom_entity_types() -> set[str]:
    return {entry.entity_type for entry in CUSTOM_CATALOG}


def build_catalog_from_registry(supported_entities: list[str]) -> list[RecognizerCatalogEntry]:
    custom_types = get_custom_entity_types()
    catalog: list[RecognizerCatalogEntry] = []

    for entity_type in sorted(supported_entities):
        if entity_type in custom_types:
            continue
        label, description = BUILTIN_LABELS.get(
            entity_type,
            (entity_type.replace("_", " ").title(), f"Built-in Presidio entity: {entity_type}"),
        )
        catalog.append(
            RecognizerCatalogEntry(
                entity_type=entity_type,
                label=label,
                description=description,
                group="builtin",
                custom=False,
                default_enabled=entity_type
                in {
                    "EMAIL_ADDRESS",
                    "PHONE_NUMBER",
                    "US_SSN",
                    "US_PASSPORT",
                    "PERSON",
                    "LOCATION",
                    "ORGANIZATION",
                },
            )
        )

    catalog.extend(CUSTOM_CATALOG)
    return catalog
