from fastapi import Request


def get_db(request: Request):
    # One session per request; dependencies and the route share it because FastAPI caches dependency results.
    with request.app.state.session_factory() as db:
        yield db
