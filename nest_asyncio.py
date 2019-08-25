import sys
import asyncio
import asyncio.events as events
import threading


def apply(loop=None):
    """
    Patch asyncio to make its event loop reentrent.
    """
    loop = loop or asyncio.get_event_loop()
    if not isinstance(loop, asyncio.BaseEventLoop):
        raise ValueError('Can\'t patch loop of type %s' % type(loop))
    if hasattr(loop, '_run_forever_orig'):
        # already patched
        return
    _patch_asyncio()
    _patch_loop(loop)
    _patch_task()
    _patch_handle()


def _patch_asyncio():
    """
    Patch asyncio module to use pure Python tasks and futures,
    use module level _current_tasks, all_tasks and patch run method.
    """
    def run(future, *, debug=False):
        loop = asyncio.get_event_loop()
        loop.set_debug(debug)
        return loop.run_until_complete(future)

    if sys.version_info >= (3, 6, 0):
        asyncio.Task = asyncio.tasks._CTask = asyncio.tasks.Task = \
            asyncio.tasks._PyTask
        asyncio.Future = asyncio.futures._CFuture = asyncio.futures.Future = \
            asyncio.futures._PyFuture
    if sys.version_info < (3, 7, 0):
        asyncio.tasks._current_tasks = asyncio.tasks.Task._current_tasks  # noqa
        asyncio.all_tasks = asyncio.tasks.Task.all_tasks  # noqa
    if not hasattr(asyncio, '_run_orig'):
        asyncio._run_orig = getattr(asyncio, 'run', None)
        asyncio.run = run


def _patch_loop(loop):
    """
    Patch loop to make it reentrent.
    """
    if sys.version_info >= (3, 7, 0):
        set_coro_tracking = loop._set_coroutine_origin_tracking
    else:
        set_coro_tracking = loop._set_coroutine_wrapper

    def run_forever(self):
        self._check_closed()
        old_thread_id = self._thread_id
        old_running_loop = events._get_running_loop()
        set_coro_tracking(self._debug)
        self._thread_id = threading.get_ident()

        if self._asyncgens is not None:
            old_agen_hooks = sys.get_asyncgen_hooks()
            sys.set_asyncgen_hooks(
                firstiter=self._asyncgen_firstiter_hook,
                finalizer=self._asyncgen_finalizer_hook)
        try:
            events._set_running_loop(self)
            while True:
                try:
                    self._run_once()
                except IndexError:
                    # Ignore 'pop from an empty deque' errors.
                    # This happens when all ready handles have already been
                    # processed but _run_once expects there to be more.
                    # Since the handles have been processed anyway it is
                    # safe to ignore this.
                    pass
                if self._stopping:
                    break
        finally:
            self._stopping = False
            self._thread_id = old_thread_id
            events._set_running_loop(old_running_loop)
            set_coro_tracking(False)
            if self._asyncgens is not None:
                sys.set_asyncgen_hooks(*old_agen_hooks)

    cls = loop.__class__
    cls._run_forever_orig = cls.run_forever
    cls.run_forever = run_forever


def _patch_task():
    """
    Patch the Task's step and enter/leave methods to make it reentrant.
    """
    def step(task, exc=None):
        curr_task = curr_tasks.get(task._loop)
        try:
            step_orig(task, exc)
        finally:
            if curr_task is None:
                curr_tasks.pop(task._loop, None)
            else:
                curr_tasks[task._loop] = curr_task

    Task = asyncio.Task
    if sys.version_info >= (3, 7, 0):

        def enter_task(loop, task):
            curr_tasks[loop] = task

        def leave_task(loop, task):
            del curr_tasks[loop]

        asyncio.tasks._enter_task = enter_task
        asyncio.tasks._leave_task = leave_task
        curr_tasks = asyncio.tasks._current_tasks
        step_orig = Task._Task__step
        Task._Task__step = step
    else:
        curr_tasks = Task._current_tasks
        step_orig = Task._step
        Task._step = step


def _patch_handle():
    """
    Patch Handle to allow recursive calls.
    """
    def run(self):
        try:
            ctx = self._context.copy()
            ctx.run(self._callback, *self._args)
        except Exception as exc:
            cb = format_helpers._format_callback_source(
                self._callback, self._args)
            msg = 'Exception in callback {}'.format(cb)
            context = {
                'message': msg,
                'exception': exc,
                'handle': self,
            }
            if self._source_traceback:
                context['source_traceback'] = self._source_traceback
            self._loop.call_exception_handler(context)
        self = None

    if sys.version_info >= (3, 7, 0):
        from asyncio import format_helpers
        asyncio.events.Handle._run = run
