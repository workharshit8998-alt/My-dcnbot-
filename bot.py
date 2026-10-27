import os
import discord
import asyncio
import datetime
import logging
import sys
import re
from typing import Optional, Final
from dotenv import load_dotenv

from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View, Modal, TextInput

from supabase import create_client, Client

load_dotenv()

# ==============================================================================
# SECTION 1: ADVANCED TELEMETRY & LOGGING SYSTEM
# ==============================================================================

class TitanDiagnosticFormatter(logging.Formatter):
    fmt = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    FORMATS = {
        logging.DEBUG: "\x1b[36;20m" + fmt + "\x1b[0m",
        logging.INFO: "\x1b[32;20m" + fmt + "\x1b[0m",
        logging.WARNING: "\x1b[33;20m" + fmt + "\x1b[0m",
        logging.ERROR: "\x1b[31;20m" + fmt + "\x1b[0m",
        logging.CRITICAL: "\x1b[31;1m" + fmt + "\x1b[0m"
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        return logging.Formatter(log_fmt).format(record)

logger = logging.getLogger('Trigger-Sovereign-V48')
logger.setLevel(logging.INFO)
sh = logging.StreamHandler(sys.stdout)
sh.setFormatter(TitanDiagnosticFormatter())
logger.addHandler(sh)

# ==============================================================================
# SECTION 2: CONFIGURATION & REGISTRY (LOADED FROM .ENV)
# ==============================================================================

MASTER_TOKEN: Final[str] = os.getenv("MASTER_TOKEN")
APP_ID: Final[int] = int(os.getenv("APP_ID", 0))
GUILD_ID: Final[int] = int(os.getenv("GUILD_ID", 0))

ALPHA_URL: Final[str] = os.getenv("ALPHA_URL")
ALPHA_KEY: Final[str] = os.getenv("ALPHA_KEY")

BETA_URL: Final[str] = os.getenv("BETA_URL")
BETA_KEY: Final[str] = os.getenv("BETA_KEY")

CHANNEL_AUDIT_LOGS = int(os.getenv("CHANNEL_AUDIT_LOGS", 0))
CHANNEL_STATS_LOGS = int(os.getenv("CHANNEL_STATS_LOGS", 0))
CHANNEL_MANUAL_RESET_LOGS = int(os.getenv("CHANNEL_MANUAL_RESET_LOGS", 0))

if not MASTER_TOKEN or not ALPHA_URL or not BETA_URL:
    logger.critical("❌ FATAL: Missing environment variables. Check your .env file.")
    sys.exit(1)

ROLE_ADMIN_ACCESS = [1486935933315059723, 1466238511136112895, 1469898822611111946]
ROLE_STAFF_ACCESS = [1476480782376898573, 1466121081826971809, 1490688085011337337, 1469582174880530483]

TESTER_COUNTS = {}

# ==============================================================================
# SECTION 3: SPECIFIC GAMEMODE SLOTS (DYNAMIC RESOLUTION TEMPLATES)
# ==============================================================================

GAMEMODE_CATEGORY_NAMES = {
    "Sword": "🔴 SWORD TESTING",
    "Nethpot": "⚫ NETHPOT TESTING",
    "Axe": "🟠 AXE TESTING",
    "Mace": "🟣 MACE TESTING",
    "Pot": "🔵 POT TESTING",
    "UHC": "🟡 UHC TESTING",
    "SMP": "🟤 SMP TESTING",
    "Crystal": "💎 CRYSTAL TESTING"
}

ROLE_METADATA_TEMPLATES = {
    "Sword": {"name": "🔴 Sword Tester", "color": discord.Color.red()},
    "Nethpot": {"name": "⚫ Nethpot Tester", "color": discord.Color.dark_grey()},
    "Axe": {"name": "🟠 Axe Tester", "color": discord.Color.orange()},
    "Crystal": {"name": "💎 Crystal Tester", "color": discord.Color.blue()},
    "Pot": {"name": "🔵 Pot Tester", "color": discord.Color.teal()},
    "UHC": {"name": "🟡 UHC Tester", "color": discord.Color.gold()},
    "SMP": {"name": "🟤 SMP Tester", "color": discord.Color.dark_orange()},
    "Mace": {"name": "🟣 Mace Tester", "color": discord.Color.purple()}
}

TESTER_ROLES_FALLBACK = {
    "Sword": 1487481120973918320, 
    "Nethpot": 1487481500420145173, 
    "Axe": 1487482678180839586,
    "Crystal": 1487481748118962246, 
    "Pot": 1487482642583650556, 
    "UHC": 1487482597050417152,
    "SMP": 1487482053950832802, 
    "Mace": 1487482193231216751
}

# ==============================================================================
# SECTION 4: GLOBAL MAPPINGS & DATA SETS
# ==============================================================================

EMOJI_REGISTRY = {"Sword": "🔴", "Nethpot": "⚫", "Axe": "🟠", "Mace": "🟣", "Pot": "🔵", "UHC": "🟡", "SMP": "🟤", "Crystal": "💎"}
MODES = list(EMOJI_REGISTRY.keys())
REGIONS = ["AS/AU", "EU", "AF", "NA", "SA"]
TIERS = ["HT1", "LT1", "HT2", "LT2", "HT3", "LT3", "HT4", "LT4", "HT5", "LT5", "NA"]

AUTO_RANK_ROLES = {
    "Crystal Premium": 1502769670850220253, "Crystal Cracked": 1502768289045152006,
    "Nethpot Premium": 1502769672745914552, "Nethpot Cracked": 1502768289791742225,
    "Axe Premium": 1502769676420387021,     "Axe Cracked": 1502768292362981462,
    "Sword Premium": 1502769674306195598,   "Sword Cracked": 1502768290991444019,
    "Pot Premium": 1502769680086073564,     "Pot Cracked": 1502769665267601529,
    "UHC Premium": 1502769678190248016,     "UHC Cracked": 1502769663745065173,
    "Smp Premium": 1502769679221919915,     "Smp Cracked": 1502768293738709143,
    "Mace Premium": 1502769675598168064,    "Mace Cracked": 1502768291855339540
}

try:
    internal_db: Client = create_client(ALPHA_URL, ALPHA_KEY)
    external_db: Client = create_client(BETA_URL, BETA_KEY)
    logger.info("DATABASE: Architecture sync validated.")
except Exception as e:
    logger.critical(f"DATABASE_FATAL: {e}")
    sys.exit(1)

# Owner-controlled admin panel access. Owner ID is the bot owner supplied by the project owner.
BOT_OWNER_ID = 1326234591979376771
_acl_key = os.getenv("ALPHA_SERVICE_KEY", "").strip()
_acl_db = create_client(ALPHA_URL, _acl_key) if _acl_key else None

async def has_admin_access(interaction: discord.Interaction) -> bool:
    if interaction.user.id == BOT_OWNER_ID:
        return True
    if not interaction.guild or _acl_db is None:
        return False
    try:
        rows = (_acl_db.table("authorized_admins").select("user_id")
                .eq("guild_id", str(interaction.guild.id))
                .eq("user_id", str(interaction.user.id))
                .limit(1).execute().data)
        return bool(rows)
    except Exception as exc:
        logger.error("Admin ACL lookup failed closed: %s", exc)
        return False

def add_vouch_to_db(tester_id: int):
    try:
        res = internal_db.table("tester_vouches").select("vouch_count").eq("user_id", str(tester_id)).execute()
        if res.data:
            new_count = res.data[0]["vouch_count"] + 1
            internal_db.table("tester_vouches").update({"vouch_count": new_count}).eq("user_id", str(tester_id)).execute()
        else:
            internal_db.table("tester_vouches").insert({"user_id": str(tester_id), "vouch_count": 1}).execute()
    except Exception as e:
        logger.error(f"Failed to add vouch to DB: {e}")

# ==============================================================================
# HELPER DATA COMPILER FOR LEADERBOARDS
# ==============================================================================

def generate_tester_leaderboard_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        title="🏆 TriggerMc Official Tester Leaderboard",
        color=0x2b2d31,
        timestamp=datetime.datetime.now()
    )
    embed.set_footer(text="Performance tracking data updated live.")
    
    global TESTER_COUNTS
    try:
        res = internal_db.table("tester_scores").select("*").execute()
        for row in res.data:
            TESTER_COUNTS[int(row["user_id"])] = row["tests_completed"]
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}")

    if not TESTER_COUNTS:
        embed.description = "*No active tests recorded on this session node yet.*"
        return embed

    sorted_testers = sorted(TESTER_COUNTS.items(), key=lambda item: item[1], reverse=True)
    
    leaderboard_content = ""
    for rank, (tester_id, count) in enumerate(sorted_testers, start=1):
        member = guild.get_member(tester_id)
        tester_name = member.mention if member else f"Unknown Tester (`{tester_id}`)"
        
        medal = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"`#{rank}`"
        leaderboard_content += f"{medal} {tester_name} — **{count}** tests completed\n"
        
    embed.description = leaderboard_content
    return embed

# ==============================================================================
# SECTION 5: BOT LIFECYCLE INITIALIZER
# ==============================================================================

class TriggerSovereignBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all(), application_id=APP_ID, help_command=None)
    async def setup_hook(self):
        self.add_view(PersistentPortal())
        self.add_view(CommunityEventNode())
        await self.load_extension("new_features")
    async def on_ready(self):
        global TESTER_COUNTS
        try:
            res = internal_db.table("tester_scores").select("*").execute()
            for row in res.data:
                TESTER_COUNTS[int(row["user_id"])] = row["tests_completed"]
            logger.info(f"Loaded {len(TESTER_COUNTS)} tester scores from Supabase.")
        except Exception as e:
            logger.error(f"Failed to load tester scores: {e}")

        logger.info(f"TITAN ENGINE V49.3 PROVISIONING ONLINE - {self.user}")

bot = TriggerSovereignBot()

# ==============================================================================
# SECTION 6: DATA SUITE MANAGEMENT TERMINAL MODALS & DROPDOWNS
# ==============================================================================

class EditIgnModal(Modal, title="Update Player IGN"):
    new_ign = TextInput(label="New Minecraft IGN", min_length=3, max_length=16, required=True)
    def __init__(self, current_ign):
        super().__init__()
        self.current_ign = current_ign

    async def on_submit(self, i: discord.Interaction):
        if not await has_admin_access(i):
            return await i.response.send_message("❌ Error: Owner access needed.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        try:
            internal_db.table("profiles").update({"ign": self.new_ign.value}).eq("ign", self.current_ign).execute()
            external_db.table("players").update({"username": self.new_ign.value}).eq("username", self.current_ign).execute()
            await i.followup.send(f"✅ Updated database mappings to `{self.new_ign.value}`.", ephemeral=True)
        except Exception as e:
            logger.error(f"DATA SYSTEM ERROR: {e}")
            await i.followup.send("❌ Error parsing parameter adjustments into DB.", ephemeral=True)

class EditRegionModal(Modal, title="Modify Network Region"):
    region = TextInput(label="Target Region (AS/AU, EU, AF, NA, SA)", min_length=2, max_length=6, required=True)
    def __init__(self, ign):
        super().__init__()
        self.ign = ign

    async def on_submit(self, i: discord.Interaction):
        if not await has_admin_access(i):
            return await i.response.send_message("❌ Error: Owner access needed.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        target_region = self.region.value.strip().upper()
        if target_region not in REGIONS:
            return await i.followup.send(f"❌ Error: `{target_region}` is an invalid region structure.", ephemeral=True)
        try:
            external_db.table("players").update({"region": target_region}).eq("username", self.ign).execute()
            await i.followup.send(f"✅ Success: Set network location to `{target_region}`.", ephemeral=True)
        except Exception as e:
            logger.error(f"DATA SYSTEM ERROR: {e}")
            await i.followup.send("❌ Error writing region matrix.", ephemeral=True)

class SelectTierValueDropdown(discord.ui.Select):
    def __init__(self, ign, mode):
        self.ign, self.mode = ign, mode
        options = [discord.SelectOption(label=t, value=t) for t in TIERS]
        super().__init__(placeholder=f"Select Tier rank for {mode.upper()}...", options=options)

    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        selected_tier = self.values[0]
        try:
            target_col = "vanilla" if self.mode == "crystal" else self.mode
            external_db.table("players").update({target_col: selected_tier}).eq("username", self.ign).execute()
            await i.followup.send(f"✅ Success: Set `{self.ign}`'s `{self.mode.upper()}` tier to **{selected_tier}**.", ephemeral=True)
        except Exception as e:
            logger.error(f"TIER WRITE ERROR: {e}")
            await i.followup.send("❌ Error writing tier change to data matrix.", ephemeral=True)

class SelectTierModeDropdown(discord.ui.Select):
    def __init__(self, ign):
        self.ign = ign
        options = [discord.SelectOption(label=m, value=m.lower(), emoji=EMOJI_REGISTRY[m]) for m in MODES]
        super().__init__(placeholder="Select the target gamemode field...", options=options)

    async def callback(self, i: discord.Interaction):
        selected_mode = self.values[0]
        next_view = View()
        next_view.add_item(SelectTierValueDropdown(self.ign, selected_mode))
        await i.response.send_message(f"✨ Mode chosen: `{selected_mode.upper()}`. Now select target metrics:", view=next_view, ephemeral=True)

class AdminFeatureDropdown(discord.ui.Select):
    def __init__(self, ign, user_id):
        self.ign, self.user_id = ign, user_id
        options = [
            discord.SelectOption(label="Edit IGN Profile", value="edit_ign", description="Alter baseline registration strings", emoji="📝"),
            discord.SelectOption(label="Modify Specialization Tier", value="edit_tier", description="Drop-down menu configuration matrix", emoji="📊"),
            discord.SelectOption(label="Shift Network Region", value="edit_region", description="Re-route node geographic location", emoji="🌍"),
            discord.SelectOption(label="Toggle Account Status Class", value="toggle_status", description="Swap Premium <-> Cracked state", emoji="💎")
        ]
        super().__init__(placeholder="Select configuration pipeline...", options=options, custom_id="v43_admin_drop")

    async def callback(self, i: discord.Interaction):
        if not await has_admin_access(i):
            return await i.response.send_message("❌ Access Denied: Server Owner clearance required.", ephemeral=True)
        
        selection = self.values[0]
        if selection == "edit_ign":
            await i.response.send_modal(EditIgnModal(self.ign))
        elif selection == "edit_tier":
            mode_view = View()
            mode_view.add_item(SelectTierModeDropdown(self.ign))
            await i.response.send_message("⚙️ Opening Tier Change Wizard. Select mode field slot:", view=mode_view, ephemeral=True)
        elif selection == "edit_region":
            await i.response.send_modal(EditRegionModal(self.ign))
        elif selection == "toggle_status":
            await i.response.defer(ephemeral=True)
            try:
                res = internal_db.table("profiles").select("account_type").eq("ign", self.ign).execute()
                if not res.data:
                    return await i.followup.send("❌ No Alpha registration record found to toggle status.", ephemeral=True)
                
                current_type = res.data[0].get("account_type", "Premium")
                new_type = "Cracked" if current_type == "Premium" else "Premium"
                
                internal_db.table("profiles").update({"account_type": new_type}).eq("ign", self.ign).execute()
                await i.followup.send(f"✅ Class shifted from `{current_type}` to `{new_type}`.", ephemeral=True)
            except Exception as e:
                logger.error(f"TOGGLE STATUS ERROR: {e}")
                await i.followup.send("❌ Error rewriting registration class.", ephemeral=True)

class AdminTerminalView(View):
    def __init__(self, ign, user_id):
        super().__init__(timeout=180)
        self.ign, self.user_id = ign, user_id
        self.add_item(AdminFeatureDropdown(ign, user_id))

    @discord.ui.button(label="Refresh Node", style=discord.ButtonStyle.secondary, emoji="🔄", row=1)
    async def refresh_btn(self, i: discord.Interaction, b: Button):
        if not await has_admin_access(i):
            return await i.response.send_message("❌ Access Denied.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        try:
            alpha_res = internal_db.table("profiles").select("*").eq("ign", self.ign).execute()
            beta_res = external_db.table("players").select("*").eq("username", self.ign).execute()
            a_data = alpha_res.data[0] if alpha_res.data else None
            b_data = beta_res.data[0] if beta_res.data else None

            embed = discord.Embed(title=f"🛠️ Data Profile Node: {self.ign}", color=0x2b2d31, timestamp=datetime.datetime.now())
            embed.set_footer(text="TriggerMc Core Administration Panel")

            if a_data:
                dc_mention = f"<@{a_data.get('user_id')}>"
                embed.add_field(name="📡 [ALPHA DB] Registration", value=f"**Discord Link:** {dc_mention}\n**UID Reference:** `{a_data.get('user_id')}`\n**Status Class:** `{a_data.get('account_type')}`\n**Focal Gamemode:** `{a_data.get('preferred_mode')}`", inline=False)
            else:
                embed.add_field(name="📡 [ALPHA DB] Registration", value="*No registration log mapping recorded.*", inline=False)

            if b_data:
                stats_str = ""
                exclusion_filter = ["id", "username", "created_at"]
                for k, v in b_data.items():
                    if k not in exclusion_filter and v:
                        display_key = "Crystal" if k.lower() == "vanilla" else k.capitalize()
                        stats_str += f"• **{display_key}:** `{v}`\n"
                stats_str += f"• **Region Matrix:** `{b_data.get('region', 'N/A')}`"
                embed.add_field(name="🌍 [BETA DB] Network Ranks", value=stats_str if stats_str else "*No settings found.*", inline=False)
            else:
                embed.add_field(name="🌍 [BETA DB] Network Ranks", value="*No web profile present.*", inline=False)

            await i.edit_original_response(embed=embed, view=self)
        except Exception as e:
            logger.error(f"REFRESH FAILURE: {e}")
            await i.followup.send("❌ Error fetching active node properties.", ephemeral=True)

    @discord.ui.button(label="Purge Records", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def remove_btn(self, i: discord.Interaction, b: Button):
        if not await has_admin_access(i):
            return await i.response.send_message("❌ Access Denied: Server Owner required.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        try:
            if self.user_id != "N/A":
                internal_db.table("profiles").delete().eq("user_id", str(self.user_id)).execute()
            internal_db.table("profiles").delete().eq("ign", self.ign).execute()
            external_db.table("players").delete().eq("username", self.ign).execute()
            for child in self.children:
                child.disabled = True
            await i.edit_original_response(view=self)
            await i.followup.send(f"🗑️ Complete Purge: `{self.ign}` dropped from core indexes.", ephemeral=True)
        except Exception as e:
            logger.error(f"DATA SYSTEM ERROR: {e}")
            await i.followup.send("❌ Error stripping credentials from tables.", ephemeral=True)

# ==============================================================================
# SECTION 7: IN-TICKET ASYNC VERIFICATION ENGINE & STEP MANAGEMENT
# ==============================================================================

class UniversalTicketView(View):
    def __init__(self, applicant: discord.Member, required_tester_role: discord.Role):
        super().__init__(timeout=None)
        self.applicant = applicant
        self.required_tester_role = required_tester_role

    @discord.ui.button(label="Claim Ticket", style=discord.ButtonStyle.success, emoji="✋", custom_id="claim_universal_btn")
    async def claim_btn(self, i: discord.Interaction, b: Button):
        # Check if the user has the EXACT required tester role for this gamemode
        if self.required_tester_role and self.required_tester_role not in i.user.roles:
            return await i.response.send_message(f"❌ Only holders of the {self.required_tester_role.mention} role can claim this ticket!", ephemeral=True)

        await i.response.send_message(f"✅ {i.user.mention} has claimed this ticket and will be testing {self.applicant.mention}.")

        b.disabled = True
        b.label = f"Claimed by {i.user.display_name}"
        b.style = discord.ButtonStyle.secondary
        await i.message.edit(view=self)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="close_universal_btn")
    async def close_btn(self, i: discord.Interaction, b: Button):
        is_tester = any(r.id in TESTER_ROLES_FALLBACK.values() for r in i.user.roles)
        is_staff = any(r.id in (ROLE_ADMIN_ACCESS + ROLE_STAFF_ACCESS) for r in i.user.roles)
        
        if not (is_tester or is_staff or i.user.id == self.applicant.id):
            return await i.response.send_message("❌ You don't have permission to close this ticket.", ephemeral=True)

        await i.response.send_message("🔒 Closing ticket...")
        await asyncio.sleep(2)
        try:
            await i.channel.delete()
        except discord.NotFound:
            pass

async def run_ticket_invite_verification(channel: discord.TextChannel, user: discord.Member, ign: str, cat: str, mode: str):
    bold_verification_prompt = (
        f"> ## 🔒 **INSTRUCTIONS FOR VERIFICATION**\n"
        f"> {user.mention}, you must hold **1 or more invites** to proceed.\n"
        f"> \n"
        f"> ⚠️ **ACTION REQUIRED:** Please enter **`-i`** below in this channel immediately.\n"
        f"> \n"
        f"> *⏱️ Complete within 5 minutes, or this ticket node will be terminated automatically.*"
    )
    
    prompt_msg = await channel.send(content=bold_verification_prompt)

    def check_falcon_response(msg: discord.Message):
        if msg.channel.id == channel.id and msg.embeds:
            emb = msg.embeds[0]
            if emb.title == "Invite log" and (emb.description and (str(user.name) in emb.description or str(user.display_name) in emb.description)):
                return True
        return False

    try:
        falcon_msg = await bot.wait_for("message", check=check_falcon_response, timeout=300.0) 
        target_embed = falcon_msg.embeds[0]
        
        match = re.search(r'has\s+(\d+)\s+invites', target_embed.description.lower())
        if not match:
            await channel.send("❌ **Parsing Error:** Unable to map tracking metrics safely. Terminating channel layout...")
            await asyncio.sleep(5)
            await channel.delete()
            return

        total_invites = int(match.group(1))
        if total_invites < 1:
            await channel.send(f"❌ **Session Denied:** You have `{total_invites}` invites. **1** or more are required. Closing down...")
            await asyncio.sleep(5)
            await channel.delete()
            return

        clear_command_msg = await channel.send(content=f"-clearinvites @{user.name}")
        await asyncio.sleep(1.5)

        try:
            await channel.purge(limit=10)
        except discord.HTTPException:
            pass

        internal_db.table("profiles").upsert({"user_id": str(user.id), "ign": ign, "account_type": cat, "preferred_mode": mode}).execute()
        
        rid = AUTO_RANK_ROLES.get(f"{mode} {cat}")
        if rid:
            role = channel.guild.get_role(rid)
            if role: await user.add_roles(role)
        
        fallback_id = TESTER_ROLES_FALLBACK.get(mode)
        meta = ROLE_METADATA_TEMPLATES.get(mode, {"name": f"{mode} Tester", "color": discord.Color.default()})
        tester_role = channel.guild.get_role(fallback_id) if fallback_id else discord.utils.get(channel.guild.roles, name=meta["name"])

        reset_log_channel = channel.guild.get_channel(CHANNEL_MANUAL_RESET_LOGS)
        if reset_log_channel:
            tester_ping_str = tester_role.mention if tester_role else "@respective-tester"
            formatted_reset_cmd = fr"`-clearinvites {user.mention}` {tester_ping_str}"
            await reset_log_channel.send(content=formatted_reset_cmd)

        ticket_embed = discord.Embed(title=f"{EMOJI_REGISTRY.get(mode)} {mode} Testing Session", color=0x2b2d31, timestamp=datetime.datetime.now())
        ticket_embed.set_thumbnail(url=user.display_avatar.url)
        ticket_embed.description = f"Welcome {user.mention}! A tester will claim your ticket soon. Please wait patiently."
        
        ticket_embed.add_field(name="🆔 Minecraft IGN", value=f"`{ign}`", inline=True)
        ticket_embed.add_field(name="🎮 Gamemode", value=f"{EMOJI_REGISTRY.get(mode)} {mode}", inline=True)
        ticket_embed.add_field(name="💎 Platform Class", value=f"`{cat}`", inline=True)
        
        if tester_role:
            ticket_embed.add_field(name="Assigned Tester Group", value=tester_role.mention, inline=False)
            
        ticket_embed.set_footer(text="TriggerMc Normal Test System")

        view = UniversalTicketView(applicant=user, required_tester_role=tester_role)
        
        await channel.send(content=f"{user.mention} {tester_role.mention if tester_role else ''}", embed=ticket_embed, view=view)

    except asyncio.TimeoutError:
        try:
            await channel.send("⏱️ **Verification Timeout:** Limit exceeded. Purging channel framework...")
            await asyncio.sleep(5)
            await channel.delete()
        except discord.NotFound:
            pass

class PostModalGamemodeDropdown(discord.ui.Select):
    def __init__(self, ign: str, cat: str):
        self.ign = ign
        self.cat = cat
        super().__init__(placeholder="Select primary testing gamemode focus...", options=[discord.SelectOption(label=m, emoji=EMOJI_REGISTRY[m]) for m in MODES])

    async def callback(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        selected_mode = self.values[0]
        
        target_category_name = GAMEMODE_CATEGORY_NAMES.get(selected_mode)
        category_object = discord.utils.get(i.guild.categories, name=target_category_name)
        
        base_overwrites = {
            i.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            i.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }
        
        for staff_id in (ROLE_ADMIN_ACCESS + ROLE_STAFF_ACCESS):
            staff_role = i.guild.get_role(staff_id)
            if staff_role: 
                base_overwrites[staff_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        
        fallback_id = TESTER_ROLES_FALLBACK.get(selected_mode)
        meta = ROLE_METADATA_TEMPLATES.get(selected_mode, {"name": f"{selected_mode} Tester"})
        specific_tester_role = i.guild.get_role(fallback_id) if fallback_id else discord.utils.get(i.guild.roles, name=meta["name"])
        
        if specific_tester_role:
            base_overwrites[specific_tester_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
        
        base_overwrites[i.user] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

        sanitized_name = self.ign.replace(" ", "-").lower()
        
        ticket_channel = await i.guild.create_text_channel(
            name=f"🎫-{selected_mode.lower()}-{sanitized_name}",
            category=category_object,
            overwrites=base_overwrites
        )

        await i.followup.send(f"✅ Matrix synchronized! Step inside your verification ticket here: {ticket_channel.mention}", ephemeral=True)
        
        asyncio.create_task(run_ticket_invite_verification(ticket_channel, i.user, self.ign, self.cat, selected_mode))

async def create_higher_test_ticket(interaction: discord.Interaction, selected_mode: str):
    target_category = discord.utils.get(interaction.guild.categories, name="🏆 HIGHER TESTS")

    if not target_category:
        return await interaction.response.send_message("❌ Higher Test category not found.", ephemeral=True)

    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)
    }

    for role_id in ROLE_ADMIN_ACCESS + ROLE_STAFF_ACCESS:
        role = interaction.guild.get_role(role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

    for tester_role_id in TESTER_ROLES_FALLBACK.values():
        role = interaction.guild.get_role(tester_role_id)
        if role:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True)

    ticket_channel = await interaction.guild.create_text_channel(
        name=f"higher-{selected_mode.lower()}-{interaction.user.name.lower()}",
        category=target_category,
        overwrites=overwrites
    )

    embed = discord.Embed(title="🏆 Higher Tier Testing Session", color=0xFFD700, timestamp=datetime.datetime.now())
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.description = f"Welcome {interaction.user.mention}! A tester will be with you shortly.\nPlease have your client ready."
    
    embed.add_field(name="🆔 Minecraft IGN", value=f"`Not Provided`", inline=True)
    embed.add_field(name="🎮 Gamemode", value=f"{EMOJI_REGISTRY.get(selected_mode)} {selected_mode}", inline=True)
    embed.add_field(name="🌍 Region", value="`TBD`", inline=True)
    
    embed.set_footer(text="TriggerMc Higher Test System")

    fallback_id = TESTER_ROLES_FALLBACK.get(selected_mode)
    meta = ROLE_METADATA_TEMPLATES.get(selected_mode, {"name": f"{selected_mode} Tester"})
    specific_tester_role = interaction.guild.get_role(fallback_id) if fallback_id else discord.utils.get(interaction.guild.roles, name=meta["name"])

    view = UniversalTicketView(applicant=interaction.user, required_tester_role=specific_tester_role)
    
    await ticket_channel.send(content=f"{interaction.user.mention} — A tester will claim this soon.", embed=embed, view=view)
    await interaction.response.send_message(f"✅ Higher Test ticket created: {ticket_channel.mention}", ephemeral=True)

class HigherTestGamemodeDropdown(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=m, emoji=EMOJI_REGISTRY[m]) for m in MODES]
        super().__init__(placeholder="Select Higher Test gamemode...", options=options)

    async def callback(self, i: discord.Interaction):
        selected_mode = self.values[0]
        await create_higher_test_ticket(i, selected_mode)

class PreTicketWizardModal(Modal, title='TriggerMc Identity Verification Wizard'):
    ign = TextInput(label='Minecraft In-Game Name', min_length=3, max_length=16, placeholder="Exact Minecraft Username...", required=True)
    
    def __init__(self, cat: str): 
        super().__init__()
        self.cat = cat

    async def on_submit(self, i: discord.Interaction):
        dropdown_view = View()
        dropdown_view.add_item(PostModalGamemodeDropdown(self.ign.value, self.cat))
        await i.response.send_message(content=f"✨ Username saved: `{self.ign.value}`.\nChoose your target testing gamemode category block to deploy your private ticket channel:", view=dropdown_view, ephemeral=True)

class PersistentPortal(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Premium", style=discord.ButtonStyle.green, custom_id="v43_p_reg", emoji="💎")
    async def p(self, i, b): 
        await i.response.send_modal(PreTicketWizardModal("Premium"))
        
    @discord.ui.button(label="Cracked", style=discord.ButtonStyle.gray, custom_id="v43_c_reg", emoji="🏴‍☠️")
    async def c(self, i, b): 
        await i.response.send_modal(PreTicketWizardModal("Cracked"))

    @discord.ui.button(label="Higher Test", style=discord.ButtonStyle.red, emoji="🏆", custom_id="higher_test_button")
    async def higher_test(self, i: discord.Interaction, b: discord.ui.Button):
        view = discord.ui.View()
        view.add_item(HigherTestGamemodeDropdown())
        await i.response.send_message("Select the Higher Test gamemode:", view=view, ephemeral=True)

# ==============================================================================
# SECTION 8: MASTER COMMAND INTERFACES (SLASH CORE & MANAGEMENT)
# ==============================================================================

@bot.tree.command(name="close", description="🔒 Instantly delete and terminate an active testing ticket session channel.")
async def close_ticket(interaction: discord.Interaction):
    auth_ids = ROLE_ADMIN_ACCESS + ROLE_STAFF_ACCESS + list(TESTER_ROLES_FALLBACK.values())
    is_authorized = any(role.id in auth_ids for role in interaction.user.roles) or interaction.user.guild_permissions.administrator

    if not is_authorized:
        return await interaction.response.send_message("❌ Unauthorized: Only Evaluators or Staff can close active sessions.", ephemeral=True)

    if not interaction.channel:
        return await interaction.response.send_message("❌ Error: Channel not found.", ephemeral=True)

    await interaction.response.send_message("⚙️ Processing close request... Terminating channel node.")
    await asyncio.sleep(2)
    
    try:
        await interaction.channel.delete()
    except discord.NotFound:
        pass
    except discord.Forbidden:
        await interaction.followup.send("❌ Missing permissions to delete this channel.", ephemeral=True)

@bot.tree.command(name="lb", description="Display leaderboard logs.")
@app_commands.describe(target="The category of leaderboard node to pull up.")
@app_commands.choices(target=[app_commands.Choice(name="tester", value="tester")])
async def slash_leaderboard(interaction: discord.Interaction, target: app_commands.Choice[str]):
    await interaction.response.defer()
    embed = generate_tester_leaderboard_embed(interaction.guild)
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="data", description="🔒 LIVE OPERATIONAL DATA MANAGEMENT TERMINAL NODE.")
@app_commands.describe(ign="Target Minecraft IGN username profile to query.")
async def data_terminal(interaction: discord.Interaction, ign: str):
    if not await has_admin_access(interaction):
        return await interaction.response.send_message("❌ Error: Server Owner clearance required.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    try:
        alpha_res = internal_db.table("profiles").select("*").eq("ign", ign).execute()
        beta_res = external_db.table("players").select("*").eq("username", ign).execute()
        a_data = alpha_res.data[0] if alpha_res.data else None
        b_data = beta_res.data[0] if beta_res.data else None

        if not a_data and not b_data:
            return await interaction.followup.send(f"🔍 Profile record mismatch: `{ign}` not inside records.", ephemeral=True)

        embed = discord.Embed(title=f"🛠️ Data Profile Node: {ign}", color=0x2b2d31, timestamp=datetime.datetime.now())
        embed.set_footer(text="TriggerMc Core Administration Panel")

        if a_data:
            dc_mention = f"<@{a_data.get('user_id')}>"
            embed.add_field(name="📡 [ALPHA DB] Registration", value=f"**Discord Link:** {dc_mention}\n**UID Reference:** `{a_data.get('user_id')}`\n**Status Class:** `{a_data.get('account_type')}`\n**Focal Gamemode:** `{a_data.get('preferred_mode')}`", inline=False)
        else:
            embed.add_field(name="📡 [ALPHA DB] Registration", value="*No registration log mapping recorded.*", inline=False)

        if b_data:
            stats_str = ""
            exclusion_filter = ["id", "username", "created_at"]
            for k, v in b_data.items():
                if k not in exclusion_filter and v:
                    display_key = "Crystal" if k.lower() == "vanilla" else k.capitalize()
                    stats_str += f"• **{display_key}:** `{v}`\n"
            stats_str += f"• **Region Matrix:** `{b_data.get('region', 'N/A')}`"
            embed.add_field(name="🌍 [BETA DB] Network Ranks", value=stats_str if stats_str else "*No specific values configured.*", inline=False)
        else:
            embed.add_field(name="🌍 [BETA DB] Network Ranks", value="*No synchronized web ranking profile present.*", inline=False)

        resolved_uid = a_data.get('user_id', 'N/A') if a_data else "N/A"
        await interaction.followup.send(embed=embed, view=AdminTerminalView(ign, resolved_uid), ephemeral=True)

    except Exception as e:
        logger.error(f"TERMINAL EXTRACTION FAILURE: {e}")
        await interaction.followup.send("❌ Internal Core Error: Failed to compile profiles.", ephemeral=True)

@bot.tree.command(name="results", description="The EXCLUSIVE entry point for Leaderboard and Tier sync.")
@app_commands.choices(gamemode=[app_commands.Choice(name=g, value=g) for g in MODES], region=[app_commands.Choice(name=r, value=r) for r in REGIONS], previous_tier=[app_commands.Choice(name=t, value=t) for t in TIERS], assigned_tier=[app_commands.Choice(name=t, value=t) for t in TIERS])
async def results(interaction, player: discord.Member, ign: str, gamemode: app_commands.Choice[str], region: app_commands.Choice[str], previous_tier: app_commands.Choice[str], assigned_tier: app_commands.Choice[str]):
    expected_tester_name = ROLE_METADATA_TEMPLATES.get(gamemode.value, {}).get("name", "")
    has_tester_name_role = any(r.name == expected_tester_name for r in interaction.user.roles)
    
    auth_ids = ROLE_ADMIN_ACCESS + ROLE_STAFF_ACCESS + list(TESTER_ROLES_FALLBACK.values())
    has_auth_id = any(r.id in auth_ids for r in interaction.user.roles)

    if not (has_auth_id or has_tester_name_role):
        return await interaction.response.send_message("❌ Error: Unauthorized tester clearance required.", ephemeral=True)

    await interaction.response.defer()
    try:
        db_field = "vanilla" if gamemode.value.lower() == "crystal" else gamemode.value.lower()
        
        try:
            external_db.table("players").upsert({"username": ign, "region": region.value, db_field: assigned_tier.value}, on_conflict="username").execute()
        except Exception as db_err:
            logger.error(f"DB Upsert Error: {db_err}")
            await asyncio.sleep(2) 
            external_db.table("players").upsert({"username": ign, "region": region.value, db_field: assigned_tier.value}, on_conflict="username").execute()

        m_key = gamemode.value
        icon = EMOJI_REGISTRY.get(m_key, "")
        target_tier = assigned_tier.value.strip().upper()

        # Match role names without depending on emoji or exact capitalization.
        mode_aliases = {
            "CRYSTAL": ("CRYSTAL", "VANILLA"),
            "SMP": ("SMP",),
        }
        mode_terms = mode_aliases.get(m_key.upper(), (m_key.upper(),))

        nr = discord.utils.get(
            interaction.guild.roles,
            name=f"{icon} {m_key} {assigned_tier.value}"
        )
        if nr is None:
            for role in interaction.guild.roles:
                role_name = role.name.upper()
                has_mode = any(term in role_name for term in mode_terms)
                has_tier = target_tier in role_name.split()
                if has_mode and has_tier:
                    nr = role
                    break

        if nr is None:
            logger.error(
                "TIER ROLE NOT FOUND: expected role like '%s %s %s' in guild %s",
                icon, m_key, target_tier, interaction.guild.id
            )
            await interaction.followup.send(
                f"⚠️ Database updated, but I couldn't find the Discord role for "
                f"**{m_key} {target_tier}**. Check the role name and bot role hierarchy.",
                ephemeral=True
            )
        else:
            # Remove previous tier roles for this mode only, then assign the selected tier.
            old_roles = []
            for role in player.roles:
                role_name = role.name.upper()
                has_mode = any(term in role_name for term in mode_terms)
                has_any_tier = any(tier in role_name.split() for tier in TIERS)
                if role.id != nr.id and has_mode and has_any_tier:
                    old_roles.append(role)

            if old_roles:
                await player.remove_roles(*old_roles, reason=f"Tier changed to {m_key} {target_tier}")
            if nr not in player.roles:
                await player.add_roles(nr, reason=f"Tier assigned by /results: {m_key} {target_tier}")

        tester_id = interaction.user.id
        TESTER_COUNTS[tester_id] = TESTER_COUNTS.get(tester_id, 0) + 1
        current_test_count = TESTER_COUNTS[tester_id]

        try:
            res = internal_db.table("tester_scores").select("tests_completed").eq("user_id", str(tester_id)).execute()
            if res.data:
                internal_db.table("tester_scores").update({"tests_completed": current_test_count}).eq("user_id", str(tester_id)).execute()
            else:
                internal_db.table("tester_scores").insert({"user_id": str(tester_id), "tests_completed": 1}).execute()
        except Exception as e:
            logger.error(f"Failed to save tester score to DB: {e}")

        add_vouch_to_db(tester_id)

        log = discord.Embed(title="Tier Test Result", color=0xFFD700, timestamp=datetime.datetime.now())
        log.set_thumbnail(url=bot.user.display_avatar.url)
        log.add_field(name="👤 User", value=player.mention, inline=True)
        log.add_field(name="🆔 Minecraft IGN", value=f"`{ign}`", inline=True)
        log.add_field(name="🎮 Mode", value=f"{icon} {m_key}", inline=True)
        log.add_field(name="🌍 Region", value=f"`{region.value}`", inline=True)
        log.add_field(name="📉 Previous Rank", value=f"`{previous_tier.value}`", inline=True)
        log.add_field(name="📈 New Rank", value=f"**{assigned_tier.value}**", inline=True)
        log.add_field(name="🛡️ Tester", value=interaction.user.mention, inline=False) 

        audit = interaction.guild.get_channel(CHANNEL_AUDIT_LOGS)
        if audit: await audit.send(embed=log)
        
        stats_channel = interaction.guild.get_channel(CHANNEL_STATS_LOGS)
        if stats_channel:
            custom_log_message = f"{player.mention} tested by {interaction.user.mention} now {interaction.user.mention} completed {current_test_count} tests"
            await stats_channel.send(content=custom_log_message)

        await interaction.followup.send(f"✅ Sync complete for user `{ign}`.")
        
        if "🎫-" in interaction.channel.name: 
            await asyncio.sleep(3)
            try:
                await interaction.channel.delete()
            except discord.NotFound:
                pass

    except Exception as e:
        logger.error(f"CRITICAL: Results pipeline broken: {e}")
        if not interaction.response.is_done():
            await interaction.followup.send("❌ Error synchronizing results code with servers.", ephemeral=True)

@bot.tree.command(name="profile", description="View a tester's vouches.")
async def profile(interaction: discord.Interaction, tester: discord.Member):
    await interaction.response.defer()
    
    try:
        res = internal_db.table("tester_vouches").select("vouch_count").eq("user_id", str(tester.id)).execute()
        vouches = res.data[0]["vouch_count"] if res.data else 0
    except:
        vouches = 0
        
    try:
        res2 = internal_db.table("tester_scores").select("tests_completed").eq("user_id", str(tester.id)).execute()
        tests = res2.data[0]["tests_completed"] if res2.data else 0
    except:
        tests = 0

    embed = discord.Embed(title=f"📊 Tester Profile: {tester.display_name}", color=discord.Color.gold())
    embed.set_thumbnail(url=tester.display_avatar.url)
    embed.add_field(name="🛡️ Tests Completed", value=f"**{tests}**", inline=True)
    embed.add_field(name="⭐ Total Vouches", value=f"**{vouches}**", inline=True)
    
    if tests > 0:
        rating = min(100, int((vouches / tests) * 100))
        embed.add_field(name="📈 Vouch Rate", value=f"**{rating}%**", inline=True)
    else:
        embed.add_field(name="📈 Vouch Rate", value="*N/A*", inline=True)

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="vouch", description="Give a vouch to a tester who did a great job!")
@app_commands.describe(tester="The tester you want to vouch for")
async def manual_vouch(interaction: discord.Interaction, tester: discord.Member):
    if interaction.user.id == tester.id:
        return await interaction.response.send_message("❌ You cannot vouch for yourself!", ephemeral=True)
    
    is_tester = False
    for role_id in TESTER_ROLES_FALLBACK.values():
        if tester.get_role(role_id):
            is_tester = True
            break
            
    if not is_tester:
        return await interaction.response.send_message(f"❌ {tester.mention} is not a registered tester.", ephemeral=True)

    await interaction.response.defer(ephemeral=True)
    
    try:
        add_vouch_to_db(tester.id)
        await interaction.followup.send(f"⭐ Thank you! You have successfully vouched for {tester.mention}.", ephemeral=True)
    except Exception as e:
        logger.error(f"Manual vouch error: {e}")
        await interaction.followup.send("❌ Error saving vouch.", ephemeral=True)

# ==============================================================================
# SECTION 9: TEXT MANAGEMENT INFRASTRUCTURE (PREFIX INTERFACES)
# ==============================================================================

@bot.command(name="sync")
@commands.has_permissions(administrator=True)
async def sync(ctx):
    bot.tree.copy_global_to(guild=ctx.guild)
    total = await bot.tree.sync(guild=ctx.guild)
    await ctx.send(embed=discord.Embed(title="System Synchronization Success", description=f"Successfully synchronized **{len(total)}** nodes.", color=discord.Color.blue()))

@bot.command(name="setup")
@commands.has_permissions(administrator=True)
async def setup(ctx):
    portal = discord.Embed(title="TriggerMc Identity Portal", color=0x2b2d31, description="Verify your account parameters to access server matchmaking systems.")
    portal.add_field(name="📜 Portal Steps", value="1. Click your **Account Category** class button.\n2. Fill out your IGN modal registration parameter properties.\n3. Choose your target gamemode focus layout options to deploy your ticket.", inline=False)
    msg = await ctx.send(embed=portal, view=PersistentPortal())
    try:
        await msg.pin()
        await ctx.send("📌 Portal has been pinned to the channel!", delete_after=5)
    except:
        pass

@bot.group(name="lb", invoke_without_command=True)
async def lb_group(ctx):
    await ctx.send("❌ Invalid Syntax. Use `!lb test` to open the tester leaderboard layout.")

@lb_group.command(name="test")
async def lb_test_subcommand(ctx):
    embed = generate_tester_leaderboard_embed(ctx.guild)
    await ctx.send(embed=embed)

# ==============================================================================
# SECTION 10: AUXILIARY MANAGEMENT SYSTEMS
# ==============================================================================

class CommunityEventNode(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Enroll in Community Event", style=discord.ButtonStyle.blurple, custom_id="v43_ev_join_node", emoji="🎮")
    async def join_ev(self, i, b):
        r = discord.utils.get(i.guild.roles, name="Event Participant")
        if r: 
            await i.user.add_roles(r)
            await i.response.send_message("✅ Success: Enrolled in community event rosters.", ephemeral=True)

# ==============================================================================
# SECTION 11: SERVER EVENT MANAGEMENT SYSTEM
# ==============================================================================

class EventManageView(View):
    def __init__(self, event_id):
        super().__init__(timeout=180)
        self.event_id = event_id

    @discord.ui.button(label="Edit Time", style=discord.ButtonStyle.primary, emoji="⏰")
    async def edit_time(self, i: discord.Interaction, b: Button):
        class TimeModal(Modal, title="Edit Event Time"):
            time_str = TextInput(label="Start Time (Format: YYYY-MM-DD HH:MM)", placeholder="2026-10-25 18:00")
            def __init__(self, event_id):
                super().__init__()
                self.event_id = event_id
            async def on_submit(self, interaction: discord.Interaction):
                try:
                    new_time = datetime.datetime.strptime(self.time_str.value, "%Y-%m-%d %H:%M")
                    internal_db.table("server_events").update({"start_time": new_time.isoformat()}).eq("id", self.event_id).execute()
                    await interaction.response.send_message(f"✅ Event time updated to {new_time}.", ephemeral=True)
                except ValueError:
                    await interaction.response.send_message("❌ Invalid format! Use YYYY-MM-DD HH:MM", ephemeral=True)
        await i.response.send_modal(TimeModal(self.event_id))

    @discord.ui.button(label="End Event", style=discord.ButtonStyle.danger, emoji="🛑")
    async def end_event(self, i: discord.Interaction, b: Button):
        await i.response.defer(ephemeral=True)
        try:
            res = internal_db.table("server_events").select("*").eq("id", self.event_id).execute()
            if not res.data:
                return await i.followup.send("❌ Event not found.", ephemeral=True)
            
            event = res.data[0]
            role_id = event.get("role_id")
            
            if role_id:
                role = i.guild.get_role(int(role_id))
                if role:
                    removed_count = 0
                    for member in role.members:
                        await member.remove_roles(role)
                        removed_count += 1
                    await i.followup.send(f"✅ Event ended. Removed {role.name} from {removed_count} members.", ephemeral=True)
                else:
                    await i.followup.send("✅ Event ended. (Role not found to remove).", ephemeral=True)
            else:
                await i.followup.send("✅ Event ended.", ephemeral=True)

            internal_db.table("server_events").delete().eq("id", self.event_id).execute()
            
            embed = discord.Embed(title="🛑 EVENT ENDED", description=f"**{event['name']}** has officially ended. Thank you to everyone who participated!", color=discord.Color.red())
            await i.channel.send(embed=embed)

        except Exception as e:
            logger.error(f"Event end error: {e}")
            await i.followup.send("❌ Error ending event.", ephemeral=True)

@bot.tree.command(name="event", description="🔒 Admin: Create a new server event.")
@commands.has_permissions(administrator=True)
@app_commands.describe(name="Name of the event", time="Start time (YYYY-MM-DD HH:MM)", role="Role to give participants")
async def create_event(interaction: discord.Interaction, name: str, time: str, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    
    try:
        start_time = datetime.datetime.strptime(time, "%Y-%m-%d %H:%M")
    except ValueError:
        return await interaction.followup.send("❌ Invalid time format! Use `YYYY-MM-DD HH:MM` (e.g., 2026-10-25 18:00)", ephemeral=True)

    try:
        res = internal_db.table("server_events").insert({
            "name": name,
            "start_time": start_time.isoformat(),
            "role_id": str(role.id),
            "is_active": True
        }).execute()
        event_id = res.data[0]['id']
    except Exception as e:
        logger.error(f"Event creation error: {e}")
        return await interaction.followup.send("❌ Failed to save event to database.", ephemeral=True)

    embed = discord.Embed(
        title=f"🎉 NEW EVENT: {name}",
        description=f"**Starts:** <t:{int(start_time.timestamp())}:F> (<t:{int(start_time.timestamp())}:R>)\n\nClick the button below to join and receive the {role.mention} role!",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Event ID: {event_id}")

    class JoinEventView(View):
        def __init__(self):
            super().__init__(timeout=None)
        
        @discord.ui.button(label="Join Event", style=discord.ButtonStyle.success, emoji="✅", custom_id=f"join_event_{event_id}")
        async def join_btn(self, i: discord.Interaction, b: Button):
            if role in i.user.roles:
                return await i.response.send_message("❌ You have already joined this event!", ephemeral=True)
            
            await i.user.add_roles(role)
            await i.response.send_message(f"✅ You have successfully joined **{name}**! You now have the {role.mention} role.", ephemeral=True)

    bot.add_view(JoinEventView())
    msg = await interaction.channel.send(embed=embed, view=JoinEventView())

    admin_embed = discord.Embed(title="⚙️ Event Admin Panel", description="Use these buttons to manage the event.", color=discord.Color.blue())
    await interaction.followup.send(embed=admin_embed, view=EventManageView(event_id), ephemeral=True)

@bot.tree.command(name="event_list", description="List all active events.")
async def event_list(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        res = internal_db.table("server_events").select("*").execute()
        if not res.data:
            return await interaction.followup.send("📭 There are no active events right now.", ephemeral=True)
        
        embed = discord.Embed(title="📅 Active Server Events", color=discord.Color.gold())
        for event in res.data:
            start_time = datetime.datetime.fromisoformat(event['start_time'])
            role = interaction.guild.get_role(int(event['role_id']))
            role_name = role.mention if role else "*Deleted Role*"
            
            embed.add_field(
                name=f"🎉 {event['name']}",
                value=f"**Starts:** <t:{int(start_time.timestamp())}:F>\n**Role:** {role_name}\n**Participants:** {len(role.members) if role else 0}",
                inline=False
            )
        await interaction.followup.send(embed=embed)
    except Exception as e:
        logger.error(f"Event list error: {e}")
        await interaction.followup.send("❌ Failed to load events.", ephemeral=True)

@bot.tree.command(name="event_add", description="🔒 Admin: Manually add a user to an event.")
@commands.has_permissions(administrator=True)
async def event_add(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    if role in user.roles:
        return await interaction.followup.send(f"❌ {user.mention} already has that role.", ephemeral=True)
    
    await user.add_roles(role)
    await interaction.followup.send(f"✅ Added {user.mention} to the event with role {role.mention}.", ephemeral=True)

@bot.tree.command(name="event_remove", description="🔒 Admin: Manually remove a user from an event.")
@commands.has_permissions(administrator=True)
async def event_remove(interaction: discord.Interaction, user: discord.Member, role: discord.Role):
    await interaction.response.defer(ephemeral=True)
    if role not in user.roles:
        return await interaction.followup.send(f"❌ {user.mention} does not have that role.", ephemeral=True)
    
    await user.remove_roles(role)
    await interaction.followup.send(f"✅ Removed {user.mention} from the event.", ephemeral=True)

if __name__ == "__main__":
    bot.run(MASTER_TOKEN)