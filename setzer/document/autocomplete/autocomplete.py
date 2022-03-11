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

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk

import setzer.document.autocomplete.autocomplete_viewgtk as view
import setzer.document.autocomplete.modes.mode_blank as mode_blank
import setzer.document.autocomplete.modes.mode_default as mode_default
import setzer.document.autocomplete.modes.mode_begin_end as mode_begin_end
from setzer.app.service_locator import ServiceLocator
import setzer.helpers.timer as timer


class Autocomplete(object):

    def __init__(self, document, document_view):
        self.document = document
        self.content = document.content
        self.document_view = document_view

        self.view = view.DocumentAutocompleteView(self)
        self.mark_start = Gtk.TextMark.new('ac_session_start', True)
        self.mark_end = Gtk.TextMark.new('ac_session_end', False)
        self.matching_mark_start = Gtk.TextMark.new('ac_session_second_start', True)
        self.matching_mark_end = Gtk.TextMark.new('ac_session_second_end', False)

        self.provider = ServiceLocator.get_autocomplete_provider()

        self.blank_mode = mode_blank.ModeBlank(self)
        self.mode = self.blank_mode

        self.items = list()

        self.view.list.connect('row-activated', self.on_row_activated)

        self.content.connect('text_inserted', self.on_text_inserted)
        self.content.connect('text_deleted', self.on_text_deleted)
        self.content.connect('buffer_changed', self.on_buffer_changed)
        self.content.connect('cursor_changed', self.on_cursor_changed)

    def on_text_inserted(self, content, parameter):
        buffer, location_iter, text, text_length = parameter
        self.mode.on_insert_text(buffer, location_iter, text, text_length)

    def on_text_deleted(self, content, parameter):
        buffer, start_iter, end_iter = parameter
        self.mode.on_delete_range(buffer, start_iter, end_iter)

    def on_buffer_changed(self, content, buffer):
        self.activate_if_possible()
        self.mode.on_buffer_changed()

    def on_cursor_changed(self, content):
        self.mode.on_cursor_changed()

    def on_row_activated(self, box, row, user_data=None):
        self.document_view.source_view.grab_focus()
        self.submit()

    def on_keypress(self, event):
        ''' returns whether the keypress has been handled. '''

        modifiers = Gtk.accelerator_get_default_mod_mask()

        if self.is_visible():
            if event.keyval == Gdk.keyval_from_name('Down'):
                if event.state & modifiers == 0:
                    self.view.select_next()
                    return True

            if event.keyval == Gdk.keyval_from_name('Up'):
                if event.state & modifiers == 0:
                    self.view.select_previous()
                    return True

            if event.keyval == Gdk.keyval_from_name('Escape'):
                if event.state & modifiers == 0:
                    self.mode.cancel()
                    return True

            if event.keyval == Gdk.keyval_from_name('Return'):
                if event.state & modifiers == 0:
                    self.mode.submit()
                    return True

        return self.mode.on_keypress(event)

    def submit(self):
        self.mode.submit()

    def update(self):
        if self.is_active():
            self.mode.update()

    def activate_if_possible(self):
        line = self.content.get_line_at_cursor()
        offset = self.content.get_cursor_line_offset()
        line = line[:offset] + '%•%' + line[offset:]
        match = ServiceLocator.get_regex_object(r'.*\\(begin|end)\{((?:[^\{\[\(])*)%•%((?:[^\{\[\(])*)\}.*').match(line)
        if match:
            word_offset = self.content.get_cursor_offset() - len(match.group(2))
            word_len = len(match.group(2)) + len(match.group(3))
            self.start_mode(mode_begin_end.ModeBeginEnd(self, word_offset, word_len))
        else:
            current_word = self.content.get_latex_command_at_cursor()
            items = self.provider.get_items(current_word)
            if not items: return
            for item in items:
                if item['command'] == current_word:
                    return
            self.start_mode(mode_default.ModeDefault(self, self.document))

    #@timer.timer
    def populate(self, offset):
        self.view.empty_list()
        for command in reversed(self.items):
            item = view.DocumentAutocompleteItem(command, offset)
            self.view.prepend(item)
        if len(self.items) > 0:
            self.view.select_first()

    def start_mode(self, mode):
        self.mode = mode
        self.mode.update()

    def end_mode(self):
        self.mode = self.blank_mode
        self.mode.update()

    def is_active(self):
        return self.mode.is_active()

    def is_visible(self):
        return self.mode.will_show and self.view.position_is_visible() and not self.view.focus_hide


