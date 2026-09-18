import os
from datetime import timedelta

DEBUG = False

# Script that pulls the latest constitution and regenerates
# templates/constitution-contents.html. Lives in the repo root.
CONSTITUTION_UPDATE_HOOK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'update-constitution.sh')

# Member login sessions. The site is served over https, so cookies are
# secure-only; override SESSION_COOKIE_SECURE = False in instance/config.py
# when developing over plain http.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = True
PERMANENT_SESSION_LIFETIME = timedelta(days=30)

# Set in instance/config.py:
#   SECRET_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
