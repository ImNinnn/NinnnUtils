"""Shared view base classes.

Importing this module also patches discord.py send/edit calls so that any view
built on TimeoutDisabledViewMixin knows which message it is attached to.
"""

import discord
from discord.ui import Button, Container, LayoutView, Separator, TextDisplay, View


def _bind_timeout_view_message(view, message):
    if view is None or message is None:
        return
    if not hasattr(view, "_attach_message"):
        return
    try:
        view._attach_message(message)
    except Exception:
        pass


def _unpatched(owner, name: str):
    """discord.py's own method, even if this module already patched it (the cog manager can reload it)."""
    current = getattr(owner, name)
    return getattr(current, "_nutils_original", current)


def _install_patch(owner, name: str, original, patched) -> None:
    patched._nutils_original = original
    setattr(owner, name, patched)


_original_messageable_send = _unpatched(discord.abc.Messageable, "send")


async def _patched_messageable_send(self, *args, **kwargs):
    view = kwargs.get("view")
    message = await _original_messageable_send(self, *args, **kwargs)
    _bind_timeout_view_message(view, message)
    return message


_install_patch(discord.abc.Messageable, "send", _original_messageable_send, _patched_messageable_send)


_original_message_edit = _unpatched(discord.message.Message, "edit")


async def _patched_message_edit(self, *args, **kwargs):
    view = kwargs.get("view")
    message = await _original_message_edit(self, *args, **kwargs)
    _bind_timeout_view_message(view, message)
    return message


_install_patch(discord.message.Message, "edit", _original_message_edit, _patched_message_edit)


_original_interaction_response_send_message = _unpatched(discord.InteractionResponse, "send_message")


async def _patched_interaction_response_send_message(self, *args, **kwargs):
    view = kwargs.get("view", discord.utils.MISSING)
    response = await _original_interaction_response_send_message(self, *args, **kwargs)
    if view is not discord.utils.MISSING and view is not None:
        try:
            message = await self._parent.original_response()
        except Exception:
            message = None
        _bind_timeout_view_message(view, message)
    return response


_install_patch(discord.InteractionResponse, "send_message", _original_interaction_response_send_message, _patched_interaction_response_send_message)


_original_interaction_response_edit_message = _unpatched(discord.InteractionResponse, "edit_message")


async def _patched_interaction_response_edit_message(self, *args, **kwargs):
    view = kwargs.get("view", discord.utils.MISSING)
    response = await _original_interaction_response_edit_message(self, *args, **kwargs)
    if view is not discord.utils.MISSING and view is not None:
        try:
            message = await self._parent.original_response()
        except Exception:
            message = None
        _bind_timeout_view_message(view, message)
    return response


_install_patch(discord.InteractionResponse, "edit_message", _original_interaction_response_edit_message, _patched_interaction_response_edit_message)


class TimeoutDisabledViewMixin:
    def __init__(self, *args, timeout: float = 600, **kwargs):
        self._timeout_message = None
        if timeout is not None and timeout < 600:
            timeout = 600
        super().__init__(*args, timeout=timeout, **kwargs)

    def _attach_message(self, message):
        if message is None:
            return None
        self._timeout_message = message
        self.message = message
        return message

    def _get_timeout_message(self):
        for attr_name in ("message", "settings_message", "original_message", "target_message", "msg"):
            candidate = getattr(self, attr_name, None)
            if candidate is not None:
                return candidate
        return self._timeout_message

    async def on_timeout(self):
        return None


class TimeoutDisabledLayoutView(TimeoutDisabledViewMixin, LayoutView):
    pass


class TimeoutDisabledView(TimeoutDisabledViewMixin, View):
    pass


class V2InfoContainerView(TimeoutDisabledLayoutView):
    def __init__(self, title: str, description: str, accent_color: discord.Color):
        super().__init__(timeout=600)
        container = Container(
            TextDisplay(title),
            Separator(),
            TextDisplay(description),
            accent_color=accent_color,
        )
        self.add_item(container)


class EconomyChoiceView(TimeoutDisabledView):
    def __init__(self, user_id: int, on_add, on_remove, setting_name: str, on_edit=None, settings_message: discord.Message | None = None):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.on_add = on_add
        self.on_remove = on_remove
        self.on_edit = on_edit
        self.setting_name = setting_name
        self.settings_message = settings_message
        self.add_button = Button(label="Add", style=discord.ButtonStyle.success, custom_id=f"economy_add_{setting_name}")
        self.edit_button = Button(label="Edit", style=discord.ButtonStyle.primary, custom_id=f"economy_edit_{setting_name}")
        self.remove_button = Button(label="Remove", style=discord.ButtonStyle.danger, custom_id=f"economy_remove_{setting_name}")
        self.cancel_button = Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id=f"economy_cancel_{setting_name}")
        self.add_button.callback = self.add_callback
        self.edit_button.callback = self.edit_callback
        self.remove_button.callback = self.remove_callback
        self.cancel_button.callback = self.cancel_callback
        self.add_item(self.add_button)
        self.add_item(self.edit_button)
        self.add_item(self.remove_button)
        self.add_item(self.cancel_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> This selection is only for the original user.", ephemeral=True)
            return False
        return True

    async def add_callback(self, interaction: discord.Interaction):
        await self.on_add(interaction, self.settings_message)

    async def edit_callback(self, interaction: discord.Interaction):
        if callable(self.on_edit):
            await self.on_edit(interaction, self.settings_message)
        else:
            await interaction.response.defer(ephemeral=True); await interaction.followup.send("<:disapprove:1517452151012589662> Edit is not available for this section.", ephemeral=True)

    async def remove_callback(self, interaction: discord.Interaction):
        await self.on_remove(interaction, self.settings_message)

    async def cancel_callback(self, interaction: discord.Interaction):
        self.add_button.disabled = True
        self.edit_button.disabled = True
        self.remove_button.disabled = True
        self.cancel_button.disabled = True
        await interaction.response.edit_message(view=self)


async def safe_send(interaction: discord.Interaction, content: str, **kwargs):
    try:
        await interaction.response.defer(); await interaction.followup.send(content, **kwargs)
    except discord.errors.InteractionResponded:
        try:
            await interaction.followup.send(content, **kwargs)
        except (discord.NotFound, discord.HTTPException):
            pass
    except (discord.NotFound, discord.HTTPException):
        pass
