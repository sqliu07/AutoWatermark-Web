"""Process lifecycle for the single-owner task executor."""

# Allow the bounded media subprocesses to drain before the master kills a worker.
graceful_timeout = 240


def on_starting(server):
    if server.cfg.workers != 1 or server.cfg.preload_app:
        raise RuntimeError("Task processing requires a single worker without preload")


def worker_exit(server, worker):
    app = getattr(worker, "wsgi", None)
    if app is not None:
        state = getattr(app, "extensions", {}).get("state")
        if state is not None:
            state.shutdown()
