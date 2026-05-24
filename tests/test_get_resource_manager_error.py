"""Issue F: an unknown string name gives a discoverable error.

Job models register under an action-derived name (`<action>-job`), not the Job
class name, so `get_resource_manager("fetchjob")` KeyErrors with no hint. The
error now lists the registered names and points at the class / job-naming.
"""

import msgspec
import pytest

from specstar import Schema, SpecStar


class Doc(msgspec.Struct):
    title: str


def test_unknown_string_name_lists_registered_names():
    sp = SpecStar()
    sp.configure()
    sp.add_model(Schema(Doc, "v1"))
    with pytest.raises(KeyError) as exc:
        sp.get_resource_manager("nope")
    msg = str(exc.value)
    assert "nope" in msg
    assert "doc" in msg  # lists what IS registered
