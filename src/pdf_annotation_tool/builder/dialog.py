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

from dataclasses import dataclass
from typing import Tuple, TYPE_CHECKING
import uuid

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QPushButton, 
                             QGridLayout, QLineEdit, QHBoxLayout, 
                             QDialogButtonBox, QWidget, QMessageBox
)
from PyQt5.QtGui import QColor, QPalette, QFocusEvent

from pdf_annotation_tool.manipulation.trees import BaseSelectionTree, PageTreeWidget
from pdf_annotation_tool.manipulation.visualizer import TreesPanel
from pdf_annotation_tool.selection.data import SelectionCategory
from pdf_annotation_tool.selection.graphic import SelectableRegionItem
if TYPE_CHECKING:
    from pdf_annotation_tool.tool import PDFAnnotationTool


@dataclass
class SelectionUserSpecific: 
    """Data structure to store user specific information about a selection. These are given by `SelectionDialog`."""
    
    id_: str # the unique id of the new selection
    category: SelectionCategory # either Title, Text, Table, Image, or, etc.
    image_resolution: Tuple[int, int] # e.g., "512x512" becomes `(512, 512)`
    parent_id: str # the id of the parent title/container, or "ROOT" if none



class SelectionDialog(QDialog):
    """The dialog to get user input about a new selection, i.e., its category (Title, Text, Table, Image, etc.) and its parent title/container. 
    It also allows to set the maximum image resolution for screenshots. It returns a `SelectionUserSpecific` instance or `None` if the user 
    cancelled the dialog. It is used by `BaseSelectionHandler`."""
     
    MAX_IMAGE_RESOLUTION = "512x512" # default maximum image resolution for screenshots

    def __init__(self, main_view: 'PDFAnnotationTool', last_title_id: str = None, parent: QWidget = None, default_img_resolution: Tuple[int, int] = MAX_IMAGE_RESOLUTION, initial_selection: SelectableRegionItem = None):
        """Initialize the dialog's graphic.
            - main_view: the `MainView` instance to access the selection tree
            - last_title_id: the id of the last title selected, to preselect it in the tree
            - parent: the parent widget
            - default_img_resolution: the default maximum image resolution for screenshots, e.g., "512x512"
            - initial_selection: if given, it is a `SelectableRegionItem` instance to edit, otherwise a new selection is created
        """
        
        # Initialize class properties
        self.image_resolution = None
        self.main_view = main_view
        
        # Set selection data from input or create new
        if initial_selection is not None:
            self.selected_category = initial_selection.data.category
            self.last_title_id = initial_selection.data.parent
            self.new_selection_id = initial_selection.data.id_
        else:
            self.selected_category = None
            self.last_title_id = last_title_id
            self.new_selection_id = str(uuid.uuid4())
        
        # Initialize the graphic
        super().__init__(parent)
        self.resize(400, 600)  # width, height
        self.setWindowTitle("Edit Selection Properties")
            
        layout = QVBoxLayout(self)

        # --- Category buttons ---
        layout.addWidget(QLabel("Select the Category:"))
        self.buttons = {}
        grid_layout = QGridLayout()
        # Create category buttons in a 2x6 grid
        for i, category in enumerate(SelectionCategory):
            row, col = divmod(i, 6)
            btn_text = f"{category.value.name} ({category.value.shortcut})"
            btn = QPushButton(btn_text)
            btn.setCheckable(True)
            if category.value.shortcut:
                btn.setShortcut(category.value.shortcut)
            btn.clicked.connect(lambda checked, c=category: self._onCategorySelected(c))
            btn.setStyleSheet(self._category_btn_style(category.value.color, selected=False))
            btn.setMinimumHeight(28)
            btn.setMinimumWidth(80)
            grid_layout.addWidget(btn, row, col)
            self.buttons[category] = btn
        if self.selected_category is not None:
            self._onCategorySelected(self.selected_category)
        layout.addLayout(grid_layout)
        
        # --- Tree ---
        layout.addWidget(QLabel("Choose Section Parent:"))
        self.trees_panel = TreesPanel(self.main_view._selections, parent=self, show_page_tree=False, show_hier_tree=True, enable_drag_drop=False, enable_multi_selection=False)
        if self.last_title_id == None:
            self.last_title_id = self.trees_panel.hier_tree.root.data(0, BaseSelectionTree.ID_ROLE)
        self.trees_panel.hier_tree.expand_and_select_by_id(self.last_title_id)
        layout.addWidget(self.trees_panel)
                
        # --- Image resolution ---
        self.image_res_label = QLabel("Max Screenshot Resolution (WxH):")
        self.image_res_input = QLineEdit(default_img_resolution)
        res_layout = QHBoxLayout()
        res_layout.addWidget(self.image_res_label)
        res_layout.addWidget(self.image_res_input)
        layout.addLayout(res_layout)

        # --- OK/Cancel ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        layout.addWidget(self.button_box)

        self.ok_button = self.button_box.button(QDialogButtonBox.Ok)

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # Track focus events of text edit to gain focus over the button OK
        self.trees_panel.search_input.focusInEvent = self.on_search_text_focus_in
        self.trees_panel.search_input.focusOutEvent = self.on_search_text_focus_out


    def on_search_text_focus_in(self, event: QFocusEvent) -> None:
        """Disable the OK button while typing in the search input to avoid accidental acceptance."""
        
        self.ok_button.setDefault(False)
        self.ok_button.setAutoDefault(False)
        super(QLineEdit, self.trees_panel.search_input).focusInEvent(event)


    def on_search_text_focus_out(self, event: QFocusEvent) -> None:
        """Restore the OK button default behavior when leaving the search input."""
        
        self.ok_button.setDefault(True)
        self.ok_button.setAutoDefault(True)
        super(QLineEdit, self.trees_panel.search_input).focusOutEvent(event)


    def _category_btn_style(self, color: str, selected: bool=False, alpha: int=100) -> str:
        """Return the stylesheet for a category button.
            - color: the border color of the button in hex format, e.g., "#RRGGBB"
            - selected: if True, the button is in selected state
            - alpha: the alpha value (0-255) for the selected background color
        """
        
        # Determine if the current theme is dark or light
        palette = self.palette()
        base_color = palette.color(QPalette.Window)
        is_dark = base_color.value() < 128

        # Compute the selected background color by blending with light or dark
        qcolor = QColor(color)
        if selected:
            blended = qcolor.lighter(150) if is_dark else qcolor.darker(120)
            blended.setAlpha(alpha)
            selected_bg = blended.name(QColor.HexArgb)
        else:
            selected_bg = "transparent"

        # Return the stylesheet
        return (
            f"""
            QPushButton {{
                border: 2px solid {color};
                border-radius: 8px;
                padding: 4px 8px;
                min-width: 80px;
                min-height: 28px;
                background-color: transparent;
            }}
            QPushButton:checked {{
                border: 3px solid {color};
                background-color: {selected_bg};
                font-weight: bold;
            }}
            QPushButton:hover {{
                border: 2px solid {color};
                background-color: palette(midlight);
            }}
            QPushButton:checked:hover {{
                border: 3px solid {color};
                background-color: {selected_bg};
            }}
            """)

    
    def _onCategorySelected(self, category: SelectionCategory):
        """Handle the selection of a category button."""
        
        self.selected_category = category
        for c, btn in self.buttons.items():
            btn.setChecked(c == category) # Only the selected category button is checked
            btn.setStyleSheet(self._category_btn_style(c.value.color, selected=(c == category))) # Update styles


    def accept(self):
        """Handle the acceptance of the dialog, validating inputs and storing results (see `get_results`)."""
        
        # Validate inputs
        if not self.selected_category:
            QMessageBox.warning(self, "Input not valid", 
                                "Chose a selection Category among: Title, Text, Table, Image etc.")
            return
        
        # Get the parent id from the tree           
        selected_items = self.trees_panel.hier_tree.get_selected_node_data()
        if len(selected_items) <= 0:
            # No item selected
            QMessageBox.warning(self, "Input not valid",
                                "Choose at least one title to be related to.")
            return
        else:
            # Only one item should be selected
            selected = selected_items[0]
            if isinstance(selected, str):
                if selected == BaseSelectionTree.ROOT_ID:
                    # Set parent to ROOT
                    self.parent_id = selected
                elif selected == PageTreeWidget.PAGE_NODE_ID:
                    # Cannot set a page node as parent
                    QMessageBox.warning(self, "Input not valid",
                                        "Cannot set a page node as the parent node.")
                    return
                else:
                    # Something went wrong
                    QMessageBox.warning(self, "Input not valid",
                                        "Error on encoding the selection.")
                    return
            else:
                # Set parent to the selected node id
                self.parent_id = selected.id_
                
        # Get the maximum screenshot size
        self.image_resolution = SelectionDialog.parse_image_resolution(self.image_res_input.text())
        if self.image_resolution is None:
            return
        
        super().accept()


    def get_results(self) -> SelectionUserSpecific:
        """Return a `SelectionUserSpecific` instance with the user input, to be used by `BaseSelectionHandler`.
        It should be called after `accept()`."""
        return SelectionUserSpecific(
            id_ = self.new_selection_id,
            category = self.selected_category,
            image_resolution = self.image_resolution,
            parent_id = self.parent_id,
        )


    @staticmethod
    def parse_image_resolution(text: str) -> Tuple[int, int] | None:
        """Parse the image resolution from a string in the format "WIDTHxHEIGHT", e.g., "512x512".
        Return a tuple (WIDTH, HEIGHT) if valid, otherwise show an alert and return None."""
        
        try: # Check that input given by the user is feasible
            resolution = text.strip().lower().replace(" ", "").split("x")
            img_res_x = int(resolution[0])
            img_res_y = int(resolution[1])
            return (img_res_x, img_res_y)
        except Exception:
            QMessageBox.warning(None, "Input not valid", 
                                "Resolution not valid should be two integer divided by 'x', e.g. (512x512).")
            return None
