"""Central logging setup that avoids including credentials in messages."""

import logging


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    for name in ("httpx", "httpx2", "openai", "langchain", "langsmith"):
        logging.getLogger(name).setLevel(logging.WARNING)
