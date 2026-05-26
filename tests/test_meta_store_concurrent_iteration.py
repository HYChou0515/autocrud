"""The in-memory meta store must tolerate concurrent writes during a search.

``count_resources`` / ``search_resources`` iterate the meta store; another
thread creating/deleting at the same time previously raised
``RuntimeError: dictionary changed size during iteration`` because the store
iterated the live dict. The store must iterate a snapshot instead.

The tiny ``switchinterval`` forces frequent GIL hand-offs so the race shows up
deterministically (it's timing-dependent otherwise).
"""

import sys
import threading

import msgspec

from specstar import SpecStar


class Item(msgspec.Struct):
    name: str


def test_search_and_count_tolerate_concurrent_writes():
    old_interval = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        sp = SpecStar()
        sp.configure(default_user="t")
        sp.add_model(Item, name="item")
        rm = sp.get_resource_manager(Item)
        for i in range(2000):
            rm.create(Item(name=f"i{i}"))

        errors: list[Exception] = []
        stop = threading.Event()

        def churn():
            i = 0
            while not stop.is_set():
                try:
                    info = rm.create(Item(name=f"w{i}"))
                    i += 1
                    rm.permanently_delete(info.resource_id)  # add + remove a key
                except Exception as e:  # pragma: no cover - only on regression
                    errors.append(e)
                    return

        writer = threading.Thread(target=churn)
        writer.start()
        try:
            for _ in range(300):
                rm.count_resources()
                rm.search_resources()
        except Exception as e:  # the reported RuntimeError lands here without the fix
            errors.append(e)
        finally:
            stop.set()
            writer.join()

        assert not errors, repr(errors[0])
    finally:
        sys.setswitchinterval(old_interval)
