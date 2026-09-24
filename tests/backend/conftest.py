"""Backend test-session defaults.

C13: the served entry ``app.main:app`` refuses to import without AUTH_JWT_SECRET (IAM-23),
and several test modules import ``app.main`` at collection time. Provide a test-only key
unless the environment already sets one; tests that need it missing remove it themselves.
"""

import os

os.environ.setdefault("AUTH_JWT_SECRET", "backend-tests-only-signing-key-not-a-real-secret")
