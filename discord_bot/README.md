# Avery Discord bot

A small bot for the Avery House Discord server. It is a separate program from the website. It just lives in this repo so the house's code is in one place.

## What it does today

| Command | What happens |
| --- | --- |
| `/constitution query` | Searches the constitution and replies with the matching sections, each linked to the right spot on avery.caltech.edu. The text is pulled from the [constitution repo](https://github.com/averyhouse/constitution) and refreshed every 6 hours. |
| `/links` | Website, Instagram, YouTube, GitHub. |
| `/rotation` | Link to the latest rotation video. |

## One-time Discord setup

1. Go to https://discord.com/developers/applications and click **New Application**. Name it something like "Avery".
2. Open the **Bot** tab, click **Reset Token**, and copy the token. Treat it like a password.
3. Open **OAuth2 > URL Generator**. Tick the scopes `bot` and `applications.commands`, and the bot permissions **Send Messages** and **Embed Links**. Open the generated URL and add the bot to the Avery server. You need Manage Server permission there.

## Running it

    cd discord_bot
    python3 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env        # then paste the token into .env
    set -a; source .env; set +a
    python3 bot.py

On a Mac with Python from python.org, run `/Applications/Python 3.x/Install Certificates.command` once first, or the bot cannot reach Discord.

You can try the constitution search without Discord at all:

    python3 constitution.py room picks

## Keeping it running on the server

The bot has to stay running to answer commands. `avery-discord-bot.service` is a systemd unit modelled on the website's:

    sudo pip install -r /srv/avery-website/discord_bot/requirements.txt
    sudo cp avery-discord-bot.service /etc/systemd/system/
    sudo systemctl enable --now avery-discord-bot.service

## Ideas for next

- **Member verification.** Give a "Member" role to people on the website's member list, so the Discord and the website share one source of truth.
- **Event reminders** posted to a channel from the house Google Calendar.
- **Announcements** when new minutes or a constitution amendment are published.
