import logging

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        VectorParams,
        Distance,
    )
    QDRANT_AVAILABLE = True
except ImportError:
    QdrantClient = None
    VectorParams = None
    Distance = None
    QDRANT_AVAILABLE = False

logger = logging.getLogger(__name__)


class QdrantService:

    COLLECTION_NAME = "query_examples"

    client = None

    @staticmethod
    def initialize():
        if not QDRANT_AVAILABLE:
            logger.info(
                "Qdrant client is not installed; skipping Qdrant initialization."
            )
            return

        if QdrantService.client is None:
            QdrantService.client = QdrantClient(
                host="localhost",
                port=6333,
                timeout=0.5
            )

        try:
            collections = (
                QdrantService.client
                .get_collections()
                .collections
            )
        except Exception as e:
            logger.warning(
                f"Failed to connect to Qdrant at localhost:6333 ({e}). "
                "Falling back to in-memory QdrantClient (:memory:) for local development."
            )
            QdrantService.client = QdrantClient(":memory:")
            try:
                collections = (
                    QdrantService.client
                    .get_collections()
                    .collections
                )
            except Exception as inner_e:
                logger.error(f"Failed to initialize in-memory Qdrant: {inner_e}")
                return

        names = [
            c.name
            for c in collections
        ]

        if (
            QdrantService.COLLECTION_NAME
            not in names
        ):
            try: 
                QdrantService.client.create_collection(
                    collection_name=QdrantService.COLLECTION_NAME,
                    vectors_config=VectorParams(
                        size=384,
                        distance=Distance.COSINE
                    )
                )
            except Exception as e:
                logger.error(f"Failed to create Qdrant collection: {e}")
