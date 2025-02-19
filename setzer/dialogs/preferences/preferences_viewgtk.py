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


class Preferences(object):
    ''' Preferences dialog. '''

    def __init__(self, main_window):
        builder = Gtk.Builder.new_from_string('<?xml version="1.0" encoding="UTF-8"?><interface><object class="GtkDialog" id="dialog"><property name="use-header-bar">1</property></object></interface>', -1)

        self.dialog = builder.get_object('dialog')
        self.dialog.set_destroy_with_parent(True)
        self.dialog.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.dialog.set_modal(True)
        self.dialog.set_transient_for(main_window)
        self.dialog.set_can_focus(False)
        self.dialog.set_size_request(400, 400)
        self.dialog.set_default_size(400, 400)

        self.headerbar = self.dialog.get_header_bar()
        self.headerbar.set_title(_('Preferences'))

        self.topbox = self.dialog.get_content_area()
        self.topbox.set_border_width(0)

        self.notebook = Gtk.Notebook()
        self.notebook.set_show_tabs(True)
        self.notebook.set_show_border(False)
        self.topbox.pack_start(self.notebook, True, True, 0)

    def run(self):
        return self.dialog.run()
        
    def response(self, args):
        self.dialog.response(args)
        
    def __del__(self):
        self.dialog.destroy()

