"""Stand-ins for Discord objects, just detailed enough to run the bot's logic."""
import datetime
from types import SimpleNamespace

import discord


class FakeRole:
    def __init__(self, id, name, position, managed=False, perms=0, default=False):
        self.id, self.name, self.position, self.managed = id, name, position, managed
        self.permissions = SimpleNamespace(value=perms)
        self._default = default
        self.mention = f'<@&{id}>'

    def is_default(self):
        return self._default

    def __eq__(self, other):
        return isinstance(other, FakeRole) and other.id == self.id

    def __hash__(self):
        return hash(self.id)

    def __ge__(self, other):
        return self.position >= other.position

    def __repr__(self):
        return f'<Role {self.name}>'


class FakeMember:
    def __init__(self, id, name, guild=None, roles=(), nick=None, moderator=False, locked=False):
        self.id, self.name, self.nick, self.guild = id, name, nick, guild
        self.roles, self.bot, self.locked = list(roles), False, locked
        self.mention, self.dms, self.calls = f'<@{id}>', [], []
        self.created_at = datetime.datetime(2022, 9, 1, tzinfo=datetime.timezone.utc)
        self.guild_permissions = SimpleNamespace(manage_nicknames=moderator, manage_roles=moderator,
                                                 administrator=False)

    @property
    def display_name(self):
        return self.nick or self.name

    @property
    def top_role(self):
        return max(self.roles, key=lambda r: r.position)

    def _forbidden(self):
        raise discord.Forbidden(SimpleNamespace(status=403, reason='Forbidden'), 'Missing Permissions')

    async def edit(self, nick=None, reason=None):
        if self.locked:
            self._forbidden()
        self.calls.append(('edit', nick))
        self.nick = nick

    async def add_roles(self, *roles, reason=None):
        self.calls.append(('add', [r.name for r in roles]))
        self.roles += [r for r in roles if r not in self.roles]

    async def remove_roles(self, *roles, reason=None):
        self.calls.append(('remove', [r.name for r in roles]))
        self.roles = [r for r in self.roles if r not in roles]

    async def send(self, text):
        self.dms.append(text)


class FakeChannel:
    def __init__(self, id):
        self.id, self.mention, self.sent = id, f'<#{id}>', []

    async def send(self, embed=None, view=None):
        self.sent.append((embed, view))
        return SimpleNamespace(id=9000 + len(self.sent))


class FakeGuild:
    def __init__(self, id=1, owner_id=999):
        self.id, self.name, self.owner_id = id, 'Avery', owner_id
        self.roles, self.members, self.channels, self.me = [], [], {}, None

    def get_role(self, id):
        return next((r for r in self.roles if r.id == id), None)

    def get_member(self, id):
        return next((m for m in self.members if m.id == id), None)

    def get_channel(self, id):
        return self.channels.get(id)


class FakeResponse:
    def __init__(self):
        self.sent, self.modal, self.edited, self.deferred = [], None, None, False

    async def send_message(self, content=None, **kwargs):
        self.sent.append(content)

    async def send_modal(self, modal):
        self.modal = modal

    async def edit_message(self, **kwargs):
        self.edited = kwargs

    async def defer(self, **kwargs):
        self.deferred = True


def interaction(guild, user, channel=None):
    response = FakeResponse()

    async def followup_send(content=None, **kwargs):
        response.sent.append(content)

    async def edit_original_response(**kwargs):
        response.edited = kwargs

    return SimpleNamespace(guild=guild, user=user, channel=channel, response=response,
                           followup=SimpleNamespace(send=followup_send),
                           edit_original_response=edit_original_response,
                           message=SimpleNamespace(embeds=[discord.Embed(title='Verification request')]))


def server():
    """A small Avery-like server: bot role on top, then the usual roles."""
    g = FakeGuild()
    everyone = FakeRole(1, '@everyone', 0, default=True)
    roles = {name: FakeRole(i, name, pos) for i, (name, pos) in enumerate(
        [('Bot', 10), ('Member', 5), ('Unverified', 4), ('2027', 3), ('2028', 3), ('Full Member', 2)], start=10)}
    roles['ExComm'] = FakeRole(30, 'ExComm', 20, perms=discord.Permissions(manage_roles=True).value)
    g.roles = [everyone] + list(roles.values())
    g.me = FakeMember(500, 'avery-bot', g, [everyone, roles['Bot']])
    g.channels[700] = FakeChannel(700)
    return g, roles, everyone
