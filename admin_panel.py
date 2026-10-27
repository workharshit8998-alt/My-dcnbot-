"""Discord admin panel for command permissions. Additive extension; stores settings in admin_panel_config.json."""
import json
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Select, Button, RoleSelect

from __main__ import has_admin_access

log = logging.getLogger("TriggerMc.AdminPanel")
CONFIG_PATH = Path(__file__).with_name("admin_panel_config.json")
NEON = 0x36E5FF


def _load_config():
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_config(data):
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(CONFIG_PATH)


def _command_key(command):
    return getattr(command, "qualified_name", getattr(command, "name", "unknown"))


def _all_commands(bot):
    found = []
    def walk(items):
        for item in items:
            found.append(item)
            children = getattr(item, "commands", None)
            if children:
                walk(children)
    walk(bot.tree.get_commands())
    # Use qualified names, which uniquely identify subcommands.
    unique = {}
    for item in found:
        unique[_command_key(item)] = item
    return sorted(unique.values(), key=_command_key)


class CommandRoleSelect(RoleSelect):
    def __init__(self, panel):
        super().__init__(placeholder="Choose roles allowed to use this command", min_values=0, max_values=25)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        if not await has_admin_access(interaction):
            await interaction.response.send_message("You are not authorized to use this panel.", ephemeral=True)
            return
        self.panel.config.setdefault(self.panel.selected, {})["roles"] = [str(role.id) for role in self.values]
        try:
            _save_config(self.panel.config)
        except OSError as exc:
            await interaction.response.send_message(f"Could not save settings: {exc}", ephemeral=True)
            return
        await self.panel.refresh(interaction, "Allowed roles saved. An empty role list means no extra role restriction.")


class CommandSelect(Select):
    def __init__(self, panel, commands_list):
        options = [
            discord.SelectOption(
                label=_command_key(cmd)[:100],
                value=_command_key(cmd)[:100],
                description=("Group / " + _command_key(cmd))[:100]
            )
            for cmd in commands_list[:25]
        ]
        if not options:
            options = [discord.SelectOption(label="No commands found", value="__none__", default=True)]
        super().__init__(placeholder="Select a slash command to manage", min_values=1, max_values=1, options=options)
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        if not await has_admin_access(interaction):
            await interaction.response.send_message("You are not authorized to use this panel.", ephemeral=True)
            return
        self.panel.selected = self.values[0]
        await self.panel.refresh(interaction)



def _command_category(command):
    name = _command_key(command).lower()
    if any(word in name for word in ('giveaway', 'raffle', 'gaw')): return 'Giveaways'
    if any(word in name for word in ('admin', 'owner', 'staff', 'config', 'permission', 'panel')): return 'Admin'
    if any(word in name for word in ('player', 'compare', 'profile', 'tier', 'rank', 'region', 'leaderboard', 'vouch', 'test')): return 'Players & Testing'
    return 'Other'

class CategorySelect(Select):
    def __init__(self, panel):
        cats = sorted({_command_category(cmd) for cmd in _all_commands(panel.bot)})
        opts = [discord.SelectOption(label=x, value=x) for x in cats[:25]] or [discord.SelectOption(label='Other', value='Other')]
        super().__init__(placeholder='Choose a command category', min_values=1, max_values=1, options=opts, row=1)
        self.panel = panel
    async def callback(self, interaction):
        if not await has_admin_access(interaction):
            await interaction.response.send_message('Not authorized.', ephemeral=True); return
        self.panel.selected_category = self.values[0]
        await self.panel.refresh(interaction, 'Category selected. Bulk actions apply to every command in this category.')

class BulkCategoryButton(Button):
    def __init__(self, panel, action):
        labels = {'enable': 'Enable category', 'disable': 'Disable category', 'everyone': 'Allow everyone in category'}
        super().__init__(label=labels[action], style=discord.ButtonStyle.secondary, row=4)
        self.panel, self.action = panel, action
    async def callback(self, interaction):
        if not await has_admin_access(interaction):
            await interaction.response.send_message('Not authorized.', ephemeral=True); return
        category = self.panel.selected_category
        if not category:
            await interaction.response.send_message('Choose a category first.', ephemeral=True); return
        cmds = [x for x in _all_commands(self.panel.bot) if _command_category(x) == category]
        for cmd in cmds:
            settings = self.panel.config.setdefault(_command_key(cmd), {})
            if self.action == 'enable': settings['enabled'] = True
            elif self.action == 'disable': settings['enabled'] = False
            else: settings['roles'] = []
        try: _save_config(self.panel.config)
        except OSError as exc:
            await interaction.response.send_message(f'Could not save: {exc}', ephemeral=True); return
        await self.panel.refresh(interaction, f'Updated {len(cmds)} commands in {category}.')

class AdminPanelView(View):
    def __init__(self, bot, guild, selected=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.guild = guild
        self.config = _load_config()
        self.selected = selected
        self.selected_category = None
        commands_list = _all_commands(bot)
        self.add_item(CommandSelect(self, commands_list))
        self.add_item(CategorySelect(self))
        if selected and selected != "__none__":
            self.add_item(CommandRoleSelect(self))
        self.add_item(ToggleCommandButton(self))
        self.add_item(RefreshPanelButton(self))
        self.add_item(BulkCategoryButton(self, 'enable'))
        self.add_item(BulkCategoryButton(self, 'disable'))
        self.add_item(BulkCategoryButton(self, 'everyone'))

    def build_embed(self, notice=None):
        embed = discord.Embed(
            title="⚙️ TriggerMc • Admin Panel",
            description="Manage slash-command access. Changes are saved to the bot's local config.",
            color=NEON
        )
        commands_list = _all_commands(self.bot)
        if self.selected_category:
            count = sum(1 for cmd in commands_list if _command_category(cmd) == self.selected_category)
            embed.add_field(name='Selected category: ' + self.selected_category, value=f'{count} commands; bulk buttons apply to all of them.', inline=False)
        shown = commands_list[:12]
        lines = []
        for cmd in shown:
            key = _command_key(cmd)
            settings = self.config.get(key, {})
            enabled = settings.get("enabled", True)
            roles = settings.get("roles", [])
            state = "🟢 Enabled" if enabled else "🔴 Disabled"
            role_text = ", ".join(f"<@&{rid}>" for rid in roles[:4]) if roles else "No extra role restriction"
            lines.append(f"{state} · `/{key}`\n└ {role_text}")
        embed.add_field(name="Commands", value="\n".join(lines)[:1024] or "No slash commands found.", inline=False)
        if self.selected and self.selected != "__none__":
            settings = self.config.get(self.selected, {})
            embed.add_field(
                name=f"Selected: /{self.selected}",
                value=f"Status: **{'Enabled' if settings.get('enabled', True) else 'Disabled'}**\n"
                      f"Allowed roles: {', '.join(settings.get('roles', [])) or 'None (no extra restriction)'}",
                inline=False
            )
        if len(commands_list) > 20:
            embed.set_footer(text=f"Showing first 12 of {len(commands_list)} commands. Use selectors to manage commands and categories.")
        else:
            embed.set_footer(text="Only the bot owner / authorized admins can change these settings.")
        if notice:
            embed.add_field(name="Updated", value=notice, inline=False)
        return embed

    async def refresh(self, interaction, notice=None):
        self.config = _load_config()
        new_view = AdminPanelView(self.bot, self.guild, self.selected)
        if interaction.response.is_done():
            await interaction.edit_original_response(embed=new_view.build_embed(notice), view=new_view)
        else:
            await interaction.response.edit_message(embed=new_view.build_embed(notice), view=new_view)


class ToggleCommandButton(Button):
    def __init__(self, panel):
        super().__init__(label="Enable / Disable selected", style=discord.ButtonStyle.primary, emoji="🔁")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        if not await has_admin_access(interaction):
            await interaction.response.send_message("You are not authorized to use this panel.", ephemeral=True)
            return
        key = self.panel.selected
        if not key or key == "__none__":
            await interaction.response.send_message("Select a command first.", ephemeral=True)
            return
        self.panel.config.setdefault(key, {})
        current = self.panel.config[key].get("enabled", True)
        self.panel.config[key]["enabled"] = not current
        try:
            _save_config(self.panel.config)
        except OSError as exc:
            await interaction.response.send_message(f"Could not save settings: {exc}", ephemeral=True)
            return
        await self.panel.refresh(interaction, f"/{key} is now {'enabled' if not current else 'disabled'}.")


class RefreshPanelButton(Button):
    def __init__(self, panel):
        super().__init__(label="Refresh", style=discord.ButtonStyle.secondary, emoji="🔄")
        self.panel = panel

    async def callback(self, interaction: discord.Interaction):
        if not await has_admin_access(interaction):
            await interaction.response.send_message("You are not authorized to use this panel.", ephemeral=True)
            return
        await self.panel.refresh(interaction, "Command list refreshed.")


class AdminPanel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._previous_tree_check = getattr(bot.tree, "interaction_check", None)

    async def cog_load(self):
        async def permission_check(interaction: discord.Interaction) -> bool:
            previous = self._previous_tree_check
            if previous:
                ok = previous(interaction)
                if hasattr(ok, "__await__"):
                    ok = await ok
                if not ok:
                    return False
            command = interaction.command
            if command is None or interaction.guild is None:
                return True
            key = _command_key(command)
            # Panel management remains accessible to authorized admins even if configured off.
            if key == "admin_panel" and await has_admin_access(interaction):
                return True
            if await has_admin_access(interaction):
                return True
            settings = _load_config().get(key, {})
            if settings.get("enabled", True) is False:
                await interaction.response.send_message("This command is currently disabled by an administrator.", ephemeral=True)
                return False
            allowed_roles = {int(r) for r in settings.get("roles", []) if str(r).isdigit()}
            if allowed_roles:
                member_roles = {r.id for r in getattr(interaction.user, "roles", [])}
                if not member_roles.intersection(allowed_roles):
                    await interaction.response.send_message("You don't have a role allowed to use this command.", ephemeral=True)
                    return False
            return True
        self.bot.tree.interaction_check = permission_check

    @app_commands.command(name="admin_panel", description="Open the command permission management panel")
    async def admin_panel(self, interaction: discord.Interaction):
        if not await has_admin_access(interaction):
            await interaction.response.send_message("⛔ Only the bot owner or an authorized admin can open this panel.", ephemeral=True)
            return
        view = AdminPanelView(self.bot, interaction.guild)
        await interaction.response.send_message(embed=view.build_embed(), view=view, ephemeral=True)


async def setup(bot):
    await bot.add_cog(AdminPanel(bot))
