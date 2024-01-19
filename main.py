import os
from replit import db
import discord
from discord.ext import commands
from twitchAPI.twitch import Twitch
from twitchAPI.types import VideoType
from keep_alive import keep_alive
import time
import asyncio
import datetime
import math


# ========== START =========== #

# set intents
intents = discord.Intents.default()
intents.members = True
intents.presences = True

print(discord.__version__)

# get bot token
discord_token = os.environ['discord_token']

bot = commands.Bot(command_prefix = "~", intents = intents)

# get twitch api token
twitch_secret = os.environ['twitch_secret']

# authenticate on twitch
twitch = Twitch('x7fm1vx131t53txtroq427b5grlc7y', twitch_secret)
twitch.authenticate_app([])

if 'last_notification' not in db.keys():
    db['last_notification'] = None
if 'streamer_login' not in db.keys():
    db['streamer_login'] = "twitch"
if 'live_id' not in db.keys():
    db['live_id'] = '0'

# ========== GLOBAL STATIC VALUES =========== #


current_guild_id = 901904937930346567


# ========== TWITCH =========== #


def get_live_status(login):
    streamer_login = db['streamer_login']
    streamer_info = twitch.get_users(logins=[streamer_login])
    streamer_id = streamer_info['data'][0]['id']
    live_status = twitch.get_streams(user_id=streamer_id)
    if live_status['data']:
        return "🔴stream-live"
    else:
        return "stream-offline"


async def get_video_by_live_id(live_id):
    streamer_login = db['streamer_login']
    streamer_info = twitch.get_users(logins=[streamer_login])
    streamer_id = streamer_info['data'][0]['id']
    last_videos = twitch.get_videos(
        user_id=streamer_id, 
        first=5, 
        video_type=VideoType.ARCHIVE
    )

    for video in last_videos['data']:
        if str(video['stream_id']) == str(live_id):
            print(f"VOD: {video}")
            return video
    else:
        print("no video found")
        return None


async def send_notification():
    streamer_login = db['streamer_login']
    streamer_info = twitch.get_users(logins=[streamer_login])
    streamer_id = streamer_info['data'][0]['id']
    live_status = twitch.get_streams(user_id=streamer_id)
    print("LIVE STATUS: ", live_status)
    print("STREAMER INFO: ", streamer_info)
    
    status_channel = bot.get_channel(db['channel'])
    
    # gone live notification
    if live_status['data']:
        embed = discord.Embed(
            title=live_status['data'][0]['title'],
            url=f"https://www.twitch.tv/{streamer_login}",
            description=f"Playing {live_status['data'][0]['game_name']}",
            timestamp=datetime.datetime.fromisoformat(live_status['data'][0]['started_at'].replace('Z', '')),
            color=discord.Color.purple(),
        )
        embed.set_author(
            name=f"{streamer_info['data'][0]['display_name']} jest live!", 
            url=f"https://www.twitch.tv/{streamer_login}", 
            icon_url=streamer_info['data'][0]['profile_image_url'],
        )
        content = f"{streamer_info['data'][0]['display_name']} jest live!"

        last_notification = await status_channel.send(content=content, embed=embed)
        db['last_notification'] = last_notification.id
        db['live_start_iso_time'] = live_status['data'][0]['started_at'].replace('Z', '')
        db['live_id'] = live_status['data'][0]['id']
    
    # gone offline notification
    elif db['last_notification'] and not live_status['data']:
        last_notification = await bot.get_channel(db['channel']).fetch_message(db['last_notification'])
        live_for = datetime.datetime.today() - datetime.datetime.fromisoformat(db['live_start_iso_time'])
        live_for_hours = ""
        live_for_minutes = ""
        live_for_seconds = ""
        # hours
        if math.floor(live_for.seconds/3600) > 0:
            live_for_hours = f"{math.floor(live_for.seconds/3600)} hour"
            if math.floor(live_for.seconds/3600) != 1:
                live_for_hours += "s"
        # minutes
        if math.floor(live_for.seconds/60) > 0:     # also counting hours as minutes
            live_for_minutes = f"{math.floor(live_for.seconds/60) - math.floor(live_for.seconds/3600)*60} minute"
            if math.floor(live_for.seconds/60) - math.floor(live_for.seconds/3600)*60 != 1:
                live_for_minutes += "s"
        # seconds
        live_for_seconds = f"{live_for.seconds - math.floor(live_for.seconds/60)*60} second"
        if live_for.seconds - math.floor(live_for.seconds/60)*60 != 1:
            live_for_seconds += "s"

        # 'live for' text
        if live_for_hours != "":
            live_for_text = f"{live_for_hours} and {live_for_minutes}"
        elif live_for_minutes != "":
            live_for_text = f"{live_for_minutes} and {live_for_seconds}"
        else:
            live_for_text = f"{live_for_seconds}"

        notification_embed = last_notification.embeds[0]
        vod = await get_video_by_live_id(db['live_id'])
        if vod == None:
            vod = {'url': f"https://www.twitch.tv/{streamer_login}", 'title': notification_embed.title}

        embed = discord.Embed(
            title=vod['title'],
            url=vod['url'],
            description=f"Was {notification_embed.description} for {live_for_text}",
            timestamp=datetime.datetime.today(),
            color=discord.Color.purple(),
        )
        embed.set_author(
            name=f"{streamer_info['data'][0]['display_name']} jest offline!", 
            url=f"https://www.twitch.tv/{streamer_login}", 
            icon_url=streamer_info['data'][0]['profile_image_url'],
        )
        content = f"{streamer_info['data'][0]['display_name']} jest offline"

        await last_notification.edit(content=content, embed=embed)

    return


async def waiting_timer(wait_time, start_time):
    while time.time() - start_time < wait_time:
        await asyncio.sleep(1)
    return


async def alert_runner():
    this_guild = bot.get_guild(current_guild_id)
    streamer_login = db['streamer_login']
    while True:
        start_time = time.time()
        if db['active']:
            try:
                await bot.fetch_channel(db['channel'])
            except:
                print("Wrong channel!")
                print("Deactivating alerts!")
                db['active'] = False
                continue
            status_channel = this_guild.get_channel(db['channel'])
            status = get_live_status(streamer_login)
            if status_channel.name != status:
                print(f"CHANNEL NAME \"{status_channel.name}\" != {status}")
                await send_notification()
                print("SENT/EDITED GOING LIVE NOTIFICATION")
                await status_channel.edit(name=status)
                print(f"CHANGED THE NAME OF CHANNEL TO \"{status}\"")
            else:
                print(f"NOTHING CHANGED")
        await waiting_timer(20, start_time)
    return


# ========== ON READY =========== #


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}\n")

    matches = db.prefix("")
    print(f"====== DATABASE ======\n{matches}\n")

    print(f"====== LIVE ALERT ======")
    if not db['active']:
        print("ALERTS ARE OFF! Turn them on first!")

    await alert_runner()


# ========== DISCORD =========== #


@bot.event
async def on_message(message):
    if message.author.bot == True:
        return

    await bot.process_commands(message)


@bot.command(name = "set_channel")
async def set_channel(ctx, channel):
    if not ctx.author.guild_permissions.administrator:
        await ctx.channel.send("Nie masz permisji do tego bota!")
        return

    channel = ctx.message.channel_mentions[0]

    db['channel'] = channel.id
    await ctx.channel.send(f"Ustawiono kanał na {channel.mention}")


@bot.command(name = "set_streamer")
async def set_streamer(ctx, streamer):
    if not ctx.author.guild_permissions.administrator:
        await ctx.channel.send("Nie masz permisji do tego bota!")
        return

    db['streamer_login'] = streamer
    await ctx.channel.send(f"Ustawiono streamera na {db['streamer_login']}")


@bot.command(name = "activate")
async def activate(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.channel.send("Nie masz permisji do tego bota!")
        return
    
    if not db['channel']:
        await ctx.channel.send("Najpierw ustaw kanał!")
        return
    
    if db['active'] == True:
        await ctx.channel.send("Już był aktywny!")
        return

    db['active'] = True
    await ctx.channel.send("Aktywowano")


@bot.command(name = "deactivate")
async def deactivate(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.channel.send("Nie masz permisji do tego bota!")
        return
    
    if db['active'] == False:
        await ctx.channel.send("Już nie był aktywny!")
        return

    db['active'] = False
    await ctx.channel.send("Zdezaktywowano")


@bot.command(name="manual_status")
async def manual_status_change(ctx, status=None):
    if not ctx.author.guild_permissions.administrator:
        await ctx.channel.send("Nie masz permisji do tego bota!")
        return

    channel = db['channel']
    if status == None:
        status = "alert channel"
    await channel.edit(name=status)


@bot.command(name="print_videos")
async def print_videos(ctx):
    if not ctx.author.guild_permissions.administrator:
        await ctx.channel.send("Nie masz permisji do tego bota!")
        return

    streamer_login = db['streamer_login']
    streamer_info = twitch.get_users(logins=[streamer_login])
    streamer_id = streamer_info['data'][0]['id']
    
    print(await get_video_by_live_id(streamer_id))
    print(f"for live_id = {db['live_id']}")


keep_alive()
bot.run(discord_token)