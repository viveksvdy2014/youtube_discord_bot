from threading import Thread
from typing import Callable


def threaded(daemon=False):
    def decorator(func: Callable):
        def wrapper(*args: tuple, **kwargs: dict):
            new_thread = Thread(target=func, args=args, kwargs=kwargs, daemon=daemon)
            new_thread.start()
            return new_thread
        return wrapper
    return decorator
