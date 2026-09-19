"""Everything the bot remembers, in one small SQLite file (data/averite.db).

Holds names and emails, so the file stays on the server and out of git.
"""
import os
import sqlite3
import time
from pathlib import Path

DEFAULT_PATH = Path(__file__).parent / 'data' / 'averite.db'

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    guild_id INTEGER NOT NULL, key TEXT NOT NULL, value TEXT,
    PRIMARY KEY (guild_id, key));
CREATE TABLE IF NOT EXISTS roster (
    guild_id INTEGER NOT NULL, email TEXT NOT NULL, name TEXT NOT NULL,
    year TEXT, membership TEXT, discord TEXT,
    PRIMARY KEY (guild_id, email));
CREATE TABLE IF NOT EXISTS verified (
    guild_id INTEGER NOT NULL, user_id INTEGER NOT NULL, name TEXT NOT NULL,
    email TEXT, verified_at INTEGER NOT NULL, approved_by INTEGER,
    PRIMARY KEY (guild_id, user_id));
CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending', created_at INTEGER NOT NULL,
    decided_by INTEGER);
CREATE TABLE IF NOT EXISTS menus (
    id INTEGER PRIMARY KEY AUTOINCREMENT, guild_id INTEGER NOT NULL,
    title TEXT NOT NULL, description TEXT, exclusive INTEGER NOT NULL DEFAULT 0,
    channel_id INTEGER, message_id INTEGER);
CREATE TABLE IF NOT EXISTS menu_roles (
    menu_id INTEGER NOT NULL, role_id INTEGER NOT NULL, label TEXT NOT NULL,
    position INTEGER NOT NULL, PRIMARY KEY (menu_id, role_id));
"""


class Database:
    def __init__(self, path=None):
        path = str(path or os.environ.get('AVERY_BOT_DB') or DEFAULT_PATH)
        if path != ':memory:':
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self):
        self.conn.close()

    def _run(self, sql, args=()):
        with self.conn:
            return self.conn.execute(sql, args)

    # ---- settings ----
    def set(self, guild_id, key, value):
        self._run('INSERT INTO settings VALUES (?, ?, ?) ON CONFLICT (guild_id, key) '
                  'DO UPDATE SET value = excluded.value',
                  (guild_id, key, None if value is None else str(value)))

    def get(self, guild_id, key, default=None):
        row = self._run('SELECT value FROM settings WHERE guild_id = ? AND key = ?',
                        (guild_id, key)).fetchone()
        return default if row is None or row['value'] is None else row['value']

    def get_int(self, guild_id, key):
        value = self.get(guild_id, key)
        return int(value) if value not in (None, '') else None

    def get_bool(self, guild_id, key, default=False):
        value = self.get(guild_id, key)
        return default if value is None else value == 'True'

    # ---- roster ----
    def replace_roster(self, guild_id, rows):
        with self.conn:
            self.conn.execute('DELETE FROM roster WHERE guild_id = ?', (guild_id,))
            self.conn.executemany(
                'INSERT OR REPLACE INTO roster VALUES (?, ?, ?, ?, ?, ?)',
                [(guild_id, r['email'], r['name'], r.get('year'), r.get('membership'),
                  r.get('discord')) for r in rows])

    def roster_lookup(self, guild_id, email):
        return self._run('SELECT * FROM roster WHERE guild_id = ? AND email = ?',
                         (guild_id, email)).fetchone()

    def roster_count(self, guild_id):
        return self._run('SELECT COUNT(*) FROM roster WHERE guild_id = ?', (guild_id,)).fetchone()[0]

    # ---- verified members ----
    def set_verified(self, guild_id, user_id, name, email, approved_by):
        self._run('INSERT INTO verified VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT (guild_id, user_id) '
                  'DO UPDATE SET name = excluded.name, email = COALESCE(excluded.email, verified.email)',
                  (guild_id, user_id, name, email, int(time.time()), approved_by))

    def get_verified(self, guild_id, user_id):
        return self._run('SELECT * FROM verified WHERE guild_id = ? AND user_id = ?',
                         (guild_id, user_id)).fetchone()

    def verified_by_email(self, guild_id, email):
        return self._run('SELECT * FROM verified WHERE guild_id = ? AND email = ?',
                         (guild_id, email)).fetchone()

    def remove_verified(self, guild_id, user_id):
        return self._run('DELETE FROM verified WHERE guild_id = ? AND user_id = ?',
                         (guild_id, user_id)).rowcount

    def verified_count(self, guild_id):
        return self._run('SELECT COUNT(*) FROM verified WHERE guild_id = ?', (guild_id,)).fetchone()[0]

    # ---- verification requests ----
    def create_request(self, guild_id, user_id, name, email):
        return self._run('INSERT INTO requests (guild_id, user_id, name, email, created_at) '
                         'VALUES (?, ?, ?, ?, ?)',
                         (guild_id, user_id, name, email, int(time.time()))).lastrowid

    def get_request(self, request_id):
        return self._run('SELECT * FROM requests WHERE id = ?', (request_id,)).fetchone()

    def pending_request_for(self, guild_id, user_id):
        return self._run("SELECT * FROM requests WHERE guild_id = ? AND user_id = ? AND status = 'pending'",
                         (guild_id, user_id)).fetchone()

    def decide_request(self, request_id, status, decided_by):
        """True only for the first decision, so two moderators clicking at once
        cannot both approve."""
        return self._run("UPDATE requests SET status = ?, decided_by = ? WHERE id = ? AND status = 'pending'",
                         (status, decided_by, request_id)).rowcount == 1

    def pending_count(self, guild_id):
        return self._run("SELECT COUNT(*) FROM requests WHERE guild_id = ? AND status = 'pending'",
                         (guild_id,)).fetchone()[0]

    # ---- role menus ----
    def create_menu(self, guild_id, title, description, exclusive):
        return self._run('INSERT INTO menus (guild_id, title, description, exclusive) VALUES (?, ?, ?, ?)',
                         (guild_id, title, description, int(bool(exclusive)))).lastrowid

    def get_menu(self, menu_id, guild_id=None):
        row = self._run('SELECT * FROM menus WHERE id = ?', (menu_id,)).fetchone()
        if row is not None and guild_id is not None and row['guild_id'] != guild_id:
            return None
        return row

    def list_menus(self, guild_id):
        return self._run('SELECT * FROM menus WHERE guild_id = ? ORDER BY id', (guild_id,)).fetchall()

    def set_menu_message(self, menu_id, channel_id, message_id):
        self._run('UPDATE menus SET channel_id = ?, message_id = ? WHERE id = ?',
                  (channel_id, message_id, menu_id))

    def delete_menu(self, menu_id):
        with self.conn:
            self.conn.execute('DELETE FROM menu_roles WHERE menu_id = ?', (menu_id,))
            self.conn.execute('DELETE FROM menus WHERE id = ?', (menu_id,))

    def add_menu_role(self, menu_id, role_id, label):
        position = self._run('SELECT COALESCE(MAX(position), 0) + 1 FROM menu_roles WHERE menu_id = ?',
                             (menu_id,)).fetchone()[0]
        self._run('INSERT INTO menu_roles VALUES (?, ?, ?, ?) ON CONFLICT (menu_id, role_id) '
                  'DO UPDATE SET label = excluded.label', (menu_id, role_id, label, position))

    def remove_menu_role(self, menu_id, role_id):
        return self._run('DELETE FROM menu_roles WHERE menu_id = ? AND role_id = ?',
                         (menu_id, role_id)).rowcount

    def menu_roles(self, menu_id):
        return self._run('SELECT * FROM menu_roles WHERE menu_id = ? ORDER BY position', (menu_id,)).fetchall()

    def menu_for_role(self, guild_id, role_id):
        return self._run('SELECT m.* FROM menus m JOIN menu_roles r ON r.menu_id = m.id '
                         'WHERE m.guild_id = ? AND r.role_id = ? ORDER BY m.id', (guild_id, role_id)).fetchone()

    def self_assignable(self, guild_id):
        return self._run('SELECT r.role_id, r.label, m.title FROM menus m JOIN menu_roles r ON r.menu_id = m.id '
                         'WHERE m.guild_id = ? ORDER BY m.id, r.position', (guild_id,)).fetchall()
