import os
from logging.config import dictConfig
import pathlib

import discord
from dotenv import load_dotenv

load_dotenv()

DISCORD_API_KEY = os.getenv("DISCORD_API_KEY")
GUILD_ID = discord.Object(id=int(os.getenv("GUILD_ID")))
os.environ["path"] += os.pathsep + os.getenv("FFMPEG_PATH")
os.environ["path"] += os.pathsep + os.getenv("YOUTUBE_DL_PATH")

BASE_DIR = pathlib.Path(__file__).parent

COMMANDS_DIR = BASE_DIR / "cmds"
COGS_DIR = BASE_DIR / "cogs"

LOGGING_CONFIG = {
    "version": 1,
    "disabled_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)-10s - %(asctime)s -%(module)-15s : %(message)s"
        },
        "standard": {
            "format": "%(levelname)-10s - %(name)s -%(module)-15s : %(message)s"
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "standard"
        },
        "console2": {
            "level": "WARNING",
            "class": "logging.StreamHandler",
            "formatter": "standard"
        },
        "file": {
            "level": "INFO",
            "class": "logging.FileHandler",
            "filename": "logs/infos.log",
            "mode": "w",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "bot": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "discord": {
            "handlers": ["console2", "file"],
            "level": "INFO",
            "propagate": False,
        }
    }
}

dictConfig(LOGGING_CONFIG)

if __name__ == '__main__':
    print(DISCORD_API_KEY)
