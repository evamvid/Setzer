#!/usr/bin/env python3
# coding: utf-8

# Copyright (C) 2017-present Robert Griesel
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

import bibtexparser

from setzer.app.service_locator import ServiceLocator
from setzer.helpers.timer import timer


class ParserBibTeX(object):

    def __init__(self, document):
        self.document = document
        self.text = ''

    #@timer
    def on_text_deleted(self, buffer, start_iter, end_iter):
        start_offset = start_iter.get_offset()
        end_offset = end_iter.get_offset()
        self.text = self.text[:start_offset] + self.text[end_offset:]
        self.parse_symbols(self.text)

    #@timer
    def on_text_inserted(self, buffer, location_iter, text, text_length):
        offset = location_iter.get_offset()
        self.text = self.text[:offset] + text + self.text[offset:]
        self.parse_symbols(self.text)

    #@timer
    def parse_symbols(self, text):
        db = bibtexparser.loads(text)
        bibitems = set()
        for match in db.entries:
            bibitems = bibitems | {match['ID']}
        self.document.symbols['bibitems'] = bibitems


