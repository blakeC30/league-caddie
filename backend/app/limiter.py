"""Shared slowapi rate-limiter instance.

Defined here (not in main.py) so routers can import it without creating a
circular import through app.main.
"""

import os
import uuid

from slowapi import Limiter
from slowapi.util import get_remote_address


def _key_func(request):
    # In the test environment each request gets a unique bucket so no limit
    # is ever reached.  This avoids test-order sensitivity without needing to
    # reset in-memory state between tests.
    if os.environ.get("ENVIRONMENT") == "test":
        return str(uuid.uuid4())
    return get_remote_address(request)


limiter = Limiter(key_func=_key_func)
