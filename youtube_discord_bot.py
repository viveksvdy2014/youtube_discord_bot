import asyncio
import logging
import re

import discord
from discord import VoiceClient
from discord.ext import commands
from pytube import YouTube, StreamQuery, Stream
from pytube import Search

import config

logger = logging.getLogger("bot")

FFMPEG_OPTIONS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                  "options": "-vn"}

user_search_results: dict[str: list] = {}

playlist: list[YouTube] = []
current_playlist_index = -1
vc: VoiceClient
is_playing = False
is_paused = False


def contains_url(input_):
    regex = (r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)"
             r"(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))"
             r"*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))")
    url = re.findall(regex, input_)
    return True if [x[0] for x in url] else False


def main():
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix="!", intents=intents)

    async def search_yt(context, search_input):

        username = context.author.name
        await context.send(f"@{context.author.display_name}, "
                           f"Searching for \"{search_input}\". This may take a couple of seconds.")

        global is_playing

        search = Search(search_input)
        top_3: list[YouTube] = [result for result in search.results[0:3] if not result.age_restricted]
        user_search_results[username] = top_3
        menu = [f"{index + 1} - {result.author} - {result.title}" for index, result in enumerate(top_3)]
        await context.send(f"@{context.author.display_name}, "
                           f"Enter the number of the item to add to queue:\n" + "\n".join(menu))

    async def play_user_selected_item(context, user_selection: int):
        global is_playing
        users_results = user_search_results.get(context.author.name)
        if not users_results or user_selection <= 0 or user_selection > len(users_results):
            await context.send("Invalid Selection!")
            return
        user_selection -= 1
        item_to_play = users_results[user_selection]
        playlist.append(item_to_play)
        await context.send(f"Added to queue: {item_to_play.title}")

        if not is_playing:
            await play_youtube_audio(context)

    async def play_youtube_audio(ctx):

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

        global vc, current_playlist_index, is_playing
        if current_playlist_index == len(playlist) - 1:
            is_playing = False
            return

        is_playing = True

        current_playlist_index += 1
        try:
            vc
        except:
            vc = None
        if vc is None or not vc.is_connected():
            vc = await ctx.author.voice.channel.connect()
            if vc is None:
                await ctx.send("Could not connect to the voice channel")
                return
        else:
            await vc.move_to(ctx.author.voice.channel)
        await ctx.send(f"Now playing: {playlist[current_playlist_index].author} - "
                       f"{playlist[current_playlist_index].title}")
        audio_only_streams = playlist[current_playlist_index].streams.filter(only_audio=True)
        progressive_stream = playlist[current_playlist_index].streams.filter(progressive=True)
        if audio_only_streams:
            stream: Stream = get_best_audio_stream(audio_only_streams)
            url = stream.url
        else:
            stream: Stream = get_best_video_stream(progressive_stream)
            url = stream.url
        vc.play(discord.FFmpegPCMAudio(url, **FFMPEG_OPTIONS),
                after=lambda e: asyncio.run_coroutine_threadsafe(play_youtube_audio(ctx), bot.loop))

    @bot.command()
    async def pause(_, *_args):
        global is_playing, is_paused, vc
        if is_playing:
            is_playing = False
            is_paused = True
            vc.pause()
        elif is_paused:
            is_paused = False
            is_playing = True
            vc.resume()

    @bot.command()
    async def resume(_ctx, *_args):
        global is_playing, is_paused, vc
        if is_paused:
            is_paused = False
            is_playing = True
            vc.resume()

    @bot.command(aliases=["s"])
    async def skip(ctx, *args):
        global playlist, current_playlist_index
        if args:
            skip_amount = args[0]
        else:
            skip_amount = 0
        if skip_amount is not None and skip_amount > 0:
            skip_amount = int(skip_amount) - 1
        if len(playlist[current_playlist_index - 1:]) < skip_amount and skip_amount > 0:
            skip_amount = len(playlist[current_playlist_index - 1:]) - 1
        if vc is not None:
            current_playlist_index += skip_amount
            vc.stop()
            await ctx.send(f"Skipped {skip_amount + 1} songs")

    @bot.command(aliases=["q"])
    async def queue(ctx):
        global current_playlist_index
        retval = "Playlist:\n"
        for i in range(current_playlist_index, len(playlist)):
            if current_playlist_index >= len(playlist) - 1 and not is_playing:
                break
            if i > current_playlist_index + 4:
                break
            if i == current_playlist_index and current_playlist_index < len(playlist) and is_playing:
                retval += "► "
            retval += f"{playlist[i].title}\n"
        if retval != "Playlist:\n":
            await ctx.send(retval)
        else:
            await ctx.send("Queue empty")

    @bot.command(aliases=["cm"])
    async def clear_messages(ctx):
        await ctx.send("Clearing Messages in Text Channel")
        await clear_all_messages_in_bot_text_channel(ctx)

    async def clear_all_messages_in_bot_text_channel(ctx):
        if ctx.channel.name != "youtube-music-bot":
            return
        await ctx.channel.purge(limit=300)

    async def remove_playlist_info(user_input):
        user_input = re.sub(r"&pp=.*", "", user_input)
        return user_input

    @bot.event
    async def on_message(message):
        # Guild Details:
        # Name: 'Area51'
        # ID: 264319539297255434
        # Channel Details:
        # Name: 1169273382345388113
        # ID: 'youtube-music-bot'
        context = await bot.get_context(message)
        if message.channel.name != 'youtube-music-bot' or message.guild.id != 264319539297255434 or \
                message.author.id == 1168480824858001441:  # message.author.name == 'youtube-music-bot'
            return
        user_input = message.content
        try:
            user_input = int(user_input)
        except:
            pass
        if type(user_input) == int:
            await play_user_selected_item(context, user_input)
        elif type(user_input) == str:
            if user_input.startswith("!"):
                await bot.process_commands(message)
                return
            user_input = await remove_playlist_info(user_input)
            await search_yt(context, user_input)

    bot.run(config.DISCORD_API_KEY)


if __name__ == '__main__':
    main()
