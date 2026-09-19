# Avery Discord bot

A bot for the Avery House Discord server. It is a separate program from the website. It lives in this repo so the house's code is in one place.

## What it does

**Verification and real names**

1. Someone joins and gets the Unverified role, so they can see only the verify channel.
2. They press **Verify** and enter their real first and last name and their Caltech email.
3. The request appears in a private moderator channel with **Approve** and **Deny** buttons. It shows whether the email is on the roster, whether it is already used by another account, and how old the Discord account is.
4. On approval the bot sets their nickname to their real name, gives them the Member role, and removes Unverified. If the roster lists their class year or membership type, they get those roles too (a role named `2028` or `Class of 2028`, and `Full Member` or `Social Member`, if those roles exist).
5. If a verified member changes their nickname, the bot changes it back and tells them why. People who leave and rejoin get their name and roles back.

Moderators can verify someone directly, rename someone who goes by a different name, or remove a verification.

**Roles, the way Dyno does them**

- **Role menus.** A message with one button per role. Click to take a role, click again to drop it. A menu can be exclusive, so class year is pick-one. Only verified members can use them.
- **`/rank`** does the same by command.
- **`/role give`, `/role take`, `/role bulk`** for moderators.
- The role given on join is the Unverified role above.

The bot never hands out a role that carries moderator permissions through a menu. Moderators can only use it on roles below their own highest role, which is the same rule Discord applies, so it cannot be used to climb.

**House information:** `/constitution`, `/links`, `/rotation`.

## Commands

| Who | Command | What it does |
| --- | --- | --- |
| Everyone | `/verify` | Same as pressing the Verify button |
| Everyone | `/rank role` | Take or drop a self-serve role |
| Everyone | `/constitution query` | Search the constitution, with links to avery.caltech.edu |
| Everyone | `/links`, `/rotation` | House links |
| Moderators | `/verify-member member name [email]` | Verify someone without a request |
| Moderators | `/rename member name` | Change a verified member's recorded name |
| Moderators | `/unverify member`, `/whois member` | Remove or look up a verification |
| Moderators | `/role give`, `/role take`, `/role bulk` | Manage roles |
| Moderators | `/rolemenu quick`, `create`, `add`, `remove`, `post`, `list`, `delete` | Build role menus |
| Admins | `/verification setup`, `panel`, `status` | Configure verification |
| Admins | `/roster upload`, `/roster clear` | The member list requests are checked against |

"Moderators" means anyone with Manage Nicknames or Manage Roles. "Admins" means Manage Server. You can change who sees which command in **Server Settings > Integrations**.

## One-time Discord setup

1. Go to https://discord.com/developers/applications and click **New Application**.
2. Open the **Bot** tab. Click **Reset Token** and copy it. Treat it like a password. On the same page, turn on **Server Members Intent**. Without it the bot cannot see joins or nickname changes.
3. Open **OAuth2 > URL Generator**. Tick the scopes `bot` and `applications.commands`. Tick the permissions **Manage Roles**, **Manage Nicknames**, **View Channels**, **Send Messages** and **Embed Links**. Open the URL and add the bot to the Avery server.
4. In **Server Settings > Roles**, drag the bot's role above every role it should manage. Discord only lets a bot touch roles below its own. It can never rename the server owner.

## First run in the server

1. Make a private channel for moderators, a Member role, and an Unverified role. Set channel permissions so Unverified sees only the verify channel and Member sees the rest.
2. `/verification setup member_role:@Member mod_channel:#mod-verify unverified_role:@Unverified`
3. `/verification status` lists anything still wrong, such as a missing permission or a role above the bot.
4. `/roster upload` with a CSV of members. This step is optional but makes approvals much faster.
5. `/verification panel` in the verify channel posts the Verify button.
6. `/rolemenu quick title:Class year roles:2027, 2028, 2029, 2030 exclusive:True` makes the first role menu.
7. Turn off **Change Nickname** for @everyone in the server's role settings. Then people cannot edit their names at all, and the bot's change-it-back behaviour is only a backstop.

People already in the server verify the same way as new people.

### Roster file

A CSV with a header row. `name` and `email` are required. `year`, `membership` (`full` or `social`) and `discord` (username) are optional.

    name,email,year,membership,discord
    Ada Lovelace,ada@caltech.edu,2028,full,adal

If the `discord` column is filled in, it has to match the account for auto-approval. Auto-approval is off by default. Without it a moderator clicks Approve on every request, which is the safer choice, because typing someone's email does not prove you own it. Once the website's member login is live, linking through it can replace this step with real proof.

## Running it

    cd discord_bot
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # then paste the token into .env
    set -a; source .env; set +a
    python3 bot.py

On a Mac with Python from python.org, run `/Applications/Python 3.x/Install Certificates.command` once first, or the bot cannot reach Discord.

Tests need no token and no network:

    python3 -m unittest discover -s tests -t .

## Keeping it running on the server

The bot has to stay running. `avery-discord-bot.service` is a systemd unit modelled on the website's:

    sudo pip install -r /srv/avery-website/discord_bot/requirements.txt
    sudo mkdir -p /srv/avery-website/discord_bot/data
    sudo chown www-data /srv/avery-website/discord_bot/data
    sudo cp avery-discord-bot.service /etc/systemd/system/
    sudo systemctl enable --now avery-discord-bot.service

## Privacy

Names and emails are kept in `data/avery.db` on the machine that runs the bot. That folder and `.env` are ignored by git. Roster uploads go straight from Discord to the bot and are not posted in any channel. Only moderators can look up who someone is.
