"""OpenAPI schema customisation for AutoCRUD.

All OpenAPI-specific logic that was previously spread across AutoCRUD instance
methods lives here.  Callers construct an ``OpenAPIBuilder`` with the relevant
AutoCRUD state and call ``customize(app, structs)``.
"""

from __future__ import annotations

import inspect
import warnings
from collections import OrderedDict
from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from autocrud.crud.route_templates.basic import (
    FullResourceResponse,
    IRouteTemplate,
    RevisionListResponse,
    jsonschema_to_openapi,
)
from autocrud.crud.route_templates.migrate import (
    MigrateProgress,
    MigrateResult,
    MigrateRouteTemplate,
)
from autocrud.crud.route_templates.patch import (
    RFC6902,
    RFC6902_Add,
    RFC6902_Copy,
    RFC6902_Move,
    RFC6902_Remove,
    RFC6902_Replace,
    RFC6902_Test,
)
from autocrud.types import (
    IResourceManager,
    Ref,
    RefRevision,
    RefType,
    ResourceMeta,
    RevisionInfo,
    _RefInfo,
    extract_refs,
)
from autocrud.util.type_utils import (
    collect_nested_struct_types,
    get_type_name,
    get_union_args,
    is_union_type,
    unwrap_annotated,
)


class OpenAPIBuilder:
    """Encapsulates all OpenAPI schema customisation for an AutoCRUD instance."""

    def __init__(
        self,
        *,
        resource_managers: OrderedDict[str, IResourceManager],
        route_templates: list[IRouteTemplate],
        pending_create_actions: list,
        pending_update_actions: list,
        async_job_registry: dict,
        async_update_job_registry: dict,
    ) -> None:
        self._resource_managers = resource_managers
        self._route_templates = route_templates
        self._pending_create_actions = pending_create_actions
        self._pending_update_actions = pending_update_actions
        self._async_job_registry = async_job_registry
        self._async_update_job_registry = async_update_job_registry

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def customize(self, app: FastAPI, structs: list[type] | None = None) -> None:
        """Generate and register the OpenAPI schema for the FastAPI application."""
        structs = structs or []
        servers = app.servers
        if app.root_path and not servers:
            servers = [{"url": app.root_path}]

        app.openapi_schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            summary=app.summary,
            description=app.description,
            terms_of_service=app.terms_of_service,
            contact=app.contact,
            license_info=app.license_info,
            routes=app.routes,
            webhooks=app.webhooks.routes,
            tags=app.openapi_tags,
            servers=servers,
            separate_input_output_schemas=app.separate_input_output_schemas,
        )
        app.openapi_schema["components"]["schemas"] |= jsonschema_to_openapi(
            [
                ResourceMeta,
                RevisionInfo,
                RevisionListResponse,
                *[rm.resource_type for rm in self._resource_managers.values()],
                *[
                    FullResourceResponse[rm.resource_type]
                    for rm in self._resource_managers.values()
                ],
                RFC6902_Add,
                RFC6902_Remove,
                RFC6902_Replace,
                RFC6902_Move,
                RFC6902_Test,
                RFC6902_Copy,
                RFC6902,
                *structs,
            ],
        )[1]

        if any(isinstance(rt, MigrateRouteTemplate) for rt in self._route_templates):
            app.openapi_schema["components"]["schemas"] |= jsonschema_to_openapi(
                [MigrateProgress, MigrateResult],
            )[1]

        action_body_structs = []
        for action in self._pending_create_actions:
            if action.resource_name not in self._resource_managers:
                warnings.warn(
                    f"Resource '{action.resource_name}' not found in resource managers. "
                    f"Skipping action '{action.handler.__name__}'.",
                    stacklevel=2,
                )
                continue
            action_body_structs.extend(self._collect_action_body_structs(action))
        for action in self._pending_update_actions:
            if action.resource_name not in self._resource_managers:
                continue
            action_body_structs.extend(
                self._collect_action_body_structs(
                    action,
                    skip_params={
                        action.existing_param,
                        action.info_param,
                        action.meta_param,
                    },
                )
            )
        if action_body_structs:
            app.openapi_schema["components"]["schemas"] |= jsonschema_to_openapi(
                action_body_structs,
            )[1]

        self._inject_ref_metadata(app.openapi_schema)
        self._inject_custom_create_actions(app.openapi_schema)
        self._inject_custom_update_actions(app.openapi_schema)
        self._inject_async_create_jobs(app.openapi_schema)
        self._inject_async_update_jobs(app.openapi_schema)
        self._inject_indexed_fields(app.openapi_schema)
        self._promote_defs_to_components(app.openapi_schema)
        self._resolve_missing_schema_refs(app.openapi_schema)

    # ------------------------------------------------------------------
    # Schema-mutation helpers (instance methods)
    # ------------------------------------------------------------------

    def _inject_ref_metadata(self, schema: dict) -> None:
        """Post-process OpenAPI schema to inject ``x-ref-*`` extensions."""
        components = schema.get("components", {}).get("schemas", {})
        all_refs: list[_RefInfo] = []
        processed_structs: set[type] = set()

        def _find_component(simple_name: str) -> dict | None:
            comp = components.get(simple_name)
            if comp is not None:
                return comp
            candidates = [
                k
                for k in components
                if k.endswith(f"_{simple_name}") and k != simple_name
            ]
            if not candidates:
                return None
            chosen = candidates[0]
            for c in candidates:
                if c.startswith("__main__"):
                    chosen = c
                    break
            return components.get(chosen)

        def _inject_into_component(comp_name: str, refs: list[_RefInfo]) -> None:
            comp = _find_component(comp_name)
            if not comp or "properties" not in comp:
                return
            for ref_info in refs:
                prop = comp["properties"].get(ref_info.source_field)
                if not prop:
                    continue
                ext: dict[str, str] = {
                    "x-ref-resource": ref_info.target,
                    "x-ref-type": ref_info.ref_type,
                }
                if ref_info.ref_type == "resource_id":
                    ext["x-ref-on-delete"] = ref_info.on_delete.value
                prop.update(ext)

        def _process_single_struct(
            struct_type: type,
            model_name: str,
            *,
            inject_unique: bool = False,
            rm: Any = None,
        ) -> None:
            struct_name = get_type_name(struct_type)
            if struct_name is None:
                return

            refs = extract_refs(struct_type, model_name)
            all_refs.extend(refs)
            _inject_into_component(struct_name, refs)

            from autocrud.types import extract_display_name

            dn_field = extract_display_name(struct_type)
            if dn_field is not None:
                comp = _find_component(struct_name)
                if comp is not None:
                    comp["x-display-name-field"] = dn_field

            if inject_unique and rm is not None:
                unique_fields = self._get_unique_fields(rm)
                if unique_fields:
                    comp = _find_component(struct_name)
                    if comp is not None:
                        props = comp.get("properties", {})
                        for uf in unique_fields:
                            prop = props.get(uf)
                            if prop is not None:
                                prop["x-unique"] = True

            nested = collect_nested_struct_types(struct_type, set())
            for nested_struct in nested:
                if nested_struct in processed_structs:
                    continue
                processed_structs.add(nested_struct)
                nested_refs = extract_refs(nested_struct, model_name)
                all_refs.extend(nested_refs)
                nested_name = get_type_name(nested_struct)
                if nested_name is not None:
                    _inject_into_component(nested_name, nested_refs)

        for model_name, rm in self._resource_managers.items():
            processed_structs.add(rm.resource_type)

            if is_union_type(rm.resource_type):
                member_types = get_union_args(rm.resource_type) or ()
                for member_type in member_types:
                    if member_type in processed_structs:
                        continue
                    processed_structs.add(member_type)
                    _process_single_struct(
                        member_type, model_name, inject_unique=False, rm=rm
                    )
                continue

            _process_single_struct(
                rm.resource_type, model_name, inject_unique=True, rm=rm
            )

        for action in self._pending_create_actions:
            if action.resource_name not in self._resource_managers:
                continue
            for body_struct in self._collect_action_body_structs(action):
                if body_struct in processed_structs:
                    continue
                processed_structs.add(body_struct)
                _process_single_struct(
                    body_struct,
                    action.resource_name,
                    inject_unique=False,
                    rm=None,
                )

        for action in self._pending_update_actions:
            if action.resource_name not in self._resource_managers:
                continue
            for body_struct in self._collect_action_body_structs(
                action,
                skip_params={
                    action.existing_param,
                    action.info_param,
                    action.meta_param,
                },
            ):
                if body_struct in processed_structs:
                    continue
                processed_structs.add(body_struct)
                _process_single_struct(
                    body_struct,
                    action.resource_name,
                    inject_unique=False,
                    rm=None,
                )

        if all_refs:
            schema["x-autocrud-relationships"] = [
                {
                    "source": r.source,
                    "sourceField": r.source_field,
                    "target": r.target,
                    "refType": r.ref_type,
                    "onDelete": r.on_delete.value,
                    "nullable": r.nullable,
                }
                for r in all_refs
            ]

    def _inject_custom_create_actions(self, schema: dict) -> None:
        """Inject ``x-autocrud-custom-create-actions`` top-level extension."""
        if not self._pending_create_actions:
            return

        from collections import defaultdict

        actions_by_resource: dict[str, list[dict]] = defaultdict(list)
        for action in self._pending_create_actions:
            if action.resource_name not in self._resource_managers:
                continue
            action_path_segment = action.path.lstrip("/")
            info: dict[str, str] = {
                "path": f"/{action.resource_name}/{action_path_segment}",
                "label": action.label,
                "operationId": action.handler.__name__,
            }
            body_schema = self._get_body_schema_name(action.handler)
            if body_schema:
                info["bodySchema"] = body_schema
            paths = schema.get("paths", {})
            operation_path = f"/{action.resource_name}/{action_path_segment}"
            path_item = paths.get(operation_path, {})
            if not path_item:
                suffix = operation_path
                for spec_path, spec_item in paths.items():
                    if spec_path.endswith(suffix) and "post" in spec_item:
                        path_item = spec_item
                        break
            operation = path_item.get("post", {})
            parameters = operation.get("parameters", [])
            pp = [
                {
                    "name": p["name"],
                    "required": p.get("required", True),
                    "schema": p.get("schema", {}),
                }
                for p in parameters
                if p.get("in") == "path"
            ]
            qp = [
                {
                    "name": p["name"],
                    "required": p.get("required", False),
                    "schema": p.get("schema", {}),
                }
                for p in parameters
                if p.get("in") == "query"
            ]
            ref_map = self._extract_handler_ref_map(action.handler)
            for param_list in (pp, qp):
                for p in param_list:
                    ref_ext = ref_map.get(p["name"])
                    if ref_ext:
                        p["schema"].update(ref_ext)
            if pp:
                info["pathParams"] = pp
            if qp:
                info["queryParams"] = qp
            content = operation.get("requestBody", {}).get("content", {})
            rb = content.get("application/json", {}).get("schema", {})
            if not rb:
                rb = content.get("multipart/form-data", {}).get("schema", {})
            _direct_body_ref = False
            if "$ref" in rb:
                ref_name = rb["$ref"].split("/")[-1]
                if body_schema and ref_name == body_schema:
                    _direct_body_ref = True
                else:
                    rb = (
                        schema.get("components", {})
                        .get("schemas", {})
                        .get(ref_name, {})
                    )
            props: dict = {} if _direct_body_ref else rb.get("properties", {})
            required_list: list = [] if _direct_body_ref else rb.get("required", [])
            body_schema_prop_names: set[str] = set()
            if body_schema:
                for pname, pschema in props.items():
                    ref_target = pschema.get("$ref", "")
                    if not ref_target and "allOf" in pschema:
                        for item in pschema["allOf"]:
                            if "$ref" in item:
                                ref_target = item["$ref"]
                                break
                    if ref_target and ref_target.split("/")[-1] == body_schema:
                        body_schema_prop_names.add(pname)
                    elif (
                        not ref_target
                        and pschema.get("title") == body_schema
                        and pschema.get("type") == "object"
                    ):
                        body_schema_prop_names.add(pname)
            if body_schema_prop_names:
                info["bodySchemaParamName"] = next(iter(body_schema_prop_names))
            file_params: list[dict] = []
            inline_params: list[dict] = []
            for pname, pschema in props.items():
                if pname in body_schema_prop_names:
                    continue
                if pschema.get("format") == "binary":
                    file_params.append(
                        {
                            "name": pname,
                            "required": pname in required_list,
                            "schema": {
                                "type": pschema.get("type", "string"),
                                "format": "binary",
                            },
                        }
                    )
                else:
                    inline_params.append(
                        {
                            "name": pname,
                            "required": pname in required_list,
                            "schema": pschema,
                        }
                    )
            for p in inline_params:
                ref_ext = ref_map.get(p["name"])
                if ref_ext:
                    p["schema"].update(ref_ext)
            if inline_params:
                info["inlineBodyParams"] = inline_params
            if file_params:
                info["fileParams"] = file_params
            if action.async_mode is not None:
                info["asyncMode"] = action.async_mode
                if action.async_mode == "job":
                    from autocrud.crud.async_job_builder import (
                        derive_job_resource_name,
                    )

                    info["jobResourceName"] = (
                        action.job_name
                        or derive_job_resource_name(action.path, action.resource_name)
                    )
            existing_labels = {
                a["label"] for a in actions_by_resource[action.resource_name]
            }
            if action.label in existing_labels:
                warnings.warn(
                    f"Resource '{action.resource_name}' already has a create action "
                    f"with label '{action.label}' "
                    f"(duplicate handler: '{action.handler.__name__}'). "
                    f"Duplicate labels will cause frontend key collisions.",
                    stacklevel=2,
                )
            actions_by_resource[action.resource_name].append(info)

        if actions_by_resource:
            schema["x-autocrud-custom-create-actions"] = dict(actions_by_resource)

    def _inject_custom_update_actions(self, schema: dict) -> None:
        """Inject ``x-autocrud-custom-update-actions`` top-level extension."""
        if not self._pending_update_actions:
            return

        from collections import defaultdict

        actions_by_resource: dict[str, list[dict]] = defaultdict(list)
        for action in self._pending_update_actions:
            if action.resource_name not in self._resource_managers:
                continue
            action_path_segment = action.path.lstrip("/")
            info: dict[str, Any] = {
                "path": f"/{action.resource_name}/{{resource_id}}/{action_path_segment}",
                "label": action.label,
                "operationId": action.handler.__name__,
                "mode": action.mode,
            }
            body_schema = self._get_body_schema_name(
                action.handler,
                skip_params={
                    action.existing_param,
                    action.info_param,
                    action.meta_param,
                },
            )
            if body_schema:
                info["bodySchema"] = body_schema
            paths = schema.get("paths", {})
            operation_path = (
                f"/{action.resource_name}/{{resource_id}}/{action_path_segment}"
            )
            path_item = paths.get(operation_path, {})
            if not path_item:
                suffix = operation_path
                for spec_path, spec_item in paths.items():
                    if spec_path.endswith(suffix) and "post" in spec_item:
                        path_item = spec_item
                        break
            operation = path_item.get("post", {})
            parameters = operation.get("parameters", [])
            pp = [
                {
                    "name": p["name"],
                    "required": p.get("required", True),
                    "schema": p.get("schema", {}),
                }
                for p in parameters
                if p.get("in") == "path" and p["name"] != "resource_id"
            ]
            qp = [
                {
                    "name": p["name"],
                    "required": p.get("required", False),
                    "schema": p.get("schema", {}),
                }
                for p in parameters
                if p.get("in") == "query"
            ]
            ref_map = self._extract_handler_ref_map(action.handler)
            for param_list in (pp, qp):
                for p in param_list:
                    ref_ext = ref_map.get(p["name"])
                    if ref_ext:
                        p["schema"].update(ref_ext)
            if pp:
                info["pathParams"] = pp
            if qp:
                info["queryParams"] = qp
            content = operation.get("requestBody", {}).get("content", {})
            rb = content.get("application/json", {}).get("schema", {})
            if not rb:
                rb = content.get("multipart/form-data", {}).get("schema", {})
            _direct_body_ref = False
            if "$ref" in rb:
                ref_name = rb["$ref"].split("/")[-1]
                if body_schema and ref_name == body_schema:
                    _direct_body_ref = True
                else:
                    rb = (
                        schema.get("components", {})
                        .get("schemas", {})
                        .get(ref_name, {})
                    )
            props: dict = {} if _direct_body_ref else rb.get("properties", {})
            required_list: list = [] if _direct_body_ref else rb.get("required", [])
            body_schema_prop_names: set[str] = set()
            if body_schema:
                for pname, pschema in props.items():
                    ref_target = pschema.get("$ref", "")
                    if not ref_target and "allOf" in pschema:
                        for item in pschema["allOf"]:
                            if "$ref" in item:
                                ref_target = item["$ref"]
                                break
                    if ref_target and ref_target.split("/")[-1] == body_schema:
                        body_schema_prop_names.add(pname)
                    elif (
                        not ref_target
                        and pschema.get("title") == body_schema
                        and pschema.get("type") == "object"
                    ):
                        body_schema_prop_names.add(pname)
            if body_schema_prop_names:
                info["bodySchemaParamName"] = next(iter(body_schema_prop_names))
            file_params: list[dict] = []
            inline_params: list[dict] = []
            for pname, pschema in props.items():
                if pname in body_schema_prop_names:
                    continue
                if pschema.get("format") == "binary":
                    file_params.append(
                        {
                            "name": pname,
                            "required": pname in required_list,
                            "schema": {
                                "type": pschema.get("type", "string"),
                                "format": "binary",
                            },
                        }
                    )
                else:
                    inline_params.append(
                        {
                            "name": pname,
                            "required": pname in required_list,
                            "schema": pschema,
                        }
                    )
            for p in inline_params:
                ref_ext = ref_map.get(p["name"])
                if ref_ext:
                    p["schema"].update(ref_ext)
            if inline_params:
                info["inlineBodyParams"] = inline_params
            if file_params:
                info["fileParams"] = file_params
            if action.async_mode is not None:
                info["asyncMode"] = action.async_mode
                if action.async_mode == "job":
                    from autocrud.crud.async_job_builder import (
                        derive_job_resource_name,
                    )

                    info["jobResourceName"] = (
                        action.job_name
                        or derive_job_resource_name(action.path, action.resource_name)
                    )
            existing_labels = {
                a["label"] for a in actions_by_resource[action.resource_name]
            }
            if action.label in existing_labels:
                warnings.warn(
                    f"Resource '{action.resource_name}' already has an update action "
                    f"with label '{action.label}' "
                    f"(duplicate handler: '{action.handler.__name__}'). "
                    f"Duplicate labels will cause frontend key collisions.",
                    stacklevel=2,
                )
            actions_by_resource[action.resource_name].append(info)

        if actions_by_resource:
            schema["x-autocrud-custom-update-actions"] = dict(actions_by_resource)

    def _inject_async_create_jobs(self, schema: dict) -> None:
        """Inject ``x-autocrud-async-create-jobs`` top-level extension."""
        if not self._async_job_registry:
            return

        mapping: dict[str, str] = {}
        for (
            job_resource_name,
            _job_model,
            target_rm,
            _auto_payload_type,
            _param_conversions,
        ) in self._async_job_registry.values():
            mapping[job_resource_name] = target_rm.resource_name

        if mapping:
            schema["x-autocrud-async-create-jobs"] = mapping

    def _inject_async_update_jobs(self, schema: dict) -> None:
        """Inject ``x-autocrud-async-update-jobs`` top-level extension."""
        if not self._async_update_job_registry:
            return

        mapping: dict[str, str] = {}
        for (
            job_resource_name,
            _job_model,
            target_rm,
            _auto_payload_type,
            _param_conversions,
            _update_mode,
            _existing_param,
            _info_param,
            _meta_param,
        ) in self._async_update_job_registry.values():
            mapping[job_resource_name] = target_rm.resource_name

        if mapping:
            schema["x-autocrud-async-update-jobs"] = mapping

    def _inject_indexed_fields(self, schema: dict) -> None:
        """Inject ``x-autocrud-indexed-fields`` top-level extension."""
        mapping: dict[str, list[str]] = {}
        for name, rm in self._resource_managers.items():
            indexed = rm.indexed_fields
            if indexed:
                mapping[name] = [f.field_path for f in indexed]

        if mapping:
            schema["x-autocrud-indexed-fields"] = mapping

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _get_unique_fields(rm: Any) -> list[str]:
        """Extract unique field names from the RM's registered constraint checkers."""
        from autocrud.resource_manager.constraint_handler import ConstraintEventHandler
        from autocrud.resource_manager.unique_handler import UniqueConstraintChecker

        for h in rm.event_handlers:
            handler = None
            if isinstance(h, ConstraintEventHandler):
                handler = h
            if handler is not None:
                for c in handler.checkers:
                    if isinstance(c, UniqueConstraintChecker):
                        return c.unique_fields
        return []

    @staticmethod
    def _promote_defs_to_components(schema: dict) -> None:
        """Hoist inline ``$defs`` from component schemas into ``components/schemas``."""
        components = schema.get("components", {}).get("schemas", {})
        if not components:
            return

        defs_prefix = "#/$defs/"
        comp_prefix = "#/components/schemas/"

        defs_to_promote: list[tuple[dict, dict]] = []

        def _find_defs(obj: Any) -> None:
            if isinstance(obj, dict):
                if "$defs" in obj and isinstance(obj["$defs"], dict):
                    defs_to_promote.append((obj, obj["$defs"]))
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        _find_defs(v)
            elif isinstance(obj, list):
                for item in obj:
                    _find_defs(item)

        for comp_value in list(components.values()):
            _find_defs(comp_value)

        if not defs_to_promote:
            return

        rename_map: dict[str, str] = {}
        for _parent, defs_dict in defs_to_promote:
            for def_name in defs_dict:
                if def_name not in components:
                    rename_map[def_name] = def_name
                else:
                    rename_map[def_name] = def_name

        for _parent, defs_dict in defs_to_promote:
            for def_name, def_schema in defs_dict.items():
                comp_name = rename_map.get(def_name, def_name)
                if comp_name not in components:
                    components[comp_name] = def_schema

        def _rewrite_defs_refs(obj: Any) -> Any:
            if isinstance(obj, dict):
                out = {}
                for k, v in obj.items():
                    if k == "$ref" and isinstance(v, str) and v.startswith(defs_prefix):
                        def_name = v[len(defs_prefix) :]
                        comp_name = rename_map.get(def_name, def_name)
                        out[k] = f"{comp_prefix}{comp_name}"
                    elif k == "mapping" and isinstance(v, dict):
                        out[k] = {
                            disc_val: (
                                ref_val.replace(defs_prefix, comp_prefix)
                                if isinstance(ref_val, str)
                                and ref_val.startswith(defs_prefix)
                                else ref_val
                            )
                            for disc_val, ref_val in v.items()
                        }
                    else:
                        out[k] = _rewrite_defs_refs(v)
                if "$defs" in out:
                    del out["$defs"]
                return out
            if isinstance(obj, list):
                return [_rewrite_defs_refs(item) for item in obj]
            return obj

        for comp_name in list(components.keys()):
            components[comp_name] = _rewrite_defs_refs(components[comp_name])

    @staticmethod
    def _inline_embedded_schema_ref(schema_extra: dict, source_type: Any) -> dict:
        """Inline a top-level component ref for embedded FastAPI field schemas."""
        if not isinstance(schema_extra, dict) or "$ref" not in schema_extra:
            return schema_extra

        try:
            from copy import deepcopy

            from autocrud.crud.route_templates.basic import jsonschema_to_openapi

            _, components = jsonschema_to_openapi([source_type])
            ref_name = schema_extra["$ref"].split("/")[-1]
            resolved = components.get(ref_name)
            if isinstance(resolved, dict):
                return deepcopy(resolved)
        except Exception:
            pass

        return schema_extra

    @staticmethod
    def _resolve_missing_schema_refs(schema: dict) -> None:
        """Add alias entries for dangling ``$ref`` pointers in the OpenAPI schema."""
        import json
        import re

        components = schema.get("components", {}).get("schemas", {})
        if not components:
            return

        schema_json = json.dumps(schema)
        all_ref_names: set[str] = set(
            re.findall(r'"\$ref":\s*"#/components/schemas/([^"]+)"', schema_json)
        )

        missing = all_ref_names - set(components.keys())
        if not missing:
            return

        for simple_name in missing:
            candidates: list[str] = []
            for comp_name in components:
                if comp_name.endswith(f"_{simple_name}") and comp_name != simple_name:
                    candidates.append(comp_name)

            if not candidates:
                continue

            chosen = candidates[0]
            for c in candidates:
                if c.startswith("__main__"):
                    chosen = c
                    break

            components[simple_name] = components[chosen].copy()

    @staticmethod
    def _get_body_schema_name(
        handler: Any, *, skip_params: set[str] | None = None
    ) -> str | None:
        """Extract the body parameter's schema name from a handler signature."""
        import msgspec

        _skip = skip_params or set()
        sig = inspect.signature(handler)
        for param in sig.parameters.values():
            if param.name in _skip:
                continue
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                continue
            ann, _ = unwrap_annotated(ann)
            if isinstance(ann, type) and issubclass(ann, msgspec.Struct):
                return ann.__name__
            if isinstance(ann, type):
                try:
                    from pydantic import BaseModel

                    if issubclass(ann, BaseModel):
                        return ann.__name__
                except ImportError:
                    pass
        return None

    @staticmethod
    def _collect_action_body_structs(
        action: Any, *, skip_params: set[str] | None = None
    ) -> list[type]:
        """Return all ``msgspec.Struct`` types found in *action* handler params."""
        import msgspec

        _skip = skip_params or set()
        structs: list[type] = []
        sig = inspect.signature(action.handler)
        for param in sig.parameters.values():
            if param.name in _skip:
                continue
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                continue
            ann, _ = unwrap_annotated(ann)
            if isinstance(ann, type) and issubclass(ann, msgspec.Struct):
                structs.append(ann)
        return structs

    @staticmethod
    def _extract_handler_ref_map(handler: Any) -> dict[str, dict[str, str]]:
        """Scan *handler* parameter annotations for ``Ref`` / ``RefRevision`` markers."""
        ref_map: dict[str, dict[str, str]] = {}
        sig = inspect.signature(handler)
        for param in sig.parameters.values():
            ann = param.annotation
            if ann is inspect.Parameter.empty:
                continue
            _, metadata = unwrap_annotated(ann)
            for meta in metadata:
                if isinstance(meta, Ref):
                    ext: dict[str, str] = {
                        "x-ref-resource": meta.resource,
                        "x-ref-type": meta.ref_type.value,
                    }
                    if meta.ref_type == RefType.resource_id:
                        ext["x-ref-on-delete"] = meta.on_delete.value
                    ref_map[param.name] = ext
                    break
                if isinstance(meta, RefRevision):
                    ref_map[param.name] = {
                        "x-ref-resource": meta.resource,
                        "x-ref-type": "revision_id",
                    }
                    break
        return ref_map
