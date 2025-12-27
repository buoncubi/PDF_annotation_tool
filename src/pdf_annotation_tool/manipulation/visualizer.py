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

from typing import Dict, List, Set, Tuple

from PyQt5.QtWidgets import QWidget, QSplitter, QVBoxLayout, QHBoxLayout, QCheckBox, QPushButton, QLineEdit, QMenu, QToolButton, QWidgetAction, QTreeWidget, QTreeWidgetItemIterator
from PyQt5.QtCore import Qt

from pdf_annotation_tool.manipulation.trees import BaseSelectionTree, HierarchyTreeWidget, PageTreeWidget
from pdf_annotation_tool.selection.data import SelectionCategory, SelectionData
from pdf_annotation_tool.selection.manager import SelectionsManager



class TreesPanel(QWidget):
    """Combined panel displaying both page-based and hierarchical tree views of selections 
    (i.e., `PageTreeWidget` and `HierarchyTreeWidget`).
    
    Provides filtering, searching, and synchronized selection between PageTreeWidget 
    and HierarchyTreeWidget. Includes category filtering and field-based search functionality.
    """
    
    def __init__(self, selections: SelectionsManager, parent: QWidget = None, show_page_tree: bool = True, show_hier_tree: bool = True, enable_drag_drop: bool = True, enable_multi_selection: bool = True) -> None:
        """Initialize TreesPanel with dual tree views and control widgets.
        
        Args:
            selections (SelectionsManager): The selections data to display.
            parent (QWidget, optional): Parent widget.
            show_page_tree (bool): Whether to show the page-based tree view (it collapse or not the split view).
            show_hier_tree (bool): Whether to show the hierarchical tree view (it collapse or not the split view).
            enable_drag_drop (bool): Whether to enable drag-and-drop operations.
            enable_multi_selection (bool): Whether to allow multiple item selection.
            
        Returns:
            None
        """
        super().__init__(parent)
        
        # Data fields
        self.selections = selections # The actual data to be shown
        self.syncing_sel = False # Flag for selection synching

        # Sync checkbox
        self.sync_checkbox = QCheckBox("Sync Selections")
        self.sync_checkbox.setChecked(True)

        # Create the trees
        self.page_tree = PageTreeWidget(self.selections, self, enable_drag_drop, enable_multi_selection, self.sync_checkbox)
        self.hier_tree = HierarchyTreeWidget(self.selections, self, enable_drag_drop, enable_multi_selection, self.sync_checkbox)

        # Filtering UI
        filter_btn, self.category_actions = self.make_category_filter_dropdown()

        # Search UI
        self.search_input = QLineEdit()
        self.search_input.setMinimumWidth(50)
        self.search_input.setMaximumWidth(1000)
        self.search_input.setPlaceholderText("Search text...")
        self.search_btn = QPushButton("Search")
        self.field_button, self.field_actions = self.make_searching_ui()
        
        top_row = QHBoxLayout()
        top_row.addWidget(filter_btn)
        top_row.addSpacing(10)
        top_row.addWidget(self.search_input)
        top_row.addWidget(self.field_button)
        top_row.addWidget(self.search_btn)
        top_row.addSpacing(10)
        top_row.addWidget(self.sync_checkbox)
        
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.page_tree)
        splitter.addWidget(self.hier_tree)

        main_layout = QVBoxLayout(self)
        main_layout.addLayout(top_row)
        main_layout.addWidget(splitter)
        
        # HIDE widget if {False, False}, [0,1] if {False, True}, [1,0] if {True, False}, [1,1] if {True, True}
        if not show_page_tree and not show_hier_tree:
            splitter.hide()
        else:
            splitter.setSizes([int(show_page_tree) == 1, int(show_hier_tree) == 1]) 
            
        # Hook signals
        self.page_tree.selection_changed.connect(self._on_page_selection_changed)
        self.page_tree.data_changed.connect(self._on_page_data_changed)
        self.hier_tree.selection_changed.connect(self._on_hier_selection_changed)
        self.hier_tree.data_changed.connect(self._on_hier_data_changed)
        self.search_btn.clicked.connect(self._on_search)
        self.search_input.returnPressed.connect(self._on_search)
    
    
    def make_category_filter_dropdown(self) -> Tuple[QToolButton, Dict[SelectionCategory, QCheckBox]]:
        """Create dropdown button with checkboxes for filtering by selection categories.

        Creates a tool button with popup menu containing checkboxes for each `SelectionCategory`.
        When checkboxes are toggled, calls `on_category_filter_changed` to update tree visibility.

        Returns:
            Tuple containing:
            - btn (QToolButton): The dropdown button widget
            - actions (Dict[SelectionCategory, QCheckBox]): Mapping of categories to their checkboxes
        """

        # Setup category menu
        btn = QToolButton()
        btn.setText("Show Category   ")
        btn.setPopupMode(QToolButton.InstantPopup)
        menu = QMenu(btn)
        actions = {}
        for cat in SelectionCategory:
            # Instead of QAction, use QWidgetAction + QCheckBox
            checkbox = QCheckBox(cat.value.name)
            checkbox.setChecked(True)

            #qcolor = QColor(cat.value.color)
            #checkbox.setStyleSheet(f"color: {qcolor.name()}; font-weight: bold;")

            checkbox.stateChanged.connect(
                lambda state, c=cat: self.on_category_filter_changed(c, state == 2)
            )

            wa = QWidgetAction(menu)
            wa.setDefaultWidget(checkbox)
            menu.addAction(wa)
            actions[cat] = checkbox

        btn.setMenu(menu)
        return btn, actions


    def on_category_filter_changed(self, category: SelectionCategory, enabled: bool) -> None:
        """Update category visibility in both tree widgets when filter checkbox changes.

        Args:
            category (SelectionCategory): The category to enable/disable.
            enabled (bool): Whether the category should be visible.
            
        Returns:
            None
        """
        
        self.page_tree.set_category_enabled(category, enabled)
        self.hier_tree.set_category_enabled(category, enabled)


    def make_searching_ui(self) -> Tuple[QToolButton, Dict[str, QCheckBox]]:
        """Create dropdown button with checkboxes for selecting search fields.
        
        Creates a tool button with popup menu containing checkboxes for each field
        from `SelectionData.get_fields_name()`. Used to control which fields are
        searched when performing text searches.
        
        Returns:
            Tuple containing:
            - btn (QToolButton): The dropdown button widget
            - actions (Dict[str, QCheckBox]): Mapping of field names to their checkboxes
        """

        btn = QToolButton()
        btn.setText("Filter   ")
        btn.setPopupMode(QToolButton.InstantPopup)

        menu = QMenu(btn)
        actions = {}

        for fields in SelectionData.get_fields_name():
            # Instead of QAction, use QWidgetAction + QCheckBox
            checkbox = QCheckBox(fields)
            checkbox.setChecked(True)
            
            wa = QWidgetAction(menu)
            wa.setDefaultWidget(checkbox)
            menu.addAction(wa)
            actions[fields] = checkbox

        btn.setMenu(menu)
        return btn, actions


    def _on_page_selection_changed(self) -> None:
        """Synchronize hierarchy tree selection when page tree selection changes.

        When sync is enabled and not already syncing, gets selected IDs from `page_tree`
        and applies same selection to `hier_tree` via `_select_ids_in_tree`.

        Returns:
            None
        """
          
        if not self.sync_checkbox.isChecked() or self.syncing_sel:
            return
        self.syncing_sel = True
        
        try:
            selected_ids = {item.data(0, BaseSelectionTree.ID_ROLE) for item in self.page_tree.selectedItems() if item.data(0, BaseSelectionTree.ID_ROLE)}
            self._select_ids_in_tree(self.hier_tree, selected_ids)
        finally:
            self.syncing_sel = False


    def _on_hier_selection_changed(self) -> None:
        """Synchronize page tree selection when hierarchy tree selection changes.
        
        When sync is enabled and not already syncing, gets selected IDs from `hier_tree`
        and applies same selection to `page_tree` via `_select_ids_in_tree`.
        
        Returns:
            None
        """
        
        if not self.sync_checkbox.isChecked() or self.syncing_sel:
            return
        self.syncing_sel = True
        
        try:
            selected_ids = {item.data(0, BaseSelectionTree.ID_ROLE) for item in self.hier_tree.selectedItems() if item.data(0, BaseSelectionTree.ID_ROLE)} 
            self._select_ids_in_tree(self.page_tree, selected_ids)
        finally:
            self.syncing_sel = False


    def _on_page_data_changed(self) -> None:
        """Rebuild hierarchy tree when page tree data changes to maintain synchronization."""

        self.hier_tree.rebuild_safe()


    def _on_hier_data_changed(self) -> None:
        """Rebuild page tree when hierarchy tree data changes to maintain synchronization."""

        self.page_tree.rebuild_safe()


    def _select_ids_in_tree(self, tree: QTreeWidget, ids: Set[str]) -> None:
        """Select items in tree widget by their selection IDs and expand parent nodes.
        
        Iterates through all tree items, selects those with IDs in the given set,
        and expands their parent nodes for visibility. Blocks signals during operation.
        
        Args:
            tree (QTreeWidget): The tree widget to modify selection in.
            ids (Set[str]): Set of selection IDs to select.
            
        Returns:
            None
        """

        tree.blockSignals(True)
        tree.clearSelection()
        it = QTreeWidgetItemIterator(tree)
        while it.value():
            item = it.value()
            sel_id = item.data(0, BaseSelectionTree.ID_ROLE)
            if sel_id and sel_id in ids:
                item.setSelected(True)
                parent = item.parent()
                while parent:
                    parent.setExpanded(True)
                    parent = parent.parent()
            it += 1
        tree.blockSignals(False)


    def _on_search(self) -> None: # TODO move thus function in `PageTreeWidget` and `HierarchyTreeWidget`
        """Perform text search across both trees and select matching items.
        
        Gets query from `search_input` and enabled fields from `field_actions`,
        searches both trees using `search_nodes`, then selects and expands
        matching items in both trees.
        
        Returns:
            None
        """

        query = self.search_input.text().strip()
        fields = {f for f, act in self.field_actions.items() if act.isChecked()}
        if not query:
            return
        p_results = self.page_tree.search_nodes(query, fields)
        h_results = self.hier_tree.search_nodes(query, fields)
        # select results in each tree
        self.page_tree.clearSelection()
        self.hier_tree.clearSelection()
        # helper to select set of (page,idx)
        def sel_in_tree(tree_widget, results):
            idset = set()
            # build mapping
            for sel_id, (p, i, sp) in BaseSelectionTree.build_selection_map(self.selections).items():
                if (p, i) in results:
                    idset.add(sel_id)
            it = QTreeWidgetItemIterator(tree_widget)
            while it.value():
                item = it.value()
                sel_id = item.data(0, BaseSelectionTree.ID_ROLE)
                if sel_id and sel_id in idset:
                    item.setSelected(True)
                    parent = item.parent()
                    while parent:
                        parent.setExpanded(True)
                        parent = parent.parent()
                it += 1
        sel_in_tree(self.page_tree, p_results)
        sel_in_tree(self.hier_tree, h_results)


    def _on_clear_selection(self) -> None:
        """Clear selection in both page and hierarchy trees."""

        self.page_tree.clearSelection()
        self.hier_tree.clearSelection()

    # Exposed helper methods
    def expand_and_select(self, nodes: List[Tuple[int, int]]) -> None:
        """Expand both trees and select given nodes by (page, idx) coordinates.
        
        Args:
            nodes (List[Tuple[int, int]]): List of (page, idx) tuples to select.
            
        Returns:
            None
        """

        self.page_tree.expand_and_select(nodes)
        self.hier_tree.expand_and_select(nodes)


    def get_selected_nodes(self) -> List[Tuple[int, int]]: # TODO to remove (also on page_tree and hiera_tree???) it is never used
        """Return union of selected nodes in both trees as list of (page, idx)."""
        
        s = set(self.page_tree.get_selected_nodes()) | set(self.hier_tree.get_selected_nodes())
        return list(s)

    def populate_tree(self, selections: SelectionsManager) -> None:
        """Update both trees with new selections data and `rebuild` their displays.
        
        Args:
            selections (SelectionsManager): New selections data to display.
            
        Returns:
            None
        """

        self.selections = selections
        self.page_tree.rebuild(selections)
        self.hier_tree.rebuild(selections)


    def expand_and_select_by_id(self, sel_id: str) -> None:
        """Expand both trees and select node with given selection ID.
        
        Args:
            sel_id (str): Selection ID to find and select.
            
        Returns:
            None
        """

        self.page_tree.expand_and_select_by_id(sel_id)
        self.hier_tree.expand_and_select_by_id(sel_id)

