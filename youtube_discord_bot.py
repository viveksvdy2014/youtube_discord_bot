import asyncio
import logging

from discord import Intents
from discord.ext.commands import Bot

import config
from discord_bot import YouTubePlayer, setup_logger

setup_logger()

logger = logging.getLogger('discord')

if __name__ == '__main__':
    logger.info("Starting execution")
    intents = Intents.default()
    intents.message_content = True
    bot = Bot(command_prefix="!", intents=intents)
    asyncio.run(bot.add_cog(YouTubePlayer(bot)))
    bot.run(config.DISCORD_API_KEY, log_handler=None)
