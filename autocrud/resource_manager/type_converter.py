from typing import TypeVar
import msgspec

from autocrud.resource_manager.basic import Resource
from autocrud.resource_manager.data_converter import DataConverter

T = TypeVar("T")

class TypeConverter:
    def __init__(self, resource_type: type[T], *, resource_id_field_name: str|None=None):
        self.resource_type = resource_type
        self.resource_id_field_name = resource_id_field_name

        self.input_resource_type = self.get_input_resource_type()
        self.output_resource_type = self.get_output_resource_type()

        self.out_data_converter = DataConverter(self.output_resource_type)
    
    def get_input_resource_type(self):
        input_resource_type = msgspec.defstruct(
            f"{self.resource_type.__name__}InputResourceType",
            (
                (fld.name, fld.type, msgspec.field(
                    default=fld.default,
                    default_factory=fld.default_factory,
                    name=fld.encode_name
                )) for fld in msgspec.structs.fields(self.resource_type)
                if fld.name != self.resource_id_field_name
            )
        )
        return input_resource_type

    def get_output_resource_type(self):
        output_resource_type = msgspec.defstruct(
            f"{self.resource_type.__name__}OutputResourceType",
            (
                (fld.name, fld.type, msgspec.field(
                    default=fld.default,
                    default_factory=fld.default_factory,
                    name=fld.encode_name
                )) for fld in msgspec.structs.fields(self.resource_type)
            )
        )
        return output_resource_type

    def parse_output(self, input_data: Resource[T]):
        d = msgspec.to_builtins(input_data.data)
        d |= {
            self.resource_id_field_name: input_data.info.resource_id
        }
        input_data.data = d
        return msgspec.convert(input_data, Resource[self.output_resource_type])