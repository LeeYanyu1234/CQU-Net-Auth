import logging


def set_logger(log_level: str):
    if log_level and log_level.lower() == "debug":
        level = logging.DEBUG
    else:
        level = logging.INFO

    logger = logging.getLogger()
    logger.setLevel(level)

    if not logger.handlers:
        ch = logging.StreamHandler()
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    for handler in logger.handlers:
        handler.setLevel(level)

    return logger
