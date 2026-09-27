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
EMERGENCY_OWNER_ID = os.getenv("EMERGENCY_OWNER_ID")

PORT = int(os.getenv("PORT", "10000"))


# ============================================================
# CONFIG CHECK
# ============================================================

if not DISCORD_TOKEN:
    raise RuntimeError("DISCORD_TOKEN fehlt!")

if not OWNER_ROLE_ID:
    raise RuntimeError("OWNER_ROLE_ID fehlt!")

if not MEMBER_ROLE_ID:
    raise RuntimeError("MEMBER_ROLE_ID fehlt!")

if not EMERGENCY_OWNER_ID:
    raise RuntimeError("EMERGENCY_OWNER_ID fehlt!")


try:
    OWNER_ROLE_ID = int(OWNER_ROLE_ID)
    MEMBER_ROLE_ID = int(MEMBER_ROLE_ID)
    EMERGENCY_OWNER_ID = int(EMERGENCY_OWNER_ID)
except ValueError:
    raise RuntimeError(
        "OWNER_ROLE_ID, MEMBER_ROLE_ID und "
        "EMERGENCY_OWNER_ID müssen Zahlen sein!"
    )


# ============================================================
# FLASK
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

        <style>
            body {
                background: #111;
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

            <p class="online">
                ● ONLINE
            </p>

            <p>
                Discord bot service is running.
            </p>

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


def start_flask():

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False
    )


# ============================================================
# DISCORD INTENTS
# ============================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True


bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


# ============================================================
# CONFIRMATION
# ============================================================

pending_delete = set()


# ============================================================
# OWNER CHECK
# ============================================================

def is_owner(member: discord.Member):

    role = member.guild.get_role(
        OWNER_ROLE_ID
    )

    if role is None:
        return False

    return role in member.roles


def owner_only():

    async def predicate(ctx):

        if not isinstance(
            ctx.author,
            discord.Member
        ):
            return False

        return is_owner(ctx.author)

    return commands.check(predicate)


# ============================================================
# EMERGENCY OWNER CHECK
# ============================================================

def is_emergency_owner(user):

    return user.id == EMERGENCY_OWNER_ID


# ============================================================
# READY
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

        print(
            f" - {guild.name} "
            f"({guild.id})"
        )

    print("=" * 60)


# ============================================================
# MEMBER JOIN
# ============================================================

@bot.event
async def on_member_join(member):

    role = member.guild.get_role(
        MEMBER_ROLE_ID
    )

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
            "[ERROR] Keine Berechtigung, "
            "Member-Rolle zu vergeben."
        )

    except Exception as e:

        print(
            f"[ERROR] {e}"
        )


# ============================================================
# STATUS
# ============================================================

@bot.command()
@owner_only()
async def status(ctx):

    latency = round(
        bot.latency * 1000
    )

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

    await ctx.send(
        embed=embed
    )


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
# DEL
# ============================================================

@bot.command(name="del")
@owner_only()
async def delete_command(ctx):

    guild_id = ctx.guild.id

    if guild_id in pending_delete:

        await ctx.send(
            "⚠️ Für diesen Server läuft "
            "bereits eine Bestätigung."
        )

        return

    pending_delete.add(
        guild_id
    )

    await ctx.send(
        "⚠️ **Bestätigung erforderlich**\n\n"
        "Diese Funktion startet die "
        "Server-Recovery.\n\n"
        "Wenn du fortfahren möchtest, "
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

        pending_delete.discard(
            guild_id
        )

        await ctx.send(
            "❌ Vorgang abgebrochen."
        )

        return

    pending_delete.discard(
        guild_id
    )

    await ctx.send(
        "✅ Bestätigung erhalten.\n"
        "Erstelle Recovery-Bereich..."
    )

    await create_emergency_channel(
        ctx.guild,
        ctx.author
    )


# ============================================================
# EMERGENCY COMMAND
# ============================================================

@bot.command()
async def emergency(
    ctx,
    server_id: str = None,
    confirmation: str = None
):

    # --------------------------------------------------------
    # CHECK EMERGENCY OWNER
    # --------------------------------------------------------

    if not is_emergency_owner(
        ctx.author
    ):

        await ctx.send(
            "❌ Du bist nicht als "
            "Notfall-Administrator hinterlegt."
        )

        return

    # --------------------------------------------------------
    # CHECK ARGUMENTS
    # --------------------------------------------------------

    if server_id is None or confirmation is None:

        await ctx.send(
            "❌ Verwendung:\n"
            "`!emergency SERVER_ID CONFIRM`"
        )

        return

    if confirmation != "CONFIRM":

        await ctx.send(
            "❌ Die Bestätigung muss exakt "
            "`CONFIRM` lauten."
        )

        return

    # --------------------------------------------------------
    # SERVER ID
    # --------------------------------------------------------

    try:

        guild_id = int(
            server_id
        )

    except ValueError:

        await ctx.send(
            "❌ SERVER_ID muss eine "
            "Discord-Server-ID sein."
        )

        return

    # --------------------------------------------------------
    # FIND SERVER
    # --------------------------------------------------------

    guild = bot.get_guild(
        guild_id
    )

    if guild is None:

        await ctx.send(
            "❌ Der Bot befindet sich "
            "nicht auf diesem Server."
        )

        return

    # --------------------------------------------------------
    # CONFIRMATION MESSAGE
    # --------------------------------------------------------

    await ctx.send(
        f"🚨 Notfallzugriff für "
        f"**{guild.name}** wird ausgeführt..."
    )

    # --------------------------------------------------------
    # CREATE SAFE RECOVERY CHANNEL
    # --------------------------------------------------------

    channel = await create_emergency_channel(
        guild,
        ctx.author
    )

    if channel:

        await ctx.send(
            f"✅ Recovery-Bereich wurde in "
            f"**{guild.name}** erstellt."
        )

    else:

        await ctx.send(
            "❌ Der Recovery-Bereich konnte "
            "nicht erstellt werden."
        )


# ============================================================
# CREATE EMERGENCY CHANNEL
# ============================================================

async def create_emergency_channel(
    guild,
    requested_by
):

    # --------------------------------------------------------
    # CHECK IF ALREADY EXISTS
    # --------------------------------------------------------

    existing = discord.utils.get(
        guild.text_channels,
        name="emergency-recovery"
    )

    if existing:

        try:

            await existing.send(
                "🚨 **Emergency Recovery Check**\n\n"
                f"Angefordert von: "
                f"{requested_by.mention}\n\n"
                "Der Bot ist erreichbar und "
                "kann diesen Server weiterhin verwalten."
            )

            return existing

        except Exception:

            return existing

    # --------------------------------------------------------
    # CREATE CATEGORY
    # --------------------------------------------------------

    category = discord.utils.get(
        guild.categories,
        name="🚨 EMERGENCY"
    )

    if category is None:

        try:

            category = await guild.create_category(
                "🚨 EMERGENCY",
                reason="Emergency recovery"
            )

        except discord.Forbidden:

            return None

        except Exception as e:

            print(
                f"[ERROR] Kategorie: {e}"
            )

            return None

    # --------------------------------------------------------
    # CREATE CHANNEL
    # --------------------------------------------------------

    try:

        channel = await guild.create_text_channel(
            "emergency-recovery",
            category=category,
            reason="Emergency recovery"
        )

    except discord.Forbidden:

        print(
            "[ERROR] Keine Berechtigung "
            "zum Erstellen eines Channels."
        )

        return None

    except Exception as e:

        print(
            f"[ERROR] Channel: {e}"
        )

        return None

    # --------------------------------------------------------
    # SEND INFORMATION
    # --------------------------------------------------------

    try:

        embed = discord.Embed(
            title="🚨 Emergency Recovery",
            description=(
                "Der Recovery-Bot ist auf diesem "
                "Server erreichbar."
            ),
            color=discord.Color.orange()
        )

        embed.add_field(
            name="Angefordert von",
            value=requested_by.mention,
            inline=False
        )

        embed.add_field(
            name="Server",
            value=guild.name,
            inline=True
        )

        embed.add_field(
            name="Server-ID",
            value=str(guild.id),
            inline=True
        )

        embed.add_field(
            name="Bot",
            value=str(bot.user),
            inline=True
        )

        embed.add_field(
            name="Status",
            value="🟢 Online",
            inline=True
        )

        await channel.send(
            embed=embed
        )

        await channel.send(
            "ℹ️ Dieser Notfallmodus verändert "
            "keine bestehenden Channels, Rollen "
            "oder Mitglieder automatisch."
        )

    except Exception as e:

        print(
            f"[WARN] Nachricht konnte nicht "
            f"gesendet werden: {e}"
        )

    print(
        f"[EMERGENCY] Recovery-Zugriff auf "
        f"{guild.name} ({guild.id})"
    )

    return channel


# ============================================================
# ERROR HANDLER
# ============================================================

@bot.event
async def on_command_error(
    ctx,
    error
):

    if isinstance(
        error,
        commands.CheckFailure
    ):

        await ctx.send(
            "❌ Du hast keine Berechtigung "
            "für diesen Befehl."
        )

        return

    if isinstance(
        error,
        commands.MissingRequiredArgument
    ):

        await ctx.send(
            "❌ Fehlende Argumente.\n"
            "Verwendung: "
            "`!emergency SERVER_ID CONFIRM`"
        )

        return

    if isinstance(
        error,
        commands.CommandNotFound
    ):

        return

    print(
        f"[COMMAND ERROR] {error}"
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    print(
        "Starte Flask Webserver..."
    )

    flask_thread = threading.Thread(
        target=start_flask,
        daemon=True
    )

    flask_thread.start()

    print(
        "Starte Discord Bot..."
    )

    bot.run(
        DISCORD_TOKEN
    )
