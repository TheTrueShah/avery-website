"""Roles, the way Dyno does them.

- Role menus: a message with one button per role. Click to take the role,
  click again to drop it. A menu can be exclusive (class year: pick one).
- /rank: the same thing by command.
- /role give | take | bulk: moderator tools.

The role given on join is part of verification (see verification.py).
"""
import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from logic import plan_toggle
from .common import is_elevated, role_problem

log = logging.getLogger('avery-bot.roles')
AVERY_PURPLE = 0xA279B6
MAX_BUTTONS = 25  # Discord allows 5 rows of 5 buttons on one message


class RoleButton(discord.ui.DynamicItem[discord.ui.Button],
                 template=r'avery:role:(?P<menu>\d+):(?P<role>\d+)'):
    def __init__(self, menu_id, role_id, label='Role'):
        super().__init__(discord.ui.Button(label=label[:80], style=discord.ButtonStyle.secondary,
                                           custom_id=f'avery:role:{menu_id}:{role_id}'))
        self.menu_id, self.role_id = menu_id, role_id

    @classmethod
    async def from_custom_id(cls, interaction, item, match):
        return cls(int(match['menu']), int(match['role']), item.label or 'Role')

    async def callback(self, interaction: discord.Interaction):
        await interaction.client.get_cog('Roles').toggle(interaction, self.menu_id, self.role_id)


class Confirm(discord.ui.View):
    def __init__(self, author_id):
        super().__init__(timeout=60)
        self.author_id, self.confirmed = author_id, False

    async def interaction_check(self, interaction):
        return interaction.user.id == self.author_id

    @discord.ui.button(label='Yes, do it', style=discord.ButtonStyle.danger)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        await interaction.response.edit_message(content='Working on it...', view=None)
        self.stop()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.secondary)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content='Cancelled.', view=None)
        self.stop()


class Roles(commands.Cog):
    rolemenu = app_commands.Group(name='rolemenu', description='Messages with buttons that let people pick roles',
                                  default_permissions=discord.Permissions(manage_roles=True), guild_only=True)
    role = app_commands.Group(name='role', description='Give and take roles',
                              default_permissions=discord.Permissions(manage_roles=True), guild_only=True)

    def __init__(self, bot):
        self.bot = bot
        self.db = bot.db

    # ------------------------------------------------------------------
    # picking roles
    # ------------------------------------------------------------------

    async def toggle(self, interaction, menu_id, role_id):
        guild, member = interaction.guild, interaction.user
        menu = self.db.get_menu(menu_id, guild.id)
        menu_role_ids = [r['role_id'] for r in self.db.menu_roles(menu_id)] if menu else []
        role = guild.get_role(role_id)
        if menu is None or role is None or role_id not in menu_role_ids:
            await interaction.response.send_message("That role isn't available any more.", ephemeral=True)
            return
        member_role = self.db.get_int(guild.id, 'member_role')
        if member_role and member_role not in {r.id for r in member.roles}:
            await interaction.response.send_message('Verify first, then you can pick roles.', ephemeral=True)
            return
        if is_elevated(role) or role_problem(guild, role):
            await interaction.response.send_message(
                f"I can't hand out {role.name}. A moderator needs to look at this menu.", ephemeral=True)
            return
        add, remove = plan_toggle({r.id for r in member.roles}, menu_role_ids, role_id, bool(menu['exclusive']))
        removable = [r for r in (guild.get_role(i) for i in remove) if r and not role_problem(guild, r)]
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            if removable:
                await member.remove_roles(*removable, reason=f'Role menu: {menu["title"]}')
            if add:
                await member.add_roles(role, reason=f'Role menu: {menu["title"]}')
        except discord.HTTPException:
            await interaction.followup.send("I couldn't change your roles. Tell a moderator.", ephemeral=True)
            return
        if add:
            text = f'You now have **{role.name}**.'
            dropped = [r.name for r in removable]
            if dropped:
                text += f' Removed {", ".join(dropped)}.'
        else:
            text = f'Removed **{role.name}**.'
        await interaction.followup.send(text, ephemeral=True)

    @app_commands.command(name='rank', description='Take or drop one of the self-serve roles')
    @app_commands.guild_only()
    @app_commands.describe(role='Start typing to see the roles you can pick')
    async def rank(self, interaction: discord.Interaction, role: str):
        if not role.isdigit():
            await interaction.response.send_message('Pick a role from the list that appears as you type.',
                                                    ephemeral=True)
            return
        menu = self.db.menu_for_role(interaction.guild.id, int(role))
        if menu is None:
            await interaction.response.send_message("That isn't a self-serve role.", ephemeral=True)
            return
        await self.toggle(interaction, menu['id'], int(role))

    @rank.autocomplete('role')
    async def rank_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = []
        for row in self.db.self_assignable(interaction.guild.id):
            text = f'{row["label"]} ({row["title"]})'
            if current.lower() in text.lower():
                choices.append(app_commands.Choice(name=text[:100], value=str(row['role_id'])))
        return choices[:25]

    # ------------------------------------------------------------------
    # building menus
    # ------------------------------------------------------------------

    async def _menu_autocomplete(self, interaction: discord.Interaction, current: str):
        return [app_commands.Choice(name=f'{m["title"]} (#{m["id"]})'[:100], value=m['id'])
                for m in self.db.list_menus(interaction.guild.id)
                if current.lower() in m['title'].lower()][:25]

    def _render(self, menu):
        roles = self.db.menu_roles(menu['id'])
        hint = 'Pick one. Click it again to drop it.' if menu['exclusive'] else 'Click to take a role. Click again to drop it.'
        embed = discord.Embed(title=menu['title'], colour=AVERY_PURPLE,
                              description='\n'.join(filter(None, [menu['description'], hint])))
        view = discord.ui.View(timeout=None)
        for r in roles[:MAX_BUTTONS]:
            view.add_item(RoleButton(menu['id'], r['role_id'], r['label']))
        return embed, view

    async def _refresh(self, guild, menu_id):
        """Update the posted message after the menu changes. Best effort."""
        menu = self.db.get_menu(menu_id, guild.id)
        if not menu or not menu['message_id']:
            return
        channel = guild.get_channel(menu['channel_id'])
        if channel is None:
            return
        embed, view = self._render(menu)
        try:
            await channel.get_partial_message(menu['message_id']).edit(embed=embed, view=view)
        except discord.HTTPException:
            pass

    def _check_menu_role(self, interaction, role):
        if is_elevated(role):
            return f"{role.name} carries moderator permissions, so it can't go in a self-serve menu."
        return role_problem(interaction.guild, role, actor=interaction.user)

    @rolemenu.command(name='quick', description='Make a menu in one go: creates any missing roles and posts it')
    @app_commands.describe(title='e.g. Class year', roles='Role names separated by commas, e.g. 2027, 2028, 2029, 2030',
                           exclusive='People can hold only one role from this menu',
                           channel='Where to post it (default: here)')
    async def quick(self, interaction: discord.Interaction, title: str, roles: str, exclusive: bool = False,
                    channel: discord.TextChannel = None):
        guild = interaction.guild
        names = list(dict.fromkeys(n.strip() for n in roles.split(',') if n.strip()))
        if not names or len(names) > MAX_BUTTONS:
            await interaction.response.send_message(f'Give between 1 and {MAX_BUTTONS} role names.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        existing = {r.name.lower(): r for r in guild.roles}
        chosen, created, skipped = [], [], []
        for name in names:
            role = existing.get(name.lower())
            if role is None:
                try:
                    role = await guild.create_role(name=name[:100], mentionable=False,
                                                   reason=f'Role menu "{title}" by {interaction.user}')
                    created.append(role.name)
                except discord.HTTPException:
                    skipped.append(f"{name}: I couldn't create it. Do I have Manage Roles?")
                    continue
            problem = self._check_menu_role(interaction, role)
            if problem:
                skipped.append(f'{name}: {problem}')
            else:
                chosen.append(role)
        if not chosen:
            await interaction.followup.send('\n'.join(['No menu made.'] + skipped))
            return
        menu_id = self.db.create_menu(guild.id, title[:100], None, exclusive)
        for role in chosen:
            self.db.add_menu_role(menu_id, role.id, role.name)
        report = await self._post(guild, menu_id, channel or interaction.channel)
        lines = [report]
        if created:
            lines.append(f'Created roles: {", ".join(created)}.')
        await interaction.followup.send('\n'.join(lines + skipped))

    @rolemenu.command(name='create', description='Start an empty menu, then add roles to it')
    async def create(self, interaction: discord.Interaction, title: str, description: str = None,
                     exclusive: bool = False):
        menu_id = self.db.create_menu(interaction.guild.id, title[:100], description, exclusive)
        await interaction.response.send_message(
            f'Made menu **{title}** (#{menu_id}). Add roles with `/rolemenu add`, then `/rolemenu post`.',
            ephemeral=True)

    @rolemenu.command(name='add', description='Add a role to a menu')
    @app_commands.autocomplete(menu=_menu_autocomplete)
    @app_commands.describe(label='Button text, if different from the role name')
    async def add(self, interaction: discord.Interaction, menu: int, role: discord.Role, label: str = None):
        row = self.db.get_menu(menu, interaction.guild.id)
        if row is None:
            await interaction.response.send_message('No such menu. Pick one from the list.', ephemeral=True)
            return
        problem = self._check_menu_role(interaction, role)
        if problem is None and len(self.db.menu_roles(menu)) >= MAX_BUTTONS:
            problem = f'A menu holds at most {MAX_BUTTONS} roles. Make a second menu.'
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        self.db.add_menu_role(menu, role.id, (label or role.name)[:80])
        await interaction.response.send_message(f'Added {role.mention} to **{row["title"]}**.', ephemeral=True)
        await self._refresh(interaction.guild, menu)

    @rolemenu.command(name='remove', description='Take a role out of a menu')
    @app_commands.autocomplete(menu=_menu_autocomplete)
    async def remove(self, interaction: discord.Interaction, menu: int, role: discord.Role):
        row = self.db.get_menu(menu, interaction.guild.id)
        if row is None or not self.db.remove_menu_role(menu, role.id):
            await interaction.response.send_message("That role isn't in that menu.", ephemeral=True)
            return
        await interaction.response.send_message(f'Removed {role.mention} from **{row["title"]}**. '
                                                'People who already have the role keep it.', ephemeral=True)
        await self._refresh(interaction.guild, menu)

    async def _post(self, guild, menu_id, channel):
        menu = self.db.get_menu(menu_id, guild.id)
        embed, view = self._render(menu)
        try:
            message = await channel.send(embed=embed, view=view)
        except discord.HTTPException:
            return f"Menu **{menu['title']}** is saved, but I can't post in {channel.mention}. Fix that and run `/rolemenu post`."
        self.db.set_menu_message(menu_id, channel.id, message.id)
        return f"Posted **{menu['title']}** in {channel.mention}."

    @rolemenu.command(name='post', description='Post a menu in a channel')
    @app_commands.autocomplete(menu=_menu_autocomplete)
    async def post(self, interaction: discord.Interaction, menu: int, channel: discord.TextChannel = None):
        row = self.db.get_menu(menu, interaction.guild.id)
        if row is None:
            await interaction.response.send_message('No such menu. Pick one from the list.', ephemeral=True)
            return
        if not self.db.menu_roles(menu):
            await interaction.response.send_message('Add at least one role first.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send(await self._post(interaction.guild, menu, channel or interaction.channel))

    @rolemenu.command(name='list', description='Show the menus and their roles')
    async def list_command(self, interaction: discord.Interaction):
        menus = self.db.list_menus(interaction.guild.id)
        if not menus:
            await interaction.response.send_message('No menus yet. Try `/rolemenu quick`.', ephemeral=True)
            return
        lines = []
        for m in menus:
            roles = ', '.join(f'<@&{r["role_id"]}>' for r in self.db.menu_roles(m['id'])) or 'no roles yet'
            where = f'<#{m["channel_id"]}>' if m['message_id'] else 'not posted'
            lines.append(f'**{m["title"]}** (#{m["id"]}, {"pick one" if m["exclusive"] else "pick any"}, {where}): {roles}')
        await interaction.response.send_message('\n'.join(lines)[:2000], ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @rolemenu.command(name='delete', description='Delete a menu. The roles themselves are kept')
    @app_commands.autocomplete(menu=_menu_autocomplete)
    async def delete(self, interaction: discord.Interaction, menu: int):
        row = self.db.get_menu(menu, interaction.guild.id)
        if row is None:
            await interaction.response.send_message('No such menu.', ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        if row['message_id']:
            channel = interaction.guild.get_channel(row['channel_id'])
            try:
                if channel:
                    await channel.get_partial_message(row['message_id']).delete()
            except discord.HTTPException:
                pass
        self.db.delete_menu(menu)
        await interaction.followup.send(f'Deleted menu **{row["title"]}**. The roles still exist.')

    # ------------------------------------------------------------------
    # moderator tools
    # ------------------------------------------------------------------

    @role.command(name='give', description='Give someone a role')
    async def give(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await self._single(interaction, member, role, give=True)

    @role.command(name='take', description='Take a role away from someone')
    async def take(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await self._single(interaction, member, role, give=False)

    async def _single(self, interaction, member, role, give):
        problem = role_problem(interaction.guild, role, actor=interaction.user)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        try:
            if give:
                await member.add_roles(role, reason=f'By {interaction.user}')
            else:
                await member.remove_roles(role, reason=f'By {interaction.user}')
        except discord.HTTPException:
            await interaction.response.send_message("Discord wouldn't let me. Check my permissions.", ephemeral=True)
            return
        verb = 'now has' if give else 'no longer has'
        await interaction.response.send_message(f'{member.mention} {verb} {role.mention}.', ephemeral=True,
                                                allowed_mentions=discord.AllowedMentions.none())

    @role.command(name='bulk', description='Give or take a role for many people at once')
    @app_commands.describe(action='Give the role or take it away', role='The role to change',
                           target='Who it applies to', with_role='Only people who have this other role')
    @app_commands.choices(action=[app_commands.Choice(name='give', value='give'),
                                  app_commands.Choice(name='take', value='take')],
                          target=[app_commands.Choice(name='everyone (no bots)', value='humans'),
                                  app_commands.Choice(name='bots only', value='bots')])
    async def bulk(self, interaction: discord.Interaction, action: str, role: discord.Role,
                   target: str = 'humans', with_role: discord.Role = None):
        guild = interaction.guild
        problem = role_problem(guild, role, actor=interaction.user)
        if problem:
            await interaction.response.send_message(problem, ephemeral=True)
            return
        give = action == 'give'
        people = [m for m in guild.members
                  if m.bot == (target == 'bots')
                  and (with_role is None or with_role in m.roles)
                  and ((role not in m.roles) if give else (role in m.roles))]
        if not people:
            await interaction.response.send_message('Nobody to change.', ephemeral=True)
            return
        confirm = Confirm(interaction.user.id)
        scope = f' who have {with_role.name}' if with_role else ''
        await interaction.response.send_message(
            f'{"Give" if give else "Take"} **{role.name}** {"to" if give else "from"} {len(people)} people{scope}? '
            'This runs slowly on purpose to stay inside Discord\'s rate limits.', view=confirm, ephemeral=True)
        await confirm.wait()
        if not confirm.confirmed:
            return
        done = failed = 0
        for m in people:
            try:
                if give:
                    await m.add_roles(role, reason=f'Bulk by {interaction.user}')
                else:
                    await m.remove_roles(role, reason=f'Bulk by {interaction.user}')
                done += 1
            except discord.HTTPException:
                failed += 1
            await asyncio.sleep(0.3)
        text = f'Done: {done} changed' + (f', {failed} failed.' if failed else '.')
        try:
            await interaction.edit_original_response(content=text)
        except discord.HTTPException:
            log.info('Bulk role change finished: %s', text)


async def setup(bot):
    await bot.add_cog(Roles(bot))
    bot.add_dynamic_items(RoleButton)
