import pymupdf as fitz


def strip_all(doc: fitz.Document) -> None:
    doc.set_metadata({})
    if hasattr(doc, "del_xml_metadata"):
        try:
            doc.del_xml_metadata()
        except Exception:
            pass

    try:
        catalog_xref = doc.pdf_catalog()
        for key in ("Producer", "Creator", "Author", "Title", "Subject", "Keywords"):
            try:
                doc.xref_set_key(catalog_xref, f"/{key}", "null")
            except Exception:
                pass
    except Exception:
        pass
