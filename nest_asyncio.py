"""Patch asyncio to allow nested event loops."""

import asyncio
import asyncio.events as events
import os
import sys
import threading
from contextlib import contextmanager, suppress
from heapq import heappop


class NestedAsyncIO:
    __slots__ = [
        "_loop",
        "orig_run",
        "orig_tasks",
        "orig_futures",
        "orig_loop_attrs",
        "orig_get_loops",
        "orig_tc",
        "patched"
    ]
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, loop=None):
        if not self._initialized:
            self._loop = loop
            self.orig_run = None
            self.orig_tasks = []
            self.orig_futures = []
            self.orig_loop_attrs = {}
            self.orig_get_loops = {}
            self.orig_tc = None
            self.patched = False
            self.__class__._initialized = True

    def __enter__(self):
        self.apply(self._loop)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.revert()

    def apply(self, loop=None):
        """Patch asyncio to make its event loop reentrant."""
        if not self.patched:
            self.patch_asyncio()
            self.patch_policy()
            self.patch_tornado()

            loop = loop or asyncio.get_event_loop()
            self.patch_loop(loop)
            self.patched = True

    def revert(self):
        if self.patched:
            for loop in self.orig_loop_attrs:
                self.unpatch_loop(loop)
            self.unpatch_tornado()
            self.unpatch_policy()
            self.unpatch_asyncio()
            self.patched = False

    def patch_asyncio(self):
        """Patch asyncio module to use pure Python tasks and futures."""

        def run(main, *, debug=False):
            loop = asyncio.get_event_loop()
            loop.set_debug(debug)
            task = asyncio.ensure_future(main)
            try:
                return loop.run_until_complete(task)
            finally:
                if not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError):
                        loop.run_until_complete(task)

        # Use module level _current_tasks, all_tasks and patch run method.
        if getattr(asyncio, '_nest_patched', False):
            return
        if sys.version_info >= (3, 6, 0):
            self.orig_tasks = [asyncio.Task, asyncio.tasks._CTask, asyncio.tasks.Task]
            asyncio.Task = asyncio.tasks._CTask = asyncio.tasks.Task = \
                asyncio.tasks._PyTask
            self.orig_futures = [asyncio.Future, asyncio.futures._CFuture, asyncio.futures.Future]
            asyncio.Future = asyncio.futures._CFuture = asyncio.futures.Future = \
                asyncio.futures._PyFuture
        if sys.version_info < (3, 7, 0):
            asyncio.tasks._current_tasks = asyncio.tasks.Task._current_tasks
            asyncio.all_tasks = asyncio.tasks.Task.all_tasks
        elif sys.version_info >= (3, 9, 0):
            self.orig_get_loops["events__get_event_loop"] = events._get_event_loop
            self.orig_get_loops["events_get_event_loop"] = events.get_event_loop
            self.orig_get_loops["asyncio_get_event_loop"] = asyncio.get_event_loop
            events._get_event_loop = events.get_event_loop = asyncio.get_event_loop = \
                lambda stacklevel = 3: events._get_running_loop() or events.get_event_loop_policy().get_event_loop()
        self.orig_run = asyncio.run
        asyncio.run = run
        asyncio._nest_patched = True

    def unpatch_asyncio(self):
        if self.orig_run:
            asyncio.run = self.orig_run
            asyncio._nest_patched = False
            if sys.version_info >= (3, 6, 0):
                asyncio.Task, asyncio.tasks._CTask, asyncio.tasks.Task = self.orig_tasks
                asyncio.Future, asyncio.futures._CFuture, asyncio.futures.Future = self.orig_futures
            if sys.version_info >= (3, 9, 0):
                events._get_event_loop = self.orig_get_loops["events__get_event_loop"]
                events.get_event_loop = self.orig_get_loops["events_get_event_loop"]
                asyncio.get_event_loop = self.orig_get_loops["asyncio_get_event_loop"]

    def patch_policy(self):
        """Patch the policy to always return a patched loop."""
        def get_event_loop(this):
            if this._local._loop is None:
                loop = this.new_event_loop()
                self.patch_loop(loop)
                this.set_event_loop(loop)
            return this._local._loop

        cls = events.get_event_loop_policy().__class__
        self.orig_get_loops[f"{cls}.get_event_loop"] = cls.get_event_loop
        cls.get_event_loop = get_event_loop

    def unpatch_policy(self):
        cls = events.get_event_loop_policy().__class__
        if orig := self.orig_get_loops[f"{cls}.get_event_loop"]:
            cls.get_event_loop = orig

    def patch_loop(self, loop):
        """Patch loop to make it reentrant."""

        def run_forever(this):
            with manage_run(this), manage_asyncgens(this):
                while True:
                    this._run_once()
                    if this._stopping:
                        break
            this._stopping = False

        def run_until_complete(this, future):
            with manage_run(this):
                f = asyncio.ensure_future(future, loop=this)
                if f is not future:
                    f._log_destroy_pending = False
                while not f.done():
                    this._run_once()
                    if this._stopping:
                        break
                if not f.done():
                    raise RuntimeError(
                        'Event loop stopped before Future completed.')
                return f.result()

        def _run_once(this):
            """
            Simplified re-implementation of asyncio's _run_once that
            runs handles as they become ready.
            """
            ready = this._ready
            scheduled = this._scheduled
            while scheduled and scheduled[0]._cancelled:
                heappop(scheduled)

            timeout = (
                0 if ready or this._stopping
                else min(max(
                    scheduled[0]._when - this.time(), 0), 86400) if scheduled
                else None)
            event_list = this._selector.select(timeout)
            this._process_events(event_list)

            end_time = this.time() + this._clock_resolution
            while scheduled and scheduled[0]._when < end_time:
                handle = heappop(scheduled)
                ready.append(handle)

            for _ in range(len(ready)):
                if not ready:
                    break
                handle = ready.popleft()
                if not handle._cancelled:
                    # preempt the current task so that that checks in
                    # Task.__step do not raise
                    curr_task = curr_tasks.pop(this, None)

                    try:
                        handle._run()
                    finally:
                        # restore the current task
                        if curr_task is not None:
                            curr_tasks[this] = curr_task

            handle = None

        @contextmanager
        def manage_run(this):
            """Set up the loop for running."""
            this._check_closed()
            old_thread_id = this._thread_id
            old_running_loop = events._get_running_loop()
            try:
                this._thread_id = threading.get_ident()
                events._set_running_loop(this)
                this._num_runs_pending += 1
                if this._is_proactorloop:
                    if this._self_reading_future is None:
                        this.call_soon(this._loop_self_reading)
                yield
            finally:
                this._thread_id = old_thread_id
                events._set_running_loop(old_running_loop)
                this._num_runs_pending -= 1
                if this._is_proactorloop:
                    if (this._num_runs_pending == 0
                            and this._self_reading_future is not None):
                        ov = this._self_reading_future._ov
                        this._self_reading_future.cancel()
                        if ov is not None:
                            this._proactor._unregister(ov)
                        this._self_reading_future = None

        @contextmanager
        def manage_asyncgens(this):
            if not hasattr(sys, 'get_asyncgen_hooks'):
                # Python version is too old.
                return
            old_agen_hooks = sys.get_asyncgen_hooks()
            try:
                this._set_coroutine_origin_tracking(this._debug)
                if this._asyncgens is not None:
                    sys.set_asyncgen_hooks(
                        firstiter=this._asyncgen_firstiter_hook,
                        finalizer=this._asyncgen_finalizer_hook)
                yield
            finally:
                this._set_coroutine_origin_tracking(False)
                if this._asyncgens is not None:
                    sys.set_asyncgen_hooks(*old_agen_hooks)

        def _check_running(this):
            """Do not throw exception if loop is already running."""
            pass

        if getattr(loop, '_nest_patched', False):
            return
        if not isinstance(loop, asyncio.BaseEventLoop):
            raise ValueError('Can\'t patch loop of type %s' % type(loop))
        cls = loop.__class__
        self.orig_loop_attrs[cls] = {}
        self.orig_loop_attrs[cls]["run_forever"] = cls.run_forever
        cls.run_forever = run_forever
        self.orig_loop_attrs[cls]["run_until_complete"] = cls.run_until_complete
        cls.run_until_complete = run_until_complete
        self.orig_loop_attrs[cls]["_run_once"] = cls._run_once
        cls._run_once = _run_once
        self.orig_loop_attrs[cls]["_check_running"] = cls._check_running
        cls._check_running = _check_running
        self.orig_loop_attrs[cls]["_check_runnung"] = cls._check_running
        cls._check_runnung = _check_running  # typo in Python 3.7 source
        cls._num_runs_pending = 1 if loop.is_running() else 0
        cls._is_proactorloop = (
            os.name == 'nt' and issubclass(cls, asyncio.ProactorEventLoop))
        if sys.version_info < (3, 7, 0):
            cls._set_coroutine_origin_tracking = cls._set_coroutine_wrapper
        curr_tasks = asyncio.tasks._current_tasks if sys.version_info >= (3, 7, 0) else asyncio.Task._current_tasks
        cls._nest_patched = True

    def unpatch_loop(self, loop):
        loop._nest_patched = False
        if self.orig_loop_attrs[loop]:
            for key, value in self.orig_loop_attrs[loop].items():
                setattr(loop, key, value)

        for attr in ['_num_runs_pending', '_is_proactorloop']:
            if hasattr(loop, attr):
                delattr(loop, attr)

    def patch_tornado(self):
        """
        If tornado is imported before nest_asyncio, make tornado aware of
        the pure-Python asyncio Future.
        """
        if 'tornado' in sys.modules:
            import tornado.concurrent as tc  # type: ignore
            self.orig_tc = tc.Future
            tc.Future = asyncio.Future
            if asyncio.Future not in tc.FUTURES:
                tc.FUTURES += (asyncio.Future,)

    def unpatch_tornado(self):
        if self.orig_tc:
            import tornado.concurrent as tc
            tc.Future = self.orig_tc
