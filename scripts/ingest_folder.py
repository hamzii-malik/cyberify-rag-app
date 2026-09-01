"""Ingest every .md / .txt file in a folder.

Usage:
    python -m scripts.ingest_folder seed
"""

import sys
from pathlib import Path

from app.ingest import ingest_document


def main(folder: str) -> None:
    path = Path(folder)
    files = sorted(list(path.glob("*.md")) + list(path.glob("*.txt")))

    if not files:
        print(f"No .md or .txt files found in {folder}/")
        return

    for f in files:
        text = f.read_text(encoding="utf-8")
        result = ingest_document(title=f.stem, source=f.name, text=text)
        print(f"  {f.name:<22} -> document #{result['document_id']}, {result['chunks']} chunks")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python -m scripts.ingest_folder <folder>")
        sys.exit(1)
    main(sys.argv[1])
