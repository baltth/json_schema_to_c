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
from typing import get_type_hints
from abc import ABC, abstractmethod


class NoDefaultValue(Exception):
    pass


class Generator(ABC):
    description: str = ''
    c_type: str = None

    def __init__(self, schema, name, generators):
        _ = generators  # used only by subclasses
        self.name = name
        for attr in get_type_hints(self.__class__):
            if attr in schema:
                setattr(self, attr, schema[attr])

    @abstractmethod
    def generate_parser_call(self, out_var_name, out_file):
        pass

    def generate_field_declaration(self, field_name, out_file):
        out_file.print_with_docstring(
            "{} {};".format(self.c_type, field_name), self.description
        )

    def generate_type_declaration(self, out_file, *, force=False):
        if force:
            out_file.print("typedef ")
            self.generate_field_declaration(self.name + "_t", out_file)

    def generate_parser_bodies(self, out_file):
        pass

    @classmethod
    def has_default_value(cls):
        return False

    def generate_set_default_value(self, out_var_name, out_file):
        raise NoDefaultValue("Default values not supported for {}".format(self.__class__.__name__))

    @classmethod
    def generate_logged_error(cls, log_message, out_file):
        if isinstance(log_message, str):
            out_file.print("LOG_ERROR(CURRENT_TOKEN(parse_state).start, \"{}\")".format(log_message))
        else:
            assert len(log_message) > 1, "Use a simple string, not a 1 element array."
            out_file.print(
                "LOG_ERROR(CURRENT_TOKEN(parse_state).start, \"{}\", {})"
                .format(
                    log_message[0],
                    ", ".join(log_message[1:]),
                )
            )
        out_file.print("return true;")