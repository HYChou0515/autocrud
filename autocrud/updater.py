"""
Advanced updater system for fine-grained attribute control.
"""

from typing import Any, Dict, List
from dataclasses import dataclass
from enum import Enum


class UpdateAction(Enum):
    """Update action types"""

    SET = "set"  # Set to new value
    UNDEFINED = "undefined"  # Don't change
    LIST_SET = "list_set"  # Replace entire list
    LIST_ADD = "list_add"  # Add items to list
    LIST_REMOVE = "list_remove"  # Remove items from list
    DICT_SET = "dict_set"  # Replace entire dict
    DICT_UPDATE = "dict_update"  # Add/update items in dict
    DICT_REMOVE = "dict_remove"  # Remove items from dict


@dataclass
class UpdateOperation:
    """Represents a single update operation"""

    action: UpdateAction
    value: Any = None

    @classmethod
    def undefined(cls) -> "UpdateOperation":
        """Create an undefined operation (no change)"""
        return cls(action=UpdateAction.UNDEFINED)

    @classmethod
    def set_value(cls, value: Any) -> "UpdateOperation":
        """Set attribute to new value"""
        return cls(action=UpdateAction.SET, value=value)

    @classmethod
    def list_set(cls, items: List[Any]) -> "UpdateOperation":
        """Replace entire list"""
        return cls(action=UpdateAction.LIST_SET, value=items)

    @classmethod
    def list_add(cls, items: List[Any]) -> "UpdateOperation":
        """Add items to list"""
        return cls(action=UpdateAction.LIST_ADD, value=items)

    @classmethod
    def list_remove(cls, items: List[Any]) -> "UpdateOperation":
        """Remove items from list"""
        return cls(action=UpdateAction.LIST_REMOVE, value=items)

    @classmethod
    def dict_set(cls, data: Dict[str, Any]) -> "UpdateOperation":
        """Replace entire dict"""
        return cls(action=UpdateAction.DICT_SET, value=data)

    @classmethod
    def dict_update(cls, data: Dict[str, Any]) -> "UpdateOperation":
        """Add/update items in dict"""
        return cls(action=UpdateAction.DICT_UPDATE, value=data)

    @classmethod
    def dict_remove(cls, keys: List[str]) -> "UpdateOperation":
        """Remove items from dict by keys"""
        return cls(action=UpdateAction.DICT_REMOVE, value=keys)


class AdvancedUpdater:
    """Advanced updater for fine-grained attribute control"""

    def __init__(self, operations: Dict[str, UpdateOperation]):
        self.operations = operations

    def apply_to(self, current_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply update operations to current data"""
        result = current_data.copy()

        for attr_name, operation in self.operations.items():
            if operation.action == UpdateAction.UNDEFINED:
                # Don't change
                continue
            elif operation.action == UpdateAction.SET:
                # Set to new value
                result[attr_name] = operation.value
            elif operation.action == UpdateAction.LIST_SET:
                # Replace entire list
                result[attr_name] = operation.value
            elif operation.action == UpdateAction.LIST_ADD:
                # Add items to list
                current_list = result.get(attr_name, [])
                if not isinstance(current_list, list):
                    current_list = []
                result[attr_name] = current_list + operation.value
            elif operation.action == UpdateAction.LIST_REMOVE:
                # Remove items from list
                current_list = result.get(attr_name, [])
                if isinstance(current_list, list):
                    result[attr_name] = [
                        item for item in current_list if item not in operation.value
                    ]
            elif operation.action == UpdateAction.DICT_SET:
                # Replace entire dict
                result[attr_name] = operation.value
            elif operation.action == UpdateAction.DICT_UPDATE:
                # Add/update items in dict
                current_dict = result.get(attr_name, {})
                if not isinstance(current_dict, dict):
                    current_dict = {}
                updated_dict = current_dict.copy()
                updated_dict.update(operation.value)
                result[attr_name] = updated_dict
            elif operation.action == UpdateAction.DICT_REMOVE:
                # Remove items from dict by keys
                current_dict = result.get(attr_name, {})
                if isinstance(current_dict, dict):
                    updated_dict = current_dict.copy()
                    for key in operation.value:
                        updated_dict.pop(key, None)
                    result[attr_name] = updated_dict

        return result

    @classmethod
    def from_dict(cls, update_data: Dict[str, Any]) -> "AdvancedUpdater":
        """Create updater from dictionary format"""
        operations = {}

        for attr_name, value in update_data.items():
            if isinstance(value, dict) and "_action" in value:
                # Structured update operation
                action_type = value["_action"]
                operation_value = value.get("value")

                if action_type == "undefined":
                    operations[attr_name] = UpdateOperation.undefined()
                elif action_type == "set":
                    operations[attr_name] = UpdateOperation.set_value(operation_value)
                elif action_type == "list_set":
                    operations[attr_name] = UpdateOperation.list_set(operation_value)
                elif action_type == "list_add":
                    operations[attr_name] = UpdateOperation.list_add(operation_value)
                elif action_type == "list_remove":
                    operations[attr_name] = UpdateOperation.list_remove(operation_value)
                elif action_type == "dict_set":
                    operations[attr_name] = UpdateOperation.dict_set(operation_value)
                elif action_type == "dict_update":
                    operations[attr_name] = UpdateOperation.dict_update(operation_value)
                elif action_type == "dict_remove":
                    operations[attr_name] = UpdateOperation.dict_remove(operation_value)
                else:
                    # Raise error for unknown action
                    valid_actions = [action.value for action in UpdateAction]
                    raise ValueError(
                        f"Unknown action type '{action_type}' for attribute '{attr_name}'. Valid actions are: {', '.join(valid_actions)}"
                    )
            else:
                # Simple value update
                operations[attr_name] = UpdateOperation.set_value(value)

        return cls(operations)


# Convenience functions for creating common update operations
def undefined() -> Dict[str, str]:
    """Create undefined operation marker"""
    return {"_action": "undefined"}


def set_value(value: Any) -> Dict[str, Any]:
    """Create set value operation"""
    return {"_action": "set", "value": value}


def list_set(items: List[Any]) -> Dict[str, Any]:
    """Create list set operation"""
    return {"_action": "list_set", "value": items}


def list_add(items: List[Any]) -> Dict[str, Any]:
    """Create list add operation"""
    return {"_action": "list_add", "value": items}


def list_remove(items: List[Any]) -> Dict[str, Any]:
    """Create list remove operation"""
    return {"_action": "list_remove", "value": items}


def dict_set(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create dict set operation"""
    return {"_action": "dict_set", "value": data}


def dict_update(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create dict update operation"""
    return {"_action": "dict_update", "value": data}


def dict_remove(keys: List[str]) -> Dict[str, Any]:
    """Create dict remove operation"""
    return {"_action": "dict_remove", "value": keys}
