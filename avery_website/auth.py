"""Members-only area.

Sign-in is Google OAuth (any Google account, normally a Caltech one). After
signing in, the account's email has to appear in instance/members.txt or the
person is turned away. Files dropped into instance/files/ and lines in
instance/links.txt show up on the members page.
"""
import datetime
import functools
import os

from authlib.integrations.flask_client import OAuth
from flask import (abort, redirect, render_template, send_from_directory,
                   session, url_for)

from .app import app

oauth = OAuth(app)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile', 'prompt': 'select_account'},
)


def _instance(*parts):
    return os.path.join(app.instance_path, *parts)


def load_members():
    """Emails allowed in, one per line in instance/members.txt. Blank lines
    and anything after a # are ignored."""
    try:
        with open(_instance('members.txt'), encoding='utf-8') as f:
            emails = {line.split('#', 1)[0].strip().lower() for line in f}
    except OSError:
        return set()
    emails.discard('')
    return emails


def google_configured():
    return bool(app.config.get('GOOGLE_CLIENT_ID')
                and app.config.get('GOOGLE_CLIENT_SECRET'))


def current_member():
    """The signed-in member, or None. Re-checks the list on every request so
    removing someone from members.txt takes effect immediately."""
    user = session.get('user')
    if user and user.get('email', '') in load_members():
        return user
    return None


def member_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not current_member():
            return redirect(url_for('members_login'))
        return view(*args, **kwargs)
    return wrapped


@app.context_processor
def inject_member():
    return {'member': current_member()}


@app.template_filter('filesize')
def filesize(n):
    for unit in ('B', 'KB', 'MB', 'GB'):
        if n < 1024 or unit == 'GB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024


def list_files():
    out = []
    try:
        entries = sorted(os.scandir(_instance('files')), key=lambda e: e.name.lower())
    except OSError:
        return out
    for e in entries:
        if e.is_file() and not e.name.startswith('.'):
            st = e.stat()
            out.append({'name': e.name, 'size': st.st_size,
                        'modified': datetime.date.fromtimestamp(st.st_mtime)})
    return out


def list_links():
    """Lines of "Title | https://..." in instance/links.txt."""
    out = []
    try:
        with open(_instance('links.txt'), encoding='utf-8') as f:
            lines = f.read().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.split('#', 1)[0].strip()
        if '|' in line:
            title, url = (s.strip() for s in line.split('|', 1))
            if title and url:
                out.append({'title': title, 'url': url})
    return out


@app.route('/members/login')
def members_login():
    if current_member():
        return redirect(url_for('members'))
    return render_template('members_login.html',
                           configured=google_configured(),
                           denied=session.pop('denied_email', None))


@app.route('/members/login/google')
def members_login_google():
    if not google_configured():
        abort(503)
    return oauth.google.authorize_redirect(url_for('members_auth', _external=True))


@app.route('/members/auth')
def members_auth():
    token = oauth.google.authorize_access_token()
    info = token.get('userinfo') or oauth.google.userinfo()
    email = (info.get('email') or '').strip().lower()
    session.clear()
    if not info.get('email_verified') or email not in load_members():
        session['denied_email'] = email
        return redirect(url_for('members_login'))
    session.permanent = True
    session['user'] = {'email': email, 'name': info.get('name') or email}
    return redirect(url_for('members'))


@app.route('/members/logout')
def members_logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/members/')
@member_required
def members():
    return render_template('members.html', files=list_files(), links=list_links())


@app.route('/members/files/<path:name>')
@member_required
def members_file(name):
    return send_from_directory(_instance('files'), name)
