# Janet is a worker, not a web process

A Discord bot holds a websocket open to Discord and never serves HTTP, so it
runs as a long-lived worker. The repo previously tried to run it as a Heroku
`web` dyno under `gunicorn app:bot`, which cannot work: gunicorn serves WSGI
callables and `bot` is a `discord.py` Bot whose `run()` blocks at import.
Three commits went into trying to make that work, so the instinct is strong and
the correction needs recording. Janet runs on Railway as a `worker` process
started by `python app.py`. Gunicorn is removed from the Pipfile entirely, and
the virtualenv committed at `janetbot/` is deleted from the repo.
