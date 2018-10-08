import sys
import asyncio


def run(future, *, debug=False):
    loop = asyncio.get_event_loop()
    run_orig = asyncio._run_orig  # noqa
    if run_orig and not loop.is_running():
        return run_orig(future, debug=debug)
    else:
        loop.set_debug(debug)
        return run_until_complete(loop, future)


def run_until_complete(self, future):
    if self.is_running():
        return run_until_complete_nested(self, future)
    else:
        return self._run_until_complete_orig(future)


def run_until_complete_nested(self, future):
    self._check_closed()
    if future in asyncio.Task.all_tasks(self):
        # future is already submitted, loop until it's done while
        # prodding the event loop with call_later to keep it spinning
        while not future.done():
            self.call_later(0.01, lambda: None)
            self._run_once()
        result = future.result()
    else:
        preserved_ready = list(self._ready)
        self._ready.clear()
        f = asyncio.ensure_future(future)
        if f is not future:
            f._log_destroy_pending = False
        current_tasks = asyncio.tasks._current_tasks  # noqa
        preserved_task = current_tasks.pop(self, None)
        while not f.done():
            self._run_once()
        self._ready.extendleft(reversed(preserved_ready))
        if preserved_task is not None:
            current_tasks[self] = preserved_task
        result = f.result()
    return result


def apply(loop=None):
    loop = loop or asyncio.get_event_loop()
    if hasattr(loop, '_run_until_complete_orig'):
        # already patched
        return
    cls = loop.__class__
    cls._run_until_complete_orig = cls.run_until_complete
    cls.run_until_complete = run_until_complete
    if sys.version_info[:2] == (3, 6):
        # use pure python tasks and futures
        asyncio.Task = asyncio.tasks._CTask = asyncio.tasks.Task = \
            asyncio.tasks._PyTask
        asyncio.Future = asyncio.futures._CFuture = asyncio.futures.Future = \
            asyncio.futures._PyFuture
    if sys.version_info < (3, 7, 0):
        asyncio.tasks._current_tasks = asyncio.tasks.Task._current_tasks  # noqa
    if not hasattr(asyncio, '_run_orig'):
        asyncio._run_orig = getattr(asyncio, 'run', None)
        asyncio.run = run
