import logging
import sys
from pathlib import Path

import chromadb

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from rag.logging_config import configure_logging

logger = logging.getLogger(__name__)


def main() -> None:
    configure_logging()
    chroma_client = chromadb.HttpClient(host="127.0.0.1", port=8000)
    collections = chroma_client.list_collections()

    logger.info("Local Chroma collection stats")
    if not collections:
        logger.info("No collections in database")
        return

    for col in collections:
        collection = chroma_client.get_collection(name=col.name)
        data_count = collection.count()
        logger.info("Collection %s: %d vectors", col.name, data_count)


if __name__ == "__main__":
    main()
