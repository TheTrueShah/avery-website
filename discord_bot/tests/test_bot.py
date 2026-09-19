"""Run from discord_bot/:  python -m unittest discover -s tests -t .

Nothing here talks to Discord. The flows run against the stand-ins in fakes.py.
"""
import asyncio
import unittest
from types import SimpleNamespace

import discord

from cogs.common import is_elevated, role_problem
from cogs.roles import Roles
from cogs.verification import Verification
from db import Database
from logic import clean_name, name_problem, parse_roster, plan_toggle
from tests.fakes import FakeMember, FakeRole, interaction, server


class Logic(unittest.TestCase):
    def test_clean_name(self):
        self.assertEqual(clean_name('  Ryan   Shahbaba '), 'Ryan Shahbaba')
        self.assertEqual(clean_name('@every#one: `hi`'), 'everyone hi')
        self.assertLessEqual(len(clean_name('A' * 20 + ' ' + 'B' * 40)), 32)

    def test_name_problem(self):
        self.assertIsNone(name_problem('Ada Lovelace'))
        self.assertIsNone(name_problem('Juan de la Cruz'))
        self.assertIsNotNone(name_problem('xXgamerXx'))
        self.assertIsNotNone(name_problem('12 34'))

    def test_roster_parsing(self):
        text = ('﻿Full Name,Caltech Email,Class,Type,Discord\n'
                'Ada Lovelace,ADA@caltech.edu,2028,Full,@ada\n'
                'Bad Row,not-an-email,2027,,\n'
                'Ada Again,ada@caltech.edu,2028,,\n'
                ',,,,\n'
                'Alan Turing,alan@caltech.edu,,social,\n')
        rows, problems = parse_roster(text)
        self.assertEqual([r['email'] for r in rows], ['ada@caltech.edu', 'alan@caltech.edu'])
        self.assertEqual(rows[0], {'email': 'ada@caltech.edu', 'name': 'Ada Lovelace', 'year': '2028',
                                   'membership': 'full', 'discord': 'ada'})
        self.assertEqual(len(problems), 2)
        self.assertEqual(parse_roster('first,last\nA,B\n')[0], [])

    def test_plan_toggle(self):
        years = [1, 2, 3]
        self.assertEqual(plan_toggle({1}, years, 2, exclusive=True), ([2], [1]))
        self.assertEqual(plan_toggle({1}, years, 2, exclusive=False), ([2], []))
        self.assertEqual(plan_toggle({1, 9}, years, 1, exclusive=True), ([], [1]))


class Storage(unittest.TestCase):
    def test_request_decided_once(self):
        db = Database(':memory:')
        self.addCleanup(db.close)
        rid = db.create_request(1, 2, 'Ada Lovelace', 'ada@caltech.edu')
        self.assertTrue(db.decide_request(rid, 'approved', 7))
        self.assertFalse(db.decide_request(rid, 'denied', 8))
        self.assertEqual(db.get_request(rid)['status'], 'approved')

    def test_rename_keeps_email(self):
        db = Database(':memory:')
        self.addCleanup(db.close)
        db.set_verified(1, 2, 'Ada Lovelace', 'ada@caltech.edu', 7)
        db.set_verified(1, 2, 'Ada King', None, 7)
        self.assertEqual(dict(db.get_verified(1, 2))['email'], 'ada@caltech.edu')
        self.assertEqual(db.get_verified(1, 2)['name'], 'Ada King')

    def test_menus_are_per_server(self):
        db = Database(':memory:')
        self.addCleanup(db.close)
        mid = db.create_menu(1, 'Class year', None, True)
        self.assertIsNotNone(db.get_menu(mid, 1))
        self.assertIsNone(db.get_menu(mid, 2))


class Safety(unittest.TestCase):
    def test_role_problem(self):
        g, roles, everyone = server()
        mod = FakeMember(3, 'mod', g, [everyone, roles['Member']], moderator=True)
        self.assertIsNone(role_problem(g, roles['2028']))
        self.assertIn('above', role_problem(g, roles['ExComm']))            # above the bot
        self.assertIsNotNone(role_problem(g, everyone))
        self.assertIsNotNone(role_problem(g, roles['Member'], actor=mod))    # not below the mod's own top role
        self.assertIsNone(role_problem(g, roles['2028'], actor=mod))
        owner = FakeMember(g.owner_id, 'owner', g, [everyone])
        self.assertIsNone(role_problem(g, roles['Member'], actor=owner))
        self.assertTrue(is_elevated(roles['ExComm']))
        self.assertFalse(is_elevated(roles['2028']))


class Flows(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.g, self.roles, self.everyone = server()
        self.db = Database(':memory:')
        bot = SimpleNamespace(db=self.db, intents=SimpleNamespace(members=True))
        self.v, self.r = Verification(bot), Roles(bot)
        self.db.set(1, 'member_role', self.roles['Member'].id)
        self.db.set(1, 'unverified_role', self.roles['Unverified'].id)
        self.db.set(1, 'mod_channel', 700)
        self.db.replace_roster(1, [{'email': 'ada@caltech.edu', 'name': 'Ada Lovelace', 'year': '2028',
                                    'membership': 'full', 'discord': None}])
        self.addCleanup(self.db.close)
        self.new = FakeMember(42, 'xX_gamer_Xx', self.g, [self.everyone, self.roles['Unverified']])
        self.mod = FakeMember(7, 'mod', self.g, [self.everyone, self.roles['ExComm']], moderator=True)
        self.g.members = [self.new, self.mod, self.g.me]

    def names(self, member):
        return {r.name for r in member.roles}

    async def test_request_goes_to_moderators_then_approval_sets_real_name(self):
        i = interaction(self.g, self.new)
        await self.v.submit(i, 'ada  lovelace', 'Ada@Caltech.edu')
        self.assertIn('moderator', i.response.sent[0])
        embed, view = self.g.channels[700].sent[0]
        self.assertIn('On the roster as **Ada Lovelace**', embed.fields[-1].value)
        self.assertEqual([c.custom_id for c in view.children], ['avery:verify:approve:1', 'avery:verify:deny:1'])
        self.assertEqual(self.new.nick, None)                                  # nothing happens before approval

        click = interaction(self.g, self.mod)
        await self.v.decide(click, 'approve', 1)
        self.assertEqual(self.new.nick, 'Ada Lovelace')                        # roster spelling, not what was typed
        self.assertEqual(self.names(self.new), {'@everyone', 'Member', '2028', 'Full Member'})
        self.assertIsNone(click.response.edited['view'])                       # buttons removed
        self.assertTrue(self.new.dms)

        again = interaction(self.g, self.mod)
        await self.v.decide(again, 'deny', 1)
        self.assertIn('already handled', again.response.sent[0])
        self.assertIn('Member', self.names(self.new))

    async def test_only_moderators_can_approve(self):
        await self.v.submit(interaction(self.g, self.new), 'Ada Lovelace', 'ada@caltech.edu')
        other = FakeMember(43, 'rando', self.g, [self.everyone])
        click = interaction(self.g, other)
        await self.v.decide(click, 'approve', 1)
        self.assertIn('Only moderators', click.response.sent[0])
        self.assertIsNone(self.db.get_verified(1, 42))

    async def test_auto_approve_only_for_clean_roster_matches(self):
        self.db.set(1, 'auto_approve', True)
        i = interaction(self.g, self.new)
        await self.v.submit(i, 'Ada Lovelace', 'ada@caltech.edu')
        self.assertIn("You're verified as **Ada Lovelace**", i.response.sent[0])
        self.assertEqual(self.g.channels[700].sent, [])

        # A second account claiming the same email is never auto-approved.
        imposter = FakeMember(44, 'imposter', self.g, [self.everyone])
        self.g.members.append(imposter)
        j = interaction(self.g, imposter)
        await self.v.submit(j, 'Ada Lovelace', 'ada@caltech.edu')
        self.assertIsNone(self.db.get_verified(1, 44))
        embed, _ = self.g.channels[700].sent[0]
        self.assertIn('already used by <@42>', embed.fields[-1].value)

        # Not on the roster: goes to moderators too.
        k = interaction(self.g, FakeMember(45, 'newbie', self.g, [self.everyone]))
        await self.v.submit(k, 'Alan Turing', 'alan@gmail.com')
        embed, _ = self.g.channels[700].sent[1]
        self.assertIn('Not on the roster', embed.fields[-1].value)
        self.assertIn('Not a Caltech address', embed.fields[-1].value)

    async def test_bad_input_is_rejected(self):
        i = interaction(self.g, self.new)
        await self.v.submit(i, 'gamer', 'ada@caltech.edu')
        await self.v.submit(i, 'Ada Lovelace', 'not an email')
        self.assertEqual(len(i.response.sent), 2)
        self.assertEqual(self.g.channels[700].sent, [])

    async def test_nickname_changes_are_reverted(self):
        self.db.set_verified(1, 42, 'Ada Lovelace', 'ada@caltech.edu', 7)
        before = SimpleNamespace(nick='Ada Lovelace')
        self.new.nick = 'xX_gamer_Xx'
        await self.v.on_member_update(before, self.new)
        self.assertEqual(self.new.nick, 'Ada Lovelace')
        self.assertIn('real names', self.new.dms[0])

        self.new.calls.clear()                                                 # the bot's own edit must not loop
        await self.v.on_member_update(SimpleNamespace(nick='xX_gamer_Xx'), self.new)
        self.assertEqual(self.new.calls, [])

        self.db.set(1, 'enforce_names', False)                                 # policy switched off
        self.new.nick = 'whatever'
        await self.v.on_member_update(before, self.new)
        self.assertEqual(self.new.nick, 'whatever')

    async def test_unverified_people_are_left_alone(self):
        self.new.nick = 'anything'
        await self.v.on_member_update(SimpleNamespace(nick=None), self.new)
        self.assertEqual(self.new.nick, 'anything')

    async def test_owner_nickname_failure_is_reported_not_raised(self):
        owner = FakeMember(self.g.owner_id, 'owner', self.g, [self.everyone], locked=True)
        notes = await self.v.apply_verified(owner, 'Grace Hopper', None, None, approved_by=7)
        self.assertTrue(any('nickname' in n for n in notes))
        self.assertIn('Member', self.names(owner))

    async def test_join_gets_unverified_and_rejoin_is_restored(self):
        fresh = FakeMember(50, 'fresh', self.g, [self.everyone])
        await self.v.on_member_join(fresh)
        self.assertEqual(self.names(fresh), {'@everyone', 'Unverified'})

        self.db.set_verified(1, 51, 'Ada Lovelace', 'ada@caltech.edu', 7)
        back = FakeMember(51, 'ada', self.g, [self.everyone])
        await self.v.on_member_join(back)
        self.assertEqual(back.nick, 'Ada Lovelace')
        self.assertIn('Member', self.names(back))

    async def test_role_menu_buttons(self):
        menu = self.db.create_menu(1, 'Class year', None, True)
        for name in ('2027', '2028'):
            self.db.add_menu_role(menu, self.roles[name].id, name)

        blocked = interaction(self.g, self.new)                                # not verified yet
        await self.r.toggle(blocked, menu, self.roles['2028'].id)
        self.assertIn('Verify first', blocked.response.sent[0])

        member = FakeMember(60, 'ada', self.g, [self.everyone, self.roles['Member'], self.roles['2027']])
        i = interaction(self.g, member)
        await self.r.toggle(i, menu, self.roles['2028'].id)                    # exclusive: swaps the year
        self.assertEqual(self.names(member), {'@everyone', 'Member', '2028'})
        await self.r.toggle(interaction(self.g, member), menu, self.roles['2028'].id)   # click again: drop it
        self.assertEqual(self.names(member), {'@everyone', 'Member'})

        self.db.add_menu_role(menu, self.roles['ExComm'].id, 'ExComm')         # staff roles are never self-serve
        sneaky = interaction(self.g, member)
        await self.r.toggle(sneaky, menu, self.roles['ExComm'].id)
        self.assertNotIn('ExComm', self.names(member))


class Smoke(unittest.IsolatedAsyncioTestCase):
    async def test_every_command_loads_and_serializes(self):
        from bot import EXTENSIONS, Averite
        bot = Averite(db=Database(':memory:'))
        for extension in EXTENSIONS:
            await bot.load_extension(extension)
        payload = [c.to_dict(bot.tree) for c in bot.tree.get_commands()]
        names = sorted(c['name'] for c in payload)
        self.assertEqual(names, ['constitution', 'links', 'rank', 'rename', 'role', 'rolemenu', 'roster',
                                 'rotation', 'unverify', 'verification', 'verify', 'verify-member', 'whois'])
        sub = {c['name']: sorted(o['name'] for o in c.get('options', []) if o['type'] == 1) for c in payload}
        self.assertEqual(sub['rolemenu'], ['add', 'create', 'delete', 'list', 'post', 'quick', 'remove'])
        self.assertEqual(sub['role'], ['bulk', 'give', 'take'])
        self.assertEqual(sub['verification'], ['panel', 'setup', 'status'])

        def walk(node, path):
            here = f'{path} {node["name"]}'.strip()
            self.assertRegex(node['name'], r'^[-_a-z0-9]{1,32}$', here)
            self.assertTrue(1 <= len(node['description']) <= 100, f'{here}: description is {len(node["description"])} chars')
            for choice in node.get('choices', []):
                self.assertLessEqual(len(choice['name']), 100, here)
            self.assertLessEqual(len(node.get('options', [])), 25, here)
            required = [o.get('required', False) for o in node.get('options', []) if o['type'] > 2]
            self.assertEqual(required, sorted(required, reverse=True), f'{here}: required options must come first')
            for option in node.get('options', []):
                walk(option, here)
        for command in payload:
            walk(command, '')

        db = bot.db
        for cog in list(bot.cogs):
            await bot.remove_cog(cog)
        await bot.close()
        db.close()


if __name__ == '__main__':
    unittest.main()
