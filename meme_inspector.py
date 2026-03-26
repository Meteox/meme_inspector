import os
import sqlite3
import asyncio
import random
import aiohttp
import discord
from google import genai
from datetime import datetime
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# -------------------------
# 1. SETUP & CONFIG
# -------------------------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GIPHY_API_KEY = os.getenv("GIPHY_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_KEY")

MODEL_PRIMARY = 'gemini-3.1-flash-lite-preview'
client = genai.Client(api_key=GEMINI_API_KEY)

class MemeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        log_system("Slash-Commands synchronisiert.")

bot = MemeBot()

# -------------------------
# 2. LOGGING & API CHECKS
# -------------------------
def log_system(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ⚙️  SYSTEM: {msg}")

def log_cmd(user, cmd_name, channel):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚔 CMD: {user} nutzte /{cmd_name} in #{channel}")

async def check_apis():
    """Prüft beim Start, ob alle Verbindungen stehen."""
    log_system("Starte API-Integritätstest...")
    
    # 1. Giphy Check
    giphy_ok = False
    async with aiohttp.ClientSession() as session:
        url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q=test&limit=1"
        async with session.get(url) as r:
            if r.status == 200:
                log_system("✅ Giphy API: Verbindung erfolgreich.")
                giphy_ok = True
            else:
                log_system("❌ Giphy API: Key ungültig oder Dienst offline!")

    # 2. Gemini Check
    gemini_ok = False
    try:
        response = await asyncio.to_thread(client.models.generate_content, model=MODEL_PRIMARY, contents="Hi")
        if response.text:
            log_system("✅ Gemini AI: Verbindung erfolgreich.")
            gemini_ok = True
    except Exception as e:
        log_system(f"❌ Gemini AI: Fehler ({e})")

    return giphy_ok and gemini_ok

# -------------------------
# 3. HILFSFUNKTIONEN
# -------------------------
async def get_ai_response(prompt, fallback_text):
    try:
        response = await asyncio.to_thread(client.models.generate_content, model=MODEL_PRIMARY, contents=prompt)
        return response.text[:1000]
    except: return fallback_text

async def get_dynamic_gif(ratio_val, context="meme"):
    search = "cool thumbs up"
    if context == "meme":
        if ratio_val >= 1.2: search = "meme lord praise"
        elif ratio_val >= 0.7: search = "approve nod"
        elif ratio_val >= 0.4: search = "shrug judge"
        else: search = "disappointed facepalm"
    
    url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={search}&limit=10&rating=g"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as r:
                data = await r.json()
                gifs = data.get('data', [])
                if gifs: return random.choice(gifs)['images']['original']['url']
    except: pass
    return "https://media.giphy.com/media/3o7TKSjPQC1Id6S1iM/giphy.gif"

def is_media(msg):
    ext = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm")
    if any(a.filename.lower().endswith(ext) for a in msg.attachments): return True
    if any(e.image or e.video or (e.type in ['image', 'video', 'gifv']) for e in msg.embeds): return True
    return bool(msg.stickers)

# -------------------------
# 4. BEFEHLE (KOMPLETTES SET)
# -------------------------

@bot.tree.command(name="inspect_user", description="🚔 Analyse der Ratio im aktuellen Kanal")
async def inspect_user(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer() # <--- IMMER ZUERST
    log_cmd(interaction.user, "inspect_user", interaction.channel.name)
    target = user or interaction.user
    is_meme_channel = "meme" in interaction.channel.name.lower()
    
    with sqlite3.connect("ratio.db") as conn:
        res = conn.execute("SELECT text_count, meme_count FROM stats WHERE guild_id=? AND channel_id=? AND user_id=?", 
                           (interaction.guild_id, interaction.channel_id, target.id)).fetchone()
    
    txt, meme = (res[0] if res else 0, res[1] if res else 0)
    ratio = meme / (txt if txt > 0 else 1)
    gif_url = await get_dynamic_gif(ratio, context="meme" if is_meme_channel else "chill")
    prompt = f"Du bist der Meme Inspector. Ratio {ratio:.2f} in {'einem Meme-Channel' if is_meme_channel else 'einem normalen Channel'}. Max 15 Wörter."
    ai_comment = await get_ai_response(prompt, "Daten gesichert.")
    
    embed = discord.Embed(title=f"🚔 Urteil: {target.display_name}", color=discord.Color.blue())
    embed.description = f"Kanal: **#{interaction.channel.name}**\n📊 Ratio: `{ratio:.2f}` (🖼️ {meme} / 📝 {txt})"
    embed.set_image(url=gif_url)
    embed.add_field(name="Inspector sagt:", value=ai_comment)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="meme", description="🎲 Postet ein zufälliges Meme-GIF")
async def meme(interaction: discord.Interaction, suchbegriff: str = "funny meme"):
    await interaction.response.defer() # <--- ZUERST
    log_cmd(interaction.user, f"meme ({suchbegriff})", interaction.channel.name)
    await interaction.response.defer()
    url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={suchbegriff}&limit=10&rating=g"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as r:
            data = await r.json()
            gifs = data.get('data', [])
            gif = random.choice(gifs)['images']['original']['url'] if gifs else None
    if gif: await interaction.followup.send(gif)
    else: await interaction.followup.send("Nichts gefunden.")

@bot.tree.command(name="channel_top_stats", description="📊 Top User des Kanals")
async def channel_top_stats(interaction: discord.Interaction):
    await interaction.response.defer() # <--- ZUERST
    log_cmd(interaction.user, "channel_top_stats", interaction.channel.name)
    await interaction.response.defer()
    with sqlite3.connect("ratio.db") as conn:
        res = conn.execute("SELECT user_id, text_count, meme_count FROM stats WHERE guild_id=? AND channel_id=? ORDER BY meme_count DESC LIMIT 10", 
                           (interaction.guild_id, interaction.channel_id)).fetchall()
    embed = discord.Embed(title=f"📊 Kanal-Top 10: #{interaction.channel.name}", color=discord.Color.green())
    for i, (uid, t, m) in enumerate(res, 1):
        u = interaction.guild.get_member(uid)
        embed.add_field(name=f"{i}. {u.display_name if u else uid}", value=f"🖼️ {m} | 📝 {t}", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="server_top_stats", description="🏆 Server-Meme-Ranking")
async def server_top_stats(interaction: discord.Interaction):
    await interaction.response.defer() # <--- ZUERST
    log_cmd(interaction.user, "server_top_stats", interaction.channel.name)
    await interaction.response.defer()
    with sqlite3.connect("ratio.db") as conn:
        res = conn.execute("SELECT user_id, SUM(text_count), SUM(meme_count) FROM stats WHERE guild_id=? GROUP BY user_id ORDER BY SUM(meme_count) DESC LIMIT 10", 
                           (interaction.guild_id,)).fetchall()
    embed = discord.Embed(title="🏆 Server Meme-Könige", color=discord.Color.gold())
    for i, (uid, t, m) in enumerate(res, 1):
        u = interaction.guild.get_member(uid)
        embed.add_field(name=f"{i}. {u.display_name if u else uid}", value=f"🖼️ {m} gesamt", inline=False)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="sys_inspect_deep_scan", description="⚙️ SYSTEM: Kompletter Scan")
async def sys_inspect_deep_scan(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True) # <--- ZUERST (zeigt "Bot denkt nach...")
    log_cmd(interaction.user, "sys_inspect_deep_scan", "ALL")
    if not interaction.user.guild_permissions.administrator: return
    await interaction.response.defer(thinking=True)
    total = 0
    for ch in interaction.guild.text_channels:
        perms = ch.permissions_for(interaction.guild.me)
        if not perms.read_message_history or not perms.view_channel: continue
        log_system(f"Scanne #{ch.name}...")
        async for msg in ch.history(limit=None):
            if msg.author.bot: continue
            m = is_media(msg)
            with sqlite3.connect("ratio.db") as conn:
                conn.execute("INSERT OR IGNORE INTO stats VALUES (?, ?, ?, 0, 0)", (interaction.guild.id, ch.id, msg.author.id))
                f = "meme_count" if m else "text_count"
                conn.execute(f"UPDATE stats SET {f} = {f} + 1 WHERE guild_id=? AND channel_id=? AND user_id=?", (interaction.guild.id, ch.id, msg.author.id))
            total += 1
            if total % 1000 == 0: log_system(f"Fortschritt: {total} Nachrichten...")
    await interaction.followup.send(f"✅ Scan beendet: `{total}` Nachrichten.")

@bot.tree.command(name="wannamaranthyr", description="⏳ Zeit seit DnD")
async def wannamaranthyr(interaction: discord.Interaction):
    await interaction.response.defer() # <--- ZUERST
    log_cmd(interaction.user, "wannamaranthyr", interaction.channel.name)
    await interaction.response.defer()
    with sqlite3.connect("ratio.db") as conn:
        res = conn.execute("SELECT last_session FROM dnd_stats WHERE guild_id=?", (interaction.guild_id,)).fetchone()
    if not res: return await interaction.followup.send("Datum fehlt.")
    delta = (datetime.now() - datetime.strptime(res[0], "%d.%m.%Y")).days
    gif = await get_dynamic_gif(0.1 if delta > 21 else 1.5)
    await interaction.followup.send(embed=discord.Embed(title="🕵️‍♂️ DnD Timer", description=f"Tag {delta} ohne Amaranthyr...").set_image(url=gif))

@bot.tree.command(name="dnd_set_session", description="📅 Datum setzen")
async def dnd_set_session(interaction: discord.Interaction, datum: str):
    log_cmd(interaction.user, "dnd_set_session", interaction.channel.name)
    try:
        datetime.strptime(datum, "%d.%m.%Y")
        with sqlite3.connect("ratio.db") as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS dnd_stats (guild_id INTEGER PRIMARY KEY, last_session TEXT)")
            conn.execute("INSERT OR REPLACE INTO dnd_stats VALUES (?, ?)", (interaction.guild_id, datum))
        await interaction.response.send_message("✅ Datum gespeichert.")
    except: await interaction.response.send_message("❌ Format: DD.MM.YYYY", ephemeral=True)

@bot.tree.command(name="cleanup", description="🧹 Bot-Nachrichten löschen")
async def cleanup(interaction: discord.Interaction, anzahl: int = 5):
    log_cmd(interaction.user, "cleanup", interaction.channel.name)
    await interaction.response.defer(ephemeral=True)
    deleted = 0
    async for msg in interaction.channel.history(limit=50):
        if deleted >= anzahl: break
        if msg.author == bot.user:
            await msg.delete(); deleted += 1
    await interaction.followup.send(f"✅ {deleted} gelöscht.")

@bot.tree.command(name="ask_inspector", description="🤖 Frage an die KI")
async def ask_inspector(interaction: discord.Interaction, frage: str):
    await interaction.response.defer() # <--- ZUERST
    log_cmd(interaction.user, "ask_inspector", interaction.channel.name)
    await interaction.response.defer()
    ai_res = await get_ai_response(f"Antworte kurz: {frage}", "Kein Kommentar.")
    embed = discord.Embed(title="🔍 KI-Anfrage", color=discord.Color.gold())
    embed.add_field(name="❓ Frage", value=f"*{frage}*", inline=False)
    embed.add_field(name="🚔 Urteil", value=ai_res, inline=False)
    await interaction.followup.send(embed=embed)

# -------------------------
# 5. STARTUP & EVENTS
# -------------------------
@bot.event
async def on_ready():
    log_system(f"Anmeldung erfolgreich als {bot.user}")
    
    # Datenbank Setup
    with sqlite3.connect("ratio.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS stats (guild_id INTEGER, channel_id INTEGER, user_id INTEGER, text_count INTEGER DEFAULT 0, meme_count INTEGER DEFAULT 0, PRIMARY KEY (guild_id, channel_id, user_id))")
        conn.execute("CREATE TABLE IF NOT EXISTS dnd_stats (guild_id INTEGER PRIMARY KEY, last_session TEXT)")
    log_system("Datenbank-Check: OK.")

    # API Check
    api_status = await check_apis()
    if api_status:
        log_system("Gesamtsystem: BEREIT FÜR DEN DIENST. 🚔")
    else:
        log_system("⚠️ WARNUNG: Einige APIs sind nicht bereit. Funktionen könnten eingeschränkt sein.")

    await bot.change_presence(activity=discord.Game(name="/inspect_user 🚔"))

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    m = is_media(message)
    with sqlite3.connect("ratio.db") as conn:
        conn.execute("INSERT OR IGNORE INTO stats VALUES (?, ?, ?, 0, 0)", (message.guild.id, message.channel.id, message.author.id))
        f = "meme_count" if m else "text_count"
        conn.execute(f"UPDATE stats SET {f} = {f} + 1 WHERE guild_id=? AND channel_id=? AND user_id=?", (message.guild.id, message.channel.id, message.author.id))

    if not m and "meme" in message.channel.name.lower() and len(message.content) > 60 and random.random() < 0.1:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🤖 AUTO: VETO in #{message.channel.name}")
        ai_msg = await get_ai_response("Rüge den User frech für Text im Meme-Channel.", "Bild her!")
        await message.reply(f"🚔 **Inspector:** {ai_msg}")

    await bot.process_commands(message)

bot.run(TOKEN)
