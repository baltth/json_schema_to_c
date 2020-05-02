#!/usr/bin/env python3
#
# MIT License
#
# Copyright (c) 2020 Alex Badics
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
#
import os
import re
from abc import ABC, abstractmethod

DIR_OF_THIS_FILE = os.path.dirname(__file__)

NOTE_FOR_GENERATED_FILES = """
/* This file was generated by JSON Schema to C.
 * Any changes made to it will be lost on regeneration. */
"""


class NoDefaultValue(Exception):
    pass


class Generator(ABC):
    @classmethod
    @abstractmethod
    def generate_field_declaration(cls, schema, name, field_name, out_file):
        pass

    @classmethod
    @abstractmethod
    def generate_parser_call(cls, schema, name, out_var_name, out_file):
        pass

    @classmethod
    def generate_type_declaration(cls, schema, name, out_file, *, force=False):
        if force:
            out_file.write("typedef ")
            GlobalGenerator.generate_field_declaration(schema, None, name + "_t", out_file)

    @classmethod
    def generate_parser_bodies(cls, schema, name, out_file):
        pass

    @classmethod
    def generate_set_default_value(cls, schema, out_var_name, out_file):
        raise NoDefaultValue("Default values not supported for {}".format(cls.__name__))

    @classmethod
    def generate_docstring(cls, schema, out_file):
        # Unlike the above functions, this is not here to be overridden, this is just
        # a convenience method that really is common between all types.
        if "description" in schema:
            out_file.write("/**\n")
            out_file.write("{}\n".format(schema['description']))
            out_file.write("*/\n")

    @classmethod
    def generate_logged_error(cls, log_message, out_file):
        out_file.write("error = true;\n")
        if isinstance(log_message, str):
            out_file.write("LOG_ERROR(CURRENT_TOKEN(parse_state).start, \"{}\")\n".format(log_message))
        else:
            assert len(log_message) > 1, "Use a simple string, not a 1 element array."
            out_file.write(
                "LOG_ERROR(CURRENT_TOKEN(parse_state).start, \"{}\", {})\n"
                .format(
                    log_message[0],
                    ", ".join(log_message[1:]),
                )
            )


class StringGenerator(Generator):
    @classmethod
    def generate_field_declaration(cls, schema, name, field_name, out_file):
        if "maxLength" not in schema:
            raise ValueError("Strings must have maxLength")
        cls.generate_docstring(schema, out_file)
        out_file.write("    char {}[{}];\n".format(field_name, schema["maxLength"] + 1))

    @classmethod
    def generate_parser_call(cls, schema, name, out_var_name, out_file):
        if "maxLength" not in schema:
            raise ValueError("Strings must have maxLength")
        out_file.write(
            "error = error || builtin_parse_string(parse_state, {}[0], {}, {});\n"
            .format(out_var_name, schema.get("minLength", 0), schema["maxLength"])
        )

    @classmethod
    def generate_set_default_value(cls, schema, out_var_name, out_file):
        assert 'default' in schema, "Caller is responsible for checking this."
        if len(schema['default']) > schema['maxLength']:
            raise ValueError("String default value longer than maxLength")
        out_file.write(
            'memcpy({dst}, "{src}", {size});\n'.format(
                dst=out_var_name,
                src=schema['default'],
                size=len(schema['default']) + 1
            )
        )


class NumberGenerator(Generator):
    @classmethod
    def generate_field_declaration(cls, schema, name, field_name, out_file):
        cls.generate_docstring(schema, out_file)
        out_file.write("    int64_t {};\n".format(field_name))

    @classmethod
    def generate_range_check(cls, schema, schema_field_name, out_var_name, check_operator, out_file):
        # pylint: disable=too-many-arguments
        # There's no other way around this, pylint.
        if schema_field_name not in schema:
            return
        check_number = schema[schema_field_name]
        out_file.write("if (!error && !((*{}) {} {}))".format(out_var_name, check_operator, check_number))
        out_file.write("{\n")

        # Roll back the token thing, as the value was not actually correct
        out_file.write("    parse_state->current_token -=1; \n")
        cls.generate_logged_error(
            [
                "Integer %li out of range. It must be {} {}.".format(check_operator, check_number),
                "(*{})".format(out_var_name)
            ],
            out_file
        )
        out_file.write("}\n")

    @classmethod
    def generate_parser_call(cls, schema, name, out_var_name, out_file):
        out_file.write(
            "error = error || builtin_parse_number(parse_state, {});\n"
            .format(out_var_name)
        )
        cls.generate_range_check(schema, "minimum", out_var_name, ">=", out_file)
        cls.generate_range_check(schema, "maximum", out_var_name, "<=", out_file)
        cls.generate_range_check(schema, "exclusiveMinimum", out_var_name, ">", out_file)
        cls.generate_range_check(schema, "exclusiveMaximum", out_var_name, "<", out_file)

    @classmethod
    def generate_set_default_value(cls, schema, out_var_name, out_file):
        assert 'default' in schema, "Caller is responsible for checking this."
        out_file.write("{} = {};\n".format(out_var_name, schema['default']))


class BoolGenerator(Generator):
    @classmethod
    def generate_field_declaration(cls, schema, name, field_name, out_file):
        cls.generate_docstring(schema, out_file)
        out_file.write("    bool {};\n".format(field_name))

    @classmethod
    def generate_parser_call(cls, schema, name, out_var_name, out_file):
        out_file.write(
            "error = error || builtin_parse_bool(parse_state, {});\n"
            .format(out_var_name)
        )

    @classmethod
    def generate_set_default_value(cls, schema, out_var_name, out_file):
        assert 'default' in schema, "Caller is responsible for checking this."
        out_file.write(
            "{} = {};\n".format(
                out_var_name,
                'true' if schema['default'] else 'false'
            )
        )


class ObjectGenerator(Generator):
    @classmethod
    def generate_field_declaration(cls, schema, name, field_name, out_file):
        out_file.write("    {}_t {};\n".format(name, field_name))

    @classmethod
    def generate_parser_call(cls, schema, name, out_var_name, out_file):
        out_file.write(
            "error = error || parse_{}(parse_state, {});\n"
            .format(name, out_var_name)
        )

    @classmethod
    def generate_type_declaration(cls, schema, name, out_file, *, force=False):
        # pylint: disable=unused-argument
        # "Force" must exist, with this name.
        for prop_name, prop_schema in schema["properties"].items():
            GlobalGenerator.generate_type_declaration(prop_schema, "{}_{}".format(name, prop_name), out_file)

        cls.generate_docstring(schema, out_file)
        out_file.write("typedef struct {}_s ".format(name) + "{\n")
        for prop_name, prop_schema in schema["properties"].items():
            GlobalGenerator.generate_field_declaration(
                prop_schema,
                "{}_{}".format(name, prop_name),
                prop_name,
                out_file
            )
        out_file.write("}} {}_t;\n\n".format(name))

    @classmethod
    def generate_seen_flags(cls, schema, out_file):
        for prop_name in schema["properties"]:
            out_file.write("bool seen_{} = false;".format(prop_name))

    @classmethod
    def generate_default_field_setting(cls, schema, out_file):
        for prop_name, prop_schema in schema["properties"].items():
            if 'default' not in prop_schema:
                continue
            out_file.write("if (!seen_{}) ".format(prop_name))
            out_file.write("{ \n")
            GlobalGenerator.generate_set_default_value(
                prop_schema,
                "out->{}".format(prop_name),
                out_file
            )
            out_file.write("}\n")

    @classmethod
    def generate_required_checks(cls, schema, name, out_file):
        for prop_name, prop_schema in schema["properties"].items():
            if 'default' in prop_schema:
                continue
            if 'required' not in schema:
                raise ValueError("Objects schemas with non-default fields must have a 'required' constraint")
            if prop_name not in schema['required']:
                raise ValueError(
                    "All fields must either be required or have a default value ({})"
                    .format(prop_name)
                )
            out_file.write("if (!seen_{}) ".format(prop_name))
            out_file.write("{ \n")
            cls.generate_logged_error("Missing required field in {}: {}".format(name, prop_name), out_file)
            out_file.write("}\n")

    @classmethod
    def generate_field_parsers(cls, schema, name, out_file):
        for prop_name, prop_schema in schema["properties"].items():
            out_file.write('if (current_string_is(parse_state, "{}"))\n'.format(prop_name))
            out_file.write("{\n")
            out_file.write("    if(seen_{}){{ \n".format(prop_name))
            cls.generate_logged_error("Duplicate field definition in {}: {}".format(name, prop_name), out_file)
            out_file.write("    } \n")
            out_file.write("    seen_{} = true;\n".format(prop_name))
            out_file.write("    parse_state->current_token += 1;\n")
            GlobalGenerator.generate_parser_call(
                prop_schema,
                "{}_{}".format(name, prop_name),
                "&out->{}".format(prop_name),
                out_file
            )
            out_file.write("} else ")
        out_file.write("{\n")
        cls.generate_logged_error(["Unknown field in {}: %.*s".format(name), "CURRENT_STRING_FOR_ERROR(parse_state)"], out_file)
        out_file.write("}\n")

    @classmethod
    def generate_parser_bodies(cls, schema, name, out_file):
        if "additionalProperties" not in schema or schema["additionalProperties"]:
            raise ValueError(
                "Object types must have additionalProperties set to false")
        for prop_name, prop_schema in schema["properties"].items():
            GlobalGenerator.generate_parser_bodies(prop_schema, "{}_{}".format(name, prop_name), out_file)
        out_file.write("static bool parse_{name}(parse_state_t* parse_state, {name}_t* out)".format(name=name))
        out_file.write("{\n")
        out_file.write("    bool error=check_type(parse_state, JSMN_OBJECT);\n")
        out_file.write("    uint64_t i;\n")
        cls.generate_seen_flags(schema, out_file)
        out_file.write("    const uint64_t n = parse_state->tokens[parse_state->current_token].size;\n")
        out_file.write("    parse_state->current_token += 1;\n")
        out_file.write("    for (i = 0; !error && i < n; ++ i) {\n")
        out_file.write("        ")
        cls.generate_field_parsers(schema, name, out_file)
        out_file.write("    }\n")

        out_file.write("    if (!error){\n")
        cls.generate_required_checks(schema, name, out_file)
        out_file.write("    }\n")

        out_file.write("    if (!error){\n")
        cls.generate_default_field_setting(schema, out_file)
        out_file.write("    }\n")

        out_file.write("    return error;\n")
        out_file.write("}\n\n")


class ArrayGenerator(Generator):
    @classmethod
    def generate_field_declaration(cls, schema, name, field_name, out_file):
        out_file.write("    {}_t {};\n".format(name, field_name))

    @classmethod
    def generate_parser_call(cls, schema, name, out_var_name, out_file):
        out_file.write(
            "error = error || parse_{}(parse_state, {});\n"
            .format(name, out_var_name)
        )

    @classmethod
    def generate_type_declaration(cls, schema, name, out_file, *, force=False):
        # pylint: disable=unused-argument
        # "Force" must exist, with this name.
        if "maxItems" not in schema:
            raise ValueError("Arrays must have maxItems")
        GlobalGenerator.generate_type_declaration(schema["items"], "{}_item".format(name), out_file)

        cls.generate_docstring(schema, out_file)
        out_file.write("typedef struct {}_s ".format(name) + "{\n")

        out_file.write("/**\n")
        out_file.write("The number of elements in the array.\n")
        out_file.write("*/\n")
        out_file.write("    uint64_t n;\n")
        GlobalGenerator.generate_field_declaration(
            schema["items"],
            "{}_item".format(name),
            "items[{}]".format(schema["maxItems"]), out_file
        )
        out_file.write("}} {}_t;\n\n".format(name))

    @classmethod
    def generate_range_checks(cls, schema, name, out_file):
        out_file.write("    if (!error && (n > {}))\n".format(schema["maxItems"]))
        out_file.write("    {\n")
        cls.generate_logged_error(
            ["Array {} too large. Length: %i. Maximum length: {}.".format(name, schema["maxItems"]), "n"],
            out_file
        )
        out_file.write("    }\n")
        if "minItems" in schema:
            out_file.write("    if (!error && (n < {}))\n".format(schema["minItems"]))
            out_file.write("    {\n")
            cls.generate_logged_error(
                ["Array {} too small. Length: %i. Minimum length: {}.".format(name, schema["minItems"]), "n"],
                out_file
            )
            out_file.write("    }\n")

    @classmethod
    def generate_parser_bodies(cls, schema, name, out_file):
        GlobalGenerator.generate_parser_bodies(schema["items"], "{}_item".format(name), out_file)
        out_file.write("static bool parse_{name}(parse_state_t* parse_state, {name}_t* out)".format(name=name))
        out_file.write("{\n")
        out_file.write("    bool error=check_type(parse_state, JSMN_ARRAY);\n")
        out_file.write("    int i;\n")
        out_file.write("    const int n = parse_state->tokens[parse_state->current_token].size;\n")
        cls.generate_range_checks(schema, name, out_file)
        out_file.write("    if (!error){ \n")
        out_file.write("        out->n = n;\n")
        out_file.write("        parse_state->current_token += 1;\n")
        out_file.write("        for (i = 0; !error && i < n; ++ i) {\n")
        out_file.write("        ")
        GlobalGenerator.generate_parser_call(
            schema["items"],
            "{}_item".format(name),
            "&out->items[i]",
            out_file
        )
        out_file.write("        }\n")
        out_file.write("    }\n")
        out_file.write("    return error;\n")
        out_file.write("}\n\n")


class GlobalGenerator(Generator):
    OTHER_GENERATORS = {
        "string": StringGenerator,
        "integer": NumberGenerator,
        "boolean": BoolGenerator,
        "object": ObjectGenerator,
        "array": ArrayGenerator,
    }

    @classmethod
    def generate_field_declaration(cls, schema, name, field_name, out_file):
        cls.OTHER_GENERATORS[schema["type"]]\
            .generate_field_declaration(schema, name, field_name, out_file)

    @classmethod
    def generate_parser_call(cls, schema, name, out_var_name, out_file):
        cls.OTHER_GENERATORS[schema["type"]]\
            .generate_parser_call(schema, name, out_var_name, out_file)

    @classmethod
    def generate_type_declaration(cls, schema, name, out_file, *, force=False):
        cls.OTHER_GENERATORS[schema["type"]]\
            .generate_type_declaration(schema, name, out_file, force=force)

    @classmethod
    def generate_parser_bodies(cls, schema, name, out_file):
        cls.OTHER_GENERATORS[schema["type"]]\
            .generate_parser_bodies(schema, name, out_file)

    @classmethod
    def generate_set_default_value(cls, schema, out_var_name, out_file):
        cls.OTHER_GENERATORS[schema["type"]]\
            .generate_set_default_value(schema, out_var_name, out_file)


def generate_root_parser(schema, out_file):
    out_file.write("bool json_parse_{id}(const char* json_string, {id}_t* out)".format(id=schema['$id']))
    out_file.write("{ \n")

    out_file.write("    bool error = false;\n")
    out_file.write("    parse_state_t parse_state_var;\n")
    out_file.write("    parse_state_t* parse_state = &parse_state_var;\n")
    out_file.write("    error = error || builtin_parse_json_string(parse_state, json_string);\n")
    out_file.write("    ")
    GlobalGenerator.generate_parser_call(
        schema,
        schema['$id'],
        "out",
        out_file,
    )
    out_file.write("    return error;\n")
    out_file.write("}\n")


def generate_parser_h(schema, h_file, prefix, postfix):
    h_file.write(NOTE_FOR_GENERATED_FILES)

    header_guard_name = re.sub("[^A-Z0-9]", "_", os.path.basename(h_file.name).upper())
    h_file.write("#ifndef {}\n".format(header_guard_name))
    h_file.write("#define {}\n".format(header_guard_name))

    h_file.write("#include <stdint.h>\n")
    h_file.write("#include <stdbool.h>\n\n")

    if prefix:
        h_file.write("/* === User-added prefix === */\n")
        h_file.write(prefix)

    h_file.write("/* === Generated type declarations === */\n")
    GlobalGenerator.generate_type_declaration(schema, schema['$id'], h_file, force=True)
    h_file.write("bool json_parse_{id}(const char* json_string, {id}_t* out);\n".format(id=schema['$id']))

    if postfix:
        h_file.write("/* === User-added postfix === */\n")
        h_file.write(postfix)

    h_file.write("#endif /* {} */\n".format(header_guard_name))


def generate_parser_c(schema, c_file, h_file_name, prefix, postfix):
    c_file.write(NOTE_FOR_GENERATED_FILES)
    c_file.write('#include "{}"\n'.format(h_file_name))

    if prefix:
        c_file.write("/* === User-added prefix === */\n")
        c_file.write(prefix)

    with open(os.path.join(DIR_OF_THIS_FILE, '..', 'jsmn', 'jsmn.h')) as jsmn_h:
        c_file.write('#define JSMN_STATIC\n')
        c_file.write("/* === jsmn.h (From https://github.com/zserge/jsmn) === */\n")
        c_file.write(jsmn_h.read())

    with open(os.path.join(DIR_OF_THIS_FILE, 'builtin_parsers.c')) as builtins_file:
        c_file.write("/* === builtin_parsers.c === */\n")
        c_file.write(builtins_file.read())

    c_file.write("/* === Generated parsers === */\n")
    GlobalGenerator.generate_parser_bodies(schema, schema['$id'], c_file)
    generate_root_parser(schema, c_file)

    if postfix:
        c_file.write("/* === User-added postfix === */\n")
        c_file.write(postfix)
