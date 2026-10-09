import os

# The scope setting lives in the developer's settings; tests choose their own.
# Removed at import so session-scoped fixtures and subprocesses never see it.
os.environ.pop('MAKOTO_BLOCK_IN', None)
