import os
import secrets
import subprocess
import sys

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.config.from_pyfile('config.py')
# Server-specific settings (secret key, Google OAuth client) live outside git
# in <repo>/instance/config.py. See instance/config.example.py.
app.config.from_pyfile(os.path.join(app.instance_path, 'config.py'), silent=True)

if not app.config.get('SECRET_KEY'):
    print("avery-website: SECRET_KEY is not set in instance/config.py; using a "
          "random one, so member logins will reset whenever the app restarts.",
          file=sys.stderr)
    app.config['SECRET_KEY'] = secrets.token_hex(32)

# nginx sits in front of the app; trust its X-Forwarded-* headers so that
# url_for(_external=True) builds https:// URLs (needed for Google sign-in).
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


def constitution_hook(wait=False):
    """Run the script that pulls the constitution repo and regenerates
    templates/constitution-contents.html. Errors are swallowed so a missing
    script, git, or pandoc never takes the site down."""
    hook = app.config.get("CONSTITUTION_UPDATE_HOOK")
    if not hook:
        return
    try:
        if wait:
            subprocess.run([hook], timeout=120)
        else:
            subprocess.Popen([hook])
    except (OSError, subprocess.SubprocessError):
        pass
