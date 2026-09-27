import os
import asyncio
import threading

import discord
from discord.ext import commands

from flask import Flask, jsonify


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OWNER_ROLE_ID = os.getenv("OWNER_ROLE_ID")
MEMBER_ROLE_ID = os.getenv("MEMBER_ROLE_ID")

PORT = int(os.getenv("PORT", "10000"))


# ============================================================
# CHECK CONFIG
# ============================================================

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt!")

if not OWNER_ROLE_ID:
    raise RuntimeError("OWNER_ROLE_ID fehlt!")

if not MEMBER_ROLE_ID:
    raise RuntimeError("MEMBER_ROLE_ID fehlt!")

try:
    OWNER_ROLE_ID = int(OWNER_ROLE_ID)
    MEMBER_ROLE_ID = int(MEMBER_ROLE_ID)
except ValueError:
    raise RuntimeError(
        "OWNER_ROLE_ID und MEMBER_ROLE_ID müssen Zahlen sein!"
    )


# ============================================================
# FLASK SERVER
# ============================================================

app = Flask(__name__)


@app.route("/")
def home():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>GoonBot</title>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                background: #111111;
                color: white;
                font-family: Arial, sans-serif;
                text-align: center;
                padding-top: 80px;
            }

            .box {
                max-width: 500px;
                margin: auto;
                background: #1c1c1c;
                padding: 30px;
                border-radius: 15px;
                box-shadow: 0 0 30px rgba(0,0,0,0.5);
            }

            .online {
                color: #00ff88;
                font-weight: bold;
            }
        </style>
    </head>

    <body>
        <div class="box">
            <h1>GoonBot</h1>
            <p class="online">● ONLINE</p>
            <p>Discord bot service is running.</p>
        </div>
    </body>
    </html>
    """


@app.route("/health")
def health():
    return jsonify({
        "status": "online",
        "service": "GoonBot"
    })


# ============================================================
# FLASK THREAD
# ============================================================

def start_flask():
    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    )


# ============================================================
# DISCORD BOT
# ============================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# CONFIRMATION SYSTEM
# ============================================================

pending_delete = set()


# ============================================================
# OWNER CHECK
# ============================================================

def is_owner(member: discord.Member):

    role = member.guild.get_role(OWNER_ROLE_ID)

    if role is None:
        return False

    return role in member.roles


def owner_only():
    async def predicate(ctx):

        if not isinstance(ctx.author, discord.Member):
            return False

        return is_owner(ctx.author)

    return commands.check(predicate)


# ============================================================
# BOT READY
# ============================================================

@bot.event
async def on_ready():

    print("=" * 60)
    print("BOT ONLINE")
    print("=" * 60)

    print(f"Bot:    {bot.user}")
    print(f"Bot ID: {bot.user.id}")
    print(f"Server: {len(bot.guilds)}")

    for guild in bot.guilds:
        print(f" - {guild.name} ({guild.id})")

    print("=" * 60)


# ============================================================
# MEMBER JOIN
# ============================================================

@bot.event
async def on_member_join(member):

    role = member.guild.get_role(MEMBER_ROLE_ID)

    if role is None:
        print(
            f"[WARN] Member role nicht gefunden "
            f"in {member.guild.name}"
        )
        return

    try:
        await member.add_roles(
            role,
            reason="Automatic member role"
        )

        print(
            f"[JOIN] {member} -> "
            f"{role.name}"
        )

    except discord.Forbidden:
        print(
            f"[ERROR] Keine Berechtigung, "
            f"Rolle an {member} zu vergeben."
        )

    except Exception as e:
        print(f"[ERROR] {e}")


# ============================================================
# STATUS
# ============================================================

@bot.command()
@owner_only()
async def status(ctx):

    latency = round(bot.latency * 1000)

    embed = discord.Embed(
        title="🤖 Bot Status",
        color=discord.Color.green()
    )

    embed.add_field(
        name="Status",
        value="🟢 Online",
        inline=True
    )

    embed.add_field(
        name="Ping",
        value=f"{latency} ms",
        inline=True
    )

    embed.add_field(
        name="Server",
        value=str(len(bot.guilds)),
        inline=True
    )

    await ctx.send(embed=embed)


# ============================================================
# LOCKDOWN
# ============================================================

@bot.command()
@owner_only()
async def lockdown(ctx):

    await ctx.send(
        "🔒 Lockdown wird aktiviert..."
    )

    success = 0
    failed = 0

    for channel in ctx.guild.text_channels:

        try:

            await channel.set_permissions(
                ctx.guild.default_role,
                send_messages=False,
                reason="Emergency lockdown"
            )

            success += 1

        except Exception:
            failed += 1

    await ctx.send(
        f"🔒 Lockdown abgeschlossen.\n"
        f"Erfolgreich: `{success}`\n"
        f"Fehlgeschlagen: `{failed}`"
    )


# ============================================================
# DELETE COMMAND
# ============================================================

@bot.command(name="del")
@owner_only()
async def delete_command(ctx):

    guild_id = ctx.guild.id

    if guild_id in pending_delete:

        await ctx.send(
            "⚠️ Für diesen Server läuft bereits "
            "eine Bestätigung."
        )

        return

    pending_delete.add(guild_id)

    warning = await ctx.send(
        "🚨 **NOTFALL-AKTION** 🚨\n\n"
        "Diese Aktion kann Server-Strukturen verändern "
        "und Channels löschen.\n\n"
        "Wenn du wirklich fortfahren willst, "
        "schreibe innerhalb von **30 Sekunden**:\n\n"
        "`CONFIRM`"
    )

    def check(message):

        return (
            message.guild is not None
            and message.guild.id == guild_id
            and message.author.id == ctx.author.id
            and message.content.strip() == "CONFIRM"
        )

    try:

        await bot.wait_for(
            "message",
            timeout=30,
            check=check
        )

    except asyncio.TimeoutError:

        pending_delete.discard(guild_id)

        await ctx.send(
            "❌ Vorgang abgebrochen. "
            "Keine Bestätigung erhalten."
        )

        return

    pending_delete.discard(guild_id)

    await ctx.send(
        "✅ Bestätigung erhalten.\n"
        "Starte Recovery..."
    )

    await perform_emergency_delete(ctx.guild)


# ============================================================
# EMERGENCY RECOVERY
# ============================================================

async def perform_emergency_delete(guild):

    print(
        f"[RECOVERY] Starte Recovery für "
        f"{guild.name}"
    )

    # --------------------------------------------------------
    # REMOVE ROLES FROM MEMBERS
    # --------------------------------------------------------

    removed_roles = 0

    bot_member = guild.me

    if bot_member is not None:

        bot_top_role = bot_member.top_role

        for member in guild.members:

            if member == guild.owner:
                continue

            if member == bot_member:
                continue

            removable_roles = []

            for role in member.roles:

                if role.is_default():
                    continue

                if role.managed:
                    continue

                if role >= bot_top_role:
                    continue

                removable_roles.append(role)

            if not removable_roles:
                continue

            try:

                await member.remove_roles(
                    *removable_roles,
                    reason="Emergency recovery"
                )

                removed_roles += len(removable_roles)

            except Exception as e:

                print(
                    f"[WARN] Rollen konnten bei "
                    f"{member} nicht entfernt werden: {e}"
                )

    # --------------------------------------------------------
    # KICK OTHER BOTS
    # --------------------------------------------------------

    kicked_bots = 0

    for member in guild.members:

        if not member.bot:
            continue

        if member == bot_member:
            continue

        try:

            await member.kick(
                reason="Emergency recovery"
            )

            kicked_bots += 1

        except Exception as e:

            print(
                f"[WARN] Bot konnte nicht gekickt werden: "
                f"{e}"
            )

    # --------------------------------------------------------
    # DELETE CHANNELS
    # --------------------------------------------------------

    deleted_channels = 0

    channels = list(guild.channels)

    for channel in channels:

        try:

            await channel.delete(
                reason="Emergency recovery"
            )

            deleted_channels += 1

        except Exception as e:

            print(
                f"[WARN] Channel konnte nicht gelöscht werden: "
                f"{e}"
            )

    # --------------------------------------------------------
    # CREATE RECOVERY STRUCTURE
    # --------------------------------------------------------

    created = await create_recovery_structure(guild)

    # --------------------------------------------------------
    # FINISHED
    # --------------------------------------------------------

    print(
        f"[RECOVERY] Fertig | "
        f"Roles: {removed_roles} | "
        f"Bots: {kicked_bots} | "
        f"Channels: {deleted_channels}"
    )

    recovery_channel = created.get("welcome")

    if recovery_channel:

        try:

            await recovery_channel.send(
                "🚨 **Server Recovery abgeschlossen.**\n\n"
                f"Entfernte Rollen: `{removed_roles}`\n"
                f"Entfernte Bots: `{kicked_bots}`\n"
                f"Gelöschte Channels: `{deleted_channels}`\n\n"
                "Die grundlegende Serverstruktur wurde wiederhergestellt."
            )

        except Exception:
            pass


# ============================================================
# CREATE RECOVERY STRUCTURE
# ============================================================

async def create_recovery_structure(guild):

    created = {}

    # --------------------------------------------------------
    # INFORMATION
    # --------------------------------------------------------

    information = await guild.create_category(
        "📌 INFORMATION"
    )

    rules = await guild.create_text_channel(
        "📜・rules",
        category=information
    )

    announcements = await guild.create_text_channel(
        "📢・announcements",
        category=information
    )

    welcome = await guild.create_text_channel(
        "👋・welcome",
        category=information
    )

    news = await guild.create_text_channel(
        "📰・news",
        category=information
    )

    created["rules"] = rules
    created["welcome"] = welcome
    created["announcements"] = announcements
    created["news"] = news

    # --------------------------------------------------------
    # COMMUNITY
    # --------------------------------------------------------

    community = await guild.create_category(
        "💬 COMMUNITY"
    )

    await guild.create_text_channel(
        "💬・chat",
        category=community
    )

    await guild.create_text_channel(
        "😂・memes",
        category=community
    )

    await guild.create_text_channel(
        "📸・media",
        category=community
    )

    await guild.create_text_channel(
        "🔥・off-topic",
        category=community
    )

    # --------------------------------------------------------
    # GAMING
    # --------------------------------------------------------

    gaming = await guild.create_category(
        "🎮 GAMING"
    )

    await guild.create_text_channel(
        "🎮・gaming",
        category=gaming
    )

    await guild.create_text_channel(
        "🏆・events",
        category=gaming
    )

    await guild.create_text_channel(
        "🎵・music",
        category=gaming
    )

    # --------------------------------------------------------
    # EVENTS
    # --------------------------------------------------------

    events = await guild.create_category(
        "🎁 EVENTS"
    )

    giveaways = await guild.create_text_channel(
        "🎉・giveaways",
        category=events
    )

    await guild.create_text_channel(
        "💎・vip",
        category=events
    )

    # --------------------------------------------------------
    # SUPPORT
    # --------------------------------------------------------

    support = await guild.create_category(
        "🛠 SUPPORT"
    )

    support_channel = await guild.create_text_channel(
        "🆘・support",
        category=support
    )

    faq = await guild.create_text_channel(
        "❓・faq",
        category=support
    )

    suggestions = await guild.create_text_channel(
        "💡・suggestions",
        category=support
    )

    # --------------------------------------------------------
    # STAFF
    # --------------------------------------------------------

    staff = await guild.create_category(
        "🔒 STAFF"
    )

    staff_chat = await guild.create_text_channel(
        "🔒・staff-chat",
        category=staff
    )

    # --------------------------------------------------------
    # STARTER MESSAGES
    # --------------------------------------------------------

    try:

        await rules.send(
            "📜 **Server Rules**\n\n"
            "1. Respektvoll miteinander umgehen.\n"
            "2. Kein Spam.\n"
            "3. Keine Belästigung.\n"
            "4. Keine unerlaubten Inhalte.\n"
            "5. Anweisungen des Teams beachten."
        )

    except Exception:
        pass

    try:

        await welcome.send(
            "👋 **Willkommen!**\n\n"
            "Schön, dass du da bist!"
        )

    except Exception:
        pass

    try:

        await announcements.send(
            "📢 **Announcements**\n\n"
            "Hier erscheinen wichtige Server-Ankündigungen."
        )

    except Exception:
        pass

    try:

        await news.send(
            "📰 **News**\n\n"
            "Hier erscheinen Server-News."
        )

    except Exception:
        pass

    try:

        await giveaways.send(
            "🎉 **Giveaways**\n\n"
            "Hier werden zukünftige Giveaways angekündigt."
        )

    except Exception:
        pass

    try:

        await support_channel.send(
            "🆘 **Support**\n\n"
            "Benötigst du Hilfe? Schreibe hier dein Anliegen."
        )

    except Exception:
        pass

    try:

        await faq.send(
            "❓ **FAQ**\n\n"
            "Häufig gestellte Fragen werden hier beantwortet."
        )

    except Exception:
        pass

    try:

        await suggestions.send(
            "💡 **Suggestions**\n\n"
            "Hier kannst du Vorschläge für den Server posten."
        )

    except Exception:
        pass

    try:

        await staff_chat.send(
            "🔒 **Staff Chat**\n\n"
            "Interner Bereich für das Team."
        )

    except Exception:
        pass

    return created


# ============================================================
# COMMAND ERROR HANDLER
# ============================================================

@bot.event
async def on_command_error(ctx, error):

    if isinstance(error, commands.CheckFailure):

        await ctx.send(
            "❌ Du hast keine Berechtigung für diesen Befehl."
        )

        return

    if isinstance(error, commands.CommandNotFound):

        return

    print(
        f"[COMMAND ERROR] {error}"
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print("Starte Flask Webserver...")

    flask_thread = threading.Thread(
        target=start_flask,
        daemon=True
    )

    flask_thread.start()

    print("Starte Discord Bot...")

    bot.run(DISCORD_TOKEN)
