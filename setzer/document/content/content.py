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

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('GtkSource', '4')
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import GObject
from gi.repository import GtkSource

import re
import time
import difflib
import math

from setzer.app.service_locator import ServiceLocator
from setzer.helpers.observable import Observable


class Content(Observable):

    def __init__(self, language, document):
        Observable.__init__(self)
        self.document = document

        self.settings = ServiceLocator.get_settings()

        self.source_buffer = GtkSource.Buffer()
        self.source_view = GtkSource.View.new_with_buffer(self.source_buffer)
        self.source_language_manager = ServiceLocator.get_source_language_manager()
        self.source_style_scheme_manager = ServiceLocator.get_source_style_scheme_manager()
        if language == 'bibtex': self.source_language = self.source_language_manager.get_language('bibtex')
        else: self.source_language = self.source_language_manager.get_language('latex')
        self.source_buffer.set_language(self.source_language)
        self.update_syntax_scheme()

        self.scroll_to = None
        self.insert_position = 0

        self.synctex_tag_count = 0
        self.synctex_highlight_tags = dict()

        self.indentation_update = None
        self.indentation_tags = dict()

        self.placeholder_tag = self.source_buffer.create_tag('placeholder')
        self.placeholder_tag.set_property('background', '#fce94f')
        self.placeholder_tag.set_property('foreground', '#000')

        self.source_buffer.connect('mark-set', self.on_mark_set)
        self.source_buffer.connect('mark-deleted', self.on_mark_deleted)
        self.source_buffer.connect('insert-text', self.on_insert_text)
        self.source_buffer.connect('delete-range', self.on_delete_range)
        self.source_buffer.connect('changed', self.on_buffer_changed)
        self.source_buffer.connect('modified-changed', self.on_modified_changed)
        self.undo_manager = self.source_buffer.get_undo_manager()
        self.undo_manager.connect('can-undo-changed', self.on_can_undo_changed)
        self.undo_manager.connect('can-redo-changed', self.on_can_redo_changed)
        self.settings.connect('settings_changed', self.on_settings_changed)

    def on_settings_changed(self, settings, parameter):
        section, item, value = parameter

        if (section, item) in [('preferences', 'syntax_scheme'), ('preferences', 'syntax_scheme_dark_mode')]:
            self.update_syntax_scheme()

    def on_insert_text(self, buffer, location_iter, text, text_length):
        self.document.parser.on_text_inserted(buffer, location_iter, text, text_length)
        self.indentation_update = {'line_start': location_iter.get_line(), 'text_length': text_length}
        self.add_change_code('text_inserted', (buffer, location_iter, text, text_length))

    def on_delete_range(self, buffer, start_iter, end_iter):
        self.document.parser.on_text_deleted(buffer, start_iter, end_iter)
        self.indentation_update = {'line_start': start_iter.get_line(), 'text_length': 0}
        self.add_change_code('text_deleted', (buffer, start_iter, end_iter))

    def on_modified_changed(self, buffer):
        self.add_change_code('modified_changed')

    def on_can_undo_changed(self, undo_manager):
        self.add_change_code('can_undo_changed', self.undo_manager.can_undo())

    def on_can_redo_changed(self, undo_manager):
        self.add_change_code('can_redo_changed', self.undo_manager.can_redo())

    def on_buffer_changed(self, buffer):
        self.update_indentation_tags()

        self.update_placeholder_selection()

        self.add_change_code('buffer_changed', buffer)

        if self.is_empty():
            self.add_change_code('document_not_empty')
        else:
            self.add_change_code('document_empty')

    def on_mark_set(self, buffer, insert, mark, user_data=None):
        if mark.get_name() == 'insert':
            self.update_placeholder_selection()
            self.add_change_code('cursor_changed')
        self.update_selection_state()

    def on_mark_deleted(self, buffer, mark, user_data=None):
        if mark.get_name() == 'insert':
            self.add_change_code('cursor_changed')
        self.update_selection_state()

    def initially_set_text(self, text):
        self.source_buffer.begin_not_undoable_action()
        self.source_buffer.set_text(text)
        self.source_buffer.end_not_undoable_action()
        self.source_buffer.set_modified(False)

    def update_selection_state(self):
        self.add_change_code('selection_might_have_changed', self.source_buffer.get_has_selection())

    def update_syntax_scheme(self):
        name = self.settings.get_value('preferences', 'syntax_scheme')
        self.source_style_scheme_light = self.source_style_scheme_manager.get_scheme(name)
        name = self.settings.get_value('preferences', 'syntax_scheme_dark_mode')
        self.source_style_scheme_dark = self.source_style_scheme_manager.get_scheme(name)
        self.set_use_dark_scheme(ServiceLocator.get_is_dark_mode())

    def set_use_dark_scheme(self, use_dark_scheme):
        if use_dark_scheme: self.source_buffer.set_style_scheme(self.source_style_scheme_dark)
        else: self.source_buffer.set_style_scheme(self.source_style_scheme_light)

    def get_style_scheme(self):
        return self.source_buffer.get_style_scheme()

    def get_can_undo(self):
        return self.undo_manager.can_undo()

    def get_can_redo(self):
        return self.undo_manager.can_redo()

    def update_indentation_tags(self):
        if self.indentation_update != None:
            start_iter = self.source_buffer.get_iter_at_line(self.indentation_update['line_start'])
            end_iter = start_iter.copy()
            end_iter.forward_chars(self.indentation_update['text_length'])
            end_iter.forward_to_line_end()
            start_iter.set_line_offset(0)
            text = self.source_buffer.get_text(start_iter, end_iter, True)
            for count, line in enumerate(text.splitlines()):
                for tag in start_iter.get_tags():
                    self.source_buffer.remove_tag(tag, start_iter, end_iter)
                number_of_characters = len(line.replace('\t', ' ' * self.settings.get_value('preferences', 'tab_width'))) - len(line.lstrip())
                if number_of_characters > 0:
                    end_iter = start_iter.copy()
                    end_iter.forward_chars(1)
                    self.source_buffer.apply_tag(self.get_indentation_tag(number_of_characters), start_iter, end_iter)
                start_iter.forward_line()

            self.indentation_update = None

    def get_indentation_tag(self, number_of_characters):
        try:
            tag = self.indentation_tags[number_of_characters]
        except KeyError:
            tag = self.source_buffer.create_tag('indentation-' + str(number_of_characters))
            font_manager = ServiceLocator.get_font_manager()
            tag.set_property('indent', -1 * number_of_characters * font_manager.get_char_width(' '))
            self.indentation_tags[number_of_characters] = tag
        return tag

    def insert_before_document_end(self, text):
        end_iter = self.source_buffer.get_end_iter()
        result = end_iter.backward_search('\\end{document}', Gtk.TextSearchFlags.VISIBLE_ONLY, None)
        if result != None:
            self.source_buffer.place_cursor(result[0])
            self.insert_text_at_cursor_and_select_dot('''
''' + text + '''

''')
        else:
            self.insert_text_at_cursor_indent_and_select_dot(text)

    def insert_text_at_cursor_indent_and_select_dot(self, text):
        self.source_buffer.begin_user_action()
        text = self.replace_tabs_with_spaces_if_set(text)
        text = self.replace_first_dot_with_selection(text)
        insert_iter = self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert())
        text = self.indent_text_with_whitespace_at_iter(text, insert_iter)

        self.insert_text_at_cursor_no_user_action(text)
        self.select_nth_dot_before_cursor_for_n_dots_in_text(text)
        self.source_buffer.end_user_action()

    def select_nth_dot_before_cursor_for_n_dots_in_text(self, text):
        dotindex = text.find('•')
        if dotindex > -1:
            start_iter = self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert())
            start_iter.backward_chars(abs(dotindex - len(text)))
            bound = start_iter.copy()
            bound.forward_chars(1)
            self.source_buffer.select_range(start_iter, bound)

    def insert_text_at_cursor_and_select_dot(self, text):
        self.source_buffer.begin_user_action()
        text = self.replace_tabs_with_spaces_if_set(text)
        text = self.replace_first_dot_with_selection(text)
        self.insert_text_at_cursor_no_user_action(text)
        self.select_nth_dot_before_cursor_for_n_dots_in_text(text)
        self.source_buffer.end_user_action()

    def insert_text_at_cursor(self, text):
        self.source_buffer.begin_user_action()
        text = self.replace_tabs_with_spaces_if_set(text)
        text = self.replace_first_dot_with_selection(text)
        self.insert_text_at_cursor_no_user_action(text)
        self.source_buffer.end_user_action()

    def replace_tabs_with_spaces_if_set(self, text):
        if self.settings.get_value('preferences', 'spaces_instead_of_tabs'):
            number_of_spaces = self.settings.get_value('preferences', 'tab_width')
            text = text.replace('\t', ' ' * number_of_spaces)
        return text

    def replace_first_dot_with_selection(self, text):
        dotcount = text.count('•')
        insert_iter = self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert())
        bounds = self.source_buffer.get_selection_bounds()
        selection = ''
        if dotcount == 1:
            bounds = self.source_buffer.get_selection_bounds()
            if len(bounds) > 0:
                selection = self.source_buffer.get_text(bounds[0], bounds[1], True)
                if len(selection) > 0:
                    text = text.replace('•', selection, 1)
        return text

    def insert_text_at_cursor_no_user_action(self, text):
        self.source_buffer.delete_selection(False, False)
        self.source_buffer.insert_at_cursor(text)

    def replace_range_and_select_dot(self, start_iter, end_iter, text):
        self.source_buffer.begin_user_action()
        self.replace_range_no_user_action(start_iter, end_iter, text)
        self.select_nth_dot_before_cursor_for_n_dots_in_text(text)
        self.source_buffer.end_user_action()

    def replace_range_no_user_action(self, start_iter, end_iter, text):
        self.source_buffer.delete(start_iter, end_iter)
        self.source_buffer.insert(start_iter, text)

    def indent_text_with_whitespace_at_iter(self, text, start_iter):
        line_iter = self.source_buffer.get_iter_at_line(start_iter.get_line())
        ws_line = self.source_buffer.get_text(line_iter, start_iter, False)
        lines = text.split('\n')
        ws_number = len(ws_line) - len(ws_line.lstrip())
        whitespace = ws_line[:ws_number]
        final_text = ''
        for no, line in enumerate(lines):
            if no != 0:
                final_text += '\n' + whitespace
            final_text += line
        return final_text

    def insert_before_after(self, before, after):
        bounds = self.source_buffer.get_selection_bounds()

        if len(bounds) > 1:
            text = before + self.source_buffer.get_text(*bounds, 0) + after
            self.replace_range_and_select_dot(bounds[0], bounds[1], text)
        else:
            text = before + '•' + after
            self.insert_text_at_cursor_indent_and_select_dot(text)

    def comment_uncomment(self):
        self.source_buffer.begin_user_action()

        bounds = self.source_buffer.get_selection_bounds()

        if len(bounds) > 1:
            end = (bounds[1].get_line() + 1) if (bounds[1].get_line_index() > 0) else bounds[1].get_line()
            line_numbers = list(range(bounds[0].get_line(), end))
        else:
            line_numbers = [self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert()).get_line()]

        do_comment = False
        for line_number in line_numbers:
            line = self.get_line(line_number)
            if not line.lstrip().startswith('%'):
                do_comment = True

        if do_comment:
            for line_number in line_numbers:
                self.source_buffer.insert(self.source_buffer.get_iter_at_line(line_number), '%')
        else:
            for line_number in line_numbers:
                line = self.get_line(line_number)
                offset = len(line) - len(line.lstrip())
                start = self.source_buffer.get_iter_at_line(line_number)
                start.forward_chars(offset)
                end = start.copy()
                end.forward_char()
                self.source_buffer.delete(start, end)

        self.source_buffer.end_user_action()

    def get_char_at_cursor(self):
        return self.get_chars_at_cursor(1)

    def get_chars_at_cursor(self, number_of_chars):
        start_iter = self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert())
        end_iter = start_iter.copy()
        end_iter.forward_chars(number_of_chars)
        return self.source_buffer.get_text(start_iter, end_iter, False)

    def get_char_before_cursor(self):
        start_iter = self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert())
        end_iter = start_iter.copy()
        end_iter.backward_char()
        return self.source_buffer.get_text(start_iter, end_iter, False)

    def overwrite_chars_at_cursor(self, text):
        start_iter = self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert())
        end_iter = start_iter.copy()
        end_iter.forward_chars(len(text))
        self.source_buffer.begin_user_action()
        self.source_buffer.delete(start_iter, end_iter)
        self.source_buffer.insert_at_cursor(text)
        self.source_buffer.end_user_action()

    def get_line_at_cursor(self):
        return self.get_line(self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert()).get_line())

    def get_line(self, line_number):
        start = self.source_buffer.get_iter_at_line(line_number)
        end = start.copy()
        if not end.ends_line():
            end.forward_to_line_end()
        return self.source_buffer.get_slice(start, end, False)

    def get_all_text(self):
        return self.source_buffer.get_text(self.source_buffer.get_start_iter(), self.source_buffer.get_end_iter(), True)

    def get_text_after_offset(self, offset):
        return self.source_buffer.get_text(self.source_buffer.get_iter_at_offset(offset), self.source_buffer.get_end_iter(), True)

    def get_selected_text(self):
        bounds = self.source_buffer.get_selection_bounds()
        if len(bounds) == 2:
            return self.source_buffer.get_text(bounds[0], bounds[1], True)
        else:
            return None

    def get_current_line_number(self):
        return self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert()).get_line()

    def is_empty(self):
        return self.source_buffer.get_end_iter().get_offset() > 0

    def update_placeholder_selection(self):
        if self.get_cursor_offset() != self.insert_position:
            if not self.source_buffer.get_selection_bounds():
                start_iter = self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert())
                prev_iter = start_iter.copy()
                prev_iter.backward_char()
                if start_iter.has_tag(self.placeholder_tag):
                    while start_iter.has_tag(self.placeholder_tag):
                        start_iter.backward_char()
                    if not start_iter.has_tag(self.placeholder_tag):
                        start_iter.forward_char()
                    end_iter = start_iter.copy()

                    tag_length = 0
                    while end_iter.has_tag(self.placeholder_tag):
                        tag_length += 1
                        end_iter.forward_char()

                    moved_backward_from_end = (self.insert_position == self.get_cursor_offset() + tag_length)
                    if not moved_backward_from_end:
                        self.source_buffer.select_range(start_iter, end_iter)
                elif prev_iter.has_tag(self.placeholder_tag):
                    while prev_iter.has_tag(self.placeholder_tag):
                        prev_iter.backward_char()
                    if not prev_iter.has_tag(self.placeholder_tag):
                        prev_iter.forward_char()
                    end_iter = prev_iter.copy()

                    tag_length = 0
                    while end_iter.has_tag(self.placeholder_tag):
                        tag_length += 1
                        end_iter.forward_char()

                    moved_forward_from_start = (self.insert_position == self.get_cursor_offset() - tag_length)
                    if not moved_forward_from_start:
                        self.source_buffer.select_range(prev_iter, end_iter)

            self.insert_position = self.get_cursor_offset()

    def set_synctex_position(self, position):
        start = self.source_buffer.get_iter_at_line(position['line'])
        end = start.copy()
        if not start.ends_line():
            end.forward_to_line_end()
        text = self.source_buffer.get_text(start, end, False)

        matches = self.get_synctex_word_bounds(text, position['word'], position['context'])
        if matches != None:
            for word_bounds in matches:
                end = start.copy()
                new_start = start.copy()
                new_start.forward_chars(word_bounds[0])
                end.forward_chars(word_bounds[1])
                self.add_synctex_tag(new_start, end)
        else:
            ws_number = len(text) - len(text.lstrip())
            start.forward_chars(ws_number)
            self.add_synctex_tag(start, end)

    def add_synctex_tag(self, start_iter, end_iter):
        self.source_buffer.place_cursor(start_iter)
        self.synctex_tag_count += 1
        color_manager = ServiceLocator.get_color_manager()
        self.source_buffer.create_tag('synctex_highlight-' + str(self.synctex_tag_count), background_rgba=color_manager.get_rgba(0.976, 0.941, 0.420, 0.6), background_full_height=True)
        tag = self.source_buffer.get_tag_table().lookup('synctex_highlight-' + str(self.synctex_tag_count))
        self.source_buffer.apply_tag(tag, start_iter, end_iter)
        if not self.synctex_highlight_tags:
            GObject.timeout_add(15, self.remove_or_color_synctex_tags)
        self.synctex_highlight_tags[self.synctex_tag_count] = {'tag': tag, 'time': time.time()}

    def get_synctex_word_bounds(self, text, word, context):
        if not word: return None
        word = word.split(' ')
        if len(word) > 2:
            word = word[:2]
        word = ' '.join(word)
        regex_pattern = re.escape(word)

        for c in regex_pattern:
            if ord(c) > 127:
                regex_pattern = regex_pattern.replace(c, '(?:\w)')

        matches = list()
        top_score = 0.1
        regex = ServiceLocator.get_regex_object(r'(\W{0,1})' + regex_pattern.replace('\x1b', r'(?:\w{2,3})').replace('\x1c', r'(?:\w{2})').replace('\x1d', r'(?:\w{2,3})').replace('\-', r'(?:-{0,1})') + r'(\W{0,1})')
        for match in regex.finditer(text):
            offset1 = context.find(word)
            offset2 = len(context) - offset1 - len(word)
            match_text = text[max(match.start() - max(offset1, 0), 0):min(match.end() + max(offset2, 0), len(text))]
            score = difflib.SequenceMatcher(None, match_text, context).ratio()
            if bool(match.group(1)) or bool(match.group(2)):
                if score > top_score + 0.1:
                    top_score = score
                    matches = [[match.start() + len(match.group(1)), match.end() - len(match.group(2))]]
                elif score > top_score - 0.1:
                    matches.append([match.start() + len(match.group(1)), match.end() - len(match.group(2))])
        if len(matches) > 0:
            return matches
        else:
            return None

    def remove_or_color_synctex_tags(self):
        for tag_count in list(self.synctex_highlight_tags):
            item = self.synctex_highlight_tags[tag_count]
            time_factor = time.time() - item['time']
            if time_factor > 1.5:
                if time_factor <= 1.75:
                    opacity_factor = int(self.ease(1 - (time_factor - 1.5) * 4) * 20)
                    color_manager = ServiceLocator.get_color_manager()
                    item['tag'].set_property('background-rgba', color_manager.get_rgba(0.976, 0.941, 0.420, opacity_factor * 0.03))
                else:
                    start = self.source_buffer.get_start_iter()
                    end = self.source_buffer.get_end_iter()
                    self.source_buffer.remove_tag(item['tag'], start, end)
                    self.source_buffer.get_tag_table().remove(item['tag'])
                    del(self.synctex_highlight_tags[tag_count])
        return bool(self.synctex_highlight_tags)

    def ease(self, factor): return (factor - 1)**3 + 1

    def place_cursor(self, line_number, offset=0):
        text_iter = self.source_buffer.get_iter_at_line_offset(line_number, offset)
        self.source_buffer.place_cursor(text_iter)

    def get_cursor_offset(self):
        return self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert()).get_offset()

    def get_cursor_line_offset(self):
        return self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert()).get_line_offset()

    def get_cursor_line_number(self):
        return self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert()).get_line()

    def get_line_number_at_offset(self, offset):
        return self.source_buffer.get_iter_at_offset(offset).get_line()

    def get_screen_offsets_by_iter(self, text_iter):
        font_manager = ServiceLocator.get_font_manager()
        line_height = font_manager.get_line_height()
        iter_location = self.source_view.get_iter_location(text_iter)
        gutter = self.source_view.get_window(Gtk.TextWindowType.LEFT)

        if gutter != None:
            gutter_width = gutter.get_width()
        else:
            gutter_width = 0

        x_offset = - self.document.view.scrolled_window.get_hadjustment().get_value()
        y_offset = - self.document.view.scrolled_window.get_vadjustment().get_value()
        x_position = x_offset + iter_location.x - 2 + gutter_width
        y_position = y_offset + iter_location.y + line_height

        return x_position, y_position

    def cursor_ends_word(self):
        return self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert()).ends_word()

    def cut(self):
        self.copy()
        self.delete_selection()

    def copy(self):
        text = self.get_selected_text()
        if text != None:
            clipboard = self.source_view.get_clipboard(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(text, -1)

    def paste(self):
        self.source_view.emit('paste-clipboard')

    def delete_selection(self):
        self.source_buffer.delete_selection(True, True)

    def select_all(self, widget=None):
        self.source_buffer.select_range(self.source_buffer.get_start_iter(), self.source_buffer.get_end_iter())

    def get_modified(self):
        return self.source_buffer.get_modified()

    def set_modified(self, modified):
        self.source_buffer.set_modified(modified)

    def undo(self):
        self.source_buffer.undo()

    def redo(self):
        self.source_buffer.redo()

    def scroll_cursor_onscreen(self):
        text_iter = self.source_buffer.get_iter_at_mark(self.source_buffer.get_insert())
        visible_lines = self.get_number_of_visible_lines()
        iter_position = self.source_view.get_iter_location(text_iter).y
        end_yrange = self.source_view.get_line_yrange(self.source_buffer.get_end_iter())
        buffer_height = end_yrange.y + end_yrange.height
        font_manager = ServiceLocator.get_font_manager()
        line_height = font_manager.get_line_height()
        window_offset = self.source_view.get_visible_rect().y
        window_height = self.source_view.get_visible_rect().height
        gap = min(math.floor(max((visible_lines - 2), 0) / 2), 5)
        if iter_position < window_offset + gap * line_height:
            self.scroll_view(max(iter_position - gap * line_height, 0))
            return
        gap = min(math.floor(max((visible_lines - 2), 0) / 2), 8)
        if iter_position > (window_offset + window_height - (gap + 1) * line_height):
            self.scroll_view(min(iter_position + gap * line_height - window_height, buffer_height))

    def scroll_view(self, position, duration=0.2):
        view = self.document.view.scrolled_window
        adjustment = view.get_vadjustment()
        self.scroll_to = {'position_start': adjustment.get_value(), 'position_end': position, 'time_start': time.time(), 'duration': duration}
        view.set_kinetic_scrolling(False)
        GObject.timeout_add(15, self.do_scroll)

    def do_scroll(self):
        view = self.document.view.scrolled_window
        if self.scroll_to != None:
            adjustment = view.get_vadjustment()
            time_elapsed = time.time() - self.scroll_to['time_start']
            if self.scroll_to['duration'] == 0:
                time_elapsed_percent = 1
            else:
                time_elapsed_percent = time_elapsed / self.scroll_to['duration']
            if time_elapsed_percent >= 1:
                adjustment.set_value(self.scroll_to['position_end'])
                self.scroll_to = None
                view.set_kinetic_scrolling(True)
                return False
            else:
                adjustment.set_value(self.scroll_to['position_start'] * (1 - self.ease(time_elapsed_percent)) + self.scroll_to['position_end'] * self.ease(time_elapsed_percent))
                return True
        return False

    def ease(self, time): return (time - 1)**3 + 1

    def get_number_of_visible_lines(self):
        font_manager = ServiceLocator.get_font_manager()
        line_height = font_manager.get_line_height()
        return math.floor(self.source_view.get_visible_rect().height / line_height)

    def add_packages(self, packages):
        first_package = True
        text = ''
        for packagename in packages:
            if not first_package: text += '\n'
            text += '\\usepackage{' + packagename + '}'
            first_package = False
        self.insert_text_after_packages_if_possible(text)

    def insert_text_after_packages_if_possible(self, text):
        package_data = self.document.get_package_details()
        if package_data:
            max_end = 0
            for package in package_data.values():
                offset, match_obj = package
                if offset > max_end:
                    max_end = offset + match_obj.end() - match_obj.start()
            insert_iter = self.source_buffer.get_iter_at_offset(max_end)
            if not insert_iter.ends_line():
                insert_iter.forward_to_line_end()
            self.source_buffer.place_cursor(insert_iter)
            self.insert_text_at_cursor_indent_and_select_dot('\n' + text)
        else:
            end_iter = self.source_buffer.get_end_iter()
            result = end_iter.backward_search('\\documentclass', Gtk.TextSearchFlags.VISIBLE_ONLY, None)
            if result != None:
                result[0].forward_to_line_end()
                self.source_buffer.place_cursor(result[0])
                self.insert_text_at_cursor_indent_and_select_dot('\n' + text)
            else:
                self.insert_text_at_cursor_indent_and_select_dot(text)

    def remove_packages(self, packages):
        packages_dict = self.document.get_package_details()
        for package in packages:
            try:
                offset, match_obj = packages_dict[package]
            except KeyError: return
            start_iter = self.source_buffer.get_iter_at_offset(offset)
            end_iter = self.source_buffer.get_iter_at_offset(offset + match_obj.end() - match_obj.start())
            text = self.source_buffer.get_text(start_iter, end_iter, False)
            if text == match_obj.group(0):  
                if start_iter.get_line_offset() == 0:
                    start_iter.backward_char()
                self.source_buffer.delete(start_iter, end_iter)


