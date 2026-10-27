"""Additive competitive tools for TriggerMc; leaves the existing /results pipeline untouched."""
import os
import random
import datetime
import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
from supabase import create_client

from __main__ import internal_db, external_db, ALPHA_URL

log = logging.getLogger("TriggerMc.Features")
SERVICE_KEY = os.getenv("ALPHA_SERVICE_KEY", "").strip()
FEATURE_DB_READY = bool(SERVICE_KEY)
feature_db = create_client(ALPHA_URL, SERVICE_KEY) if SERVICE_KEY else internal_db

MODES = ["Sword", "Nethpot", "Axe", "Mace", "Pot", "UHC", "SMP", "Crystal"]
PLAYER_FIELDS = {"Sword": "sword", "Nethpot": "nethpot", "Axe": "axe", "Mace": "mace", "Pot": "pot", "UHC": "uhc", "SMP": "smp", "Crystal": "vanilla"}
NEON = 0x36E5FF


def _admin(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild and isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator)


def _id_from_footer(message: discord.Message, prefix: str) -> Optional[str]:
    if not message.embeds:
        return None
    footer = message.embeds[0].footer.text or ""
    marker = prefix + ":"
    return footer.split(marker, 1)[1].strip() if marker in footer else None


def _needs_service_key(interaction: discord.Interaction) -> bool:
    if FEATURE_DB_READY:
        return False
    async def notify():
        message = "Persistent tools need setup: run supabase_features.sql in the ALPHA project and add ALPHA_SERVICE_KEY as a private Wispbyte environment variable. Never commit or share that key."
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    interaction.client.loop.create_task(notify())
    return True


async def _giveaway_callback(interaction: discord.Interaction):
    if not FEATURE_DB_READY:
        return await interaction.response.send_message("Persistent giveaway storage isn't configured.", ephemeral=True)
    giveaway_id = _id_from_footer(interaction.message, "Giveaway ID")
    if not giveaway_id:
        return await interaction.response.send_message("Giveaway ID is missing from this post.", ephemeral=True)
    try:
        rows = feature_db.table("giveaways").select("*").eq("id", giveaway_id).limit(1).execute().data
        if not rows or rows[0].get("is_ended"):
            return await interaction.response.send_message("This giveaway has ended.", ephemeral=True)
        ends = datetime.datetime.fromisoformat(rows[0]["ends_at"].replace("Z", "+00:00"))
        if datetime.datetime.now(datetime.timezone.utc) >= ends:
            return await interaction.response.send_message("Entry time has ended. An admin can run /giveaway_end.", ephemeral=True)
        existing = feature_db.table("giveaway_entries").select("user_id").eq("giveaway_id", giveaway_id).eq("user_id", str(interaction.user.id)).limit(1).execute().data
        if existing:
            return await interaction.response.send_message("You're already entered!", ephemeral=True)
        feature_db.table("giveaway_entries").insert({"giveaway_id": giveaway_id, "user_id": str(interaction.user.id)}).execute()
        await interaction.response.send_message("🎉 You're entered in the giveaway!", ephemeral=True)
    except Exception:
        log.exception("Giveaway entry failed")
        await interaction.response.send_message("Could not save your entry. Please notify an admin.", ephemeral=True)


async def _tournament_callback(interaction: discord.Interaction):
    if not FEATURE_DB_READY:
        return await interaction.response.send_message("Tournament storage isn't configured.", ephemeral=True)
    tournament_id = _id_from_footer(interaction.message, "Tournament ID")
    if not tournament_id:
        return await interaction.response.send_message("Tournament ID is missing from this post.", ephemeral=True)
    try:
        rows = feature_db.table("tournaments").select("*").eq("id", tournament_id).limit(1).execute().data
        if not rows or rows[0].get("status") != "open":
            return await interaction.response.send_message("Registration is closed.", ephemeral=True)
        tournament = rows[0]
        existing = feature_db.table("tournament_entries").select("user_id").eq("tournament_id", tournament_id).eq("user_id", str(interaction.user.id)).limit(1).execute().data
        if existing:
            return await interaction.response.send_message("You're already registered!", ephemeral=True)
        count = len(feature_db.table("tournament_entries").select("user_id").eq("tournament_id", tournament_id).execute().data or [])
        if count >= int(tournament["capacity"]):
            return await interaction.response.send_message("This tournament is full.", ephemeral=True)
        feature_db.table("tournament_entries").insert({"tournament_id": tournament_id, "user_id": str(interaction.user.id)}).execute()
        await interaction.response.send_message("Registered for " + tournament["name"] + "!", ephemeral=True)
    except Exception:
        log.exception("Tournament registration failed")
        await interaction.response.send_message("Could not save your registration. Please notify an admin.", ephemeral=True)


class GiveawayJoinView(View):
    def __init__(self, disabled: bool = False):
        super().__init__(timeout=None)
        button = Button(label="Enter Giveaway", emoji="🎉", style=discord.ButtonStyle.success, custom_id="trig_mc_giveaway_enter_v1", disabled=disabled)
        button.callback = _giveaway_callback
        self.add_item(button)


class TournamentJoinView(View):
    def __init__(self, disabled: bool = False):
        super().__init__(timeout=None)
        button = Button(label="Join Tournament", emoji="🏆", style=discord.ButtonStyle.success, custom_id="trig_mc_tournament_join_v1", disabled=disabled)
        button.callback = _tournament_callback
        self.add_item(button)


class SupportCloseView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Support Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="trig_mc_support_close_v1")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("This isn't a support ticket channel.", ephemeral=True)
        if not FEATURE_DB_READY:
            return await interaction.response.send_message("Persistent ticket database isn't configured.", ephemeral=True)
        try:
            rows = feature_db.table("support_tickets").select("*").eq("channel_id", str(interaction.channel.id)).eq("status", "open").limit(1).execute().data
            if not rows:
                return await interaction.response.send_message("No open support ticket was found here.", ephemeral=True)
            ticket = rows[0]
            is_opener = str(interaction.user.id) == str(ticket["opener_id"])
            staff_id = int(os.getenv("SUPPORT_ROLE_ID", "0") or 0)
            is_staff = _admin(interaction) or (isinstance(interaction.user, discord.Member) and any(r.id == staff_id for r in interaction.user.roles))
            if not (is_opener or is_staff):
                return await interaction.response.send_message("Only the opener or support staff can close this ticket.", ephemeral=True)
            await interaction.response.send_message("Closing this support ticket in 3 seconds…", ephemeral=True)
            feature_db.table("support_tickets").update({"status": "closed", "closed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}).eq("id", ticket["id"]).execute()
            await interaction.channel.send("Ticket closed by " + interaction.user.mention + ".")
            import asyncio
            await asyncio.sleep(3)
            await interaction.channel.delete(reason="Support ticket closed")
        except Exception:
            log.exception("Support ticket close failed")
            if not interaction.response.is_done():
                await interaction.response.send_message("Ticket close failed. Check database setup and permissions.", ephemeral=True)


class SupportPanelView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Support Ticket", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="trig_mc_support_create_v1")
    async def create_ticket(self, interaction: discord.Interaction, button: Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("Use this in the server.", ephemeral=True)
        if not FEATURE_DB_READY:
            return await interaction.response.send_message("Run supabase_features.sql in ALPHA and add ALPHA_SERVICE_KEY privately in Wispbyte first.", ephemeral=True)
        await interaction.response.defer(ephemeral=True, thinking=True)
        guild = interaction.guild
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, read_message_history=True)
        staff_id = int(os.getenv("SUPPORT_ROLE_ID", "0") or 0)
        staff_role = guild.get_role(staff_id) if staff_id else None
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        category_id = int(os.getenv("SUPPORT_CATEGORY_ID", "0") or 0)
        category = guild.get_channel(category_id) if category_id else None
        safe_name = "".join(ch.lower() if ch.isalnum() or ch in "-_" else "-" for ch in interaction.user.name)[:35]
        try:
            channel = await guild.create_text_channel(name="support-" + (safe_name or str(interaction.user.id)), category=category if isinstance(category, discord.CategoryChannel) else None, overwrites=overwrites, reason="Support ticket opened")
            result = feature_db.table("support_tickets").insert({"guild_id": str(guild.id), "opener_id": str(interaction.user.id), "channel_id": str(channel.id), "status": "open"}).execute()
            ticket_id = result.data[0]["id"] if result.data else "unknown"
            embed = discord.Embed(title="🎫 TriggerMc Support", color=NEON, description="Welcome " + interaction.user.mention + ". Describe your issue and staff will help.")
            embed.set_footer(text="Support Ticket ID: " + str(ticket_id))
            await channel.send(content=interaction.user.mention, embed=embed, view=SupportCloseView())
            await interaction.followup.send("Your support ticket is ready: " + channel.mention, ephemeral=True)
        except Exception:
            log.exception("Support ticket creation failed")
            try:
                if "channel" in locals():
                    await channel.delete(reason="Ticket setup failed")
            except Exception:
                pass
            await interaction.followup.send("Could not create the ticket. Check SQL setup and Manage Channels permission.", ephemeral=True)


class CompetitiveFeatures(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(SupportPanelView())
        self.bot.add_view(SupportCloseView())
        self.bot.add_view(GiveawayJoinView())
        self.bot.add_view(TournamentJoinView())

    @app_commands.command(name="compare", description="Compare two Minecraft players' recorded tiers.")
    @app_commands.describe(player_one="First Minecraft username", player_two="Second Minecraft username")
    async def compare(self, interaction: discord.Interaction, player_one: str, player_two: str):
        await interaction.response.defer()
        names = [player_one.strip(), player_two.strip()]
        if any(not n or len(n) > 16 for n in names):
            return await interaction.followup.send("Enter valid Minecraft usernames (1–16 characters).", ephemeral=True)
        if names[0].casefold() == names[1].casefold():
            return await interaction.followup.send("Choose two different players.", ephemeral=True)
        try:
            found = []
            for name in names:
                rows = external_db.table("players").select("*").eq("username", name).limit(1).execute().data
                if not rows:
                    return await interaction.followup.send("No player record found for " + name + ".", ephemeral=True)
                found.append(rows[0])
            embed = discord.Embed(title="⚔️ Player Comparison", color=NEON, description="**" + str(found[0].get("username", names[0])) + "**  VS  **" + str(found[1].get("username", names[1])) + "**")
            embed.add_field(name="🌍 Region", value=str(found[0].get("region") or "N/A"), inline=True)
            embed.add_field(name="🌍 Region", value=str(found[1].get("region") or "N/A"), inline=True)
            embed.add_field(name=" ", value=" ", inline=True)
            for mode, field in PLAYER_FIELDS.items():
                embed.add_field(name=mode, value="**" + str(found[0].get(field) or "Unranked") + "**", inline=True)
                embed.add_field(name=mode + " ", value="**" + str(found[1].get(field) or "Unranked") + "**", inline=True)
                embed.add_field(name="VS", value="⚡", inline=True)
            embed.set_footer(text="Existing BETA players table • Crystal uses the vanilla column")
            await interaction.followup.send(embed=embed)
        except Exception:
            log.exception("Player comparison failed")
            await interaction.followup.send("Player comparison failed. Check the existing players table and permissions.", ephemeral=True)

    @app_commands.command(name="support_setup", description="Post the separate neon support-ticket panel.")
    @app_commands.checks.has_permissions(administrator=True)
    async def support_setup(self, interaction: discord.Interaction):
        if not interaction.channel or not interaction.guild:
            return await interaction.response.send_message("Use this in a server channel.", ephemeral=True)
        if not FEATURE_DB_READY:
            return await interaction.response.send_message("Configure ALPHA_SERVICE_KEY in Wispbyte and run supabase_features.sql first.", ephemeral=True)
        embed = discord.Embed(title="💠 TriggerMc Support Center", color=NEON, description="Need help? Open a private support ticket below. Please create one ticket per issue.")
        await interaction.channel.send(embed=embed, view=SupportPanelView())
        await interaction.response.send_message("Support panel posted.", ephemeral=True)

    @app_commands.command(name="giveaway_create", description="Create a persistent giveaway (manual ending).")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(prize="Prize being given away", duration_minutes="Entry window in minutes", winners="Number of winners")
    async def giveaway_create(self, interaction: discord.Interaction, prize: str, duration_minutes: app_commands.Range[int, 1, 10080], winners: app_commands.Range[int, 1, 20] = 1):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("Use this in a server channel.", ephemeral=True)
        if not FEATURE_DB_READY:
            return await interaction.response.send_message("Configure ALPHA_SERVICE_KEY and run supabase_features.sql first.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            ends = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=int(duration_minutes))
            row = feature_db.table("giveaways").insert({"guild_id": str(interaction.guild.id), "channel_id": str(interaction.channel.id), "message_id": "pending", "prize": prize[:200], "winner_count": int(winners), "ends_at": ends.isoformat(), "is_ended": False, "created_by": str(interaction.user.id)}).execute().data[0]
            giveaway_id = str(row["id"])
            embed = discord.Embed(title="🎉 NEON GIVEAWAY", color=0xB44CFF, description="**Prize:** " + prize[:200] + "\n**Winners:** " + str(winners) + "\n**Entries close:** <t:" + str(int(ends.timestamp())) + ":F>\n\nPress Enter Giveaway to join. An admin must run /giveaway_end to draw winners.")
            embed.set_footer(text="Giveaway ID: " + giveaway_id)
            message = await interaction.channel.send(embed=embed, view=GiveawayJoinView())
            feature_db.table("giveaways").update({"message_id": str(message.id)}).eq("id", giveaway_id).execute()
            await interaction.followup.send("Giveaway created. ID: " + giveaway_id, ephemeral=True)
        except Exception:
            log.exception("Giveaway creation failed")
            await interaction.followup.send("Giveaway creation failed. Check SQL setup and bot permissions.", ephemeral=True)

    @app_commands.command(name="giveaway_end", description="Manually end a giveaway and draw winners.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(giveaway_id="ID shown in the giveaway embed footer")
    async def giveaway_end(self, interaction: discord.Interaction, giveaway_id: str):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not FEATURE_DB_READY:
            return await interaction.response.send_message("Configure ALPHA_SERVICE_KEY and run supabase_features.sql first.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            rows = feature_db.table("giveaways").select("*").eq("id", giveaway_id.strip()).eq("guild_id", str(interaction.guild.id)).eq("is_ended", False).limit(1).execute().data
            if not rows:
                return await interaction.followup.send("Active giveaway not found. Check its ID.", ephemeral=True)
            giveaway = rows[0]
            entries = feature_db.table("giveaway_entries").select("user_id").eq("giveaway_id", giveaway_id.strip()).execute().data or []
            pool = list(dict.fromkeys(str(entry["user_id"]) for entry in entries))
            count = min(int(giveaway["winner_count"]), len(pool))
            chosen = random.sample(pool, count) if count else []
            feature_db.table("giveaways").update({"is_ended": True, "ended_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}).eq("id", giveaway_id.strip()).execute()
            channel = interaction.guild.get_channel(int(giveaway["channel_id"]))
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(int(giveaway["message_id"]))
                    embed = message.embeds[0] if message.embeds else discord.Embed(title="Giveaway")
                    embed.color = discord.Color.dark_grey()
                    embed.add_field(name="Status", value="ENDED", inline=False)
                    await message.edit(embed=embed, view=GiveawayJoinView(disabled=True))
                except Exception:
                    log.warning("Could not update ended giveaway post")
                await channel.send("🎉 Giveaway winners: " + ", ".join("<@" + uid + ">" for uid in chosen) if chosen else "Giveaway ended with no valid entries.")
            result = ", ".join("<@" + uid + ">" for uid in chosen) if chosen else "No entries"
            await interaction.followup.send("Giveaway ended. Winners: " + result, ephemeral=True)
        except Exception:
            log.exception("Giveaway ending failed")
            await interaction.followup.send("Could not end giveaway. Verify its ID and database setup.", ephemeral=True)

    @app_commands.command(name="tournament_create", description="Create a manual competitive tournament signup.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(name="Tournament name", gamemode="Competitive gamemode", capacity="Maximum number of players")
    @app_commands.choices(gamemode=[app_commands.Choice(name=m, value=m) for m in MODES])
    async def tournament_create(self, interaction: discord.Interaction, name: str, gamemode: app_commands.Choice[str], capacity: app_commands.Range[int, 2, 256] = 64):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message("Use this in a server channel.", ephemeral=True)
        if not FEATURE_DB_READY:
            return await interaction.response.send_message("Configure ALPHA_SERVICE_KEY and run supabase_features.sql first.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            row = feature_db.table("tournaments").insert({"guild_id": str(interaction.guild.id), "channel_id": str(interaction.channel.id), "message_id": "pending", "name": name[:100], "gamemode": gamemode.value, "capacity": int(capacity), "status": "open", "created_by": str(interaction.user.id)}).execute().data[0]
            tournament_id = str(row["id"])
            embed = discord.Embed(title="🏆 " + name[:100], color=NEON, description="**Gamemode:** " + gamemode.value + "\n**Capacity:** " + str(capacity) + " players\n\nPress Join Tournament to register. An admin can run /tournament_close to close registration.")
            embed.set_footer(text="Tournament ID: " + tournament_id)
            message = await interaction.channel.send(embed=embed, view=TournamentJoinView())
            feature_db.table("tournaments").update({"message_id": str(message.id)}).eq("id", tournament_id).execute()
            await interaction.followup.send("Tournament created. ID: " + tournament_id, ephemeral=True)
        except Exception:
            log.exception("Tournament creation failed")
            await interaction.followup.send("Tournament creation failed. Check SQL setup and bot permissions.", ephemeral=True)

    @app_commands.command(name="tournament_list", description="List open tournaments and their registrations.")
    async def tournament_list(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not FEATURE_DB_READY:
            return await interaction.response.send_message("Configure ALPHA_SERVICE_KEY and run supabase_features.sql first.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            rows = feature_db.table("tournaments").select("*").eq("guild_id", str(interaction.guild.id)).eq("status", "open").order("created_at", desc=True).limit(10).execute().data or []
            if not rows:
                return await interaction.followup.send("No open tournaments right now.", ephemeral=True)
            embed = discord.Embed(title="🏆 Open TriggerMc Tournaments", color=NEON)
            for row in rows:
                count = len(feature_db.table("tournament_entries").select("user_id").eq("tournament_id", str(row["id"])).execute().data or [])
                embed.add_field(name=row["name"], value="Mode: " + row["gamemode"] + " • Players: " + str(count) + "/" + str(row["capacity"]) + "\nID: " + str(row["id"]), inline=False)
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            log.exception("Tournament list failed")
            await interaction.followup.send("Could not load tournaments. Check database setup.", ephemeral=True)

    @app_commands.command(name="tournament_close", description="Close tournament registration manually.")
    @app_commands.checks.has_permissions(administrator=True)
    @app_commands.describe(tournament_id="ID shown in the tournament embed footer")
    async def tournament_close(self, interaction: discord.Interaction, tournament_id: str):
        if not interaction.guild:
            return await interaction.response.send_message("Use this in a server.", ephemeral=True)
        if not FEATURE_DB_READY:
            return await interaction.response.send_message("Configure ALPHA_SERVICE_KEY and run supabase_features.sql first.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            rows = feature_db.table("tournaments").select("*").eq("id", tournament_id.strip()).eq("guild_id", str(interaction.guild.id)).eq("status", "open").limit(1).execute().data
            if not rows:
                return await interaction.followup.send("Open tournament not found. Check its ID.", ephemeral=True)
            row = rows[0]
            feature_db.table("tournaments").update({"status": "closed", "closed_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}).eq("id", tournament_id.strip()).execute()
            channel = interaction.guild.get_channel(int(row["channel_id"]))
            if channel and isinstance(channel, discord.TextChannel):
                try:
                    message = await channel.fetch_message(int(row["message_id"]))
                    embed = message.embeds[0] if message.embeds else discord.Embed(title=row["name"])
                    embed.add_field(name="Registration", value="CLOSED", inline=False)
                    await message.edit(embed=embed, view=TournamentJoinView(disabled=True))
                except Exception:
                    log.warning("Could not update tournament post")
            await interaction.followup.send("Registration closed for " + row["name"] + ".", ephemeral=True)
        except Exception:
            log.exception("Tournament close failed")
            await interaction.followup.send("Could not close tournament. Check its ID and database setup.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(CompetitiveFeatures(bot))
    # Re-register stable custom IDs after restarts.
    bot.add_view(SupportPanelView())
    bot.add_view(SupportCloseView())
    bot.add_view(GiveawayJoinView())
    bot.add_view(TournamentJoinView())
