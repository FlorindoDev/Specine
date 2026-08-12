# Dataset supportati

Il fork usa esclusivamente APPS, APPS-Eval e CodeContests-Raw.

Eseguire `python download_datasets.py` dalla directory principale del progetto e scegliere il dataset dal menu.

APPS e APPS-Eval condividono `apps.jsonl`. CodeContests-Raw usa `code_contests.jsonl`.

La fonte è il record Zenodo `15033911` pubblicato dagli autori di Specine. Il downloader verifica l'archivio ufficiale, estrae soltanto il file scelto e controlla dimensione e CRC32 prima di renderlo disponibile.
