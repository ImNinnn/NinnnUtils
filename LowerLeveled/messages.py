import discord

async def safe_edit_message(message: discord.Message, view: discord.ui.View):
    try:
        await message.edit(view=view)
    except (discord.NotFound, discord.HTTPException):
        pass


async def safe_send(interaction: discord.Interaction, content: str, **kwargs):
    try:
        await interaction.response.send_message(content, **kwargs)
    except discord.errors.InteractionResponded:
        try:
            await interaction.followup.send(content, **kwargs)
        except (discord.NotFound, discord.HTTPException):
            pass
    except (discord.NotFound, discord.HTTPException):
        pass

def is_valid_send_mode(value: str) -> bool:
    return str(value).strip().lower() in {"dm", "channel", "both"}


def normalize_send_mode(value: str) -> str:
    return str(value).strip().lower() if is_valid_send_mode(value) else "dm"
