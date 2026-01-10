from typing import Any, Callable, Dict, List, Union, get_args, get_origin
import msgspec
from msgspec import Struct, UNSET, UnsetType
from autocrud.resource_manager.basic import IBlobStore
from autocrud.types import Binary


class BinaryProcessor:
    """
    Handles processing of Binary fields within resource data structures.

    This class compiles optimized traversal functions based on type hints to efficiently
    locate and process `Binary` types, offloading their data to a blob store. It handles
    recursive structures and efficient traversal of Structs, Lists, and Dicts.
    """

    def __init__(self, type_hint: Any):
        self._processor = self._compile(type_hint, mode="process")
        self._restorer = self._compile(type_hint, mode="restore")

    def process(self, data: Any, store: IBlobStore | None) -> Any:
        """
        Traverse the data and process any Binary fields found.

        Args:
            data: The data structure to process (Struct, dict, list, etc.)
            store: The blob store implementation to use for saving binary data.
                   If None, the data is returned unmodified.

        Returns:
            The processed data structure with Binary fields potentially updated
            (e.g. data removed and blob info added).
        """
        if store is None:
            return data
        if self._processor:
            return self._processor(data, store)
        return data

    def restore(self, data: Any, store: IBlobStore | None) -> Any:
        """
        Traverse the data and restore Binary fields from the blob store.

        Args:
            data: The data structure to process (Struct, dict, list, etc.)
            store: The blob store implementation to use for retrieving binary data.
                   If None, the data is returned unmodified.

        Returns:
            The processed data structure with Binary.data populated from the blob store.
        """
        if store is None:
            return data
        if self._restorer:
            return self._restorer(data, store)
        return data

    def _compile(
        self, type_hint: Any, mode: str, cache: dict[Any, Any] | None = None
    ) -> Callable[[Any, IBlobStore], Any] | None:
        """
        Compile a processor function for the given type_hint.

        Handles caching and recursive type definitions (e.g. nested structs) to prevent
        infinite recursion during compilation.

        Args:
            type_hint: The type to inspect (e.g. MyStruct, List[int], etc.)
            mode: 'process' or 'restore'
            cache: Internal cache for recursive calls.

        Returns:
            A callable that takes (data, store) and returns processed data,
            or None if no processing is needed for this type.
        """
        if cache is None:
            cache = {}

        cache_key = (type_hint, mode)
        if cache_key in cache:
            return cache[cache_key]

        # Pre-register a generic fallback for recursion loops during compilation
        # We use a mutable container to update the processor later
        container = [None]

        def deferred_processor(data, store):
            if container[0]:
                return container[0](data, store)
            return data

        cache[cache_key] = deferred_processor

        # Compile the actual processor
        actual_processor = self._compile_impl(type_hint, mode, cache)

        if actual_processor:
            container[0] = actual_processor
            return deferred_processor

        # If no processor needed, we prefer returning None for optimization,
        # but if we are in a recursion loop, previous callers got 'deferred_processor'.
        # Since 'container[0]' is None, deferred_processor acts as identity.
        # So it is safe.
        return None

    def _compile_impl(
        self, type_hint: Any, mode: str, cache: dict[Any, Any]
    ) -> Callable[[Any, IBlobStore], Any] | None:
        """
        Implementation of the compilation logic for different types.

        Dispatches generation of processor functions based on the type origin
        (Union, List, Dict, Struct, etc.).
        """
        if type_hint is Binary:
            return self._process_leaf if mode == "process" else self._restore_leaf

        origin = get_origin(type_hint)

        if origin is Union:
            args = get_args(type_hint)
            non_none_args = [a for a in args if a is not type(None)]
            if len(non_none_args) == 1:
                inner_proc = self._compile(non_none_args[0], mode, cache)
                if inner_proc:

                    def optional_wrapper(data, store):
                        if data is None:
                            return None
                        return inner_proc(data, store)

                    return optional_wrapper
            return self._process_generic if mode == "process" else self._restore_generic

        if origin is list or origin is List:
            args = get_args(type_hint)
            if args:
                item_proc = self._compile(args[0], mode, cache)
                if item_proc:

                    def list_processor(data, store):
                        if not data:
                            return data
                        new_list = [item_proc(item, store) for item in data]
                        if any(n is not o for n, o in zip(new_list, data)):
                            return new_list
                        return data

                    return list_processor
            return self._process_generic if mode == "process" else self._restore_generic

        if origin is dict or origin is Dict:
            args = get_args(type_hint)
            if args and len(args) == 2:
                val_proc = self._compile(args[1], mode, cache)
                if val_proc:

                    def dict_processor(data, store):
                        if not data:
                            return data
                        new_dict = {k: val_proc(v, store) for k, v in data.items()}
                        if any(new_dict[k] is not data[k] for k in data):
                            return new_dict
                        return data

                    return dict_processor
            return self._process_generic if mode == "process" else self._restore_generic

        if (
            isinstance(type_hint, type)
            and issubclass(type_hint, Struct)
            and type_hint is not Binary
        ):
            field_processors = {}
            for field in msgspec.structs.fields(type_hint):
                proc = self._compile(field.type, mode, cache)
                if proc:
                    field_processors[field.name] = proc

            if field_processors:

                def struct_processor(data, store):
                    changes = {}

                    if isinstance(data, dict):
                        for fname, proc in field_processors.items():
                            if fname in data:
                                val = data[fname]
                                new_val = proc(val, store)
                                if new_val is not val:
                                    changes[fname] = new_val
                        if changes:
                            return data | changes
                        return data

                    # Assume Struct
                    for fname, proc in field_processors.items():
                        val = getattr(data, fname)
                        new_val = proc(val, store)
                        if new_val is not val:
                            changes[fname] = new_val
                    if changes:
                        return msgspec.structs.replace(data, **changes)
                    return data

                return struct_processor
            return None

        if type_hint is Any:
            return self._process_generic if mode == "process" else self._restore_generic

        return None

    def _process_leaf(self, data: Any, store: IBlobStore) -> Any:
        """
        Process a single Binary value.

        If the Binary object has data, it is stored in the blob store and
        stripped from the object to prevent it being stored in metadata.
        """
        if isinstance(data, Binary):
            if data.data is not UNSET:
                stored_bin = store.put(data.data, content_type=data.content_type)
                return msgspec.structs.replace(
                    stored_bin,
                    data=UNSET,
                )
        return data

    def _restore_leaf(self, data: Any, store: IBlobStore) -> Any:
        """
        Restore a single Binary value.

        If the Binary object has data, it is returned as is.
        If it has a file_id but no data, data is retrieved from the blob store.
        """
        if isinstance(data, Binary):
            if isinstance(data.data, UnsetType) and not isinstance(
                data.file_id, UnsetType
            ):
                return store.get(data.file_id)
        return data

    def _process_generic(self, data: Any, store: IBlobStore) -> Any:
        if isinstance(data, Binary):
            return self._process_leaf(data, store)

        if isinstance(data, Struct):
            changes = {}
            for field in msgspec.structs.fields(data):
                val = getattr(data, field.name)
                new_val = self._process_generic(val, store)
                if new_val is not val:
                    changes[field.name] = new_val
            if changes:
                return msgspec.structs.replace(data, **changes)
            return data

        if isinstance(data, list):
            new_list = [self._process_generic(item, store) for item in data]
            if any(n is not o for n, o in zip(new_list, data)):
                return new_list
            return data

        if isinstance(data, dict):
            new_dict = {k: self._process_generic(v, store) for k, v in data.items()}
            if any(new_dict[k] is not data[k] for k in data):
                return new_dict

        return data

    def _restore_generic(self, data: Any, store: IBlobStore) -> Any:
        if isinstance(data, Binary):
            return self._restore_leaf(data, store)

        if isinstance(data, Struct):
            changes = {}
            for field in msgspec.structs.fields(data):
                val = getattr(data, field.name)
                new_val = self._restore_generic(val, store)
                if new_val is not val:
                    changes[field.name] = new_val
            if changes:
                return msgspec.structs.replace(data, **changes)
            return data

        if isinstance(data, list):
            new_list = [self._restore_generic(item, store) for item in data]
            if any(n is not o for n, o in zip(new_list, data)):
                return new_list
            return data

        if isinstance(data, dict):
            new_dict = {k: self._restore_generic(v, store) for k, v in data.items()}
            if any(new_dict[k] is not data[k] for k in data):
                return new_dict

        return data
