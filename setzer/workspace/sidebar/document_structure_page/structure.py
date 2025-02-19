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
from gi.repository import Gtk
from gi.repository import Gdk
from gi.repository import cairo

import os.path

import setzer.workspace.sidebar.document_structure_page.structure_widget as structure_widget
import setzer.workspace.sidebar.document_structure_page.structure_viewgtk as structure_section_view


class StructureSection(structure_widget.StructureWidget):

    def __init__(self, data_provider, labels):
        structure_widget.StructureWidget.__init__(self, data_provider)

        self.levels = {'part': 0, 'chapter': 1, 'section': 2, 'subsection': 3, 'subsubsection': 4, 'paragraph': 5, 'subparagraph': 6, 'file': 7}

        self.labels = labels
        self.view = structure_section_view.StructureSectionView(self)
        self.init_view()

        self.nodes = list()
        self.nodes_in_line = list()

    def on_button_press(self, drawing_area, event):
        modifiers = Gtk.accelerator_get_default_mod_mask()

        if event.type == Gdk.EventType.BUTTON_PRESS and event.button == 1 and event.state & modifiers == 0:
            item_num = max(0, min(int((event.y - 9) // self.view.line_height), len(self.nodes_in_line) - 1))
            item = self.nodes_in_line[item_num]['item']

            document = item[0]
            line_number = item[1]
            if document == None:
                filename = self.nodes_in_line[item_num]['item'][3]
                document = self.data_provider.workspace.open_document_by_filename(filename)
            self.data_provider.workspace.set_active_document(document)
            document.content.place_cursor(line_number)
            document.content.scroll_cursor_onscreen()
            self.data_provider.workspace.active_document.view.source_view.grab_focus()

    #@timer
    def update_items(self, *params):
        sections = dict()

        includes = self.data_provider.get_includes()
        blocks = list()
        for block in self.data_provider.document.get_blocks():
            while len(includes) > 0 and includes[0]['offset'] < block[0]:
                if includes[0]['document'] != None:
                    for block_included in includes[0]['document'].get_blocks():
                        if len(block_included) < 7:
                            block_included.append(includes[0]['document'])
                        blocks.append(block_included)
                else:
                    file_block = [0, 0, 0, 0, 'file', includes[0]['filename'], includes[0]['document']]
                    blocks.append(file_block)
                del(includes[0])
            if len(block) < 7:
                block.append(self.data_provider.document)
            blocks.append(block)

        while len(includes) > 0:
            if includes[0]['document'] != None:
                for block in includes[0]['document'].get_blocks():
                    if len(block) < 7:
                        block.append(includes[0]['document'])
                    blocks.append(block)
            else:
                file_block = [0, 0, 0, 0, 'file', includes[0]['filename'], includes[0]['document']]
                blocks.append(file_block)
            del(includes[0])

        last_line = -1
        for block in blocks:
            if block[1] != None and block[4] in self.levels and block[2] != last_line:
                sections[block[2]] = {'document': block[6], 'offset_start': block[0], 'starting_line': block[2], 'block': block}
                last_line = block[2]

        current_level = 0
        nodes = list()
        nodes_in_line = list()
        predecessor = {0: None, 1: None, 2: None, 3: None, 4: None, 5: None, 6: None, 7: None}
        for section in sections.values():
            section_type = section['block'][4]
            level = self.levels[section_type]
            node = {'item': [section['document'], section['starting_line'], section_type + '-symbolic', ' '.join(section['block'][5].splitlines())], 'children': list()}
            if predecessor[level] == None:
                nodes.append(node)
            else:
                predecessor[level]['children'].append(node)
            nodes_in_line.append(node)

            for i in range(level + 1, 8):
                predecessor[i] = node

        if len(nodes_in_line) == 0:
            self.height = 0
            self.view.hide()
            self.labels['inline'].hide()
            self.labels['overlay'].hide()
        else:
            self.height = len(nodes_in_line) * self.view.line_height + 33
            self.view.show()
            self.labels['inline'].show()
            self.labels['overlay'].show()
        self.view.set_size_request(-1, self.height)
        self.nodes_in_line = nodes_in_line
        self.nodes = nodes
        self.set_hover_item(None)
        self.view.queue_draw()

    #@timer
    def draw(self, drawing_area, ctx):
        if len(self.nodes) == 0:
            return True

        first_line, last_line = self.get_first_line_last_line(ctx)
        self.drawing_setup(ctx)
        self.draw_background(ctx)
        self.draw_nodes(self.nodes, first_line, last_line, 0, 0, drawing_area, ctx)

    def draw_nodes(self, nodes, first_line, last_line, level, count, drawing_area, ctx):
        for node in nodes:
            if count >= first_line and count <= last_line:
                self.draw_hover_background(ctx, count)
                self.draw_icon(ctx, node['item'][2], 9 + level * 18, count)

                if node['item'][2] == 'file-symbolic':
                    text = os.path.basename(node['item'][3])
                else:
                    text = node['item'][3]

                self.draw_text(ctx, 35 + level * 18, count, text)
            count += 1
            count = self.draw_nodes(node['children'], first_line, last_line, level + 1, count, drawing_area, ctx)
        return count


