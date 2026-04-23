"""
Background tasks that run continuously alongside the FastAPI HTTP server.

These are asyncio tasks started from the app lifespan hook. They share the
same process as the HTTP handlers but operate autonomously.
"""
