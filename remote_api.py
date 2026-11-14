"""Entry point for the hosted, invite-only ZIP analysis service."""

from api import create_app


app = create_app(remote=True)
