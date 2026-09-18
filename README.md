# Avery Website

The official Avery House website, https://avery.caltech.edu. A small Flask app served by uWSGI behind nginx. The branch `master` is what runs in production. The old `maximal` branch has extra features (music queue, Facebook gallery, Google Calendar events) that depend on external APIs and are not maintained.

## Local development

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    ./update-constitution.sh          # needs git + pandoc; builds the constitution page
    flask --app avery_website.main run --debug

Then open http://127.0.0.1:5000/.

## Making changes

- Page content lives in `avery_website/templates/`. Every page extends `layout.html`, which has the header, nav, and footer.
- Styles are plain CSS in `avery_website/static/css/all.css`. There is no build step.
- **Home page photo:** replace `avery_website/static/img/beach.jpg` with any 4:3 photo of the house.
- **Rotation video:** in `templates/rotation_video.html`, put the new year and its YouTube video ID first in the `videos` list.
- **Constitution:** the text comes from the separate [constitution repo](https://github.com/averyhouse/constitution). Edit `constitution.md` there, then run `./update-constitution.sh` here (or visit `/constitution/update` on the live site) to regenerate `templates/constitution-contents.html`.

Do code changes locally, push to GitHub, then pull on the server.

## Members area

`/members/` is only visible to house members. People sign in with Google, and the site checks their email against a list that ExComm maintains. There are no passwords to manage.

Everything for it lives in the `instance/` folder in the repo root **on the server**. That folder is ignored by git, so the member list and any private files never end up on GitHub.

| File | What it does |
| --- | --- |
| `instance/members.txt` | One email per line. Only these accounts get in. Edits take effect immediately. |
| `instance/files/` | Drop PDFs, images, or documents here and they are listed on the members page. |
| `instance/links.txt` | Optional. Lines of `Title | https://...` shown above the files. |
| `instance/config.py` | Secret key and the Google sign-in credentials. |

Each one has an `.example` file next to it to copy from.

### One-time Google setup

1. Sign in to https://console.cloud.google.com with a Caltech Google account the house controls, and create a project.
2. Under **APIs & Services > OAuth consent screen**, choose user type **Internal** if offered. That limits sign-in to caltech.edu accounts. Otherwise choose External and publish the app.
3. Under **Credentials > Create credentials > OAuth client ID**, pick **Web application** and add this authorized redirect URI exactly: `https://avery.caltech.edu/members/auth`. For local testing also add `http://127.0.0.1:5000/members/auth`.
4. Copy `instance/config.example.py` to `instance/config.py` and fill in the client ID, the client secret, and a random `SECRET_KEY`.
5. Copy `instance/members.example.txt` to `instance/members.txt`, put the real emails in, and restart the service.

nginx must pass `X-Forwarded-Proto` to the app, which the stock Ubuntu `proxy_params` file already does. Without it Google rejects the sign-in with a redirect mismatch.

## Deploying on the server

The app lives in `/srv/avery-website` and runs as the `www-data` user under `avery-website.service`.

    cd /srv/avery-website
    sudo -u www-data git pull
    # instance/ is not in git: copy it over by hand the first time, and keep it owned by www-data
    sudo pip install -r requirements.txt     # only needed when requirements.txt changed
    sudo -u www-data ./update-constitution.sh # only needed when the constitution changed
    sudo systemctl restart avery-website.service

If you pulled as your own user instead of `www-data`, fix ownership afterwards with `sudo chown -R www-data:webadmin /srv/avery-website`.

## First-time server setup

1. Install nginx, uwsgi with the python3 plugin, git, and pandoc.
2. Clone this repo to `/srv/avery-website` and install `requirements.txt`.
3. Copy `avery-website.nginx.conf` to `/etc/nginx/sites-available/` and symlink it into `sites-enabled/`.
4. Copy `avery-website.service` to `/etc/systemd/system/`, then `systemctl enable --now avery-website.service`.
