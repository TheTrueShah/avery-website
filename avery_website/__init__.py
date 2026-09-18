import os
from .app import app, constitution_hook

# Generate the constitution page on first start if it hasn't been built yet.
_contents = os.path.join(app.root_path, 'templates', 'constitution-contents.html')
if not os.path.exists(_contents) or os.stat(_contents).st_size == 0:
    constitution_hook()
