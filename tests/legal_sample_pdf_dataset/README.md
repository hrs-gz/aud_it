# Synthetic Legal PDF Redaction Test Dataset

This dataset is fully synthetic. It contains no real person, account, case, medical, financial, school, immigration, or legal matter.

## Intended use

Use these PDFs to test a local legal-document workflow for:

- Auto-detection of common personally identifiable information.
- Custom legal-field detection such as Alien Registration Numbers, USCIS receipt numbers, EOIR case numbers, I-94 numbers, passport numbers, clinic IDs, grant IDs, authorization codes, student IDs, police report numbers, and benefits case IDs.
- Manual rectangle redaction over digital PDFs and OCR-based redaction over an image-only scanned-style PDF.
- Batch review, entity grouping by document/page, redaction reporting, and export validation.

## Included files

See `dataset_manifest.csv` for document-level purpose and `expected_sensitive_entities.csv` / `.json` for expected redaction targets.

## Suggested custom regex patterns

These are intentionally broad starting points for testing, not production legal advice.

- A_NUMBER: `\bA[- ]?\d{3}[- ]?\d{3}[- ]?\d{3}\b`
- USCIS_RECEIPT: `\b(?:MSC|IOE|LIN|SRC|WAC|EAC|NBC)\d{10}\b`
- EOIR_CASE: `\bEOIR-\d{2}-\d{6}\b`
- I94_NUMBER: `\b\d{11}\b`
- PASSPORT_NUMBER: `\b[A-Z]\d{8}\b`
- CLIENT_ID: `\bC-\d{4}-\d{5}\b`
- GRANT_ID: `\b[A-Z]{2,4}-[A-Z]{3}-\d{2}-[A-Z]\d\b`
- ROUTING_NUMBER: `\b\d{9}\b`
- BANK_ACCOUNT: `\b\d{10}\b`
- SSN: `\b\d{3}-\d{2}-\d{4}\b`

## Important note

The scanned-style PDF is image-only. It should not expose text through normal PDF text extraction. Use it to test optical character recognition (OCR), confidence display, manual correction, and image redaction behavior.
