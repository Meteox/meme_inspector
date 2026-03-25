import discord
from discord.ext import commands
from discord import app_commands
import sqlite3
import re
import asyncio
import random
import aiohttp

# -------------------------
# CONFIG
# -------------------------
TOKEN = "deine"
GIPHY_API_KEY = "mama"

class MemeBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Slash-Commands synchronisiert!")

bot = MemeBot()

# -------------------------
# HELPER FUNCTIONS
# -------------------------

MEDIA_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".webm")

def is_media(message):
    """ Prüft auf echte Bilder, Videos, GIFs oder Sticker. """
    # 1. Dateianhänge prüfen (Bilder/Videos)
    if any(attachment.filename.lower().endswith(MEDIA_EXTENSIONS) for attachment in message.attachments):
        return True
    # 2. Embeds prüfen (GIF-Links, Tenor, Giphy)
    if any(embed.image or embed.video or (embed.type in ['image', 'video', 'gifv']) for embed in message.embeds):
        return True
    # 3. Sticker prüfen (NEU: Sticker zählen jetzt als Meme)
    if len(message.stickers) > 0:
        return True
    return False

async def get_dynamic_gif(ratio_val):
    """ Sucht ein Giphy GIF basierend auf der Meme:Text Ratio """
    perfect_keywords = ["party", "dancing", "celebration", "fireworks", "king", "victory", "hype"]
    good_keywords = ["thumbs up", "nice", "clapping", "happy", "smiling", "cool", "nod"]
    neutral_keywords = ["shrug", "okay", "not bad", "thinking", "staring"]
    bad_keywords = ["yawning", "boring", "reading", "sleeping", "waiting", "bored"]
    outrageous_keywords = ["facepalm", "angry", "screaming", "disappointed", "stop talking", "ugh"]

    if ratio_val >= 1.5:
        search = random.choice(perfect_keywords)
    elif ratio_val >= 1.2:
        search = random.choice(good_keywords)
    elif ratio_val >= 0.8:
        search = random.choice(neutral_keywords)
    elif ratio_val >= 0.5:
        search = random.choice(bad_keywords)
    else:
        search = random.choice(outrageous_keywords)

    url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={search}&limit=20&rating=g"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    gifs = data.get('data', [])
                    if gifs:
                        return random.choice(gifs)['url']
    except: pass
    return "https://media.giphy.com/media/3o7TKSjPQC1Id6S1iM/giphy.gif"

# -------------------------
# SLASH COMMANDS
# -------------------------

@bot.tree.command(name="ratio", description="Checkt die letzten 100 Nachrichten (Meme:Text Ratio)")
async def ratio(interaction: discord.Interaction):
    await interaction.response.defer()
    
    txt_count, meme_count = 0, 0
    async for msg in interaction.channel.history(limit=100):
        if not msg.author.bot:
            if is_media(msg): 
                meme_count += 1
            elif msg.content and msg.content.strip(): 
                # Alles was kein Media ist, aber Text/Emojis enthält, zählt als Text
                txt_count += 1
                
    if txt_count + meme_count == 0:
        return await interaction.followup.send("Keine Nachrichten zum Analysieren gefunden.")
    
    ratio_val = meme_count / (txt_count if txt_count > 0 else 1)
    gif_url = await get_dynamic_gif(ratio_val)
    
    if ratio_val >= 1.5: status = "💎 **PERFECT** - Meme-Paradies!"
    elif ratio_val >= 1.2: status = "✅ **GOOD** - Stabile Quote."
    elif ratio_val >= 0.8: status = "⚖️ **NEUTRAL** - Ausgeglichen."
    elif ratio_val >= 0.5: status = "⚠️ **BAD** - Zu viel Gelaber."
    else: status = "🚫 **OUTRAGEOUS** - Text-Wüste!"

    await interaction.followup.send(
        f"🕒 **Quick-Check (Letzte 100)**\n"
        f"🖼️ Memes: `{meme_count}` | 📝 Text: `{txt_count}`\n"
        f"📊 Ratio: `{ratio_val:.2f}` Memes pro Text.\n"
        f"Urteil: {status}\n\n"
        f"{gif_url}"
    )

@bot.tree.command(name="ratio_user", description="🚔 Einzel-Inspektion eines Verdächtigen")
@app_commands.describe(user="Der User (leer lassen für dich selbst)")
async def ratio_user(interaction: discord.Interaction, user: discord.Member = None):
    await interaction.response.defer()
    target = user or interaction.user
    
    with sqlite3.connect("ratio.db") as conn:
        c = conn.cursor()
        c.execute("SELECT text_count, meme_count FROM stats WHERE guild_id=? AND channel_id=? AND user_id=?", 
                  (interaction.guild_id, interaction.channel_id, target.id))
        res = c.fetchone()
    
    if not res or (res[0] == 0 and res[1] == 0):
        return await interaction.followup.send(f"🔍 Keine Akten zu {target.display_name} gefunden.")
    
    txt, meme = res
    ratio_val = meme / (txt if txt > 0 else 1)
    gif_url = await get_dynamic_gif(ratio_val)
    
    if ratio_val >= 1.5: status = "💎 **PERFECT**"
    elif ratio_val >= 1.2: status = "✅ **GOOD**"
    elif ratio_val >= 0.8: status = "⚖️ **NEUTRAL**"
    elif ratio_val >= 0.5: status = "⚠️ **BAD**"
    else: status = "🚫 **OUTRAGEOUS**"

    await interaction.followup.send(
        f"🚔 **Meme-Inspektion bei {target.mention}**\n"
        f"🖼️ Memes: `{meme}` | 📝 Texte: `{txt}`\n"
        f"📊 Ratio: `{ratio_val:.2f}` Memes pro Text.\n"
        f"Urteil: {status}\n\n"
        f"{gif_url}"
    )

@bot.tree.command(name="ratio_top", description="🏆 Das Meme-Leaderboard dieses Kanals")
async def ratio_top(interaction: discord.Interaction):
    await interaction.response.defer()
    with sqlite3.connect("ratio.db") as conn:
        c = conn.cursor()
        c.execute("""SELECT user_id, text_count, meme_count FROM stats 
                     WHERE guild_id=? AND channel_id=? AND (text_count + meme_count) > 5 
                     ORDER BY (CAST(meme_count AS FLOAT) / CASE WHEN text_count = 0 THEN 1 ELSE text_count END) DESC LIMIT 5""", 
                  (interaction.guild_id, interaction.channel_id))
        rows = c.fetchall()
    
    if not rows: return await interaction.followup.send("Nicht genug Daten vorhanden.")
    
    lines = [f"{['🥇','🥈','🥉','🏅','🏅'][i]} <@{uid}>: `{meme/(txt if txt>0 else 1):.2f}` Ratio" for i, (uid, txt, meme) in enumerate(rows)]
    embed = discord.Embed(title=f"🏆 Meme-Leaderboard: #{interaction.channel.name}", description="\n".join(lines), color=discord.Color.gold())
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="ratio_all", description="Gesamt-Statistik des Kanals")
async def ratio_all(interaction: discord.Interaction):
    with sqlite3.connect("ratio.db") as conn:
        c = conn.cursor()
        c.execute("SELECT SUM(text_count), SUM(meme_count) FROM stats WHERE guild_id=? AND channel_id=?", 
                  (interaction.guild_id, interaction.channel_id))
        res = c.fetchone()
    
    txt, meme = (res[0] or 0, res[1] or 0)
    if txt + meme == 0: return await interaction.response.send_message("Keine Daten.")
    
    ratio_val = meme / (txt if txt > 0 else 1)
    await interaction.response.send_message(f"🌍 **Gesamt-Statistik: #{interaction.channel.name}**\n🖼️ Memes: `{meme}` | 📝 Texte: `{txt}`\n📊 Ratio: `{ratio_val:.2f}`")

@bot.tree.command(name="ratio_refresh", description="Datenbank komplett neu scannen")
async def ratio_refresh(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    with sqlite3.connect("ratio.db") as conn:
        conn.execute("DELETE FROM stats WHERE guild_id=? AND channel_id=?", (interaction.guild_id, interaction.channel_id))
    
    count = 0
    async for msg in interaction.channel.history(limit=None):
        if not msg.author.bot:
            m_status = is_media(msg)
            if m_status or (msg.content and msg.content.strip()):
                with sqlite3.connect("ratio.db") as conn:
                    c = conn.cursor()
                    c.execute("INSERT OR IGNORE INTO stats VALUES (?, ?, ?, 0, 0)", (interaction.guild_id, interaction.channel_id, msg.author.id))
                    f = "meme_count" if m_status else "text_count"
                    c.execute(f"UPDATE stats SET {f} = {f} + 1 WHERE guild_id=? AND channel_id=? AND user_id=?", (interaction.guild_id, interaction.channel_id, msg.author.id))
                    conn.commit()
                count += 1
    await interaction.followup.send(f"✅ Scan von `{count}` Nachrichten abgeschlossen!")

# -------------------------
# GLOBAL SERVER COMMANDS
# -------------------------

@bot.tree.command(name="ratio_server_scan", description="🚔 Große Inspektion: Scannt den gesamten Server (Alle Kanäle)")
async def ratio_server_scan(interaction: discord.Interaction):
    """Scannt den kompletten Nachrichtenverlauf aller Kanäle und füllt die Datenbank"""
    await interaction.response.defer(thinking=True)
    
    total_msgs = 0
    channels_scanned = 0

    for channel in interaction.guild.text_channels:
        perms = channel.permissions_for(interaction.guild.me)
        if not perms.read_message_history or not perms.read_messages:
            continue
        
        channels_scanned += 1
        async for msg in channel.history(limit=None): # limit=None für ALLES
            if msg.author.bot: continue
            
            m_status = is_media(msg)
            if m_status or (msg.content and msg.content.strip()):
                with sqlite3.connect("ratio.db") as conn:
                    c = conn.cursor()
                    c.execute("INSERT OR IGNORE INTO stats VALUES (?, ?, ?, 0, 0)", 
                              (interaction.guild.id, channel.id, msg.author.id))
                    f = "meme_count" if m_status else "text_count"
                    c.execute(f"UPDATE stats SET {f} = {f} + 1 WHERE guild_id=? AND channel_id=? AND user_id=?", 
                              (interaction.guild.id, channel.id, msg.author.id))
                    conn.commit()
                total_msgs += 1
                
    await interaction.followup.send(f"✅ **Inspektion abgeschlossen!**\nScanned Kanäle: `{channels_scanned}`\nErfasste Nachrichten: `{total_msgs}`\nDie globale Datenbank ist nun aktuell.")

@bot.tree.command(name="ratio_server_stats", description="📊 Gesamt-Statistik des kompletten Servers")
async def ratio_server_stats(interaction: discord.Interaction):
    """Gibt die Summe aller Texte und Memes über alle Kanäle aus"""
    with sqlite3.connect("ratio.db") as conn:
        c = conn.cursor()
        c.execute("SELECT SUM(text_count), SUM(meme_count) FROM stats WHERE guild_id=?", (interaction.guild_id,))
        res = c.fetchone()
    
    txt, meme = (res[0] or 0, res[1] or 0)
    if txt + meme == 0:
        return await interaction.response.send_message("Keine Server-Daten vorhanden. Nutze erst `/ratio_server_scan`.")
    
    ratio_val = meme / (txt if txt > 0 else 1)
    
    embed = discord.Embed(title=f"🌍 Globale Server-Statistik: {interaction.guild.name}", color=discord.Color.blue())
    embed.add_field(name="📝 Gesamt Texte", value=f"`{txt}`", inline=True)
    embed.add_field(name="🖼️ Gesamt Memes", value=f"`{meme}`", inline=True)
    embed.add_field(name="📊 Server-Ratio", value=f"`{ratio_val:.2f}` Memes/Text", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ratio_server_user", description="👤 Globale Statistik eines Users über alle Kanäle")
@app_commands.describe(user="Der User (leer lassen für dich selbst)")
async def ratio_server_user(interaction: discord.Interaction, user: discord.Member = None):
    """Summiert die Nachrichten eines Users aus allen Kanälen der Datenbank"""
    target = user or interaction.user
    with sqlite3.connect("ratio.db") as conn:
        c = conn.cursor()
        c.execute("SELECT SUM(text_count), SUM(meme_count) FROM stats WHERE guild_id=? AND user_id=?", 
                  (interaction.guild_id, target.id))
        res = c.fetchone()
    
    txt, meme = (res[0] or 0, res[1] or 0)
    total = txt + meme
    if total == 0:
        return await interaction.response.send_message(f"Keine globalen Daten für {target.display_name} gefunden.")

    ratio_val = meme / (txt if txt > 0 else 1)
    await interaction.response.send_message(
        f"🚔 **Globale Akte: {target.mention}**\n"
        f"Gesamt-Nachrichten: `{total}`\n"
        f"Davon Memes: `{meme}` | Texte: `{txt}`\n"
        f"Globale Ratio: `{ratio_val:.2f}`"
    )

@bot.tree.command(name="ratio_server_top", description="🏆 Top 10 User des Servers (nach Gesamt-Nachrichten)")
async def ratio_server_top(interaction: discord.Interaction):
    """Ranking der aktivsten User basierend auf der Summe aller Nachrichten"""
    with sqlite3.connect("ratio.db") as conn:
        c = conn.cursor()
        # Summiert Texte + Memes pro User über alle Kanäle des Servers
        c.execute("""SELECT user_id, SUM(text_count + meme_count) as total 
                     FROM stats WHERE guild_id=? 
                     GROUP BY user_id 
                     ORDER BY total DESC LIMIT 10""", (interaction.guild_id,))
        rows = c.fetchall()
    
    if not rows:
        return await interaction.response.send_message("Keine Daten für ein Top-Ranking gefunden.")
    
    lines = [f"**#{i+1}** <@{uid}>: `{total}` Nachrichten" for i, (uid, total) in enumerate(rows)]
    embed = discord.Embed(title=f"🏆 Top 10 aktivste User: {interaction.guild.name}", 
                          description="\n".join(lines), color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)
# -------------------------
# EVENTS
# -------------------------

@bot.event
async def on_ready():
    with sqlite3.connect("ratio.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS stats (guild_id INTEGER, channel_id INTEGER, user_id INTEGER, text_count INTEGER DEFAULT 0, meme_count INTEGER DEFAULT 0, PRIMARY KEY (guild_id, channel_id, user_id))")
    await bot.change_presence(activity=discord.Game(name="/ratio | 🚔 Meme Inspector"))
    print(f"🚀 {bot.user} ist im Einsatz!")

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild: return
    m_status = is_media(message)
    # Wenn es kein Bild/Video/GIF ist, aber Inhalt hat -> Text-Counter hoch
    if m_status or (message.content and message.content.strip()):
        with sqlite3.connect("ratio.db") as conn:
            c = conn.cursor()
            c.execute("INSERT OR IGNORE INTO stats (guild_id, channel_id, user_id) VALUES (?, ?, ?)", (message.guild.id, message.channel.id, message.author.id))
            f = "meme_count" if m_status else "text_count"
            c.execute(f"UPDATE stats SET {f} = {f} + 1 WHERE guild_id=? AND channel_id=? AND user_id=?", (message.guild.id, message.channel.id, message.author.id))
            conn.commit()
    await bot.process_commands(message)

bot.run(TOKEN)