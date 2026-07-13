import contextlib
import logging
import os

import dotenv
import uvicorn

with contextlib.suppress(Exception):
    dotenv.load_dotenv(os.path.join(os.getcwd(), ".env"))


def main() -> None:
    from dial_deep_research.app.factory import create_app
    from dial_deep_research.settings import settings
    from dial_deep_research.utils.logging_config import configure_logging

    configure_logging(settings.log_level)
    logging.getLogger(__name__).info(
        "Starting %s on %s:%d",
        settings.dial_app_name,
        settings.app_host,
        settings.app_port,
    )
    # The preparation agent is process-stateless (per-turn state rides on DIAL
    # custom_content.state, not a server-side checkpointer), so the app may run
    # multiple workers/replicas.
    uvicorn.run(
        create_app(),
        host=settings.app_host,
        port=settings.app_port,
        log_config=None,
    )


if __name__ == "__main__":
    main()
