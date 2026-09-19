"""Rules with no Discord dependency, so they can be unit tested."""
import csv
import io
import re

NICK_MAX = 32  # Discord's nickname limit
_EMAIL = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def clean_name(raw):
    """Tidy a name for use as a nickname: single spaces, none of the
    characters Discord rejects in nicknames, at most 32 characters."""
    name = re.sub(r'[@#:`]', '', raw or '')
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:NICK_MAX].rstrip()


def name_problem(name):
    """Why this can't be a real name, or None if it looks fine."""
    letters = sum(ch.isalpha() for ch in name)
    if letters < 2:
        return 'Enter your real first and last name.'
    if len(name.split()) < 2:
        return 'Enter your first and last name, not just one word.'
    return None


def normalize_email(raw):
    return (raw or '').strip().lower()


def valid_email(email):
    return bool(_EMAIL.match(email))


def is_caltech(email):
    domain = email.rsplit('@', 1)[-1]
    return domain == 'caltech.edu' or domain.endswith('.caltech.edu')


_HEADERS = {
    'name': 'name', 'full name': 'name', 'fullname': 'name',
    'email': 'email', 'e-mail': 'email', 'caltech email': 'email',
    'year': 'year', 'class': 'year', 'class year': 'year', 'grad year': 'year',
    'membership': 'membership', 'type': 'membership', 'member type': 'membership',
    'discord': 'discord', 'discord username': 'discord',
}


def parse_roster(text):
    """Read a roster CSV. Needs name and email columns; year, membership and
    discord are optional. Returns (rows, problems)."""
    reader = csv.DictReader(io.StringIO(text.lstrip('﻿')))
    fields = {f: _HEADERS.get((f or '').strip().lower()) for f in (reader.fieldnames or [])}
    if 'name' not in fields.values() or 'email' not in fields.values():
        return [], ['The file needs a header row with at least "name" and "email" columns.']
    rows, problems, seen = [], [], set()
    for number, raw in enumerate(reader, start=2):
        row = {fields[k]: (v or '').strip() for k, v in raw.items() if fields.get(k)}
        email, name = normalize_email(row.get('email')), clean_name(row.get('name'))
        if not email and not name:
            continue
        if not valid_email(email):
            problems.append(f'Row {number}: "{row.get("email", "")}" is not an email address.')
            continue
        if not name:
            problems.append(f'Row {number}: no name for {email}.')
            continue
        if email in seen:
            problems.append(f'Row {number}: {email} appears twice. Kept the first one.')
            continue
        seen.add(email)
        rows.append({'email': email, 'name': name, 'year': row.get('year') or None,
                     'membership': (row.get('membership') or '').lower() or None,
                     'discord': (row.get('discord') or '').lstrip('@').lower() or None})
    return rows, problems


def plan_toggle(member_role_ids, menu_role_ids, clicked_id, exclusive):
    """What clicking a role button should do. Returns (add, remove) as lists of
    role ids. Clicking a role you have removes it. In an exclusive menu, such
    as class year, taking a role drops the others from the same menu."""
    if clicked_id in member_role_ids:
        return [], [clicked_id]
    remove = [r for r in menu_role_ids if exclusive and r != clicked_id and r in member_role_ids]
    return [clicked_id], remove
