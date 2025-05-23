from lark import Lark
from TerraformTransformer import TerraformTransformer
from typing import Any
import re
import copy
import json

# TODO: AI generated, needs work
# TODO: make sure it handles "in-string" references to other variables
terraform_parser = Lark(r"""
    start: (variable_block | COMMENT)*

    variable_block: "variable" QUOTED_STRING "{" [attribute+] "}"

    attribute: description
             | type_def
             | default
             | validation
             | sensitive
             | nullable
             | COMMENT

    description: "description" "=" ESCAPED_STRING
    type_def: "type" "=" type
    default: "default" "=" value
    sensitive: "sensitive" "=" BOOL
    nullable: "nullable" "=" BOOL

    validation: "validation" "{" [validation_condition+] "}"
    validation_condition: ("condition" "=" expression | "error_message" "=" ESCAPED_STRING) ";"

    type: simple_type
        | collection_type
        | structural_type
        | any_type

    simple_type: "string" -> string
               | "number" -> number
               | "bool" -> bool
               | "any" -> any

    collection_type: list_type | set_type | map_type | tuple_type

    list_type: "list(" type ")"
    set_type: "set(" type ")"
    map_type: "map(" type ")"
    tuple_type: "tuple(" [type ("," type)*] ")"

    structural_type: object_type

    object_type: "object({" [object_field (","? object_field)*] "})"
    object_field: CNAME (":" | "=") type [COMMENT]

    any_type: "any"

    value: ESCAPED_STRING          -> string
         | SIGNED_NUMBER           -> number
         | BOOL                    -> boolean
         | "null"                  -> null
         | list_value
         | map_value
         | object_value

    list_value: "[" [value ("," value)*] "]"
    map_value: "{" [key_value ("," key_value)*] "}"
    object_value: "{" [object_value_field ("," object_value_field)*] "}"
    object_value_field: CNAME "=" value

    key_value: (QUOTED_STRING | CNAME) "=" value

    expression: /[^{}]+/  # Simplified expression parser (real implementation would need full HCL expr handling)

    QUOTED_STRING: /"[^"\\]*(?:\\.[^"\\]*)*"/
    ESCAPED_STRING: QUOTED_STRING
    BOOL: "true" | "false"
    COMMENT: /#.*/

    %import common.CNAME
    %import common.SIGNED_NUMBER
    %import common.WS
    %ignore WS
    %ignore COMMENT
""", start="start")

def sanitize_schema_name(name):
    name = re.sub(r"[^a-zA-Z0-9_]", "_", name)
    return name.replace("_variables_tf", "")

def generate_openapi_schema(input_object):
    print(json.dumps(input_object, indent=2))
    schema = {
        "type": "object",
        "properties": {},
        "additionalProperties": False
    }

    for key, value in input_object.items():
        property_schema = _map_tf_type_to_openapi(value["type"])
        property_schema["description"] = value.get("description", "")
        
        if "default" in value:
            property_schema["default"] = value["default"]
        
        schema["properties"][key] = property_schema
    return schema

def _map_tf_type_to_openapi(tf_type):
    # Complex types
    if isinstance(tf_type, dict):
        type_def = tf_type.get("type")
        
        if type_def in ["list", "set"]:
            return {
                "type": "array",
                "items": _map_tf_type_to_openapi(tf_type["element_type"]),
                # Sets get uniqueItems constraint
                **({"uniqueItems": True} if type_def == "set" else {})
            }
            
        elif type_def == "map":
            return {
                "type": "object",
                "additionalProperties": _map_tf_type_to_openapi(tf_type["element_type"])
            }
        
        elif type_def == "object":
            properties = {}
            required = []
            for field in tf_type.get("fields", []):
                properties[field["name"]] = _map_tf_type_to_openapi(field["type"])
                required.append(field["name"])
            
            return {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False
            }
        
        # Tuple type (array with positional types)
        elif type_def == "tuple":
            return {
                "type": "array",
                "prefixItems": [
                    _map_tf_type_to_openapi(t) 
                    for t in tf_type.get("element_types", [])
                ]
            }
        
        # Fallback
        return {"type": "string"}
    
    # Shrimple types 
    type_mapping = {
        "string": {"type": "string"},
        "number": {"type": "number", "format": "float"},
        "bool": {"type": "boolean"},
        "any": {
            "oneOf": [
                {"type": "string"},
                {"type": "number"},
                {"type": "boolean"},
                {"type": "object"},
                {"type": "array"}
            ]
        }
    }
    
    return type_mapping.get(tf_type, {"type": "string"})
