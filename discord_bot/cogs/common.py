"""Role safety checks shared by the cogs."""
import discord

# A role carrying any of these is a staff role. The bot never hands those out
# through a self-serve menu.
ELEVATED = discord.Permissions(
    administrator=True, manage_guild=True, manage_roles=True, manage_channels=True,
    kick_members=True, ban_members=True, manage_webhooks=True, moderate_members=True,
    mention_everyone=True, manage_messages=True, manage_nicknames=True)


def is_elevated(role):
    return bool(role.permissions.value & ELEVATED.value)


def role_problem(guild, role, actor=None):
    """Why the bot can't (or shouldn't) assign this role, or None if it can.
    With `actor`, also applies Discord's own rule that people may only manage
    roles below their highest one, so the bot can't be used to climb."""
    if role.is_default():
        return "@everyone can't be assigned."
    if role.managed:
        return f'{role.name} is managed by an integration.'
    if role >= guild.me.top_role:
        return f'Move my role above {role.name} in Server Settings > Roles first.'
    if actor is not None and actor.id != guild.owner_id and role >= actor.top_role:
        return f'{role.name} is not below your own highest role.'
    return None
