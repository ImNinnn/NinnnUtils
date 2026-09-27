"""/settings: personal settings (colour, pings, timezone, banner) and the server settings panels."""

import asyncio
import re

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, ChannelSelect, Container, Modal, RoleSelect, Section, Separator, TextDisplay, TextInput, View

from save import get_guild_config, load_board_data, load_fun_data, load_levels, load_user_settings, save_board_data, save_fun_data, save_guild_data, save_levels, save_user_settings
from utils import runtime
from utils.audit import add_admin_log_channel, get_admin_log_channel_mentions, get_guild_admin_log_channel_ids, remove_admin_log_channel
from utils.banners import create_banner_preview, get_banner_search_matches, get_user_banner_style, load_banner_definitions
from utils.formatting import COLOR_EMOJIS, parse_duration_to_seconds
from utils.permissions import validate_role_selection
from utils.user_settings import USER_COLOR_OPTIONS, get_user_color, get_user_color_value, get_user_pings_enabled, get_user_settings_entry, parse_utc_offset
from utils.views import TimeoutDisabledLayoutView, TimeoutDisabledView, safe_send


async def refresh_ticket_announce_message(guild_id: str) -> None:
    # Imported here so a reloaded tickets cog is used, and to keep the cogs independent at import time.
    from cogs.tickets import refresh_ticket_announce_message as refresh
    await refresh(guild_id)


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


def format_channel_reference(guild: discord.Guild, channel_id) -> str:
    if not channel_id:
        return "None"
    try:
        ch_id = int(channel_id)
    except (TypeError, ValueError):
        return str(channel_id)
    channel = guild.get_channel(ch_id)
    return channel.mention if channel else f"<#{ch_id}>"


def format_role_reference(guild: discord.Guild, role_id) -> str:
    if not role_id:
        return "None"
    try:
        role_id_int = int(role_id)
    except (TypeError, ValueError):
        return str(role_id)
    role = guild.get_role(role_id_int)
    return role.mention if role else f"<@&{role_id_int}>"


class TicketConfigModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Set ticket settings")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.style_input = TextInput(label="Ticket style (button/list)", placeholder="button or list", required=True, max_length=10)
        self.reasons_input = TextInput(
            label="Ticket reasons",
            placeholder="(Reason1)(Reason2)(Reason3)... up to 10",
            required=False,
            style=discord.TextStyle.long,
            max_length=500,
        )
        self.add_item(self.style_input)
        self.add_item(self.reasons_input)

    async def on_submit(self, interaction: discord.Interaction):
        style = self.style_input.value.strip().lower()
        reasons_raw = self.reasons_input.value.strip()
        if style not in {"button", "list"}:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Ticket style must be button or list.", ephemeral=True)
            return
        reasons = []
        if reasons_raw:
            reasons = re.findall(r"\(([^)]+)\)", reasons_raw)
            reasons = [reason.strip() for reason in reasons if reason.strip()]
            if len(reasons) > 10:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> You may only configure up to 10 ticket reasons.", ephemeral=True)
                return
        await self.callback(interaction, style, reasons, self.settings_message)


class RoleSelectorView(View):
    def __init__(self, user_id: int, guild: discord.Guild, placeholder: str, callback, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.callback = callback
        self.settings_message = settings_message
        self.role_select = RoleSelect(placeholder=placeholder, custom_id="role_selector", min_values=1, max_values=1)
        self.role_select.callback = self.on_role_selected
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="role_select_cancel")
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.role_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        if not self.role_select.values:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No role was selected.", ephemeral=True)
            return
        role = self.role_select.values[0]
        self.role_select.disabled = True
        self.cancel_button.disabled = True
        await self.callback(interaction, role, self.settings_message)
        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def on_cancel(self, interaction: discord.Interaction):
        self.role_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(content="Role selection cancelled.", view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


def get_guild_board_entries(guild_id: str) -> list[str]:
    board_data = load_board_data()
    entries = []
    if guild_id in board_data:
        for emoji_key, cfg in board_data[guild_id].items():
            ch_id = cfg.get("channel_id")
            required = cfg.get("required_count")
            channel_repr = f"<#{ch_id}>" if ch_id else "Unknown"
            req_text = f"required {required}" if required is not None else "required ?"
            entries.append(f"{emoji_key} in {channel_repr} ({req_text})")
    return entries


def get_guild_counter_entries(guild: discord.Guild) -> list[str]:
    guild_config, _ = get_guild_config(str(guild.id))
    entries = []
    for ch_key, cfg in guild_config.get("counter_channels", {}).items():
        try:
            ch_id = int(ch_key)
            ch = guild.get_channel(ch_id)
            ch_repr = ch.mention if ch else f"<#{ch_id}>"
        except (TypeError, ValueError):
            ch_repr = str(ch_key)
        current_val = cfg.get("current_value", 0)
        entries.append(f"{ch_repr}: {current_val}")
    return entries


def get_level_channel_id(guild_id: str):
    levels = load_levels()
    if guild_id in levels:
        return levels[guild_id].get("config", {}).get("channel_id")
    return None


def set_level_channel(guild_id: str, channel_id: int | None):
    levels = load_levels()
    if guild_id not in levels:
        levels[guild_id] = {"config": {}, "users": {}}
    if "config" not in levels[guild_id]:
        levels[guild_id]["config"] = {}
    levels[guild_id]["config"]["channel_id"] = channel_id
    save_levels(levels)


class SettingsMenuView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, username: str, color: discord.Color):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.username = username
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.user_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_user",
        )
        self.guild_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id="settings_open_guild",
        )

        async def open_user(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            new_view = UserSettingsView(
                interaction.user.id,
                current_color=user_settings.get("color", "white"),
                current_pings=user_settings.get("user_pings", True),
                current_style=user_settings.get("banner_style", "normal"),
                settings_message=interaction.message,
            )
            await interaction.response.edit_message(view=new_view)

        async def open_guild(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use guild settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            new_view = GuildSettingsMenuView(
                interaction.user.id,
                str(interaction.guild.id),
            )
            await interaction.response.edit_message(view=new_view)

        self.user_button.callback = open_user
        self.guild_button.callback = open_guild

        container = Container(
            TextDisplay(f"<:gear:1517576939097952496> **Settings for {self.username}**"),
            Separator(),
            Section("<:edit:1517497568421085256> User settings", accessory=self.user_button),
            Section("<:drawer:1517497564189036574> Guild settings", accessory=self.guild_button),
            Separator(),
            TextDisplay("Found a bug ? Report it in the [support server](https://discord.gg/FSBPvc9zqY)"),
            accent_color=self.color,
        )
        self.add_item(container)


class UserSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, current_color: str, current_pings: bool, current_style: str = "normal", settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.current_color = current_color or "white"
        self.current_pings = current_pings
        self.current_style = str(current_style or "normal").strip().lower()
        self.settings_message = settings_message
        self.build_components()

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = self.settings_message or interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return

        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass

        try:
            channel = runtime.bot.get_channel(settings_message.channel.id)
            if channel is not None:
                fresh_message = await channel.fetch_message(settings_message.id)
                await fresh_message.edit(view=view)
                return
        except Exception:
            pass

        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass

        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    def build_components(self):
        self.clear_items()
        self.ping_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.secondary,
            custom_id="user_settings_pings",
        )

        async def ping_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            self.current_pings = not self.current_pings
            user_settings["user_pings"] = self.current_pings
            save_user_settings(settings)
            refreshed_view = UserSettingsView(
                self.user_id,
                self.current_color,
                self.current_pings,
                self.current_style,
                settings_message=self.settings_message,
            )
            await interaction.response.edit_message(view=refreshed_view)
            if self.settings_message is not None and self.settings_message.id != interaction.message.id:
                try:
                    await self.settings_message.edit(view=refreshed_view)
                except (discord.NotFound, discord.HTTPException):
                    pass

        self.ping_button.callback = ping_callback

        self.ads_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.secondary,
            custom_id="user_settings_ads",
        )

        async def ads_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            # store as disable flag for clarity: True means ads disabled
            currently_disabled = bool(user_settings.get("disable_ads", False))
            user_settings["disable_ads"] = not currently_disabled
            save_user_settings(settings)
            refreshed_view = UserSettingsView(
                self.user_id,
                self.current_color,
                self.current_pings,
                self.current_style,
                settings_message=self.settings_message,
            )
            await interaction.response.edit_message(view=refreshed_view)
            if self.settings_message is not None and self.settings_message.id != interaction.message.id:
                try:
                    await self.settings_message.edit(view=refreshed_view)
                except (discord.NotFound, discord.HTTPException):
                    pass

        self.ads_button.callback = ads_callback

                                 
        try:
            _settings = load_user_settings()
            _entry = get_user_settings_entry(_settings, str(self.user_id))
            _tz_val = _entry.get("timezone_offset")
        except Exception:
            _tz_val = None

        tz_label = "Set"
        self.timezone_button = discord.ui.Button(
            label=tz_label,
            style=discord.ButtonStyle.secondary,
            custom_id="user_settings_timezone",
        )

        async def timezone_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            current = user_settings.get("timezone_offset")
            modal = TimezoneModal(str(interaction.user.id), current, settings_message=self.settings_message)
            try:
                await interaction.response.send_modal(modal)
            except Exception:
                try:
                    await interaction.followup.send("<:disapprove:1517452151012589662> Could not open modal.", ephemeral=True)
                except Exception:
                    pass

        self.timezone_button.callback = timezone_callback

        self.color_select = discord.ui.Select(
            placeholder="Select your profile color",
            options=[
                discord.SelectOption(label="Random", value="random", default=(self.current_color == "random"), description="Use a random color each time")
                if color == "random"
                else discord.SelectOption(label=color.title(), value=color, default=(color == self.current_color), description=f"Use the {color} color")
                for color in USER_COLOR_OPTIONS
            ],
            custom_id="user_settings_color_select",
            min_values=1,
            max_values=1,
        )

        async def color_select_callback(interaction: discord.Interaction):
            settings = load_user_settings()
            user_settings = get_user_settings_entry(settings, str(interaction.user.id))
            selected_color = self.color_select.values[0]
            user_settings["color"] = selected_color
            save_user_settings(settings)
            self.current_color = selected_color

            refreshed_view = UserSettingsView(
                self.user_id,
                selected_color,
                self.current_pings,
                self.current_style,
                settings_message=self.settings_message,
            )
            await interaction.response.edit_message(view=refreshed_view)
            if self.settings_message is not None and self.settings_message.id != interaction.message.id:
                try:
                    await self.settings_message.edit(view=refreshed_view)
                except (discord.NotFound, discord.HTTPException):
                    pass

        self.color_select.callback = color_select_callback

                                                                             
        self.banner_style_select = discord.ui.Select(
            placeholder="Banner styles managed centrally",
            options=[
                discord.SelectOption(label="Random", value="random", default=(str(self.current_style).lower() == "random"), description="Choose a random banner style each time"),
            ],
            custom_id="user_settings_banner_style_select",
            min_values=1,
            max_values=1,
        )

        async def banner_style_select_callback(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
                await interaction.followup.send("Banner styles are now managed centrally via banners.json and cannot be set here.", ephemeral=True)
            except Exception:
                pass

        self.banner_style_select.callback = banner_style_select_callback

        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="user_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.back_button.callback = back_callback

                                                                
        banner_open_button = Button(label="Open", style=discord.ButtonStyle.secondary, custom_id="user_settings_banners_open")
        async def banner_open_cb(interaction: discord.Interaction):
            try:
                await interaction.response.edit_message(view=UserBannersView(str(interaction.user.id), settings_message=self.settings_message))
            except Exception:
                try:
                    await interaction.followup.send("Could not open banners panel.", ephemeral=True)
                except Exception:
                    pass
        banner_open_button.callback = banner_open_cb

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **User settings**"),
            TextDisplay("Adjust your personal preferences below."),
            Separator(),
            Section("<:image:1517497571470348539> User banners", accessory=banner_open_button),
            TextDisplay(f"<:rainbow:1518708398772846722> User color: {COLOR_EMOJIS.get(self.current_color, self.current_color)} {self.current_color if isinstance(self.current_color, str) else ''}"),

            Section(f"<:timer:1517996239583576194> Timezone: {('UTC'+_tz_val) if _tz_val else 'UTC (not set)'}", accessory=self.timezone_button),
            Section(f"<:bell:1517497562184024275> Ping notifications: {'Enabled' if self.current_pings else 'Disabled'}", accessory=self.ping_button),
            Section(f"<:mail:1529115056866984061> Partnerships messages: {'Disabled' if get_user_settings_entry(load_user_settings(), str(self.user_id)).get('disable_ads') else 'Enabled'}", accessory=self.ads_button),
                                 
            accent_color=get_user_color_value(str(self.user_id)),
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.color_select))
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class TimezoneModal(Modal):
    def __init__(self, user_id: str, current_offset: str | None, settings_message: discord.Message | None = None):
        super().__init__(title="Set timezone offset")
        self.user_id = user_id
        self.settings_message = settings_message
        default = current_offset or "+00:00"
        self.offset_input = TextInput(label="UTC offset (e.g. +02:00, -1:00, +12:30)", placeholder="+02:00", required=False, default=default, max_length=6)
        self.add_item(self.offset_input)

    async def on_submit(self, interaction: discord.Interaction):
        val = (self.offset_input.value or "").strip()
        settings = load_user_settings()
        entry = get_user_settings_entry(settings, str(self.user_id))
        if not val:
                                    
            if entry.get("timezone_offset"):
                entry.pop("timezone_offset", None)
                save_user_settings(settings)
        else:
            offs = parse_utc_offset(val)
            if offs is None:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Invalid timezone format. Use +02:00 or -1:00.", ephemeral=True)
                return
            sign = "-" if offs.total_seconds() < 0 else "+"
            total_minutes = int(abs(int(offs.total_seconds())) // 60)
            hh = total_minutes // 60
            mm = total_minutes % 60
            normalized = f"{sign}{hh:02d}:{mm:02d}"
            entry["timezone_offset"] = normalized
            save_user_settings(settings)

        refreshed = UserSettingsView(int(self.user_id), get_user_color(str(self.user_id)), get_user_pings_enabled(str(self.user_id)), get_user_banner_style(str(self.user_id)), settings_message=self.settings_message)
        try:
            await interaction.response.edit_message(view=refreshed)
        except Exception:
            try:
                if self.settings_message is not None:
                    await self.settings_message.edit(view=refreshed)
            except Exception:
                pass
        try:
            await safe_send(interaction, "<:approve:1517452125687513158> Timezone updated.", ephemeral=True)
        except Exception:
            pass

class BannerSearchModal(Modal):
    def __init__(self, user_id: str, settings_message: discord.Message | None = None):
        super().__init__(title="Search banners")
        self.user_id = user_id
        self.settings_message = settings_message
        self.query = TextInput(label="Banner name or category", placeholder="Try: forest or category:vanilla", required=True, max_length=100)
        self.add_item(self.query)

    async def on_submit(self, interaction: discord.Interaction):
        q = (self.query.value or "").strip()
        defs = load_banner_definitions()
        matches = get_banner_search_matches(defs, q)
        if not matches:
            try:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No banners matched that name or category.", ephemeral=True)
            except Exception:
                pass
            return
                                                                             
        options = matches[:6]
        if len(options) == 1:
            chosen = options[0]
            try:
                member = interaction.user
                file = await create_banner_preview(member, kind="welcome", style_override=chosen)
                if file is None:
                    try:
                        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Could not generate preview for this banner.", ephemeral=True)
                    except Exception:
                        pass
                    return
                preview_view = BannerPreviewView(str(self.user_id), chosen, settings_message=self.settings_message)
                try:
                    await interaction.response.send_message(file=file, view=preview_view, ephemeral=True)
                except Exception:
                    try:
                        await interaction.followup.send("Could not open preview.", ephemeral=True)
                    except Exception:
                        pass
            except Exception:
                try:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("Could not open preview.", ephemeral=True)
                except Exception:
                    pass
            return

                                                            
        view = TimeoutDisabledView()
        for name in options:
            btn = Button(label=name.replace('_',' '), style=discord.ButtonStyle.primary)
            async def sel_cb(inter, chosen=name):
                try:
                    member = inter.user
                    file = await create_banner_preview(member, kind="welcome", style_override=chosen)
                    if file is None:
                        try:
                            await inter.response.defer(ephemeral=True); await inter.followup.send("Could not generate preview for this banner.", ephemeral=True)
                        except Exception:
                            pass
                        return
                    preview_view = BannerPreviewView(str(self.user_id), chosen, settings_message=self.settings_message)
                    try:
                        await inter.response.send_message(file=file, view=preview_view, ephemeral=True)
                    except Exception:
                        try:
                            await inter.followup.send("Could not open preview.", ephemeral=True)
                        except Exception:
                            pass
                except Exception:
                    try:
                        await inter.response.defer(ephemeral=True); await inter.followup.send("Could not open preview.", ephemeral=True)
                    except Exception:
                        pass
            btn.callback = sel_cb
            view.add_item(btn)
        try:
            await interaction.response.send_message("Multiple matches — pick one:", view=view, ephemeral=True)
        except Exception:
            try:
                await interaction.followup.send("Could not present matches.", ephemeral=True)
            except Exception:
                pass


class UserBannersView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: str, page: int = 0, settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.page = page
        self.settings_message = settings_message
        self.per_page = 6
        self.build_components()

    def build_components(self):
        self.clear_items()
        defs = load_banner_definitions()
        keys = list(defs.keys())
        total_pages = max(1, (len(keys) + self.per_page - 1) // self.per_page)
        start = self.page * self.per_page
        page_items = keys[start:start + self.per_page]

        parts = [
            TextDisplay("## <:image:1517497571470348539> User banners"),
            TextDisplay("Scroll available banners and pick one. Search by name or category."),
            Separator(),
            TextDisplay(f"Page {self.page+1}/{total_pages}"),
        ]

        for name in page_items:
            label = name.replace('_', ' ')
            desc = defs.get(name, {}).get('label') or defs.get(name, {}).get('desc') or ''
            preview_button = Button(label="Preview", style=discord.ButtonStyle.primary, custom_id=f"banner_preview:{name}")

            async def preview_cb(interaction: discord.Interaction, chosen=name):
                try:
                    member = interaction.user
                    file = await create_banner_preview(member, kind="welcome", style_override=chosen)
                    if file is None:
                        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Could not generate preview for this banner.", ephemeral=True)
                        return
                    preview_view = BannerPreviewView(str(self.user_id), chosen, settings_message=self.settings_message)
                    await interaction.response.send_message(file=file, view=preview_view, ephemeral=True)
                except Exception:
                    try:
                        await interaction.response.defer(ephemeral=True); await interaction.followup.send("Could not open preview.", ephemeral=True)
                    except Exception:
                        pass

            preview_button.callback = preview_cb
            parts.append(Section(f"**{label}**\n{desc}", accessory=preview_button))

        parts.append(Separator())
        container = Container(*parts, accent_color=discord.Color.blue())
        self.add_item(container)

        prev_button = Button(label="Previous", style=discord.ButtonStyle.secondary, custom_id="banners_prev", disabled=self.page == 0)
        next_button = Button(label="Next", style=discord.ButtonStyle.secondary, custom_id="banners_next", disabled=self.page >= total_pages - 1)
        search_button = Button(label="Search", style=discord.ButtonStyle.primary, custom_id="banners_search")
        cancel_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="banners_cancel")

        async def prev_cb(interaction: discord.Interaction):
            if self.page > 0:
                self.page -= 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        async def next_cb(interaction: discord.Interaction):
            if self.page < total_pages - 1:
                self.page += 1
                self.build_components()
                await interaction.response.edit_message(view=self)

        prev_button.callback = prev_cb
        next_button.callback = next_cb
        async def search_cb(interaction: discord.Interaction):
            try:
                await interaction.response.send_modal(BannerSearchModal(str(interaction.user.id), settings_message=self.settings_message))
            except Exception:
                try:
                    await interaction.followup.send("Could not open search.", ephemeral=True)
                except Exception:
                    pass

        async def cancel_cb(interaction: discord.Interaction):
            try:
                refreshed = UserSettingsView(int(self.user_id), get_user_color(str(self.user_id)), get_user_pings_enabled(str(self.user_id)), get_user_banner_style(str(self.user_id)), settings_message=self.settings_message)
                await interaction.response.edit_message(view=refreshed)
            except Exception:
                try:
                    await interaction.followup.send("Could not return to settings.", ephemeral=True)
                except Exception:
                    pass

        search_button.callback = search_cb
        cancel_button.callback = cancel_cb
        self.add_item(discord.ui.ActionRow(prev_button, next_button, search_button, cancel_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != int(self.user_id):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This panel is only for the original user.", ephemeral=True)
            return False
        return True


class BannerPreviewView(TimeoutDisabledView):
    def __init__(self, user_id: str, style_name: str, settings_message: discord.Message | None = None):
        super().__init__(timeout=300)
        self.user_id = user_id
        self.style_name = style_name
        self.settings_message = settings_message
        self.confirm_button = Button(label="Select this banner", style=discord.ButtonStyle.success)
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary)

        async def confirm_cb(interaction: discord.Interaction):
            try:
                settings = load_user_settings()
                entry = get_user_settings_entry(settings, str(self.user_id))
                entry['banner_style'] = self.style_name
                save_user_settings(settings)
                refreshed = UserSettingsView(int(self.user_id), get_user_color(str(self.user_id)), get_user_pings_enabled(str(self.user_id)), get_user_banner_style(str(self.user_id)), settings_message=self.settings_message)
                try:
                    await interaction.response.edit_message(content=f"<:approve:1517452125687513158> Banner set to **{self.style_name.replace('_',' ')}**.", view=None)
                except Exception:
                    try:
                        await interaction.followup.send(f"<:approve:1517452125687513158> Banner set to **{self.style_name.replace('_',' ')}**.", ephemeral=True)
                    except Exception:
                        pass
                                                           
                try:
                    if self.settings_message is not None:
                        await self.settings_message.edit(view=refreshed)
                except Exception:
                    pass
            except Exception:
                try:
                    await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Could not set banner.", ephemeral=True)
                except Exception:
                    pass

        async def cancel_cb(interaction: discord.Interaction):
            try:
                await interaction.response.edit_message(content="Canceled.", view=None)
            except Exception:
                try:
                    await interaction.followup.send("Canceled.", ephemeral=True)
                except Exception:
                    pass

        self.confirm_button.callback = confirm_cb
        self.cancel_button.callback = cancel_cb
        self.add_item(self.confirm_button)
                                                                                                  
        self.touch_button = Button(label="Fix mobile preview", style=discord.ButtonStyle.secondary)
        async def touch_cb(interaction: discord.Interaction):
            try:
                await interaction.response.defer(ephemeral=True)
            except Exception:
                try:
                    await interaction.followup.send("", ephemeral=True)
                except Exception:
                    pass

        self.touch_button.callback = touch_cb
        self.add_item(self.touch_button)
        self.add_item(self.cancel_button)


class GuildSettingsMenuView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.color = get_user_color_value(str(user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.general_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_general_{self.user_id}",
        )
        self.channel_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_channel_{self.user_id}",
        )
        self.economy_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_economy_{self.user_id}",
        )
        self.level_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_level_{self.user_id}",
        )
        self.automod_button = Button(
            label="Open",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_settings_menu_automod_{self.user_id}",
        )

        async def open_general(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use guild settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            guild_config, _ = get_guild_config(self.guild_id)
            new_view = GuildSettingsView(
                interaction.user.id,
                self.guild_id,
                ghost_pings=guild_config.get("ghost_ping_enabled", False),
                history_enabled=guild_config.get("edit_delete_history_enabled", True),
                economy_enabled=guild_config.get("economy_enabled", True),
                levels_enabled=guild_config.get("levels_enabled", True),
                level_up_enabled=guild_config.get("level_up_message_enabled", False),
                join_dm_enabled=guild_config.get("join_dm_enabled", False),
                join_dm_message=guild_config.get("join_dm_message"),
                join_role_ids=guild_config.get("join_role_ids", []),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_channel_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use channel settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_channels:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Channels permission.",
                    ephemeral=True,
                )
                return

            new_view = ChannelSettingsView(
                interaction.user.id,
                self.guild_id,
                get_user_color_value(str(interaction.user.id)),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_economy_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use economy settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            from cogs.economy import EconomySettingsView
            new_view = EconomySettingsView(
                interaction.user.id,
                self.guild_id,
                get_user_color_value(str(interaction.user.id)),
            )
            await interaction.response.edit_message(view=new_view)

        async def open_level_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use level settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            from cogs.levels import LevelSettingsView
            new_view = LevelSettingsView(
                interaction.user.id,
                self.guild_id,
                get_user_color_value(str(interaction.user.id)),
                settings_message=interaction.message,
            )
            await interaction.response.edit_message(view=new_view)

        async def open_automod_settings(interaction: discord.Interaction):
            if not interaction.guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use automod settings from a user install.",
                    ephemeral=True,
                )
                return

            member = interaction.user if isinstance(interaction.user, discord.Member) else interaction.guild.get_member(interaction.user.id)
            if not member or not member.guild_permissions.manage_guild:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    "<:disapprove:1517452151012589662> You can't use this because you need the Manage Server permission.",
                    ephemeral=True,
                )
                return

            from cogs.moderation import AutomodSettingsView

            new_view = AutomodSettingsView(
                interaction.user.id,
                self.guild_id,
                get_user_color_value(str(interaction.user.id)),
            )
            await interaction.response.edit_message(view=new_view)

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=SettingsMenuView(interaction.user.id, interaction.user.display_name, get_user_color_value(str(interaction.user.id))))

        self.general_button.callback = open_general
        self.channel_button.callback = open_channel_settings
        self.economy_button.callback = open_economy_settings
        self.level_button.callback = open_level_settings
        self.automod_button.callback = open_automod_settings

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id=f"guild_settings_menu_back_{self.user_id}")
        self.back_button.callback = back_callback

        container = Container(
            TextDisplay("<:gear:1517576939097952496> **Guild settings**"),
            TextDisplay("Choose which guild section to configure."),
            Separator(),
            Section("<:edit:1517497568421085256> General settings", accessory=self.general_button),
            Section("<:list:1517497572770451567> Channel settings", accessory=self.channel_button),
            Section("<:money:1517580310395486239> Economy settings", accessory=self.economy_button),
            Section("<:chalice:1517579767573123092> Level settings", accessory=self.level_button),
            Section("<:warning:1517452174991556758> Automod settings", accessory=self.automod_button),
            accent_color=self.color,
        )
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class GuildSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, ghost_pings: bool, history_enabled: bool, economy_enabled: bool = True, levels_enabled: bool = True, level_up_enabled: bool = False, join_dm_enabled: bool = False, join_dm_message: str | None = None, join_role_ids: list[int] | None = None, page: int = 1):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.ghost_pings = ghost_pings
        self.history_enabled = history_enabled
        self.economy_enabled = economy_enabled
        self.levels_enabled = levels_enabled
        self.level_up_enabled = level_up_enabled
        self.join_dm_enabled = join_dm_enabled
        self.join_dm_message = join_dm_message or ""
        self.join_role_ids = list(join_role_ids or [])
        self.page = max(1, min(int(page), 2))
        self.color = get_user_color_value(str(user_id))
        self.build_components()

    def build_components(self):
        self.clear_items()
        self.ghost_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_ghost_pings",
        )
        self.history_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_history",
        )
        self.economy_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_economy",
        )
        self.levels_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_levels",
        )
        self.level_button = discord.ui.Button(
            label="Toggle",
            style=discord.ButtonStyle.primary,
            custom_id="guild_level_up",
        )

        async def ghost_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.ghost_pings = not self.ghost_pings
            guild_config["ghost_ping_enabled"] = self.ghost_pings
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        async def history_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.history_enabled = not self.history_enabled
            guild_config["edit_delete_history_enabled"] = self.history_enabled
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        async def economy_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.economy_enabled = not self.economy_enabled
            guild_config["economy_enabled"] = self.economy_enabled
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        async def level_system_callback(interaction: discord.Interaction):
            guild_config, data = get_guild_config(self.guild_id)
            self.levels_enabled = not self.levels_enabled
            guild_config["levels_enabled"] = self.levels_enabled
            save_guild_data(data)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        async def level_callback(interaction: discord.Interaction):
            guild_config, guild_data = get_guild_config(self.guild_id)
            levels = load_levels()
            if self.guild_id not in levels:
                levels[self.guild_id] = {"config": {}, "users": {}}
            config = levels[self.guild_id].get("config", {})

            self.level_up_enabled = not self.level_up_enabled
            guild_config["level_up_message_enabled"] = self.level_up_enabled
            save_guild_data(guild_data)

            config["level_up_message_enabled"] = self.level_up_enabled
            levels[self.guild_id]["config"] = config
            save_levels(levels)
            await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page))

        self.ghost_button.callback = ghost_callback
        self.history_button.callback = history_callback
        self.economy_button.callback = economy_callback
        self.levels_button.callback = level_system_callback
        self.level_button.callback = level_callback

        self.back_button = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="guild_settings_back")

        async def back_callback(interaction: discord.Interaction):
            await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

        self.back_button.callback = back_callback

        fun_data = load_fun_data()
        auto_reply_triggers = sorted(fun_data.get(self.guild_id, {}).keys()) if self.guild_id in fun_data else []
        auto_reply_text = _shorten("\n".join(auto_reply_triggers), 1200) if auto_reply_triggers else "None"
        join_dm_preview = _shorten(self.join_dm_message.strip(), 800) if self.join_dm_message else "No message set"
        join_role_names = []
        guild = runtime.bot.get_guild(int(self.guild_id)) if self.guild_id.isdigit() else None
        if guild is not None:
            for role_id in self.join_role_ids:
                try:
                    role = guild.get_role(int(role_id))
                except (TypeError, ValueError):
                    continue
                if role is not None:
                    join_role_names.append(role.name)
        join_role_preview = ", ".join(join_role_names[:6]) if join_role_names else "None"
        if len(join_role_names) > 6:
            join_role_preview += "..."

        if self.page == 1:
            self.join_dm_edit_button = None
            self.auto_reply_button = None
            self.join_roles_button = None
            page_button = discord.ui.Button(label="Page 2", style=discord.ButtonStyle.secondary, custom_id="guild_settings_next")
            page_button.callback = self.open_page_two
            container_items = [
                TextDisplay("<:gear:1517576939097952496> **General settings**"),
                TextDisplay("Page 1/2 - Adjust the main toggles below."),
                Separator(),
                Section(f"<:ghost:1517497569939558470> Ghost pings: {'Enabled' if self.ghost_pings else 'Disabled'}", accessory=self.ghost_button),
                Section(f"<:trash:1517497581058527404> Edit/Delete history: {'Enabled' if self.history_enabled else 'Disabled'}", accessory=self.history_button),
                Section(f"<:money:1517580310395486239> Economy: {'Enabled' if self.economy_enabled else 'Disabled'}", accessory=self.economy_button),
                Section(f"<:chalice:1517579767573123092> Levels: {'Enabled' if self.levels_enabled else 'Disabled'}", accessory=self.levels_button),
                Section(f"<:spark:1517583248421552305> Level-up and Quest in channel messages: {'Enabled' if self.level_up_enabled else 'Disabled'}", accessory=self.level_button),
            ]
        else:
            self.join_dm_edit_button = discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id="guild_join_dm_edit",
            )
            self.auto_reply_button = discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id="guild_auto_reply",
            )
            self.join_roles_button = discord.ui.Button(
                label="Edit",
                style=discord.ButtonStyle.primary,
                custom_id="guild_join_roles_edit",
            )
            self.join_dm_edit_button.callback = self.handle_join_dm_edit
            self.auto_reply_button.callback = self.handle_auto_reply_edit
            self.join_roles_button.callback = self.handle_join_roles_edit
            page_button = discord.ui.Button(label="Page 1", style=discord.ButtonStyle.secondary, custom_id="guild_settings_prev")
            page_button.callback = self.open_page_one
            container_items = [
                TextDisplay("<:gear:1517576939097952496> **General settings**"),
                TextDisplay("Page 2/2 - Manage join DM and auto-reply settings below."),
                Separator(),
                Section(f"<:mail:1529115056866984061> Join DM: {'Enabled' if self.join_dm_enabled else 'Disabled'}\n{join_dm_preview}", accessory=self.join_dm_edit_button),
                Section(f"<:spark:1517583248421552305> Auto-reply triggers\n{auto_reply_text}", accessory=self.auto_reply_button),
                Section(f"<:bell:1517497562184024275> Join roles\n{join_role_preview}", accessory=self.join_roles_button),
            ]

        container = Container(*container_items, accent_color=self.color)
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(page_button, self.back_button))

    async def open_page_two(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=2))

    async def open_page_one(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=1))

    async def handle_join_dm_edit(self, interaction: discord.Interaction):
        guild_config, _ = get_guild_config(self.guild_id)
        await interaction.response.send_modal(
            JoinDMModal(
                self.save_join_dm_message,
                self.guild_id,
                guild_config.get("join_dm_enabled", False),
                guild_config.get("join_dm_message"),
                interaction.message,
            )
        )

    async def save_join_dm_message(self, interaction: discord.Interaction, enabled: bool, message: str, settings_message: discord.Message | None = None):
        guild_config, data = get_guild_config(self.guild_id)
        self.join_dm_enabled = enabled
        guild_config["join_dm_enabled"] = enabled
        guild_config["join_dm_message"] = message if message not in (None, "") else None
        save_guild_data(data)
        self.join_dm_message = guild_config["join_dm_message"] or ""
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:approve:1517452125687513158> Join DM settings saved.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
            settings_message,
        )

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass

        try:
            channel = runtime.bot.get_channel(settings_message.channel.id)
            if channel is not None:
                settings_message = await channel.fetch_message(settings_message.id)
                await settings_message.edit(view=view)
                return
        except Exception:
            pass

        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass

        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    async def handle_auto_reply_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message or await interaction.original_response()
        if settings_message is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Unable to determine the settings message.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Auto-reply triggers?",
            view=AutoReplyChoiceView(
                self.user_id,
                self.open_auto_reply_add,
                self.open_auto_reply_remove,
                settings_message,
            ),
            ephemeral=True,
        )

    async def handle_join_roles_edit(self, interaction: discord.Interaction):
        settings_message = interaction.message or await interaction.original_response()
        if settings_message is None:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Unable to determine the settings message.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Join roles?",
            view=JoinRoleChoiceView(
                self.user_id,
                self.open_join_role_add,
                self.open_join_role_remove,
                settings_message,
            ),
            ephemeral=True,
        )

    async def open_auto_reply_add(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        await interaction.response.send_modal(AutoReplyAddModal(self.add_auto_reply, self.guild_id, settings_message))

    async def open_auto_reply_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        await interaction.response.send_modal(AutoReplyRemoveModal(self.remove_auto_reply, self.guild_id, settings_message))

    async def open_join_role_add(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        if not interaction.guild:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action needs a guild context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select a role to add as a join role.",
            view=JoinRoleSelectionView(self.user_id, interaction.guild, "Choose a role to add", self.add_join_role, settings_message),
            ephemeral=True,
        )

    async def open_join_role_remove(self, interaction: discord.Interaction, settings_message: discord.Message | None):
        if not interaction.guild:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This action needs a guild context.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select a role to remove from the join roles.",
            view=JoinRoleSelectionView(self.user_id, interaction.guild, "Choose a role to remove", self.remove_join_role, settings_message),
            ephemeral=True,
        )

    async def add_join_role(self, interaction: discord.Interaction, role_id: int, settings_message: discord.Message | None):
        role = interaction.guild.get_role(role_id) if interaction.guild else None
        role_error = validate_role_selection(interaction, role, "join role") if role else None
        if role is not None and role.managed:
            role_error = "<:disapprove:1517452151012589662> That role is managed by an integration and can't be given to members."
        if role_error:
            await interaction.followup.send(role_error, ephemeral=True)
            return
        guild_config, data = get_guild_config(self.guild_id)
        existing_role_ids = list(guild_config.get("join_role_ids", []))
        if role_id not in existing_role_ids:
            existing_role_ids.append(role_id)
            guild_config["join_role_ids"] = existing_role_ids
            save_guild_data(data)
            self.join_role_ids = existing_role_ids
            await interaction.followup.send("<:approve:1517452125687513158> Join role added.", ephemeral=True)
        else:
            await interaction.followup.send("<:disapprove:1517452151012589662> That role is already configured as a join role.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
            settings_message,
        )

    async def remove_join_role(self, interaction: discord.Interaction, role_id: int, settings_message: discord.Message | None):
        guild_config, data = get_guild_config(self.guild_id)
        existing_role_ids = list(guild_config.get("join_role_ids", []))
        updated_role_ids = [existing_id for existing_id in existing_role_ids if existing_id != role_id]
        if updated_role_ids != existing_role_ids:
            guild_config["join_role_ids"] = updated_role_ids
            save_guild_data(data)
            self.join_role_ids = updated_role_ids
            await interaction.followup.send("<:trash:1517497581058527404> Join role removed.", ephemeral=True)
        else:
            await interaction.followup.send("<:disapprove:1517452151012589662> That role was not configured as a join role.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
            settings_message,
        )

    async def add_auto_reply(self, interaction: discord.Interaction, word: str, replies: list[str], settings_message: discord.Message | None):
        fun_data = load_fun_data()
        if self.guild_id not in fun_data:
            fun_data[self.guild_id] = {}
        fun_data[self.guild_id][word.lower()] = replies
        save_fun_data(fun_data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Auto reply for '{word}' saved.", ephemeral=True)

        await self.refresh_settings_message(
            interaction,
            GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
            settings_message,
        )

    async def remove_auto_reply(self, interaction: discord.Interaction, word: str, settings_message: discord.Message | None):
        fun_data = load_fun_data()
        if self.guild_id in fun_data and word.lower() in fun_data[self.guild_id]:
            del fun_data[self.guild_id][word.lower()]
            if not fun_data[self.guild_id]:
                del fun_data[self.guild_id]
            save_fun_data(fun_data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Auto reply for '{word}' removed.", ephemeral=True)

            await self.refresh_settings_message(
                interaction,
                GuildSettingsView(self.user_id, self.guild_id, self.ghost_pings, self.history_enabled, self.economy_enabled, self.levels_enabled, self.level_up_enabled, join_dm_enabled=self.join_dm_enabled, join_dm_message=self.join_dm_message, join_role_ids=self.join_role_ids, page=self.page),
                settings_message,
            )
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:disapprove:1517452151012589662> No auto reply found for '{word}'.", ephemeral=True)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True


class JoinDMModal(Modal):
    def __init__(self, callback, guild_id: str, current_enabled: bool, current_message: str | None, settings_message: discord.Message | None):
        super().__init__(title="Join DM settings")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.enabled_input = TextInput(
            label="Enabled (enable/disable)",
            placeholder="Type enable or disable",
            required=True,
            max_length=10,
            default="enable" if current_enabled else "disable",
        )
        self.message_input = TextInput(
            label="Join DM message",
            placeholder="Use {user} for the member mention or {guild} for the server name.\nYou can add new lines here.",
            required=False,
            max_length=2000,
            default=(current_message or "")[:2000],
            style=discord.TextStyle.long,
        )
        self.add_item(self.enabled_input)
        self.add_item(self.message_input)

    async def on_submit(self, interaction: discord.Interaction):
        enabled_value = self.enabled_input.value.strip().lower()
        if enabled_value in {"enable", "enabled", "on", "true", "yes", "1"}:
            enabled = True
        elif enabled_value in {"disable", "disabled", "off", "false", "no", "0"}:
            enabled = False
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Please enter either enable or disable for the state.", ephemeral=True)
            return
        await self.callback(interaction, enabled, self.message_input.value, self.settings_message)


class ConfirmRemoveView(TimeoutDisabledView):
    def __init__(self, user_id: int, confirm_callback, original_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.confirm_callback = confirm_callback
        self.original_message = original_message
        self.confirm_button = Button(label="Confirm", style=discord.ButtonStyle.danger, custom_id="confirm_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="cancel_remove")
        self.confirm_button.callback = self.on_confirm
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.confirm_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This confirmation is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_confirm(self, interaction: discord.Interaction):
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.confirm_callback(interaction, self.original_message)

    async def on_cancel(self, interaction: discord.Interaction):
        self.confirm_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class ChannelSelectorView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild: discord.Guild, placeholder: str, callback, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.callback = callback
        self.settings_message = settings_message
        self.channel_select = ChannelSelect(placeholder=placeholder, custom_id="channel_selector", min_values=1, max_values=1)
        self.channel_select.callback = self.on_channel_selected
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="channel_select_cancel")
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.channel_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_channel_selected(self, interaction: discord.Interaction):
        if not self.channel_select.values:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No channel was selected.", ephemeral=True)
            return

        channel = self.channel_select.values[0]
        self.channel_select.disabled = True
        self.cancel_button.disabled = True
        await self.callback(interaction, channel, self.settings_message)
        try:
            await interaction.message.edit(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass

    async def on_cancel(self, interaction: discord.Interaction):
        self.channel_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(content="Channel selection cancelled.", view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class YesNoView(TimeoutDisabledView):
    def __init__(self, user_id: int, yes_callback, no_callback):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.yes_callback = yes_callback
        self.no_callback = no_callback
        self.yes_button = Button(label="Yes", style=discord.ButtonStyle.success, custom_id="yes_option")
        self.no_button = Button(label="No", style=discord.ButtonStyle.danger, custom_id="no_option")
        self.yes_button.callback = self.on_yes
        self.no_button.callback = self.on_no
        self.add_item(self.yes_button)
        self.add_item(self.no_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_yes(self, interaction: discord.Interaction):
        self.yes_button.disabled = True
        self.no_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.yes_callback(interaction)

    async def on_no(self, interaction: discord.Interaction):
        self.yes_button.disabled = True
        self.no_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.no_callback(interaction)


class BoardCountPromptView(TimeoutDisabledView):
    def __init__(self, user_id: int, channel: discord.abc.GuildChannel, emoji: str, settings_message: discord.Message, callback):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.channel = channel
        self.emoji = emoji
        self.settings_message = settings_message
        self.callback = callback
        self.count_button = Button(label="Set required count", style=discord.ButtonStyle.primary, custom_id="board_set_count")
        self.count_button.callback = self.on_set_count
        self.add_item(self.count_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_set_count(self, interaction: discord.Interaction):
        await interaction.response.send_modal(BoardCountModal(self.callback, self.channel, self.emoji, self.settings_message))


class BoardCountModal(Modal):
    def __init__(self, callback, channel: discord.abc.GuildChannel, emoji: str, settings_message: discord.Message):
        super().__init__(title="Board required count")
        self.callback = callback
        self.channel = channel
        self.emoji = emoji
        self.settings_message = settings_message
        self.count_input = TextInput(label="Required count", placeholder="How many reactions are required?", required=True, max_length=10)
        self.add_item(self.count_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            required_count = int(self.count_input.value)
        except ValueError:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Required count must be a number.", ephemeral=True)
            return
        if required_count < 1:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Required count must be at least 1.", ephemeral=True)
            return
        await self.callback(interaction, self.channel, self.emoji, required_count, self.settings_message)


class AutoReplyAddModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Add auto reply")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.word_input = TextInput(label="Trigger word", placeholder="Enter the trigger word", required=True, max_length=100)
        self.reply1 = TextInput(label="Reply 1", placeholder="First reply", required=True, max_length=200)
        self.reply2 = TextInput(label="Reply 2", placeholder="Second reply (optional)", required=False, max_length=200)
        self.reply3 = TextInput(label="Reply 3", placeholder="Third reply (optional)", required=False, max_length=200)
        self.reply4 = TextInput(label="Reply 4", placeholder="Fourth reply (optional)", required=False, max_length=200)
        self.add_item(self.word_input)
        self.add_item(self.reply1)
        self.add_item(self.reply2)
        self.add_item(self.reply3)
        self.add_item(self.reply4)

    async def on_submit(self, interaction: discord.Interaction):
        replies = [value for value in [self.reply1.value, self.reply2.value, self.reply3.value, self.reply4.value] if value]
        await self.callback(
            interaction,
            self.word_input.value.strip(),
            replies,
            self.settings_message,
        )


class AutoReplyRemoveModal(Modal):
    def __init__(self, callback, guild_id: str, settings_message: discord.Message | None):
        super().__init__(title="Remove auto reply")
        self.callback = callback
        self.guild_id = guild_id
        self.settings_message = settings_message
        self.word_input = TextInput(label="Trigger word to remove", placeholder="Enter the exact trigger word", required=True, max_length=100)
        self.add_item(self.word_input)

    async def on_submit(self, interaction: discord.Interaction):
        await self.callback(
            interaction,
            self.word_input.value.strip(),
            self.settings_message,
        )


class AutoReplyChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="auto_reply_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="auto_reply_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="auto_reply_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class JoinRoleChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, on_add, on_remove, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="join_role_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="join_role_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="join_role_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class JoinRoleSelectionView(TimeoutDisabledView):
    def __init__(self, user_id: int, guild: discord.Guild, prompt: str, callback, settings_message: discord.Message | None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild = guild
        self.callback = callback
        self.settings_message = settings_message
        self.role_select = RoleSelect(
            placeholder=prompt,
            min_values=1,
            max_values=1,
            custom_id="join_role_select",
        )
        self.role_select.callback = self.on_role_selected
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="join_role_select_cancel")
        self.cancel_button.callback = self.on_cancel
        self.add_item(self.role_select)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def on_role_selected(self, interaction: discord.Interaction):
        if not self.role_select.values:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No role was selected.", ephemeral=True)
            return
        role_id = self.role_select.values[0].id
        self.role_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(view=self)
        except (discord.NotFound, discord.HTTPException):
            pass
        await self.callback(interaction, role_id, self.settings_message)

    async def on_cancel(self, interaction: discord.Interaction):
        self.role_select.disabled = True
        self.cancel_button.disabled = True
        try:
            await interaction.response.edit_message(content="Role selection cancelled.", view=self)
        except (discord.NotFound, discord.HTTPException):
            pass


class ChannelEditChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, setting_name: str, on_add, on_remove, settings_message: discord.Message):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.setting_name = setting_name
        self.on_add = on_add
        self.on_remove = on_remove
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id="channel_edit_add")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id="channel_edit_remove")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="channel_edit_cancel")
        self.add_button.callback = self.add_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)




class HoneypotSanctionModal(Modal):
    def __init__(self, callback, channel: discord.abc.GuildChannel, settings_message: discord.Message | None):
        super().__init__(title="Set honeypot sanction")
        self.callback = callback
        self.channel = channel
        self.settings_message = settings_message
        self.action_input = TextInput(label="Action (timeout/kick/ban)", placeholder="timeout", required=True, max_length=20)
        self.duration_input = TextInput(label="Timeout duration (1d, 10s, 50m)", placeholder="1d", required=False, max_length=20)
        self.add_item(self.action_input)
        self.add_item(self.duration_input)

    async def on_submit(self, interaction: discord.Interaction):
        action = self.action_input.value.strip().lower()
        if action not in {"timeout", "kick", "ban"}:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Action must be timeout, kick, or ban.", ephemeral=True)
            return

        duration_text = self.duration_input.value.strip() if self.duration_input.value else ""
        duration_seconds = None
        if action == "timeout":
            if not duration_text:
                duration_text = "1d"
            duration_seconds = parse_duration_to_seconds(duration_text)
            if duration_seconds is None or duration_seconds <= 0:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Timeout duration must be a valid value like 1d, 10s, or 50m.", ephemeral=True)
                return
        else:
            duration_seconds = 0
            if duration_text:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Duration is only valid for timeout actions.", ephemeral=True)
                return

        await self.callback(interaction, self.channel, action, duration_seconds, duration_text, self.settings_message)


class ChannelSettingsView(TimeoutDisabledLayoutView):
    def __init__(self, user_id: int, guild_id: str, color: discord.Color, page: int = 1):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.guild_id = guild_id
        self.page = page
        self.color = color
        self.build_components()

    def build_components(self):
        self.clear_items()
        guild = runtime.bot.get_guild(int(self.guild_id))
        guild_config, _ = get_guild_config(self.guild_id)
        welcome_channel = format_channel_reference(guild, guild_config.get("welcome_channel_id")) if guild else "None"
        goodbye_channel = format_channel_reference(guild, guild_config.get("goodbye_channel_id")) if guild else "None"
        level_channel = "None"
        level_id = get_level_channel_id(self.guild_id)
        if level_id:
            level_channel = format_channel_reference(guild, level_id) if guild else "None"
        admin_channels = get_admin_log_channel_mentions(guild) if guild else []
        admin_label = "Remove" if admin_channels else "Set"
        admin_value = "\n".join(admin_channels) if admin_channels else "None"

        board_entries = get_guild_board_entries(self.guild_id)
        counter_entries = get_guild_counter_entries(guild) if guild else []
        honeypot_channel = format_channel_reference(guild, guild_config.get("honeypot_channel_id")) if guild else "None"
        honeypot_sanction = guild_config.get("honeypot_sanction") or {}
        honeypot_action = str(honeypot_sanction.get("action", "timeout")).lower()
        honeypot_duration = str(honeypot_sanction.get("duration", "") or "")
        if honeypot_action == "timeout":
            honeypot_summary = f"Timeout ({honeypot_duration or '1d'})"
        else:
            honeypot_summary = honeypot_action.title() if honeypot_action in {"kick", "ban"} else "None"
        honeypot_value = f"{honeypot_channel}\nSanction: {honeypot_summary}" if guild_config.get("honeypot_channel_id") else f"{honeypot_channel}\nSanction: None"

        if self.page == 1:
            self.welcome_button = Button(label="Remove" if guild_config.get("welcome_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_welcome_toggle")
            self.goodbye_button = Button(label="Remove" if guild_config.get("goodbye_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_goodbye_toggle")
            self.level_button = Button(label="Remove" if level_id else "Set", style=discord.ButtonStyle.primary, custom_id="channel_level_toggle")
            self.admin_button = Button(label=admin_label, style=discord.ButtonStyle.primary, custom_id="channel_admin_toggle")
            self.honeypot_button = Button(label="Remove" if guild_config.get("honeypot_channel_id") else "Set", style=discord.ButtonStyle.primary, custom_id="channel_honeypot_toggle")

            self.welcome_button.callback = self.handle_welcome_toggle
            self.goodbye_button.callback = self.handle_goodbye_toggle
            self.level_button.callback = self.handle_level_toggle
            self.admin_button.callback = self.handle_admin_toggle
            self.honeypot_button.callback = self.handle_honeypot_toggle

            page_button = Button(label="Page 2", style=discord.ButtonStyle.secondary, custom_id="channel_settings_next")
            page_button.callback = self.open_page_two
        else:
            self.board_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_board_edit")
            self.counter_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_counter_edit")
            self.ticket_config_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id="channel_ticket_settings_edit")

            self.board_button.callback = self.handle_board_edit
            self.counter_button.callback = self.handle_counter_edit
            self.ticket_config_button.callback = self.handle_ticket_settings_edit

            page_button = Button(label="Page 1", style=discord.ButtonStyle.secondary, custom_id="channel_settings_prev")
            page_button.callback = self.open_page_one

        self.back_button = Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="channel_settings_back")
        self.back_button.callback = self.handle_back

        container_items = [
            TextDisplay("<:gear:1517576939097952496> **Channel settings**"),
            TextDisplay(f"Page {self.page}/2 - Set and remove channel settings below."),
            Separator(),
        ]

        if self.page == 1:
            container_items += [
                Section(f"<:plus:1518348756570079262> Welcome Channel\n{welcome_channel}", accessory=self.welcome_button),
                Section(f"<:minus:1518348754111959150> Goodbye Channel\n{goodbye_channel}", accessory=self.goodbye_button),
                Section(f"<:chalice:1517579767573123092> Level-up and Quest Announce Channel\n{level_channel}", accessory=self.level_button),
                Section(f"<:unlocked:1517574880034558102> Admin Log Channel\n{admin_value}", accessory=self.admin_button),
                Section(f"<:honey:1524116282075512842> Honeypot Channel\n{honeypot_value}", accessory=self.honeypot_button),
            ]
        else:
            board_text = _shorten("\n".join(board_entries), 1000) if board_entries else "None"
            counter_text = _shorten("\n".join(counter_entries), 1000) if counter_entries else "None"
            ticket_style = guild_config.get("ticket_style", "button").title()
            ticket_reasons = guild_config.get("ticket_reasons", []) or []
            ticket_channel_ref = format_channel_reference(guild, guild_config.get("ticket_channel_id")) if guild else "None"
            ticket_role_ref = format_role_reference(guild, guild_config.get("ticket_manager_role_id")) if guild else "None"
            ticket_reasons_text = "None" if not ticket_reasons else "\n".join(f"- {reason}" for reason in ticket_reasons[:10])
            ticket_config_text = f"Style: {ticket_style}\nChannel: {ticket_channel_ref}\nManager: {ticket_role_ref}\nReasons:\n{ticket_reasons_text}"
            container_items += [
                Section(f"<:list:1517497572770451567> Board Channels\n{board_text}", accessory=self.board_button),
                Section(f"<:multi:1518348755261460661> Counter Channels\n{counter_text}", accessory=self.counter_button),
                Section(f"<:ticket:1533568847725203609> Ticket Settings\n{ticket_config_text}", accessory=self.ticket_config_button),
            ]

        container = Container(*container_items, accent_color=self.color)
        self.add_item(container)
        self.add_item(discord.ui.ActionRow(page_button, self.back_button))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This settings panel is only for the original user.", ephemeral=True)
            return False
        return True

    async def refresh_settings_message(self, interaction: discord.Interaction, view: discord.ui.View, settings_message: discord.Message | None = None):
        if settings_message is None:
            settings_message = interaction.message
            if settings_message is None:
                try:
                    settings_message = await interaction.original_response()
                except (discord.NotFound, discord.HTTPException):
                    settings_message = None
        if settings_message is None:
            return
        try:
            await settings_message.edit(view=view)
            return
        except (discord.NotFound, discord.HTTPException):
            pass

        try:
            await interaction.followup.edit_message(message_id=settings_message.id, view=view)
            return
        except Exception:
            pass

        try:
            await interaction.edit_original_response(view=view)
        except Exception:
            pass

    async def handle_back(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=GuildSettingsMenuView(interaction.user.id, self.guild_id))

    async def open_page_two(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2))

    async def open_page_one(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1))

    async def handle_welcome_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("welcome_channel_id"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the welcome channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_welcome, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the welcome channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select welcome channel", self.set_welcome_channel, interaction.message),
            ephemeral=True,
        )

    async def set_welcome_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["welcome_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Welcome channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_welcome(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["welcome_channel_id"] = None
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Welcome channel has been removed.", ephemeral=True)

    async def handle_goodbye_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("goodbye_channel_id"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the goodbye channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_goodbye, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the goodbye channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select goodbye channel", self.set_goodbye_channel, interaction.message),
            ephemeral=True,
        )

    async def set_goodbye_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["goodbye_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Goodbye channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_goodbye(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["goodbye_channel_id"] = None
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Goodbye channel has been removed.", ephemeral=True)

    async def handle_level_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        level_id = get_level_channel_id(self.guild_id)
        if level_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the level-up announce channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_level_channel, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the level-up announce channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select level-up announce channel", self.set_level_channel, interaction.message),
            ephemeral=True,
        )

    async def set_level_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        set_level_channel(self.guild_id, channel.id)
        await safe_send(interaction, f"<:approve:1517452125687513158> Level-up announce channel set to {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_level_channel(self, interaction: discord.Interaction, original_message: discord.Message):
        set_level_channel(self.guild_id, None)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Level-up announce channel has been removed.", ephemeral=True)

    async def handle_admin_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        admin_ids = get_guild_admin_log_channel_ids(guild)
        if admin_ids:
            channel = guild.get_channel(admin_ids[0])
            if channel:
                await interaction.response.defer(ephemeral=True); await interaction.followup.send(
                    f"Confirm removing admin logging from {channel.mention}?",
                    view=ConfirmRemoveView(self.user_id, self.confirm_remove_admin_log, interaction.message),
                    ephemeral=True,
                )
                return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the admin log channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select admin log channel", self.add_admin_log_channel, interaction.message),
            ephemeral=True,
        )

    async def add_admin_log_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        add_admin_log_channel(interaction.guild, channel.id)
        await safe_send(interaction, f"<:approve:1517452125687513158> Admin logging enabled in {channel.mention}", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_admin_log(self, interaction: discord.Interaction, original_message: discord.Message):
        admin_ids = get_guild_admin_log_channel_ids(interaction.guild)
        if admin_ids:
            remove_admin_log_channel(interaction.guild, admin_ids[0])
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send(f"<:trash:1517497581058527404> Admin logging disabled.", ephemeral=True)

    async def handle_board_edit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Board Channels?",
            view=ChannelEditChoiceView(self.user_id, "Board Channels", self.open_board_add, self.open_board_remove, interaction.message),
            ephemeral=True,
        )

    async def open_board_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the board channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select board channel", self.board_channel_selected, settings_message),
            ephemeral=True,
        )

    async def board_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        if not interaction.guild or not interaction.channel:
            await safe_send(interaction, "<:disapprove:1517452151012589662> Unable to continue board configuration.", ephemeral=True)
            return
        try:
            prompt = await interaction.channel.send(
                f"{interaction.user.mention}, react to this message with the emoji you want to use for the board. You have 60 seconds.",
            )
        except (discord.Forbidden, discord.HTTPException):
            await safe_send(interaction, "<:disapprove:1517452151012589662> I can't send messages in this channel. Use /settings in a channel where I can talk.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send("React to the channel prompt to choose the board emoji.", ephemeral=True)

        def check(reaction, user):
            return (
                user.id == interaction.user.id
                and reaction.message.id == prompt.id
            )

        try:
            reaction, user = await runtime.bot.wait_for("reaction_add", timeout=60.0, check=check)
        except asyncio.TimeoutError:
            try:
                await prompt.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
            await interaction.followup.send("<:disapprove:1517452151012589662> Emoji selection timed out.", ephemeral=True)
            return

        emoji = str(reaction.emoji)
        try:
            await prompt.delete()
        except (discord.NotFound, discord.HTTPException):
            pass
        await interaction.followup.send(
            "Emoji received. Set the required reaction count.",
            view=BoardCountPromptView(self.user_id, channel, emoji, settings_message, self.add_board_channel),
            ephemeral=True,
        )

    async def add_board_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, emoji: str, required_count: int, settings_message: discord.Message):
        board_data = load_board_data()
        if self.guild_id not in board_data:
            board_data[self.guild_id] = {}
        board_data[self.guild_id][emoji] = {
            "channel_id": channel.id,
            "required_count": required_count,
            "tracked_messages": {},
        }
        save_board_data(board_data)
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:approve:1517452125687513158> Board for {emoji} saved to {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_board_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the board channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select board channel to remove", self.remove_board_channel, settings_message),
            ephemeral=True,
        )

    async def remove_board_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        board_data = load_board_data()
        if self.guild_id not in board_data:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> No board channels are configured.", ephemeral=True)
            return
        removed = False
        for emoji_key, cfg in list(board_data[self.guild_id].items()):
            if cfg.get("channel_id") == channel.id:
                del board_data[self.guild_id][emoji_key]
                removed = True
        if removed:
            if not board_data[self.guild_id]:
                del board_data[self.guild_id]
            save_board_data(board_data)
            await interaction.response.defer(ephemeral=True); await interaction.followup.send(f"<:trash:1517497581058527404> Removed board channel {channel.mention}.", ephemeral=True)
            await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> That channel is not configured as a board channel.", ephemeral=True)

    async def handle_counter_edit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "What would you like to do with Counter Channels?",
            view=ChannelEditChoiceView(self.user_id, "Counter Channels", self.open_counter_add, self.open_counter_remove, interaction.message),
            ephemeral=True,
        )

    async def open_counter_add(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the counter channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select counter channel", self.counter_channel_selected, settings_message),
            ephemeral=True,
        )

    async def counter_channel_selected(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        async def yes_callback(interact: discord.Interaction):
            await self.add_counter_channel(interact, channel, True, settings_message)

        async def no_callback(interact: discord.Interaction):
            await self.add_counter_channel(interact, channel, False, settings_message)

        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            f"Should failures reset the counter in {channel.mention}?",
            view=YesNoView(self.user_id, yes_callback, no_callback),
            ephemeral=True,
        )

    async def add_counter_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, reset_on_fail: bool, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config.setdefault("counter_channels", {})[str(channel.id)] = {
            "current_value": 0,
            "last_user_id": None,
            "reset_on_fail": reset_on_fail,
        }
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Counter channel configured for {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def open_counter_remove(self, interaction: discord.Interaction, settings_message: discord.Message):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the counter channel to remove:",
            view=ChannelSelectorView(self.user_id, guild, "Select counter channel to remove", self.remove_counter_channel, settings_message),
            ephemeral=True,
        )

    async def remove_counter_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        if str(channel.id) not in guild_config.get("counter_channels", {}):
            await safe_send(interaction, "<:disapprove:1517452151012589662> That channel is not configured as a counter channel.", ephemeral=True)
            return
        del guild_config["counter_channels"][str(channel.id)]
        save_guild_data(data)
        await safe_send(interaction, f"<:trash:1517497581058527404> Removed counter channel {channel.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)

    async def handle_ticket_settings_edit(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        await interaction.response.send_modal(TicketConfigModal(self.set_ticket_config_flow, self.guild_id, interaction.message))

    async def set_ticket_config_flow(self, interaction: discord.Interaction, style: str, reasons: list[str], settings_message: discord.Message | None):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_style"] = style
        guild_config["ticket_reasons"] = reasons
        save_guild_data(data)
        await safe_send(interaction, "<:approve:1517452125687513158> Ticket settings saved. Next, select the ticket channel.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        await refresh_ticket_announce_message(self.guild_id)
        guild = interaction.guild
        if not guild:
            return
        await interaction.followup.send(
            "Select the ticket channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select ticket channel", self.set_ticket_channel_flow, settings_message),
            ephemeral=True,
        )

    async def set_ticket_channel_flow(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message | None):
        if getattr(channel, "type", None) != discord.ChannelType.text:
            await safe_send(interaction, "<:disapprove:1517452151012589662> Please select a text channel for the ticket channel.", ephemeral=True)
            return
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_channel_id"] = channel.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Ticket channel set to {channel.mention}. Next, select the ticket manager role.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        # Post the "Open a ticket" message now, so tickets work even if the role step is skipped.
        await refresh_ticket_announce_message(self.guild_id)
        guild = interaction.guild
        if not guild:
            return
        await interaction.followup.send(
            "Select the ticket manager role:",
            view=RoleSelectorView(self.user_id, guild, "Select ticket manager role", self.set_ticket_role_flow, settings_message),
            ephemeral=True,
        )

    async def set_ticket_role_flow(self, interaction: discord.Interaction, role: discord.Role, settings_message: discord.Message | None):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["ticket_manager_role_id"] = role.id
        save_guild_data(data)
        await safe_send(interaction, f"<:approve:1517452125687513158> Ticket manager role set to {role.mention}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=2), settings_message)
        await refresh_ticket_announce_message(self.guild_id)

    async def handle_honeypot_toggle(self, interaction: discord.Interaction):
        guild = interaction.guild
        if not guild:
            await safe_send(interaction, "<:disapprove:1517452151012589662> This action must be used in a server.", ephemeral=True)
            return
        guild_config, _ = get_guild_config(self.guild_id)
        if guild_config.get("honeypot_channel_id"):
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("Please confirm removal of the honeypot channel.", view=ConfirmRemoveView(self.user_id, self.confirm_remove_honeypot, interaction.message), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True); await interaction.followup.send(
            "Select the honeypot channel:",
            view=ChannelSelectorView(self.user_id, guild, "Select honeypot channel", self.open_honeypot_sanction, interaction.message),
            ephemeral=True,
        )

    async def open_honeypot_sanction(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, settings_message: discord.Message):
        resolved_channel = channel
        if interaction.guild and getattr(channel, "id", None):
            resolved_channel = interaction.guild.get_channel(channel.id) or await interaction.guild.fetch_channel(channel.id)
        if not resolved_channel or getattr(resolved_channel, "type", None) != discord.ChannelType.text:
            await safe_send(interaction, "<:disapprove:1517452151012589662> Please select a text channel for the honeypot.", ephemeral=True)
            return
        await interaction.response.send_modal(HoneypotSanctionModal(self.set_honeypot_channel, resolved_channel, settings_message))

    async def set_honeypot_channel(self, interaction: discord.Interaction, channel: discord.abc.GuildChannel, action: str, duration_seconds: int, duration_text: str, settings_message: discord.Message):
        resolved_channel = channel
        if interaction.guild and getattr(channel, "id", None):
            resolved_channel = interaction.guild.get_channel(channel.id) or await interaction.guild.fetch_channel(channel.id)

        guild_config, data = get_guild_config(self.guild_id)
        guild_config["honeypot_channel_id"] = getattr(resolved_channel, "id", channel.id)
        guild_config["honeypot_sanction"] = {
            "action": action,
            "duration_seconds": duration_seconds,
            "duration": duration_text,
        }
        save_guild_data(data)
        try:
            if resolved_channel and hasattr(resolved_channel, "send"):
                await resolved_channel.send(f"<:honey:1524116282075512842> This channel is a honeypot. Please do not send messages here. Any message sent here will trigger a sanction.")
        except (discord.Forbidden, discord.HTTPException):
            pass
        await safe_send(interaction, f"<:approve:1517452125687513158> Honeypot channel set to {getattr(resolved_channel, 'mention', str(channel.id))}.", ephemeral=True)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), settings_message)

    async def confirm_remove_honeypot(self, interaction: discord.Interaction, original_message: discord.Message):
        guild_config, data = get_guild_config(self.guild_id)
        guild_config["honeypot_channel_id"] = None
        guild_config["honeypot_sanction"] = {}
        save_guild_data(data)
        await self.refresh_settings_message(interaction, ChannelSettingsView(self.user_id, self.guild_id, self.color, page=1), original_message)
        await interaction.followup.send("<:trash:1517497581058527404> Honeypot channel has been removed.", ephemeral=True)




class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='settings', description='Open a quick settings menu for your personal and guild preferences')
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def settings(self, interaction: discord.Interaction):
        view = SettingsMenuView(
            interaction.user.id,
            interaction.user.display_name,
            get_user_color_value(str(interaction.user.id)),
        )
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SettingsCog(bot))
