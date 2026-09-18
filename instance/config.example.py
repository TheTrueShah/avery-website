# Copy this file to instance/config.py on the server and fill it in.
# instance/ is ignored by git, so secrets never end up on GitHub.

# Any long random string. Generate one with:  python3 -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = ''

# From Google Cloud Console > APIs & Services > Credentials > OAuth client ID (Web application).
# Authorized redirect URI must be exactly:  https://avery.caltech.edu/members/auth
GOOGLE_CLIENT_ID = ''
GOOGLE_CLIENT_SECRET = ''

# Uncomment when developing locally over plain http, otherwise the login cookie is dropped.
# SESSION_COOKIE_SECURE = False
