#!/usr/bin/env python3
# coding: utf-8

# Copyright (C) 2017, 2018 Robert Griesel
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>

from helpers.observable import *
from helpers.helpers import timer
from app.service_locator import ServiceLocator


class LaTeXParser(Observable):

    def __init__(self, document):
        Observable.__init__(self)
        self.document = document

        self.labels = set()

        self.parse_symbols()

    def on_insert_text(self, location_iter, text, text_len):
        self.parse_symbols()

    def on_delete_range(self, start_iter, end_iter):
        self.parse_symbols()

    #@timer
    def parse_symbols(self):
        text = self.document.get_text()
        for match in ServiceLocator.get_symbols_regex().finditer(text):
            self.labels = self.labels | {match.group(1)}


