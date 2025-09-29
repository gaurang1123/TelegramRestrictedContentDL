# Copyright (C) @TheSmartBisnu
# Channel: https://t.me/itsSmartDev

import os
import shutil
import psutil
import asyncio
from time import time

from pyleaves import Leaves
from pyrogram.enums import ParseMode
from pyrogram import Client, filters
from pyrogram.errors import PeerIdInvalid, BadRequest
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from helpers.utils import (
    getChatMsgID,
    processMediaGroup,
    get_parsed_msg,
    fileSizeLimit,
    progressArgs,
    send_media,
    get_readable_file_size,
    get_readable_time,
)

from config import PyroConf
from logger import LOGGER

# Initialize the bot client
bot = Client(
    "media_bot",
    api_id=PyroConf.API_ID,
    api_hash=PyroConf.API_HASH,
    bot_token=PyroConf.BOT_TOKEN,
    workers=1000,
    parse_mode=ParseMode.MARKDOWN,
)

# Client for user session
user = Client("user_session", workers=1000, session_string=PyroConf.SESSION_STRING)

RUNNING_TASKS = set()

def track_task(coro):
    task = asyncio.create_task(coro)
    RUNNING_TASKS.add(task)
    def _remove(_):
        RUNNING_TASKS.discard(task)
    task.add_done_callback(_remove)
    return task

@bot.on_message(filters.command("start") & filters.private)
async def start(_, message: Message):
    welcome_text = (
        "👋 **Welcome to Media Downloader Bot!**\n\n"
        "I can grab photos, videos, audio, and documents from any Telegram post.\n"
        "Just send me a link (paste it directly or use `/dl <link>`),\n"
        "or reply to a message with `/dl`.\n\n"
        "ℹ️ Use `/help` to view all commands and examples.\n"
        "🔒 Make sure the user client is part of the chat.\n\n"
        "Ready? Send me a Telegram post link!"
    )

    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Update Channel", url="https://t.me/itsSmartDev")]]
    )
    await message.reply(welcome_text, reply_markup=markup, disable_web_page_preview=True)

@bot.on_message(filters.command("help") & filters.private)
async def help_command(_, message: Message):
    help_text = (
        "💡 **Media Downloader Bot Help**\n\n"
        "➤ **Download Media**\n"
        "   – Send `/dl <post_URL>` **or** just paste a Telegram post link to fetch photos, videos, audio, or documents.\n\n"
        "➤ **Requirements**\n"
        "   – Make sure the user client is part of the chat.\n\n"
        "➤ **If the bot hangs**\n"
        "   – Send `/killall` to cancel any pending downloads.\n\n"
        "➤ **Logs**\n"
        "   – Send `/logs` to download the bot’s logs file.\n\n"
        "➤ **Stats**\n"
        "   – Send `/stats` to view current status:\n\n"
        "**Example**:\n"
        "  • `/dl https://t.me/itsSmartDev/547`\n"
        "  • `https://t.me/itsSmartDev/547`"
    )
    
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("Update Channel", url="https://t.me/itsSmartDev")]]
    )
    await message.reply(help_text, reply_markup=markup, disable_web_page_preview=True)


async def handle_download(bot: Client, message: Message, post_url: str):
    # Cut off URL at '?' if present
    if "?" in post_url:
        post_url = post_url.split("?", 1)[0]

    try:
        chat_id, message_id = getChatMsgID(post_url)
        chat_message = await user.get_messages(chat_id=chat_id, message_ids=message_id)

        LOGGER(__name__).info(f"Downloading media from URL: {post_url}")

        if chat_message.document or chat_message.video or chat_message.audio:
            file_size = (
                chat_message.document.file_size
                if chat_message.document
                else chat_message.video.file_size
                if chat_message.video
                else chat_message.audio.file_size
            )

            if not await fileSizeLimit(
                file_size, message, "download", user.me.is_premium
            ):
                return

        parsed_caption = await get_parsed_msg(
            chat_message.caption or "", chat_message.caption_entities
        )
        parsed_text = await get_parsed_msg(
            chat_message.text or "", chat_message.entities
        )

        if chat_message.media_group_id:
            if not await processMediaGroup(chat_message, bot, message):
                await message.reply(
                    "**Could not extract any valid media from the media group.**"
                )
            return

        elif chat_message.media:
            start_time = time()
            progress_message = await message.reply("**📥 Downloading Progress...**")

            media_path = await chat_message.download(
                progress=Leaves.progress_for_pyrogram,
                progress_args=progressArgs(
                    "📥 Downloading Progress", progress_message, start_time
                ),
            )

            LOGGER(__name__).info(f"Downloaded media: {media_path}")

            media_type = (
                "photo"
                if chat_message.photo
                else "video"
                if chat_message.video
                else "audio"
                if chat_message.audio
                else "document"
            )
            await send_media(
                bot,
                message,
                media_path,
                media_type,
                parsed_caption,
                progress_message,
                start_time,
            )

            os.remove(media_path)
            await progress_message.delete()

        elif chat_message.text or chat_message.caption:
            await message.reply(parsed_text or parsed_caption)
        else:
            await message.reply("**No media or text found in the post URL.**")

    except (PeerIdInvalid, BadRequest, KeyError):
        await message.reply("**Make sure the user client is part of the chat.**")
    except Exception as e:
        error_message = f"**❌ {str(e)}**"
        await message.reply(error_message)
        LOGGER(__name__).error(e)


@bot.on_message(filters.command("dl") & filters.private)
async def download_media(bot: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("**Provide a post URL after the /dl command.**")
        return

    post_url = message.command[1]
    await track_task(handle_download(bot, message, post_url))

@bot.on_message(filters.command("dlrange") & filters.private)
async def download_range(bot: Client, message: Message):
    args = message.text.split()

    if len(args) != 3 or not all(arg.startswith("https://t.me/") for arg in args[1:]):
        await message.reply("❌ Usage:\n`/dlrange <start_link> <end_link>`\n\nExample:\n`/dlrange https://t.me/mychannel/100 https://t.me/mychannel/120`")
        return

    try:
        start_chat, start_id = getChatMsgID(args[1])
        end_chat, end_id = getChatMsgID(args[2])
    except Exception as e:
        return await message.reply(f"❌ Error parsing links:\n{e}")

    if start_chat != end_chat:
        return await message.reply("❌ Both links must be from the same channel.")

    if start_id > end_id:
        return await message.reply("❌ Start ID must be less than or equal to End ID.")

    await message.reply(f"📥 **Downloading posts from {start_id} to {end_id}...**")

    for msg_id in range(start_id, end_id + 1):
        try:
            url = f"https://t.me/{start_chat}/{msg_id}"
            await handle_download(bot, message, url)
            await asyncio.sleep(2)
        except Exception as e:
            await message.reply(f"❌ Error at {url}: {e}")


@bot.on_message(filters.command("dlgroup") & filters.private)
async def download_group(bot: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("❌ Usage:\n`/dlgroup <group_link>`\n\nExample:\n`/dlgroup https://t.me/mychannel`")
        return

    group_link = message.command[1].rstrip('/')
    
    try:
        if group_link.startswith("https://t.me/"):
            chat_username = group_link.split("/")[-1]
        else:
            chat_username = group_link
            
        chat = await user.get_chat(chat_username)
        await message.reply(f"📥 **Starting bulk download from {chat.title}...**")
        
        count = 0
        async for msg in user.get_chat_history(chat.id):
            if msg.media or msg.text:
                try:
                    url = f"https://t.me/{chat_username}/{msg.id}"
                    await handle_download(bot, message, url)
                    count += 1
                    await asyncio.sleep(1)
                except Exception as e:
                    LOGGER(__name__).error(f"Error downloading {msg.id}: {e}")
                    
        await message.reply(f"✅ **Completed! Downloaded {count} items from {chat.title}**")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


@bot.on_message(filters.command("dltopic") & filters.private)
async def download_topic(bot: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("❌ Usage:\n`/dltopic <topic_link>`\n\nExample:\n`/dltopic https://t.me/mychannel/123`")
        return

    topic_link = message.command[1]
    
    try:
        chat_id, topic_id = getChatMsgID(topic_link)
        chat = await user.get_chat(chat_id)
        await message.reply(f"📥 **Starting topic download from {chat.title}...**")
        
        count = 0
        message_ids = []
        
        # First, collect all message IDs in the topic
        async for msg in user.get_chat_history(chat_id):
            # Check if message belongs to the topic thread
            if (msg.reply_to_message_id == topic_id or 
                msg.id == topic_id or
                (msg.reply_to_message and msg.reply_to_message.id == topic_id)):
                message_ids.append(msg.id)
        
        # Sort message IDs to download in chronological order
        message_ids.sort()
        
        # Download each message
        for msg_id in message_ids:
            try:
                msg = await user.get_messages(chat_id, msg_id)
                if msg.media or msg.text:
                    # Generate proper URL based on chat type
                    if str(chat_id).startswith('-100'):
                        url = f"https://t.me/c/{str(chat_id)[4:]}/{msg_id}"
                    elif hasattr(chat, 'username') and chat.username:
                        url = f"https://t.me/{chat.username}/{msg_id}"
                    else:
                        url = f"https://t.me/c/{str(chat_id)[4:]}/{msg_id}"
                    
                    await handle_download(bot, message, url)
                    count += 1
                    await asyncio.sleep(1)
            except Exception as e:
                LOGGER(__name__).error(f"Error downloading message {msg_id}: {e}")
                        
        await message.reply(f"✅ **Completed! Downloaded {count} items from topic**")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


@bot.on_message(filters.command("scantopic") & filters.private)
async def scan_topic(bot: Client, message: Message):
    if len(message.command) < 2:
        await message.reply("❌ Usage:\n`/scantopic <topic_link>`\n\nExample:\n`/scantopic https://t.me/mychannel/123`")
        return

    topic_link = message.command[1]
    
    try:
        chat_id, topic_id = getChatMsgID(topic_link)
        chat = await user.get_chat(chat_id)
        await message.reply(f"🔍 **Scanning topic in {chat.title}...**")
        
        message_ids = []
        media_count = 0
        text_count = 0
        
        # Collect all message IDs in the topic
        async for msg in user.get_chat_history(chat_id):
            if (msg.reply_to_message_id == topic_id or 
                msg.id == topic_id or
                (msg.reply_to_message and msg.reply_to_message.id == topic_id)):
                message_ids.append(msg.id)
                if msg.media:
                    media_count += 1
                elif msg.text:
                    text_count += 1
        
        message_ids.sort()
        
        if message_ids:
            ids_text = ", ".join(map(str, message_ids[:20]))  # Show first 20 IDs
            if len(message_ids) > 20:
                ids_text += f"... (+{len(message_ids) - 20} more)"
            
            scan_result = (
                f"📊 **Topic Scan Results**\n\n"
                f"**Total Messages:** {len(message_ids)}\n"
                f"**Media Messages:** {media_count}\n"
                f"**Text Messages:** {text_count}\n\n"
                f"**Message IDs:** {ids_text}\n\n"
                f"Use `/dltopic {topic_link}` to download all media from this topic."
            )
        else:
            scan_result = "❌ **No messages found in this topic.**"
            
        await message.reply(scan_result)
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


@bot.on_message(filters.command("dlgrouprange") & filters.private)
async def download_group_range(bot: Client, message: Message):
    args = message.text.split()
    
    if len(args) != 4:
        await message.reply("❌ Usage:\n`/dlgrouprange <group_link> <start_id> <end_id>`\n\nExample:\n`/dlgrouprange https://t.me/mychannel 100 200`")
        return

    group_link, start_id, end_id = args[1], int(args[2]), int(args[3])
    
    try:
        if group_link.startswith("https://t.me/"):
            chat_username = group_link.split("/")[-1]
        else:
            chat_username = group_link
            
        chat = await user.get_chat(chat_username)
        await message.reply(f"📥 **Downloading from {chat.title} (ID {start_id} to {end_id})...**")
        
        count = 0
        for msg_id in range(start_id, end_id + 1):
            try:
                url = f"https://t.me/{chat_username}/{msg_id}"
                await handle_download(bot, message, url)
                count += 1
                await asyncio.sleep(1)
            except Exception as e:
                LOGGER(__name__).error(f"Error downloading {msg_id}: {e}")
                
        await message.reply(f"✅ **Completed! Downloaded {count} items**")
        
    except Exception as e:
        await message.reply(f"❌ Error: {str(e)}")


@bot.on_message(filters.private & ~filters.command(["start", "help", "dl", "dlrange", "dlgroup", "dltopic", "scantopic", "dlgrouprange", "stats", "logs", "killall"]))
async def handle_any_message(bot: Client, message: Message):
    if message.text and not message.text.startswith("/"):
        await track_task(handle_download(bot, message, message.text))


@bot.on_message(filters.command("stats") & filters.private)
async def stats(_, message: Message):
    currentTime = get_readable_time(time() - PyroConf.BOT_START_TIME)
    total, used, free = shutil.disk_usage(".")
    total = get_readable_file_size(total)
    used = get_readable_file_size(used)
    free = get_readable_file_size(free)
    sent = get_readable_file_size(psutil.net_io_counters().bytes_sent)
    recv = get_readable_file_size(psutil.net_io_counters().bytes_recv)
    cpuUsage = psutil.cpu_percent(interval=0.5)
    memory = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    process = psutil.Process(os.getpid())

    stats = (
        "**≧◉◡◉≦ Bot is Up and Running successfully.**\n\n"
        f"**➜ Bot Uptime:** `{currentTime}`\n"
        f"**➜ Total Disk Space:** `{total}`\n"
        f"**➜ Used:** `{used}`\n"
        f"**➜ Free:** `{free}`\n"
        f"**➜ Memory Usage:** `{round(process.memory_info()[0] / 1024**2)} MiB`\n\n"
        f"**➜ Upload:** `{sent}`\n"
        f"**➜ Download:** `{recv}`\n\n"
        f"**➜ CPU:** `{cpuUsage}%` | "
        f"**➜ RAM:** `{memory}%` | "
        f"**➜ DISK:** `{disk}%`"
    )
    await message.reply(stats)


@bot.on_message(filters.command("logs") & filters.private)
async def logs(_, message: Message):
    if os.path.exists("logs.txt"):
        await message.reply_document(document="logs.txt", caption="**Logs**")
    else:
        await message.reply("**Not exists**")


@bot.on_message(filters.command("killall") & filters.private)
async def cancel_all_tasks(_, message: Message):
    cancelled = 0
    for task in list(RUNNING_TASKS):
        if not task.done():
            task.cancel()
            cancelled += 1
    await message.reply(f"**Cancelled {cancelled} running task(s).**")


if __name__ == "__main__":
    try:
        LOGGER(__name__).info("Bot Started!")
        user.start()
        bot.run()
    except KeyboardInterrupt:
        pass
    except Exception as err:
        LOGGER(__name__).error(err)
    finally:
        LOGGER(__name__).info("Bot Stopped")
