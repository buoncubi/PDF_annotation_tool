# -*- coding: utf-8 -*-
# -----------------------------------------------------------------------------
# Author: Luca Buoncompagni
# Version: 1.0
# Date: December 2025
# License: GNU Affero General Public License v3.0 (AGPL-3.0)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.
# -----------------------------------------------------------------------------

from typing import List, Tuple
from PyQt5.QtWidgets import QWidget, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QTextEdit, QComboBox, QSplitter, QSizePolicy, QFrame, QDialogButtonBox, QSpacerItem
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFontMetrics
import copy

from pdf_annotation_tool.selection.data import SelectionData, SelectionCategory
from pdf_annotation_tool.utils.image import ImageWindow

class SelectionDataEditingWidget(QWidget):
    """
    Purely graphical widget showing `SelectionData` fields, and allows some data modification.
    No dialog buttons, no accept/reject, just the layout. It is used inside `SelectionDataEditingDialog` and `AugmentInteractiveDialog`.
    """
    
    def __init__(self, selection_data: SelectionData, parent: QWidget=None, show_description: bool=True):
        super().__init__(parent)
        
        # Class properties
        self.selection_data = selection_data # Original data, not modified
        self.show_description = show_description # Whether to show the description field or not (It is not needed by `AugmentInteractiveDialog``)

        # MAIN SPLITTER: left fields | right image
        main_splitter = QSplitter(Qt.Horizontal, self)

        # -----------------------------
        # LEFT side
        # -----------------------------
        left_splitter = QSplitter(Qt.Vertical)
        left_splitter.setMinimumWidth(200)

        # --- Helper for row with label ---
        def _make_row_widget(label_text: str, widget: QWidget) -> QWidget:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(4, 2, 4, 2)
            h.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
            h.addWidget(lbl)
            h.addWidget(widget)
            return row

        # --- TOP non-editable fields ---
        top_splitter = QSplitter(Qt.Vertical)

        self.id_edit = QLineEdit(selection_data.id_)
        self._prepare_line(self.id_edit, read_only=True)
        top_splitter.addWidget(_make_row_widget("ID:", self.id_edit))

        self.doc_edit = QLineEdit(selection_data.doc)
        self._prepare_line(self.doc_edit, read_only=True)
        top_splitter.addWidget(_make_row_widget("Document:", self.doc_edit))

        self.page_edit = QLineEdit(str(selection_data.page))
        self._prepare_line(self.page_edit, read_only=True)
        self.idx_edit = QLineEdit(str(selection_data.idx))
        self._prepare_line(self.idx_edit, read_only=True)

        page_idx_row = QWidget()
        page_idx_layout = QHBoxLayout(page_idx_row)
        page_idx_layout.setContentsMargins(4, 2, 4, 2)
        page_idx_layout.setSpacing(6)
        page_idx_layout.addWidget(QLabel("Page:"))
        page_idx_layout.addWidget(self.page_edit)
        page_idx_layout.addSpacerItem(QSpacerItem(18, 1, QSizePolicy.Fixed, QSizePolicy.Minimum))
        page_idx_layout.addWidget(QLabel("Index:"))
        page_idx_layout.addWidget(self.idx_edit)
        page_idx_layout.addStretch()
        top_splitter.addWidget(page_idx_row)

        self.coords_edit = QTextEdit(
            SelectionDataEditingWidget.format_coords(selection_data.coords)
        )
        self._prepare_text(self.coords_edit, read_only=True, min_lines=6)
        top_splitter.addWidget(_make_row_widget("Coords:", self.coords_edit))

        self.parent_edit = QTextEdit(str(selection_data.parent))
        self._prepare_text(self.parent_edit, read_only=True, min_lines=1)
        top_splitter.addWidget(_make_row_widget("Parent:", self.parent_edit))

        self.children_edit = QTextEdit(
            SelectionDataEditingWidget.format_str_list(selection_data.children)
        )
        self._prepare_text(self.children_edit, read_only=True, min_lines=6)
        top_splitter.addWidget(_make_row_widget("Children:", self.children_edit))

        # Separator
        top_container = QWidget()
        top_layout = QVBoxLayout(top_container)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(top_splitter)
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFrameShadow(QFrame.Sunken)
        top_layout.addWidget(sep)
        left_splitter.addWidget(top_container)

        # --- Category ---
        cat_widget = QWidget()
        cat_h = QHBoxLayout(cat_widget)
        cat_h.setContentsMargins(6, 4, 6, 4)
        cat_label = QLabel("Category:")
        self.category_combo = QComboBox()
        for cat in SelectionCategory:
            self.category_combo.addItem(cat.value.name, cat)
        try:
            self.category_combo.setCurrentIndex(
                list(SelectionCategory).index(selection_data.category)
            )
        except Exception:
            pass
        cat_h.addWidget(cat_label)
        cat_h.addWidget(self.category_combo)
        cat_h.addStretch()
        left_splitter.addWidget(cat_widget)

        # --- Text + Description ---
        inner_splitter = QSplitter(Qt.Vertical)
        
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(selection_data.text)
        self._prepare_text(self.text_edit, min_lines=10)
        text_panel = QWidget()
        tv = QVBoxLayout(text_panel)
        tv.setContentsMargins(6, 4, 6, 4)
        tv.addWidget(QLabel("Text:"))
        tv.addWidget(self.text_edit)
        inner_splitter.addWidget(text_panel)

        if show_description:
            self.description_edit = QTextEdit()
            self.description_edit.setPlainText(selection_data.description)
            self._prepare_text(self.description_edit, min_lines=10)
            desc_panel = QWidget()
            dv = QVBoxLayout(desc_panel)
            dv.setContentsMargins(6, 4, 6, 4)
            dv.addWidget(QLabel("Description:"))
            dv.addWidget(self.description_edit)
            inner_splitter.addWidget(desc_panel)

        left_splitter.addWidget(inner_splitter)
        main_splitter.addWidget(left_splitter)

        # -----------------------------
        # RIGHT: image
        # -----------------------------
        right_splitter = QSplitter(Qt.Horizontal)
        if getattr(selection_data, "image", None):
            try:
                self.image_window = ImageWindow(selection_data.image, self)
                right_splitter.addWidget(self.image_window)
            except Exception as e:
                right_splitter.addWidget(QLabel(f"[Error loading image: {e}]"))
        else:
            right_splitter.addWidget(QLabel("No image available"))
        main_splitter.addWidget(right_splitter)

        # MAIN LAYOUT
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(main_splitter)

        #try:
        #    main_splitter.setSizes([300, 700])
        #    left_splitter.setSizes([300, 60, 340])
        #    inner_splitter.setSizes([240, 240])
        #except Exception:
        #    pass


    def get_data(self) -> SelectionData:
        """Get the edited data as a new SelectionData object."""
        
        edited_data = copy.deepcopy(self.selection_data)
        edited_data.category = self.category_combo.currentData()
        edited_data.text = self.text_edit.toPlainText()
        if self.show_description:
            edited_data.description = self.description_edit.toPlainText()
        return edited_data

    
    @staticmethod
    def _prepare_line(widget: QLineEdit, read_only: bool = False) -> None:
        """Prepare a `widget`, i.e., set `read_only`, minimum height, and size policy."""
        
        widget.setReadOnly(read_only)
        fm = QFontMetrics(widget.font())
        widget.setMinimumHeight(fm.lineSpacing())# + 12)
        widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        

    @staticmethod
    def _prepare_text(widget: QTextEdit , read_only: bool = False, min_lines=1) -> None:
        """Prepare a `widget`, i.e., set `read_only`, minimum height (with an heuristic `min_line`), and size policy."""
        
        widget.setReadOnly(read_only)
        fm = QFontMetrics(widget.font())
        widget.setMinimumHeight(fm.lineSpacing() * min_lines)# + 8)


    @staticmethod
    def format_str_list(l: List, tab: str = "   ") -> str:
        """Format a list of strings (or other types) into a pretty string representation (similar to JSON)."""
        
        if not l:
            return ""
        if len(l) == 1:
            return f"[ {l[0]} ]"
        return "[\n" + "".join(f"{tab}{i},\n" for i in l)[:-2] + "\n]"


    @staticmethod
    def format_coords(coords: List[Tuple[float, float]]) -> str:
        """Format a list of coordinates `[[x0, y0], [x1, y1], ...]` into a pretty string representation (similar to JSON)."""
        
        if not coords:
            return ""
        if len(coords) == 1:
            return f"[ {coords[0][0]:.2f} , {coords[0][1]:.2f} ]"
        return SelectionDataEditingWidget.format_str_list(
            [f"{x:.2f} , {y:.2f}" for x, y in coords]
        )
        
        

class SelectionDataEditingDialog(QDialog):
    """The dialog to edit a `SelectionData` object, using `SelectionDataEditingWidget` as the main content.
    The output data is available in the `edited_data` property after acceptance, and the `is_edited` boolean is provided as well.
    It is shown by double-clicking an item in the `BaseSelectionTree`."""

    def __init__(self, selection_data: SelectionData, parent=None):
        """Start the dialog to edit `selection_data`."""
        
        super().__init__(parent)
        
        # Class properties
        self.selection_data = selection_data # Te output data, initially the same as input
        self.is_edited = False # Whether the data has been edited or not
        self.edited_data = None
        
        self.setWindowTitle("Edit Selection Data")
        self.resize(1000, 700)

        self.widget = SelectionDataEditingWidget(selection_data, self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.widget)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)


    def accept(self) -> None:
        """Handle the acceptance of the dialog, validating inputs and storing results.
        If no changes were made, the dialog is rejected instead."""
        
        if self.edited_data != self.widget.get_data():
            self.is_edited = True
            self.edited_data = self.widget.get_data()
            super().accept()
        else:
            super().reject()
       