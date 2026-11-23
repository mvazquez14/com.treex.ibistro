import logging

from app.seed import main

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init() -> None:
    logger.info("Creating initial data")
    main()
    logger.info("Initial data created")


if __name__ == "__main__":
    init()
