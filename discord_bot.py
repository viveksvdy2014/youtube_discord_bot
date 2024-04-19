import asyncio
import logging.handlers
import os
import re
import sys
import time
import traceback
import uuid
import pathlib

import discord
from discord import Member, VoiceState, VoiceClient, VoiceChannel, Reaction, Message
from discord.ext.commands import Cog, Bot, Context, command
from pytube import Search, YouTube, StreamQuery, Stream, Playlist

from data_classes import YoutubeSearchResult
from database import initialize_history_table, insert_playlist_item_to_history_db, get_recent_history_items, \
    get_search_result_for_search_id
from decorators import threaded

FFMPEG_OPTIONS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                  "options": "-vn"}


BASE_DIR = pathlib.Path(__file__).parent
LOGS_DIR = BASE_DIR / "logs"


def setup_logger():
    logger = logging.getLogger('discord')
    logger.setLevel(logging.DEBUG)
    logging.getLogger('discord.http').setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler(sys.stdout))
    handler = logging.handlers.RotatingFileHandler(
        filename= LOGS_DIR / "discord.log",
        encoding='utf-8',
        maxBytes=32 * 1024 * 1024,  # 32 MiB
        backupCount=5,  # Rotate through 5 files
    )
    handler.setLevel(logging.DEBUG)
    dt_fmt = '%Y-%m-%d %H:%M:%S'
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class YouTubePlayer(Cog):

    def __init__(self, bot: Bot):
        self.bot: Bot = bot
        self.user_search_results = {}
        self.playlist = []
        self.is_playing = False
        self.voice_client: VoiceClient | None = None
        self.current_playlist_index = -1
        self.logger = logging.getLogger("discord")
        initialize_history_table()

    #     self.add_unfinished_playlist_items_from_db()
    #
    # def add_unfinished_playlist_items_from_db(self):
    #     un_played_urls = get_un_played_playlist_urls()

    @Cog.listener()
    async def on_voice_state_update(self, _member: Member, before: VoiceState, _voice_state: VoiceState):
        bot_voice_clients: dict[VoiceChannel:VoiceClient] = {voice_client.channel: voice_client
                                                             for voice_client in self.bot.voice_clients}
        self.logger.debug(f"Voice State change detected.")
        self.logger.debug(f"{before.channel = }")
        if not before.channel:
            return
        self.logger.debug(f"{len(before.channel.members) = }")
        self.logger.debug(f"{before.channel not in list(bot_voice_clients) = }")
        if len(before.channel.members) - 1 > 1 or before.channel not in list(bot_voice_clients):
            return
        non_bot_members = list(filter(lambda member: not member.bot, before.channel.members))
        self.logger.debug(f"Voice Channel has non bot member? {any(non_bot_members)}")
        if non_bot_members:
            return
        self.playlist = []
        self.is_playing = False
        self.current_playlist_index = -1
        await bot_voice_clients.get(before.channel).disconnect(force=True)
        await self.bot.get_channel(
            int(os.environ["TEXT_CHANNEL_ID"])
        ).send("Leaving Voice Channel as all other users left!", delete_after=5)

    @threaded(daemon=True)
    def delete_expired_search(self, display_name: str, search_uuid: str):
        time.sleep(30)
        if not self.user_search_results.get(display_name):
            return
        if not self.user_search_results.get(display_name).get(search_uuid):
            return
        self.logger.debug(f"Deleting expired search result with ID: {search_uuid}, requested by {display_name}")
        del self.user_search_results[display_name][search_uuid]

    async def search_yt(self, context: Context, search_input: str):
        requester_name = context.author.name
        await context.send(f"@{context.author.display_name}, "
                           f"searching for \"{search_input}\"", delete_after=10)
        search = Search(search_input)
        self.logger.debug(f"New search query by {requester_name}: '{search}'")
        top_3: list[YouTube] = [result for result in search.results[0:3] if not result.age_restricted]
        search_uuid = str(uuid.uuid4())
        if self.user_search_results.get(requester_name):
            self.user_search_results[requester_name][search_uuid] = top_3
        else:
            self.user_search_results[requester_name] = {search_uuid: top_3}
        menu = [f"{index + 1} - {result.title} - {result.author}" for index, result in enumerate(top_3)]
        self.logger.debug(f"{requester_name}: '{search}': {search_uuid}")
        message = await context.send(
            f"@{context.author.display_name}, "
            f"Select one of the following (as reaction):\n" +
            "\n".join(menu) +
            f"\nSearch ID: {search_uuid}",
            delete_after=30
        )
        self.delete_expired_search(context.author.display_name, search_uuid)
        reaction_emojis = ["1️⃣", "2️⃣", "3️⃣"]
        for emoji in reaction_emojis:
            await message.add_reaction(emoji)

    # @command()
    # async def pause(self):
    #     ...
    #
    # @command()
    # async def resume(self):
    #     ...
    #
    @command(aliases=["s"])
    async def skip(self, context: Context, *args: tuple):
        await context.message.delete(delay=5)
        if args and str(args[0]).isnumeric():
            skip_amount = int(str(args[0])) - 1
        else:
            skip_amount = 0
        if len(self.playlist[self.current_playlist_index - 1:]) < skip_amount and skip_amount > 0:
            skip_amount = len(self.playlist[self.current_playlist_index - 1:]) - 1
        if self.voice_client is not None:
            self.current_playlist_index += skip_amount
            self.voice_client.stop()
            await context.send(f"Skipped {skip_amount + 1} songs", delete_after=4)

    @command(aliases=["q"])
    async def queue(self, context: Context):
        await context.message.delete(delay=5)
        retval = "Playlist:\n"
        for i in range(self.current_playlist_index, len(self.playlist)):
            if self.current_playlist_index >= len(self.playlist) - 1 and not self.is_playing:
                break
            if i > self.current_playlist_index + 4:
                break
            if (i == self.current_playlist_index and self.current_playlist_index < len(self.playlist)
                    and self.is_playing):
                retval += "► "
            retval += f"{list(self.playlist[i].values())[0].title}\n"
        if retval != "Playlist:\n":
            await context.send(retval, delete_after=5)
        else:
            await context.send("Queue empty", delete_after=5)

    @command(aliases=["his"])
    async def history(self, context: Context, *args: tuple):
        await context.message.delete(delay=5)
        page = 1
        if args:
            if str(args[0][0]).strip().isnumeric():
                page = int(str(args[0][0]).strip())
        history_items, total_pages = get_recent_history_items(page)
        history_items = [f"{(page - 1) * 10 + index + 1}) {item[2]} - {item[3]} (Added by {item[1]}) (ID: {item[0]})"
                         for index, item in enumerate(history_items)]
        history_items_string = '\n'.join(history_items)
        message = await context.send(f"Playback history (Page {page} out of {total_pages}): \n"
                                     f"{history_items_string}", delete_after=60)
        reaction_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        for i in range(len(history_items)):
            await message.add_reaction(reaction_emojis[i])

    async def play_selected_track(self, selected_track: YouTube, search_id: str,
                                  user: Member, context: Context):

        def get_best_audio_stream(audio_streams: StreamQuery):
            best_stream = None
            for stream_ in audio_streams.fmt_streams:
                if not best_stream:
                    best_stream = stream_
                    continue
                if stream_.abr > best_stream.abr:
                    best_stream = stream_
            return best_stream

        def get_best_video_stream(video_streams: StreamQuery):
            best_stream = None
            for stream_ in video_streams.fmt_streams:
                if not best_stream:
                    best_stream = stream_
                    continue
                if stream_.resolution > best_stream.resolution:
                    best_stream = stream_
            return best_stream

        audio_only_streams = selected_track.streams.filter(only_audio=True)
        progressive_stream = selected_track.streams.filter(progressive=True)
        if audio_only_streams:
            self.logger.debug(f"{search_id}: Found Audio Only stream, proceeding with it.")
            stream: Stream = get_best_audio_stream(audio_only_streams)
            url = stream.url
        else:
            self.logger.debug(f"{search_id}: No Audio Only streams found, proceeding with Video Stream.")
            stream: Stream = get_best_video_stream(progressive_stream)
            url = stream.url
        selected_youtube_search_result = YoutubeSearchResult(
            uuid=search_id,
            added_by=user.display_name,
            uploader_name=selected_track.author,
            title=selected_track.title,
            url=url,
            watch_url=selected_track.watch_url
        )
        self.playlist.append({search_id: selected_youtube_search_result})
        await context.send(f"Added to queue: {selected_track.title}", delete_after=5)
        self.logger.debug(f"play_selected_track: {self.is_playing = }")
        if not self.is_playing:
            await self.play_youtube_audio(context, user)

    @command(aliases=["cm"])
    async def clear_messages(self, context: Context):
        await context.message.delete(delay=5)
        await context.send("Clearing Messages in Text Channel", delete_after=5)
        await self.clear_all_messages_in_bot_text_channel(context)

    @staticmethod
    async def clear_all_messages_in_bot_text_channel(context: Context):
        if context.channel.name != "youtube-music-bot" and context.channel.name != "bot_test":
            return
        await context.channel.purge(limit=300)

    @command(aliases=["rs"])
    async def restart(self, context: Context):
        await context.message.delete(delay=2)
        await context.send("Restarting Bot!", delete_after=2)
        time.sleep(2)
        sys.exit(0)

    @command(aliases=["dc", "l"])
    async def disconnect(self, context: Context):
        await context.message.delete(delay=2)
        await context.send("Disconnecting from Voice Channel!", delete_after=2)
        time.sleep(2)
        await context.voice_client.disconnect(force=True)

    @Cog.listener()
    async def on_reaction_add(self, reaction: Reaction, user: Member):

        async def check_search_result():
            re_matches = re.search(r".*Search ID: (?P<search_id>.+)", message)
            if not re_matches:
                return
            search_id = re_matches.group("search_id")
            search_results: list[YouTube] = self.user_search_results[user.name][search_id]
            choice = str(reaction.emoji)
            reaction_emojis = ["1️⃣", "2️⃣", "3️⃣"]
            if choice not in reaction_emojis:
                return
            selected_track: YouTube | None = None
            if choice == "1️⃣":
                selected_track = search_results[0]
            elif choice == "2️⃣":
                selected_track = search_results[1]
            elif choice == "3️⃣":
                selected_track = search_results[2]
            # await insert_playlist_item_to_playlist(selected_track)

            await self.play_selected_track(selected_track, search_id, user, context)

        async def check_history_result():
            history_entries = message.split("\n")[1:]
            choice = str(reaction.emoji)
            reaction_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
            if choice not in reaction_emojis[:len(history_entries)]:
                return

            selected_track: str | YouTube | None = None
            for index, emoji in enumerate(reaction_emojis):
                if choice == emoji:
                    selected_track = history_entries[index]
            if not selected_track:
                return
            re_matches = re.search(r".*\(ID: (?P<search_id>.+)\)", selected_track)
            if not re_matches:
                return
            search_id = re_matches.group("search_id")

            search_result: YoutubeSearchResult = get_search_result_for_search_id(search_id)
            selected_track = YouTube(search_result.watch_url)
            # await insert_playlist_item_to_playlist(selected_track)
            await self.play_selected_track(selected_track, search_id, user, context)

        if user.bot or reaction.message.channel.id != int(os.environ["TEXT_CHANNEL_ID"]):
            return
        context: Context = await self.bot.get_context(reaction.message)
        message: str = str(reaction.message.clean_content)
        await check_search_result()
        await check_history_result()
        # await reaction.message.delete()

    async def play_youtube_audio(self, context: Context, user: Member = None):

        async def connect_to_voice_channel():
            if not self.voice_client or not self.voice_client.is_connected():
                if user:
                    if user.voice:
                        self.voice_client = await user.voice.channel.connect()
                    else:
                        await context.send("Requester not connected to any voice channel", delete_after=5)
                        raise Exception("Requester not connected to any voice channel")
                else:
                    self.voice_client = await context.author.voice.channel.connect()
                if not self.voice_client:
                    await context.send("Could not connect to the voice channel", delete_after=5)
                    return
            else:
                await self.voice_client.move_to(context.author.voice.channel)

        if self.current_playlist_index == len(self.playlist) - 1:
            self.is_playing = False
            return

        self.is_playing = True
        self.current_playlist_index += 1
        try:
            await connect_to_voice_channel()
        except:
            self.logger.error("Failed to connect to Voice Client")
            self.is_playing = False
            print(traceback.format_exc())
        else:
            playing_item: YoutubeSearchResult = list(self.playlist[self.current_playlist_index].values())[0]
            await context.send(f"Now playing: {playing_item.title} - (Channel: {playing_item.uploader_name})",
                               delete_after=10)
            insert_playlist_item_to_history_db(playing_item)
            self.voice_client.play(discord.FFmpegPCMAudio(playing_item.url, **FFMPEG_OPTIONS),
                                   after=lambda e: asyncio.run_coroutine_threadsafe(self.play_youtube_audio(context),
                                                                                    self.bot.loop))

    @Cog.listener()
    async def on_message(self, message: Message):
        context = await self.bot.get_context(message)
        if message.author.bot or message.channel.id != int(os.environ["TEXT_CHANNEL_ID"]):
            return
        user_input = message.content
        if user_input.startswith("!"):
            # await self.bot.process_commands(message)
            ...
        elif "list=" in user_input:
            for video in Playlist(user_input).videos:
                self.playlist.append(video)
            if not self.is_playing:
                await self.play_youtube_audio(context, message.author)

        else:
            await self.search_yt(context, user_input)
        await message.delete(delay=5)
