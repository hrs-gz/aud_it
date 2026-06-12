from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from backend.presidio.recognizers import get_custom_recognizers


def _force_offline_tldextract() -> None:
    """The email recognizer uses tldextract, which by default fetches the
    public suffix list over the network. This app must never make network
    calls, so pin it to the bundled snapshot."""
    try:
        import tldextract

        tldextract.tldextract.TLD_EXTRACTOR = tldextract.TLDExtract(
            cache_dir=None, suffix_list_urls=(), fallback_to_snapshot=True
        )
    except Exception:
        pass


_force_offline_tldextract()

NLP_CONFIGURATION = {
    "nlp_engine_name": "spacy",
    "models": [{"lang_code": "en", "model_name": "en_core_web_lg"}],
}


def build_analyzer() -> AnalyzerEngine:
    provider = NlpEngineProvider(nlp_configuration=NLP_CONFIGURATION)
    nlp_engine = provider.create_engine()

    registry = RecognizerRegistry()
    registry.load_predefined_recognizers(nlp_engine=nlp_engine, languages=["en"])
    for recognizer in get_custom_recognizers():
        registry.add_recognizer(recognizer)

    return AnalyzerEngine(
        registry=registry,
        supported_languages=["en"],
        nlp_engine=nlp_engine,
    )
