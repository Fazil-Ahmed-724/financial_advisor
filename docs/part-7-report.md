# Part 7 implementation and verification

Verified September 30, 2026 (Asia/Karachi).

The starting services were healthy at Alembic `20260929_0005`; PostgreSQL cluster ID was `7690665958609113124`. The development volume was not reset.

## Design and privacy

TXT is split into cited sections, EPUB XHTML into chapter-file references, and PDF text into page references. Passage rows carry source checksum/extraction-version provenance and indexed PostgreSQL `tsvector` search. Results are short excerpts with title, author, and page/chapter/section citations. No generated-answer model or paid API is used.

Files use UUID storage keys in the private `book_data` volume, which has no public route or host mount. Upload type and size are validated. Original filenames are reduced to their basename and never used as storage paths. Deleting a book cascades passages/learning links and removes its source file. Backups must include PostgreSQL and `book_data`. Image-only PDFs are `ocr_required`; OCR is unavailable.

Decision-passage links are authenticated learning support. They remain separate from market observations, transaction results, tax calculations, risk checks, and process scores, and cannot create an order.

## Main changes

- Migration `20260930_0006` adds `books`, `book_passages`, and `decision_passages` with ownership constraints and indexes.
- `routes_books.py` implements upload, extraction, metadata, reprocessing, deletion, citation search, passage access, and decision attachment.
- `expo-document-picker` and `books.tsx` provide authenticated selection/upload, status, search, citation display, and decision attachment.
- Tests cover TXT/EPUB/PDF states, OCR-required detection, rejected types/size, ownership, citations, unchanged reprocessing, deletion, empty search, and separation boundaries.

## Verification

| Command | Result |
| --- | --- |
| Clean Docker backend suite | 49 passed; one upstream TestClient warning |
| Mobile TypeScript and lint | Passed |
| Alembic schema/model comparison | No new upgrade operations detected |
| Development migration | Applied in place at `20260930_0006 (head)` |
| API/database health and connectivity | Passed; both services healthy and readiness reports connected |
| PostgreSQL identity | Unchanged at `7690665958609113124` |
| Expo dependency check / Doctor | Dependencies current; 21/21 checks passed |

## Limitations

- OCR, semantic vectors, generated answers, and paid model APIs are not implemented.
- EPUB references use content-file chapter names when richer navigation labels are unavailable.
- PDF extraction quality depends on embedded text and document structure.
- Only short excerpts are returned; this is retrieval and citation display, not full-book reproduction.
- Native upload behavior still needs emulator or physical-device smoke testing.
