import os
import re

from flask import redirect, render_template, url_for

from .app import app, constitution_hook


def constitution_toc():
    """Article headings pulled out of the pandoc-generated constitution."""
    path = os.path.join(app.root_path, 'templates', 'constitution-contents.html')
    try:
        with open(path, encoding='utf-8') as f:
            html = f.read()
    except OSError:
        return []
    return [{'id': id_, 'title': re.sub(r'\s+', ' ', title).strip()}
            for id_, title in re.findall(r'<h1 id="([^"]+)">(.*?)</h1>', html, re.S)]


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/events/')
def events():
    return render_template('events.html')


@app.route('/constitution/')
def constitution():
    return render_template('constitution.html', toc=constitution_toc())


@app.route('/constitution/update', methods=["GET", "POST"])
def constitution_update():
    constitution_hook(wait=True)
    return redirect(url_for('constitution'))


@app.route('/rotation_video/')
def rotation_video():
    return render_template('rotation_video.html')


@app.errorhandler(404)
def page_not_found(err):
    return render_template('404.html'), 404
