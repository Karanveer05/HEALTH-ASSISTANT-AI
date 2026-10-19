# Extra knowledge base documents

Put trusted medical text here as `.md` or `.txt` files (for example pages saved from MedlinePlus,
WHO fact sheets or ICMR guidelines). Add a line `Source: <url>` so the report can cite it.

The RAG index is rebuilt automatically on the next server start whenever these files or the JSON
in `backend/data/` change. The curated conditions, medicines, lab tests and remedies in `data/`
are already indexed, so this folder can stay empty.
