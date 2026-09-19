"""Verification and real names.

New people can see only the verify channel. They press Verify, give their real
name and Caltech email, and a moderator approves (or the bot does, if the email
is on the uploaded roster and auto-approve is on). Approval sets their nickname
to their real name, gives the member role, and takes away the unverified role.
If a verified member later changes their nickname, the bot changes it back.
"""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from logic import (clean_name, is_caltech, name_problem, normalize_email,
                   parse_roster, valid_email)
from .common import role_problem

log = logging.getLogger('averite.verification')
AVERY_PURPLE = 0xA279B6
MEMBERSHIP_ROLES = {'full': 'Full Member', 'social': 'Social Member'}


def _is_moderator(member):
    perms = member.guild_permissions
    return perms.manage_nicknames or perms.manage_roles or perms.administrator


class VerifyModal(discord.ui.Modal, title='Verify for Avery'):
    full_name = discord.ui.TextInput(label='Your real first and last name', max_length=64,
                                     placeholder='This becomes your name in the server')
    email = discord.ui.TextInput(label='Your Caltech email', max_length=100,
                                 placeholder='you@caltech.edu')

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.submit(interaction, str(self.full_name), str(self.email))


class VerifyButton(discord.ui.DynamicItem[discord.ui.Button], template=r'avery:verify:start'):
    """The Verify button on the panel. Keeps working across bot restarts."""

    def __init__(self):
        super().__init__(discord.ui.Button(label='Verify', style=discord.ButtonStyle.primary,
                                           custom_id='avery:verify:start'))

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls()

    async def callback(self, interaction: discord.Interaction):
        await interaction.client.get_cog('Verification').start(interaction)


class DecisionButton(discord.ui.DynamicItem[discord.ui.Button],
                     template=r'avery:verify:(?P<action>approve|deny):(?P<request>\d+)'):
    """Approve / Deny on a request in the moderator channel."""

    def __init__(self, action, request_id):
        approve = action == 'approve'
        super().__init__(discord.ui.Button(
            label='Approve' if approve else 'Deny',
            style=discord.ButtonStyle.success if approve else discord.ButtonStyle.secondary,
            custom_id=f'avery:verify:{action}:{request_id}'))
        self.action, self.request_id = action, request_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(match['action'], int(match['request']))

    async def callback(self, interaction: discord.Interaction):
        await interaction.client.get_cog('Verification').decide(interaction, self.action, self.request_id)


class Verification(commands.Cog):
    config = app_commands.Group(name='verification', description='Set up member verification',
                                default_permissions=discord.Permissions(manage_guild=True), guild_only=True)
    roster = app_commands.Group(name='roster', description='The member list used to check verification requests',
                                default_permissions=discord.Permissions(manage_guild=True), guild_only=True)

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    # ------------------------------------------------------------------
    # the member's side
    # ------------------------------------------------------------------

    @app_commands.command(name='verify', description='Verify as an Avery member with your real name')
    @app_commands.guild_only()
    async def verify_command(self, interaction: discord.Interaction):
        await self.start(interaction)

    async def start(self, interaction):
        guild, user = interaction.guild, interaction.user
        if self.db.get_int(guild.id, 'member_role') is None:
            await interaction.response.send_message("Verification isn't set up here yet.", ephemeral=True)
            return
        record = self.db.get_verified(guild.id, user.id)
        if record:
            await interaction.response.send_message(
                f"You're already verified as **{record['name']}**. Ask a moderator if that needs changing.",
                ephemeral=True)
            return
        if self.db.pending_request_for(guild.id, user.id):
            await interaction.response.send_message(
                'Your request is already waiting for a moderator.', ephemeral=True)
            return
        await interaction.response.send_modal(VerifyModal(self))

    async def submit(self, interaction, raw_name, raw_email):
        guild, user = interaction.guild, interaction.user
        name, email = clean_name(raw_name), normalize_email(raw_email)
        problem = name_problem(name) or (None if valid_email(email) else "That doesn't look like an email address.")
        if problem:
            await interaction.response.send_message(f'{problem} Press Verify to try again.', ephemeral=True)
            return
        if self.db.pending_request_for(guild.id, user.id):
            await interaction.response.send_message('Your request is already waiting for a moderator.',
                                                    ephemeral=True)
            return

        entry = self.db.roster_lookup(guild.id, email)
        holder = self.db.verified_by_email(guild.id, email)
        taken = holder is not None and holder['user_id'] != user.id
        final_name = clean_name(entry['name']) if entry else name
        handle_ok = not (entry and entry['discord']) or entry['discord'] == user.name.lower()
        request_id = self.db.create_request(guild.id, user.id, final_name, email)

        if entry and not taken and handle_ok and self.db.get_bool(guild.id, 'auto_approve'):
            self.db.decide_request(request_id, 'approved', None)
            await interaction.response.defer(ephemeral=True, thinking=True)  # Discord wants a reply within 3s
            notes = await self.apply_verified(user, final_name, email, entry, approved_by=None)
            text = f"You're verified as **{final_name}**. Welcome to Avery!"
            await interaction.followup.send('\n'.join([text] + notes), ephemeral=True)
            return

        channel = guild.get_channel(self.db.get_int(guild.id, 'mod_channel') or 0)
        embed = discord.Embed(title='Verification request', colour=AVERY_PURPLE)
        embed.add_field(name='Account', value=f'{user.mention} (`{user.name}`)\nCreated {discord.utils.format_dt(user.created_at, "R")}', inline=False)
        embed.add_field(name='Name given', value=name)
        embed.add_field(name='Email given', value=email)
        checks = []
        if entry:
            checks.append(f'On the roster as **{entry["name"]}**'
                          + (f', class of {entry["year"]}' if entry['year'] else '')
                          + (f', {entry["membership"]} member' if entry['membership'] else ''))
            if not handle_ok:
                checks.append(f'Roster lists Discord username `{entry["discord"]}`, which does not match this account')
        else:
            checks.append('Not on the roster' if self.db.roster_count(guild.id) else 'No roster uploaded to check against')
        if taken:
            checks.append(f'That email is already used by <@{holder["user_id"]}>')
        if not is_caltech(email):
            checks.append('Not a Caltech address')
        embed.add_field(name='Checks', value='\n'.join(f'- {c}' for c in checks), inline=False)
        embed.set_footer(text=f'Approving sets their nickname to: {final_name}')
        view = discord.ui.View(timeout=None)
        view.add_item(DecisionButton('approve', request_id))
        view.add_item(DecisionButton('deny', request_id))
        try:
            if channel is None:
                raise LookupError('no moderator channel')
            await channel.send(embed=embed, view=view)
        except (LookupError, discord.HTTPException):
            log.warning('Could not post verification request %s in guild %s', request_id, guild.id)
            self.db.decide_request(request_id, 'failed', None)
            await interaction.response.send_message(
                "I couldn't reach the moderators' channel. Please message a moderator directly.", ephemeral=True)
            return
        await interaction.response.send_message(
            'Thanks! A moderator will approve you shortly.', ephemeral=True)

    # ------------------------------------------------------------------
    # the moderator's side
    # ------------------------------------------------------------------

    async def decide(self, interaction, action, request_id):
        guild = interaction.guild
        if not _is_moderator(interaction.user):
            await interaction.response.send_message('Only moderators can decide requests.', ephemeral=True)
            return
        request = self.db.get_request(request_id)
        if request is None or request['guild_id'] != guild.id:
            await interaction.response.send_message("I can't find that request any more.", ephemeral=True)
            return
        status = 'approved' if action == 'approve' else 'denied'
        if not self.db.decide_request(request_id, status, interaction.user.id):
            await interaction.response.send_message('Someone already handled this one.', ephemeral=True)
            return

        await interaction.response.defer()  # Discord wants a reply within 3s; the work below can take longer
        notes = []
        member = guild.get_member(request['user_id'])
        if member is None:
            notes.append('They have left the server.')
        elif status == 'approved':
            entry = self.db.roster_lookup(guild.id, request['email'])
            notes = await self.apply_verified(member, request['name'], request['email'], entry,
                                              approved_by=interaction.user.id)
            await self._dm(member, f"You're verified in {guild.name} as **{request['name']}**. Welcome!")
        else:
            await self._dm(member, f"Your verification in {guild.name} wasn't approved. "
                                   'Message a moderator if you think that is a mistake.')

        embed = interaction.message.embeds[0] if interaction.message.embeds else discord.Embed()
        embed.colour = discord.Colour.green() if status == 'approved' else discord.Colour.dark_grey()
        embed.set_footer(text=f'{status.capitalize()} by {interaction.user.display_name}')
        if notes:
            embed.add_field(name='Heads up', value='\n'.join(f'- {n}' for n in notes), inline=False)
        await interaction.edit_original_response(embed=embed, view=None)

    async def apply_verified(self, member, name, email, entry, approved_by):
        """Record the member as verified, fix their roles, set their nickname.
        Returns notes about anything that could not be done."""
        guild, notes = member.guild, []
        self.db.set_verified(guild.id, member.id, name, email, approved_by)

        wanted = []
        member_role = guild.get_role(self.db.get_int(guild.id, 'member_role') or 0)
        if member_role:
            wanted.append(member_role)
        if entry:
            by_name = {r.name.lower(): r for r in guild.roles}
            if entry['year']:
                wanted.append(by_name.get(str(entry['year']).lower()) or by_name.get(f'class of {entry["year"]}'.lower()))
            if entry['membership']:
                wanted.append(by_name.get(MEMBERSHIP_ROLES.get(entry['membership'], '').lower()))
        add = []
        for role in filter(None, wanted):
            problem = role_problem(guild, role)
            if problem:
                notes.append(problem)
            elif role not in member.roles:
                add.append(role)
        try:
            if add:
                await member.add_roles(*add, reason='Verified')
            unverified = guild.get_role(self.db.get_int(guild.id, 'unverified_role') or 0)
            if unverified and unverified in member.roles:
                await member.remove_roles(unverified, reason='Verified')
        except discord.HTTPException:
            notes.append("I couldn't change their roles. Check that I have Manage Roles.")

        if self.db.get_bool(guild.id, 'enforce_names', True) and member.nick != name:
            try:
                await member.edit(nick=name, reason='Verified: real name')
            except discord.HTTPException:
                notes.append("I couldn't set their nickname. That happens for the server owner "
                             'and for anyone whose top role is above mine.')
        return notes

    @staticmethod
    async def _dm(member, text):
        try:
            await member.send(text)
        except discord.HTTPException:
            pass  # DMs closed

    # ------------------------------------------------------------------
    # keeping names real, and remembering people who rejoin
    # ------------------------------------------------------------------

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.nick == after.nick:
            return
        guild = after.guild
        if not self.db.get_bool(guild.id, 'enforce_names', True):
            return
        record = self.db.get_verified(guild.id, after.id)
        if record is None or after.nick == record['name']:
            return
        try:
            await after.edit(nick=record['name'], reason='Real-name policy')
        except discord.HTTPException:
            return
        await self._dm(after, f'{guild.name} uses real names, so I changed your nickname back to '
                              f'**{record["name"]}**. If you go by a different name, ask a moderator to update it.')

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot:
            return
        guild = member.guild
        record = self.db.get_verified(guild.id, member.id)
        if record:  # verified before, left, came back
            entry = self.db.roster_lookup(guild.id, record['email']) if record['email'] else None
            await self.apply_verified(member, record['name'], record['email'], entry, record['approved_by'])
            return
        unverified = guild.get_role(self.db.get_int(guild.id, 'unverified_role') or 0)
        if unverified and role_problem(guild, unverified) is None:
            try:
                await member.add_roles(unverified, reason='Joined: not verified yet')
            except discord.HTTPException:
                pass

    # ------------------------------------------------------------------
    # moderator commands
    # ------------------------------------------------------------------

    @app_commands.command(name='rename', description="Change a verified member's recorded name and nickname")
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.guild_only()
    @app_commands.describe(member='Who to rename', name='The name they go by')
    async def rename(self, interaction: discord.Interaction, member: discord.Member, name: str):
        name = clean_name(name)
        if len(name) < 2:
            await interaction.response.send_message('That name is too short.', ephemeral=True)
            return
        record = self.db.get_verified(interaction.guild.id, member.id)
        if record is None:
            await interaction.response.send_message(
                f'{member.mention} is not verified yet. Use /verify-member instead.', ephemeral=True)
            return
        self.db.set_verified(interaction.guild.id, member.id, name, None, record['approved_by'])
        try:
            await member.edit(nick=name, reason=f'Renamed by {interaction.user}')
            text = f'{member.mention} is now **{name}**.'
        except discord.HTTPException:
            text = f"Recorded **{name}**, but I couldn't change the nickname (owner, or a role above mine)."
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name='verify-member', description='Verify someone yourself, without a request')
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.guild_only()
    @app_commands.describe(member='Who to verify', name='Their real name', email='Their Caltech email, if you have it')
    async def verify_member(self, interaction: discord.Interaction, member: discord.Member, name: str,
                            email: str = None):
        name, email = clean_name(name), normalize_email(email) or None
        if len(name) < 2 or (email and not valid_email(email)):
            await interaction.response.send_message('Check the name and email and try again.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        entry = self.db.roster_lookup(interaction.guild.id, email) if email else None
        notes = await self.apply_verified(member, name, email, entry, approved_by=interaction.user.id)
        await interaction.followup.send('\n'.join([f'{member.mention} is verified as **{name}**.'] + notes))

    @app_commands.command(name='unverify', description="Remove someone's verification")
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.guild_only()
    async def unverify(self, interaction: discord.Interaction, member: discord.Member):
        guild = interaction.guild
        if not self.db.remove_verified(guild.id, member.id):
            await interaction.response.send_message(f'{member.mention} was not verified.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        member_role = guild.get_role(self.db.get_int(guild.id, 'member_role') or 0)
        unverified = guild.get_role(self.db.get_int(guild.id, 'unverified_role') or 0)
        try:
            if member_role and member_role in member.roles:
                await member.remove_roles(member_role, reason=f'Unverified by {interaction.user}')
            if unverified and role_problem(guild, unverified) is None:
                await member.add_roles(unverified, reason=f'Unverified by {interaction.user}')
        except discord.HTTPException:
            pass
        await interaction.followup.send(f'{member.mention} is no longer verified.')

    @app_commands.command(name='whois', description='Who is this member? Shows their verified name')
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.guild_only()
    async def whois(self, interaction: discord.Interaction, member: discord.Member):
        record = self.db.get_verified(interaction.guild.id, member.id)
        if record is None:
            text = f'{member.mention} (`{member.name}`) is not verified.'
        else:
            text = (f'{member.mention} (`{member.name}`) is **{record["name"]}**'
                    + (f', {record["email"]}' if record['email'] else '')
                    + f'. Verified <t:{record["verified_at"]}:D>'
                    + (f' by <@{record["approved_by"]}>.' if record['approved_by'] else ' automatically.'))
        await interaction.response.send_message(text, ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    # ------------------------------------------------------------------
    # setup commands
    # ------------------------------------------------------------------

    @config.command(name='setup', description='Choose the roles and channel verification uses')
    @app_commands.describe(
        member_role='Given to people once verified',
        mod_channel='Private channel where requests appear for moderators',
        unverified_role='Optional: given on join, removed on verification',
        auto_approve='Approve without a moderator when the email is on the roster (default: off)',
        enforce_names='Change nicknames back to the real name if people edit them (default: on)')
    async def setup_command(self, interaction: discord.Interaction, member_role: discord.Role,
                            mod_channel: discord.TextChannel, unverified_role: discord.Role = None,
                            auto_approve: bool = False, enforce_names: bool = True):
        guild = interaction.guild
        for role in filter(None, (member_role, unverified_role)):
            problem = role_problem(guild, role, actor=interaction.user)
            if problem:
                await interaction.response.send_message(problem, ephemeral=True)
                return
        self.db.set(guild.id, 'member_role', member_role.id)
        self.db.set(guild.id, 'mod_channel', mod_channel.id)
        self.db.set(guild.id, 'unverified_role', unverified_role.id if unverified_role else None)
        self.db.set(guild.id, 'auto_approve', auto_approve)
        self.db.set(guild.id, 'enforce_names', enforce_names)
        await interaction.response.send_message(
            'Saved. Run `/verification status` to check my permissions, then `/verification panel` '
            'to post the Verify button.', ephemeral=True)

    @config.command(name='panel', description='Post the message with the Verify button')
    async def panel(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        channel = channel or interaction.channel
        embed = discord.Embed(
            title='Welcome to Avery', colour=AVERY_PURPLE,
            description='This server uses real names. Press **Verify**, enter your real first and last '
                        'name and your Caltech email, and a moderator will let you in. Your nickname '
                        'here will be set to your real name.')
        view = discord.ui.View(timeout=None)
        view.add_item(VerifyButton())
        try:
            await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            await interaction.response.send_message(f"I can't post in {channel.mention}.", ephemeral=True)
            return
        await interaction.response.send_message(f'Posted in {channel.mention}.', ephemeral=True)

    @config.command(name='status', description='Show the verification settings and check my permissions')
    async def status(self, interaction: discord.Interaction):
        guild, db, me = interaction.guild, self.db, interaction.guild.me
        lines, problems = [], []
        for key, label in (('member_role', 'Member role'), ('unverified_role', 'Unverified role')):
            role = guild.get_role(db.get_int(guild.id, key) or 0)
            lines.append(f'{label}: {role.mention if role else "not set"}')
            if role and role_problem(guild, role):
                problems.append(role_problem(guild, role))
        channel = guild.get_channel(db.get_int(guild.id, 'mod_channel') or 0)
        lines.append(f'Moderator channel: {channel.mention if channel else "not set"}')
        if channel and not (channel.permissions_for(me).send_messages and channel.permissions_for(me).embed_links):
            problems.append(f'I need Send Messages and Embed Links in {channel.mention}.')
        lines.append(f'Auto-approve roster matches: {"on" if db.get_bool(guild.id, "auto_approve") else "off"}')
        lines.append(f'Enforce real names: {"on" if db.get_bool(guild.id, "enforce_names", True) else "off"}')
        lines.append(f'Roster: {db.roster_count(guild.id)} people. Verified: {db.verified_count(guild.id)}. '
                     f'Waiting: {db.pending_count(guild.id)}.')
        if not me.guild_permissions.manage_roles:
            problems.append('I need the Manage Roles permission.')
        if not me.guild_permissions.manage_nicknames:
            problems.append('I need the Manage Nicknames permission.')
        if not self.bot.intents.members:
            problems.append('The Server Members intent is off, so I cannot see joins or nickname changes.')
        if guild.default_role.permissions.change_nickname:
            problems.append('Tip: turn off Change Nickname for @everyone so people cannot edit their names at all. '
                            'Until then I change them back.')
        embed = discord.Embed(title='Verification', colour=AVERY_PURPLE, description='\n'.join(lines))
        embed.add_field(name='To fix' if problems else 'Checks',
                        value='\n'.join(f'- {p}' for p in problems) if problems else 'Everything looks right.',
                        inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @roster.command(name='upload', description='Replace the roster with a CSV file (columns: name, email, year, membership, discord)')
    @app_commands.describe(file='A .csv export of the member list')
    async def roster_upload(self, interaction: discord.Interaction, file: discord.Attachment):
        if file.size > 2_000_000:
            await interaction.response.send_message('That file is too big to be a roster.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            text = (await file.read()).decode('utf-8-sig')
        except (discord.HTTPException, UnicodeDecodeError):
            await interaction.followup.send("I couldn't read that file. Export it as CSV (UTF-8) and try again.")
            return
        rows, problems = parse_roster(text)
        if not rows:
            await interaction.followup.send('\n'.join(problems or ['No people found in that file.']))
            return
        self.db.replace_roster(interaction.guild.id, rows)
        summary = [f'Roster replaced: {len(rows)} people.'] + problems[:10]
        if len(problems) > 10:
            summary.append(f'...and {len(problems) - 10} more rows skipped.')
        await interaction.followup.send('\n'.join(summary))

    @roster.command(name='clear', description='Delete the uploaded roster')
    async def roster_clear(self, interaction: discord.Interaction):
        self.db.replace_roster(interaction.guild.id, [])
        await interaction.response.send_message('Roster deleted. Verified members are not affected.', ephemeral=True)


async def setup(bot):
    await bot.add_cog(Verification(bot))
    bot.add_dynamic_items(VerifyButton, DecisionButton)
