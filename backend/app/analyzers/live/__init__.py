"""Live analyzer backend (optional, behind .env).

These adapters implement the same three interfaces as the mock backend. They are
intentionally thin: the real model calls go here and NOTHING downstream changes when
``ANALYZER_BACKEND=live``. They require credentials (see ``.env.example``) and are not
exercised by the default test suite.
"""
