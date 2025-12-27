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

import json
import abc

from typing import Dict, List, Optional, Set, Tuple, Any

from PyQt5.QtWidgets import QWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QAbstractItemView, QMenu, QAction, QMessageBox, QInputDialog, QCheckBox, QDialog
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QItemSelection, QPoint
from PyQt5.QtGui import QDragMoveEvent, QDropEvent

from pdf_annotation_tool.manipulation.editor import SelectionDataEditingDialog
from pdf_annotation_tool.selection.data import SelectionCategory, SelectionData
from pdf_annotation_tool.selection.manager import EditingData, SelectionsManager
from pdf_annotation_tool.selection.graphic import SelectableRegionItem


# TODO check if all the functions are necessary and check private/public methods
# TODO it could be more efficient if rebuild receives only the changes instead of rebuilding the entire tree


# Base Tree class used by `PageTreeWidget` and `HierarchyTreeWidget`
class BaseSelectionTree(QTreeWidget):
    """Base class providing common helpers for two tree visualizations of `selections`: a tree arranges by page and selection index (i.e., `PageTreeWidget`), and another by parent and children selections (`HierarchyTreeWidget`).
    This class is in charge of common features like drag-and-drop, context menu, editing, searching, etc. This is an abstract class, and it must be extended by concrete implementations that provide the `rebuild` method.
    """
    
    # Signals for external listeners
    selection_changed = pyqtSignal() # emitted when the selection in the tree changes
    data_changed = pyqtSignal() # emitted when the underlying data changes (e.g., after deletion or edit)
    find_in_pdf = pyqtSignal(int) # emitted to request the PDF viewer to go to a specific page
    
    # Role data stored inside the tree's node. 
    ID_ROLE = Qt.UserRole # role for the selection id (str). Together with `mapping_cache`, it allows to retrieve the `SelectablePolyItem` object as well as its position, i.e., `(page, idx)``
    VIS_FLAG_ROLE = ID_ROLE + 1 # role for the "initial visibility" flag (bool)
    #DATA_ROLE = VIS_FLAG_ROLE +1 # role for the full SelectionData object (SelectionData)
    # TODO remove ID_ROLE and PAGE_ROLE in order to keep only DATA_ROLE (is it redundant with mapping_cache? )
    # TODO make static method for `.data(0, BaseSelectionTree.ID_ROLE)` and similar (e.g., ROOT, VIS_FLAG_ROLE, etc.)
    
    # A synthetic root node is added to the tree to allow drag-and-drop at root level. Its ID is `BaseSelectionTree.ROOT_ID`
    ROOT_ID = "ROOT"
   
    # Columns shown in the tree for each node 
    TREE_HEADERS = ["ID", "Category", "Text", "Description", "Page", "Idx", "Parent", "Children"]


    def __init__(self, selections: SelectionsManager, parent: QWidget = None, enable_drag_drop: bool = True, allow_edit: bool = True, selection_synch_checkbox: QCheckBox = None):
        """Initialize the tree with given `selections` (SelectionManager).
        If `enable_drag_drop` is True, the user can drag-and-drop nodes to reorder them.
        If `allow_edit` is True, the user can edit selection data by double-clicking a node or using the context menu.
        If `selection_synch_checkbox` is provided (QCheckBox or bool), it enables/disables automatic focus on PDF while selecting on tree and synchronization of selected nodes among trees.
        `Parent` is the optional parent QT widget."""
        
        super().__init__(parent)
        
        # Class properties
        self.selections = selections # The data to be shown in the tree
        self.mapping_cache = {}  # `{id : (page, idx, item)}` => the auxiliary data structure to retrieve data from the ID stored in each nodes with the `ID_ROLE`
        self.enabled_categories = set(SelectionCategory) # set of enabled categories (SelectionCategory) to be shown in the tree used to filter nodes
        self.allow_edit = allow_edit # Whether the user can edit selection data by double-clicking a node or using the context menu
        self._selected_node = set() # set of currently selected nodes (ids)
        self._selection_synch_checkbox = selection_synch_checkbox # It enable/disable automatic synching among trees and selections focus on PDF while interacting with the tree
        
        # Tree configuration
        self.setHeaderLabels(BaseSelectionTree.TREE_HEADERS)
        self.setSelectionMode(QTreeWidget.ExtendedSelection)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)
        
        # Drag-and-drop configuration
        if enable_drag_drop:
            # Configure auto-expand on hover during drag-and-drop
            self._expand_timer = QTimer(self)
            self._expand_timer.setSingleShot(True)
            self._expand_timer.timeout.connect(self._expand_on_hover)
            self._hover_item = None
            # Configure drag and drop
            self.setDragEnabled(True)
            self.setAcceptDrops(True)
            self.setDropIndicatorShown(True)
            self.setDragDropMode(QAbstractItemView.InternalMove)
            self.setDefaultDropAction(Qt.MoveAction)      
            self.setDragDropOverwriteMode(False)
        
        # Selection mode configuration
        if not allow_edit:
            self.setSelectionMode(QAbstractItemView.SingleSelection)  # disable multi-select
        #else:
            #self.setSelectionMode(QAbstractItemView.MultiSelection)   # enable multi-select (IT IS ALREADY DONE BY DEFAULT)
        
        # Signals for selection changes
        self.itemSelectionChanged.connect(lambda: self.selection_changed.emit())
        self.selectionModel().selectionChanged.connect(self.on_selection_changed)
        
        # Show editor
        layout = QVBoxLayout(self)
        self.setLayout(layout)
        
        # Build the tree for the first time
        self.rebuild()
        
        
    def on_selection_changed(self, selected: QItemSelection, deselected: QItemSelection) -> None:
        """Synchronize the selection of the same node among different trees. 
        It also highlight regions in the PDF viewer based on the selected nodes on the tree.
        These functionalities are enabled only when the `selection_synch_checkbox` (if provided in the constructor) is true.
        This method is connected to the `selectionChanged` signal of the tree's selection model."""
        
        # This feature works only if the selections are synchronized among trees (see `TreesPanel`)
        if self._selection_synch_checkbox is None:
            return 
        if isinstance(self._selection_synch_checkbox, bool):
            if not self._selection_synch_checkbox:
                return
        if isinstance(self._selection_synch_checkbox, QCheckBox):
            if not self._selection_synch_checkbox.isChecked():
                return
        
        # Handle new selections
        for range in selected:
            for index in range.indexes():
                item = self.itemFromIndex(index)  # convert QModelIndex -> QTreeWidgetItem
                item_id = item.data(0, BaseSelectionTree.ID_ROLE) 
                if item_id == PageTreeWidget.PAGE_NODE_ID: # TODO move dependency to `PageTreeWidget` in its class 
                    continue
                self._highlight_region_in_pdf(item_id, True, show_alert=False)

        # Handle de-selections
        for range in deselected:
            for index in range.indexes():
                item = self.itemFromIndex(index)
                item_id = item.data(0, BaseSelectionTree.ID_ROLE) 
                if item_id == PageTreeWidget.PAGE_NODE_ID:
                    continue
                self._highlight_region_in_pdf(item_id, False, show_alert=False)


    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        """Handle drag move events to support auto-expanding nodes when the mouse is stationary in a node during drag-and-drop."""
        
        super().dragMoveEvent(event)

        item = self.itemAt(event.pos())
        if item and item is not self._hover_item:
            # reset timer for new hover target
            self._expand_timer.stop()
            self._hover_item = item
            if not item.isExpanded():
                self._expand_timer.start(1000)  # ms delay before expanding


    def _expand_on_hover(self) -> None:
        """Expand the currently hovered item if it is not already expanded. This is called by a timer after hovering for a while during drag-and-drop."""
        try:
            if self._hover_item and not self._hover_item.isExpanded():
                self._hover_item.setExpanded(True)
        except Exception:
            print(f"[WARNING] cannot `_expand_on_hover`, is the `QTreeWidgetItem` deleted?")
            #traceback.print_exc()


    def _make_item_for_selection(self, selection: SelectableRegionItem) -> QTreeWidgetItem:
            """
            Create a QTreeWidgetItem for a `selection` and store an 'initial visible' flag in VIS_FLAG_ROLE. The latter is charge to manage node visibility when filtering, and 
            we do not call setHidden() here because parent visibility depends on children; final visibility is computed later in one pass.
            """
            
            label, tips = BaseSelectionTree._label_for_item(selection)   # returns (str, [tooltips])
            item = QTreeWidgetItem(label)
            item.setData(0, BaseSelectionTree.ID_ROLE, selection.data.id_)
            # item.setData(0, BaseSelectionTree.DATA_ROLE, sp.data) # TODO to remove
            item.setFlags(item.flags() | Qt.ItemIsDragEnabled | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            for i, t in enumerate(tips):
                item.setToolTip(i, t)

            # initial visibility based only on the item's own category
            initial_visible = selection.data.category in self.enabled_categories
            item.setData(0, BaseSelectionTree.VIS_FLAG_ROLE, initial_visible)

            return item


    def set_category_enabled(self, category: SelectionCategory, enabled : bool) -> None:
        """Set whether a node of a certain category is enabled (shown) or disabled (hidden) in the tree."""
        
        if enabled:
            self.enabled_categories.add(category)
        else:
            self.enabled_categories.discard(category)
        self.rebuild_safe()


    def _apply_visibility_post_build(self) -> None:
        """Apply visibility to all nodes in the tree after a rebuild, based on the initial visibility flags stored in each node (with the `VIS_FLAG_ROLE`), and the visibility of their children.
        It is used to implement filtering by category, where parent nodes are visible if any of their children is visible."""
        
        def compute_visible(item: QTreeWidgetItem) -> bool:
            """Return True if item or any child is visible, else False. Also set item's hidden state.
            It is an help function of `_apply_visibility_post_build`, and it is a recursive function."""
            
            # initial flag (may be None for container/page nodes)
            flag = item.data(0, BaseSelectionTree.VIS_FLAG_ROLE)
            initial_visible = bool(flag) if flag is not None else False

            any_child_visible = False
            for i in range(item.childCount()):
                child = item.child(i)
                if compute_visible(child):
                    any_child_visible = True

            visible = initial_visible or any_child_visible
            item.setHidden(not visible)
            return visible


        root = self.root
        for i in range(root.childCount()):
            compute_visible(root.child(i))


    def refresh_mapping(self) -> None:
        """Refresh the internal mapping cache from selection ID to (page, idx, SelectableRegionItem)."""
        
        self.mapping_cache = BaseSelectionTree.build_selection_map(self.selections)
    
    
    def _on_context_menu(self, pos: QPoint) -> None:
        """Define the context menu shown when right-clicking on a node, which includes options to: delete, find in PDF, and edit the selection."""
        
        # get the item at the clicked position
        item = self.itemAt(pos)
        if item is None:
            return

        # build the context menu
        menu = QMenu(self)
        delete_action = QAction("Delete", self)
        menu.addAction(delete_action)
        find_action = QAction("Find in PDF", self)
        menu.addAction(find_action)
        edit_action = QAction("Edit Section", self)
        menu.addAction(edit_action)

        # execute the menu and get the selected action
        act = menu.exec_(self.viewport().mapToGlobal(pos))

        # handle the selected action
        if act == delete_action:
            self._on_delete()
        elif act == find_action:
            self._on_find_in_pdf()
        elif act == edit_action:
            self._on_edit()


    def _collect_data_recursively(self, item: QTreeWidgetItem) -> List[SelectionData]:
        """Recursively collect SelectionData from the given `item` and its children."""
        
        # Retrieve input `item`` data
        data_list = []
        sp_id = item.data(0, BaseSelectionTree.ID_ROLE)
        node_ref = self.mapping_cache.get(sp_id, None)
        if node_ref is None:
            return []
        _, _, node = node_ref
        node_data = node.data 
        
        #node_data = item.data(0, BaseSelectionTree.DATA_ROLE)# ID_ROLE) TODO refactor id to data        
        
        # Add the retrieved data and recurse on children
        if isinstance(node_data, SelectionData): # is not None:
            data_list.append(node_data)
        for i in range(item.childCount()):
            child = item.child(i)
            data_list.extend(self._collect_data_recursively(child))
        return data_list


    def _on_delete(self) -> None:
        """Handle the deletion of selected nodes, including their children, from the tree and the underlying selections data."""
        
        # Collect all IDs (including children of selected items)
        nodes_data = []
        for sel_item in self.selectedItems():
            
            # Check if is possible to delete the node. The root node cannot be deleted.
            if sel_item.data(0, BaseSelectionTree.ID_ROLE) == BaseSelectionTree.ROOT_ID:
                QMessageBox.warning(self, "Error", 
                                    f"Cannot delete the `{BaseSelectionTree.ROOT_ID}` since it is a dummy node!")
                continue
            
            # Collect data recursively
            data_list = self._collect_data_recursively(sel_item)
            nodes_data.extend(data_list)

        # Retrieve data from id Delete the collected node data from the selections manager
        nodes = []
        for nd in nodes_data:
            _, _, node = self.mapping_cache.get(nd.id_, None)
            if node is not None:
                nodes.append(node)
            else:
                print(f"Error, lost node with data: {nd}")
        
        # Delete all the retrieved node with `SelectionsManager` and emit data_changed signal
        self.selections.remove_selection_set(nodes)
        self.data_changed.emit()


    def _on_find_in_pdf(self) -> None:
        """Find and highlight the selected nodes in the PDF viewer, emitting the `find_in_pdf` signal for each page involved."""
        
        show_alert = len(self.selectedItems()) == 1 # Show alert only if one item is involved, i.e., the one that generate the issues (i.e., ROOT)
        for sel_item in self.selectedItems():
            sel_id = sel_item.data(0, BaseSelectionTree.ID_ROLE)
            region = self._highlight_region_in_pdf(sel_id, show_alert)
            if region is None:
                continue
            self.find_in_pdf.emit(region.data.page)
            

    def _highlight_region_in_pdf(self, sel_id: str, makeSelected: bool = True, show_alert: bool = True) -> SelectableRegionItem | None:
        """Highlight or unhighlight the region in the PDF viewer corresponding to the given `sel_id`. It is used by `on_selection_changed` and `_on_find_in_pdf`.
        If `makeSelected` is True, the region is highlighted; if False, it is un-highlighted.
        If `show_alert` is True, it shows an alert if the `sel_id` is invalid (e.g., ROOT or PAGE_NODE_ID)."""
        
        # Check if the id is valid, i.e., not ROOT or PAGE_NODE_ID
        if sel_id == BaseSelectionTree.ROOT_ID or sel_id == PageTreeWidget.PAGE_NODE_ID:
            if show_alert:
                QMessageBox.warning(self, "Warning", 
                                    f"Cannot find the `{sel_id}` into the PDF. Is it a dummy node?!")
            return None
        
        # Retrieve the region from the mapping cache and set its selected state
        _, _, region = self.mapping_cache[sel_id]
        region.setSelected(makeSelected) 
        
        # Return the region for further processing if needed
        return region


    def _on_edit(self) -> None:
        """Edit the selected nodes by opening the `SelectionDataEditingDialog` for each selected item."""
        
        for item in self.selectedItems():
            self.open_selection_editor(item)


    def open_selection_editor(self, item: QTreeWidgetItem) -> None:
        """Open the selection editor dialog for the given `item`. It is used by `_on_edit` for invoking `open_selection_editor_by_id`."""
        
        sel_id = item.data(0, BaseSelectionTree.ID_ROLE)
        self.open_selection_editor_by_id(sel_id)

    
    def open_selection_editor_by_id(self, sel_id: str) -> None:
        """Open the selection editor dialog for the node with the given `sel_id`. It is used in `_on_edit` by the mean of `open_selection_editor_by_id`."""
        
        # Check if editing is allowed
        if not self.allow_edit:
            return
        
        # If `sel_id` does not refer to a leaf (i.e., the root or a page number node), do nothing (TODO maybe show alert?)
        if sel_id is None or sel_id == BaseSelectionTree.ROOT_ID or sel_id == PageTreeWidget.PAGE_NODE_ID: # TODO remove dependence of PageTreeWidget from this class
            return
        
        # If `sel_id` refers to a leaf, open editor with item's data.text
        
        # Get current data and check if valid
        self.refresh_mapping()
        if sel_id not in self.mapping_cache:
            return
        page, idx, sp = self.mapping_cache[sel_id]
        
        # Open editor dialog
        dialog = SelectionDataEditingDialog(sp.data, self)
        if dialog.exec_() == QDialog.Accepted:
            
            # If the data was edited, update the selection
            edited_sel = sp.copy(dialog.edited_data)
            self.selections.edit_selection(page, idx, edited_sel)
            
            # Rebuild the tree and emit data_changed signal
            self.rebuild()
            self.data_changed.emit()
        
    
    @staticmethod
    def _label_for_item(region: SelectableRegionItem) -> List[str]:
        """Return a tuple (label, tooltips) for the given region` (SelectableRegionItem).
        It is used by `_make_item_for_selection` to create the tree node label and tooltips."""
        
        
        def limit_str(s: Any, limit: int, should_encode = False) -> str:
            """An help function to limit the length of a string to `limit` characters, adding an ellipsis if truncated.
            It also encodes special characters if `should_encode` is True."""
            
            if s is None or s == "": 
                return ""
            s = str(s)
            if should_encode:
                 s = s.encode('unicode_escape').decode()
            if len(s) > limit:
                return f"{s[0:limit]}…"
            else:
                return s
        
        
        def limit_list(elements: List, limit: int) -> str:
            """Limit the length of a list of strings (i.e., `elements`), and it invokes `limit_str(limit)` to each element and returning a string representation of the list."""
            
            if elements is None or len(elements) <= 0: 
                return ""
            out = []
            for e in elements:
                out.append(limit_str(e, limit))
            return str(out)
       
                 
        # Retrieve data from the region to be shown in the tree's nodes
        d = region.data
        id_ = limit_str(d.id_, limit=3)
        category = limit_str(d.category.value.name, limit=10)
        text = limit_str(d.text, limit=20, should_encode=True)
        description = limit_str(d.description, limit=20, should_encode=True)
        page = limit_str(d.page, limit=3)
        idx = limit_str(d.idx, limit=3)
        parent = limit_str(d.parent, limit=3)
        children = limit_list(d.children, limit=3)
        node_label = [id_, category, text, description, page, idx, parent, children]
        
        # Prepare the tooltips for each column
        tips = [
            f"id : {d.id_}",
            f"category : {d.category.value.name}",
            f"text : {d.text}",
            f"description : {d.description}",
            f"page : {d.page}",
            f"idx : {d.idx}",
            f"parent : {d.parent}",
            f"children : {d.children}",
            f"image : {limit_str(d.image, limit=40)}"
        ]
        
        return node_label, tips


    def add_root(self) -> None:
        """Add the synthetic root node to the tree, which has ID equal to `BaseSelectionTree.ROOT_ID`. It is used in `rebuild` methods of subclasses."""
         
        root = QTreeWidgetItem([f"ROOT"])
        root.setData(0, PageTreeWidget.ID_ROLE, BaseSelectionTree.ROOT_ID)
        self.addTopLevelItem(root)
        self.root = root
        
        
    @abc.abstractmethod
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle the drop event during drag-and-drop to reorder nodes. This method must be implemented by subclasses."""
        super().dropEvent(event)
        #raise NotImplementedError
    
    
    @abc.abstractmethod
    def rebuild(self, selections: SelectionsManager = None) -> None:  
        """Rebuild the tree from the current `selections` data. This method must be implemented by subclasses
        and it is called every time the `selections` structure is changed. When `sections` is provided, it replaces the current `self.selections`."""
        
        raise NotImplementedError


    def rebuild_safe(self) -> None:
        """Invokes `self.rebuild()` while suppressing selection and data change signals (e.g., to preserve the expanded state of nodes)."""
        
        self.blockSignals(True)
        try:
            self.rebuild()
        finally:
            self.blockSignals(False)


    def search_nodes(self, query: str, fields: Set[str]) -> List[Tuple[int, int]]:
        """Return list of tuples `(page, idx)` that represent the position in the `SelectionManager` of the 
        selections matching the `query` applied to the given `fields` (which are properties in the `SelectionData` class.
        It is used by `TreesPanel` to implement the search functionality."""
        
        results = []
        self.refresh_mapping()
        for _, (page, idx, sp) in self.mapping_cache.items():
            if BaseSelectionTree._matches(sp.data, query, fields):
                results.append((page, idx))
        return results


    @staticmethod
    def _matches(data: SelectionData, query: str, fields: Set[str]) -> bool:
        """Logic to check if `data` (SelectionData) matches the `query` string in any of the given `fields`.
        Possible fields are fields in `SelectionData`, e.g., `SelectionData.JSON_KEY_ID`, `SelectionData.JSON_KEY_TEXT`, etc.
        It is used by `search_nodes` to filter selections based on user input."""
        
        q = query.lower()
        if not q:
            return False
        
        for f in fields:
            if f == SelectionData.JSON_KEY_ID:
                if q in data.id_.lower():
                    return True
            elif f == SelectionData.JSON_KEY_DOC:
                if q in (data.doc or "").lower():
                    return True
            elif f == SelectionData.JSON_KEY_PAGE:
                if q == str(data.page):
                    return True
            elif f == SelectionData.JSON_KEY_COORDS:
                if q in json.dumps(data.coords).lower():
                    return True
            elif f == SelectionData.JSON_KEY_TEXT:
                if q in (data.text or "").lower():
                    return True
            elif f == SelectionData.JSON_KEY_CATEGORY:
                if q in (data.category.value.name or "").lower():
                    return True
            # DO NOT SEARCH BY IMAGE (it is binary data)
            elif f == SelectionData.JSON_KEY_PARENT:
                if q in (data.parent or "").lower():
                    return True
            elif f == SelectionData.JSON_KEY_CHILDREN:
                if any(q in (c or "").lower() for c in (data.children or [])):
                    return True
            elif f == SelectionData.JSON_KEY_DESCRIPTION:
                if q in (data.description or "").lower():
                    return True        
        return False


    def get_expanded_items(self) -> List[str]:
        """Return list of unique keys of expanded nodes in the tree, including the ROOT. It is used to restore the expanded state after a rebuild."""
        
        expanded = []
        root = self.invisibleRootItem()
        stack = [root]
        # Traverse the tree to find expanded items
        while stack:
            parent = stack.pop()
            for i in range(parent.childCount()):
                child = parent.child(i)
                # Build a unique identifier: e.g. full text path
                key = child.data(0, BaseSelectionTree.ID_ROLE) # self.item_path(child)
                if child.isExpanded():
                    expanded.append(key) # store only expanded items
                stack.append(child)
        return expanded


    #def item_path(self, item: QTreeWidgetItem) -> str:  # TODO I did it by using node's ID -> to debug (see `get_expanded_items` and `restore_expanded_items`)!
    #    """Return a unique string for an item based on its parent chain."""
    #    
    #    parts = []
    #    while item is not None:
    #        parts.insert(0, item.text(0))
    #        item = item.parent()
    #    return "/".join(parts)


    def restore_expanded_items(self, expanded_keys: Set[str]) -> None:
        """Expand items whose key is in expanded_keys, which is given by `get_expanded_items`.
        It is used to restore the expanded state after a rebuild; the expanded items should be got before than tree manipulation)."""
        
        root = self.invisibleRootItem()
        stack = [root]
        # Traverse the tree to restore expanded state
        while stack:
            parent = stack.pop()
            # Iterate in reverse order to maintain original order in stack
            for i in range(parent.childCount()):
                # Check if the child should be expanded
                child = parent.child(i)
                key = child.data(0, BaseSelectionTree.ID_ROLE) # self.item_path(child)
                if key in expanded_keys:
                    # Expand the child and add it to the stack for further traversal
                    child.setExpanded(True)
                stack.append(child)


    def expand_and_select_by_id(self, sel_id: str) -> None:
        """Expand the tree and select the node with the given `sel_id`. It is based on `find_node_by_id` and `expand_and_select`, and it used by `TreesPanel` to select nodes based on search results."""
        
        if not self.mapping_cache: # i.e., empty tree
            item = self.root
        else:
            item = self.find_node_by_id(sel_id)
        self.expand_and_select(item)


    def find_node_by_id(self, target_id: str) -> QTreeWidgetItem | None:
        """
        Recursively searches for a node with the `target_id`. It returns the matching item or None if not found.
        It is used by `expand_and_select_by_id` to find and select a node based on its ID.
        """


        def recurse(parent_item: QTreeWidgetItem) -> QTreeWidgetItem | None:
            """Recursive helper function to search through child items."""
            
            for i in range(parent_item.childCount()):
                child = parent_item.child(i)
                if child.data(0, BaseSelectionTree.ID_ROLE) == target_id:
                    return child
                found = recurse(child)
                if found:
                    return found
            return None


        # search top-level items
        for i in range(self.topLevelItemCount()):
            item = self.topLevelItem(i)
            if item.data(0, BaseSelectionTree.ID_ROLE) == target_id:
                return item
            found = recurse(item)
            if found:
                return found

        return None
        

    def expand_and_select(self, nodes: List[Tuple[int, int]]) -> None: 
        """Expand tree and select nodes given list of `(page, idx)` that identify the position of a element in the `SelectionManager`."""
        
        if nodes is None:
            print("Error on tree node expand and select. Given three node is `None`.")
            return
        
        # Clear current selection and refresh data
        self.clearSelection()
        #self.refresh_mapping()
        if len(self.mapping_cache) <= 0:
            self.root.setSelected(True)
            return
        
        # Special case: if the node is the ROOT, select it and return
        if nodes == self.root:
            self.root.setSelected(True)
            return
            # Expand all children and select the first one (TODO maybe not needed)
            #for i in range(self.root.childCount()):
            #    child = self.root.child(i)
            #    self.expand_and_select(child)
            #return
        
        # Search for the node with the given (page, idx)
        node_id = nodes.data(0, BaseSelectionTree.ID_ROLE)
        for sel_id in self.mapping_cache.keys():
            if sel_id == node_id:
                # Found the node, expand its parents and select it
                nodes.setSelected(True)
                parent = nodes.parent()
                while parent:
                    parent.setExpanded(True)
                    parent.setSelected(False)
                    parent = parent.parent()
                break


    def get_selected_nodes(self) -> List[Tuple[int, int]]: # TODO this method is propagated to TreesPanel but it is not used
        """Return list of tuples `(page, idx)` representing the position in the `SelectionManager` of the currently selected nodes in the tree."""
        
        res = []
        for it in self.selectedItems():
            sel_id = it.data(0, BaseSelectionTree.ID_ROLE)
            if sel_id:
                self.refresh_mapping()
                if sel_id in self.mapping_cache:
                    p, i, _ = self.mapping_cache[sel_id]
                    res.append((p, i))
        return res


    def get_selected_node_data(self) -> List[SelectionData]:
        """Return list of `SelectionData` objects corresponding to the currently selected nodes in the tree.
        It also encompass the ROOT and PAGE_NODE_ID nodes, if necessary."""
        
        mapping_cache = self.mapping_cache
        out = []        
        for s in self.selectedItems():
            s_id = s.data(0, BaseSelectionTree.ID_ROLE)
            if s_id == BaseSelectionTree.ROOT_ID:
                out.append(BaseSelectionTree.ROOT_ID)
            elif s_id == PageTreeWidget.PAGE_NODE_ID:
                out.append(PageTreeWidget.PAGE_NODE_ID)
            else:
                _, _, node = mapping_cache[s_id]
                out.append(node.data)
        return out


    @staticmethod
    def build_selection_map(selections: SelectionsManager) -> Dict[str, Tuple[int, int, SelectableRegionItem]]:
        """Return a mapping from selection where keys are `ID` and values are tuples of `(page, idx, SelectableRegionItem)`. 
        This map is performed for all selections in the given `selections` dictionary.
        It is used to build the `mapping_cache` in `refresh_mapping`, which is used at construction and rebuild time."""
        
        mapping = {}
        for page, arr in selections.items():
            for idx, item in enumerate(arr):
                mapping[item.data.id_] = (page, idx, item)
        return mapping
   
   
   
   
# Specific tree widget for page oriented list of selections  (it uses `PageTree`)          
class PageTreeWidget(BaseSelectionTree):
    """The specific implementation of `BaseSelectionTree` where top-level nodes are pages and children are selections on that page.
    It shows the actual representation of the `SelectionsManager` data structure.
    It supports drag-and-drop to reorder selections within and across pages, as well as adding new selections to specific pages.
    It also manages the visibility of nodes based on their category and the visibility of their children.
    It emits signals when the selection changes, when data is changed (e.g., nodes are edited or deleted), and when a page needs to be found in the PDF viewer."""
    
    PAGE_ROLE = BaseSelectionTree.VIS_FLAG_ROLE + 1  # just a different role to store the page number in page nodes
    PAGE_NODE_ID = "PAGE_NODE_ID" # special name (used as ID) for page nodes (not a real selection ID)
    
    
    def __init__(self, selections, parent=None, enable_drag_drop=True, enable_multi_selection=True, selection_synch_checkbox=None):
        """Initialize the PageTreeWidget with given `selections` (SelectionManager). See `BaseSelectionTree` for parameter details."""
        super().__init__(selections, parent, enable_drag_drop, enable_multi_selection, selection_synch_checkbox)


    def rebuild(self, selections: SelectionsManager = None):
        """Build tree where top-level nodes are pages and children are ordered selections. It is called every time the `selections` structure is changed.
        When `sections` is None, it uses the current `self.selections`. This function is required by the `BaseSelectionTree` abstract class."""
        
        # Get valid input
        if selections is not None:
            self.selections = selections
        
        # Preserve expanded state
        expanded_keys = self.get_expanded_items()
        
        # Start building a new tree
        self.clear()
        self.add_root() # It also sets `self.root``
        self.refresh_mapping() # in case you need it during the build (e.g., for `find_node_by_id`)

        # Iterate over pages and regions in the `selections` dictionary to build the tree
        for page_number, selections in self.selections.items():
            # create a page node
            page_item = self._make_page_node(page_number)  
            
            for idx, sp in enumerate(selections):
                # assign page/idx
                sp.data.page = page_number
                sp.data.idx = idx

                # create item (does not call setHidden; stores initial flag)
                child = self._make_item_for_selection(sp)
                page_item.addChild(child)

        # update mapping cache (if your refresh_mapping uses the tree)
        self.refresh_mapping()
        # compute final visibility bottom-up (single traversal)
        self._apply_visibility_post_build()
        # Restore node expansion as it was before rebuilding
        self.restore_expanded_items(expanded_keys)
        #self.expandAll()
     
       
    def _make_page_node(self, page_number: int) -> QTreeWidgetItem:
        """Create a QTreeWidgetItem for a page node with the given `page_number`. It is used in `rebuild` and `dropEvent` methods.
        This node have the `PAGE_NODE_ID` identifier and stores the relative page number into the node through the `PAGE_ROLE`."""
        
        page_item = QTreeWidgetItem([f"Page {page_number}"])
        page_item.setData(0, BaseSelectionTree.ID_ROLE, PageTreeWidget.PAGE_NODE_ID)
        page_item.setData(0, PageTreeWidget.PAGE_ROLE, page_number)
        page_item.setFlags(page_item.flags() & ~Qt.ItemIsDragEnabled)
        self.root.addChild(page_item)
        return page_item
    
       
    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop events for drag-and-drop operations within the tree widget.

        This method processes dropped items and manages their placement in the tree structure.
        It supports dropping selections onto page nodes (to move them to that page) or dropping
        at the root level (which prompts for a page number). After processing the drop, it
        synchronizes the underlying selections data structure. This method is required from `BaseSelectionTree`.

        Args:
            event (QDropEvent): The drop event containing information about the dragged items
                            and drop location.

        Returns:
            None
            
        Note:
            - Dropping at root level prompts user to select a page number
            - Creates new page nodes if the target page doesn't exist
            - Calls `_apply_drop()` to synchronize the selections data structure
            - Shows warning dialog for invalid drop operations
        """
        
        # Get info about what has been dragged and where they have been dropped.
        dragged_items, drop_parent, reason = self._get_drop_target(event)

        # Ignore saving into a leaf node or into itself
        if reason is not None and drop_parent is not None:
            event.ignore()
            QMessageBox.warning(self, "Invalid move", f"Cannot move selection: `{reason}`.")
            return

        # If the items are dropped as child of the ROOT, then we need to ask in which page node should we drugged and, eventually, create it.
        if drop_parent is None or drop_parent.data(0, BaseSelectionTree.ID_ROLE) == BaseSelectionTree.ROOT_ID: # Then is the dummy ROOT node
            # Ask the user for the page node number
            page_num, ok = QInputDialog.getInt(
                self,
                "Assign Page",
                "Enter page number for dropped selection:",
                1,  # default
                1,   # min value
                # max value # TODO add page numbers as maximum integer
            )
            if not ok:
                event.ignore()
                return

            # check if a page node already exists
            root = self.root
            page_item = None
            for i in range(root.childCount()):
                child = root.child(i)
                try:
                    n = child.data(0, PageTreeWidget.PAGE_ROLE)
                except ValueError:
                    continue
                if n == page_num:
                    page_item = child
                    break

            # create new page node if necessary
            if page_item is None:
                page_item = self._make_page_node(page_num)  

            # reparent dragged items under the chosen page
            for it in dragged_items:
                # make a copy of the item (optional: remove old one instead)
                parent = it.parent()
                if parent is None:
                    idx = self.indexOfTopLevelItem(it)
                    self.takeTopLevelItem(idx)
                else:
                    parent.removeChild(it)
                page_item.addChild(it)

            event.accept()
        else:
            # Normal internal move
            event.setDropAction(Qt.MoveAction)
            super().dropEvent(event)
            event.accept()

        # rebuild selections in parent (keeps your dictionary in sync)
        self._apply_drop()


    def _get_drop_target(self, event: QDropEvent) -> Tuple[List[QTreeWidgetItem], Optional[QTreeWidgetItem], Optional[str]]:
        """Analyze drop event and return dragged items, target parent, and validation result. It is used to understand what has been dragged and where.
        
        Args:
            event (QDropEvent): The drop event to analyze.
            
        Returns:
            Tuple containing:
            - dragged_items (List[QTreeWidgetItem]): Items being dragged
            - drop_parent (Optional[QTreeWidgetItem]): Target parent node or None for root
            - reason (Optional[str]): Error message if invalid, None if valid
        """
    
        # 1) figure out which items are being dragged (internal move = selected items)
        dragged_items = []
        try:
            src = event.source()
        except Exception:
            src = None

        if src is self:
            # internal drag: use the currently selected items
            dragged_items = list(self.selectedItems())
        else:
            # external drag: we can't reliably map to QTreeWidgetItem without parsing mimeData
            # you can decode application/x-qabstractitemmodeldatalist if needed
            dragged_items = []

        # 2) figure out drop target using the drop indicator + item under cursor
        pos = event.pos()
        target_item = self.itemAt(pos)
        indicator = self.dropIndicatorPosition()

        if indicator == QAbstractItemView.OnItem: # Then it is dropped as a child of target_item.
            if target_item is None:
                # weird but treat as append to top-level
                drop_parent = None
            else:
                drop_parent = target_item

        elif indicator == QAbstractItemView.AboveItem: # Then it is dropped above target_item.
            if target_item is None:
                drop_parent = None
            else:
                drop_parent = target_item.parent()

        elif indicator == QAbstractItemView.BelowItem: # Then it is dropped below target_item.
            if target_item is None:
                drop_parent = None
            else:
                drop_parent = target_item.parent()
        elif indicator == QAbstractItemView.OnViewport: # Then it is dropped into empty space.
            drop_parent = None
        else:
            return dragged_items, None, -1, #"unknown drop indicator"

        # 3) collect original positions of dragged items (parent + index)
        original_positions = []
        for it in dragged_items:
            p = it.parent()
            if p is None:
                idx = self.indexOfTopLevelItem(it)
            else:
                idx = p.indexOfChild(it)
            original_positions.append((it, p, idx))

        # 4) basic invalid cases
        #  - can't drop an item to become a child of itself
        if drop_parent in dragged_items:
            return dragged_items, drop_parent, "cannot make an item a child of itself"

        #  - can't drop into one of the dragged item's descendants
        def is_descendant(ancestor, node):
            while node is not None:
                if node is ancestor:
                    return True
                node = node.parent()
            return False

        for it, p, idx in original_positions:
            if is_descendant(it, drop_parent):
                return dragged_items, drop_parent, "cannot drop into a descendant of the moved item"

        # 5) example application-level rule: you cannot drop under a leaf
        #    (replace / remove this check according to your app's definition of leaf)
        if drop_parent is not None and drop_parent.childCount() == 0:
            return dragged_items, drop_parent, "cannot drop under a leaf node"

        # 6) forbid dropping at root level
        if drop_parent is None:
            return dragged_items, drop_parent, "cannot drop at root level"

        # success
        return dragged_items, drop_parent, None

  
    def _apply_drop(self) -> None: 
        """Synchronize selections data structure after drag-and-drop operations.
        
        Rebuilds the selections dictionary by traversing the tree structure and 
        updates any selections that changed page or position. Emits data_changed signal.
        
        The edits are based on `SelectionManager.move_selection_set`.
        
        Returns:
            None
        """
        
        # Rebuild selections dict after move
        root = self.root
        new_sel: Dict[int, List[SelectableRegionItem]] = {}
        editing = []
        
        # Traverse the tree
        for i in range(root.childCount()):
            # retrieve page node
            page_item = root.child(i)
            page_num = page_item.data(0, PageTreeWidget.PAGE_ROLE)
            new_sel[page_num] = []

            # Iterate over all the children of a page node
            for j in range(page_item.childCount()):
                # Retrieve selection data
                child = page_item.child(j)
                sel_id = child.data(0, BaseSelectionTree.ID_ROLE)
                data_ref = self.mapping_cache.get(sel_id, None)
                if data_ref is not None:
                    old_page, old_idx, old_selection = data_ref
                    # set the new selection after the drag-and-drop operation    
                    if old_selection.data.page != page_num or old_selection.data.idx != j:                        
                        new_selection = old_selection.copy()
                        new_selection.data.page = page_num
                        new_selection.data.idx = j 
                        # Append the data to perform all the changes
                        editing.append(EditingData(editing_page=old_page, editing_idx=old_idx, new_selection=new_selection))
                        
        # If there are some changes apply them and emith data changed signal
        if len(editing) > 0:
            self.selections.move_selection_set(editing)
            QTimer.singleShot(0, lambda: self.rebuild_safe())
            self.data_changed.emit()
            

    def _find_in_pdf_action(self, from_tree_selection: bool = False) -> None:
        """Navigate to selected items in PDF viewer and emit find_in_pdf signal.
        
        Handles ROOT nodes (shows alert), page nodes (emits page number), and 
        selection nodes (highlights region and emits page number).
        
        Args:
            from_tree_selection (bool): If True, suppresses ROOT node alerts.
            
        Returns:
            None
        """

        for sel_item in self.selectedItems():
            sel_id = sel_item.data(0, BaseSelectionTree.ID_ROLE)
            
            if sel_id == BaseSelectionTree.ROOT_ID:
                if not from_tree_selection: # Disable alert if it is called programmatically
                    QMessageBox.warning(self, "Error", "Cannot find the `ROOT` in the PDF since it is a dummy node.")
                return
            
            if sel_id == PageTreeWidget.PAGE_NODE_ID:
                page = sel_item.data(0, PageTreeWidget.PAGE_ROLE)
                self.find_in_pdf.emit(page)
                return
            
            region = self._highlight_region_in_pdf(sel_id)
            self.find_in_pdf.emit(region.data.page)




# Specific tree widget for hierarchical list of selections  (it uses `HierarchyTree`) 
class HierarchyTreeWidget(BaseSelectionTree):
    """Tree widget that displays selections organized by parent-child hierarchy as described in `SelectionData`."""
    
    def __init__(self, selections: SelectionsManager, parent: QWidget = None, enable_drag_drop: bool = True, enable_multi_selection : bool =True, selection_synch_checkbox: QCheckBox =None):
        """Initialize HierarchyTreeWidget with given selections. See BaseSelectionTree for parameter details."""
        super().__init__(selections, parent, enable_drag_drop, enable_multi_selection, selection_synch_checkbox)


    def rebuild(self, selections: SelectionsManager = None) -> None:
        """Build tree structure based on parent/children relationships in SelectionData.
        
        Creates all selection items first, then connects them according to their 
        parent field. Items without parents become root-level children.
        
        Args:
            selections: Optional new selections data. Uses `self.selections` if None.
            
        Returns:
            None
        """
        
        if selections is not None:
            self.selections = selections

        # clear and ensure mapping_cache contains sp -> data
        expanded_keys = self.get_expanded_items()
        self.clear()
        self.add_root() # It updates self.root
        self.refresh_mapping() 

        node_items = {}

        # create items for **all** selections and record initial visibility flags
        for sel_id, (_, _, sp) in self.mapping_cache.items():
            item = self._make_item_for_selection(sp)
            node_items[sel_id] = item

        # attach by parent (keeps full tree structure, filtered nodes stay in tree)
        for sel_id, item in node_items.items():
            _, _, sp = self.mapping_cache[sel_id]
            parent_id = sp.data.parent
            if parent_id and parent_id in node_items:
                node_items[parent_id].addChild(item)
            else:
                self.root.addChild(item)

        # mapping_cache might need refresh now that items are attached
        self.refresh_mapping()

        # compute final visibility bottom-up in a single pass
        self._apply_visibility_post_build()

        self.restore_expanded_items(expanded_keys)
        #self.expandAll()
        ##self.selection_changed.emit()


    def dropEvent(self, event: QDropEvent) -> None:
        """Handle drop events by updating parent-child relationships and calling apply_drop."""

        # Allow the node movements 
        event.setDropAction(Qt.MoveAction)
        super().dropEvent(event)
        event.accept()

        # rebuild selections in parent (keeps your dictionary in sync)
        self.apply_drop()


    def apply_drop(self) -> None:
        """Update parent-child relationships after drag-and-drop operations.
        
        Recursively traverses tree to detect hierarchy changes and updates 
        SelectionData parent fields accordingly.
        
        The edits are based on `SelectionManager.move_selection_set`.
        
        Returns:
            None
        """
    
        #self.refresh_mapping()
        old_map = self.mapping_cache.copy() #  self.mapping_cache.copy() # TODO it is required to make a copy?
        edits = [] # The vector will all changes to be applied by SelectionManager
        
        
        def recurse(item: QTreeWidgetItem, parent_id: Optional[str] = None) -> None:
            """Recursively process tree items to update parent-child relationships.
            
            Updates the parent field of each selection and preserves sibling order 
            based on tree widget positions. Processes all children recursively.
            
            It has the main purpose to populate the `edits` list.
            
            Args:
                item (QTreeWidgetItem): Current tree item to process.
                parent_id (Optional[str]): ID of the parent selection, None for root items.
                
            Returns:
                None
            """
            
            sel_id = item.data(0, BaseSelectionTree.ID_ROLE)
            if sel_id in old_map:
                old_page, old_idx, old_item = old_map[sel_id]
                sp = old_item.copy()
                sp.data.parent = parent_id
                
                #sp.data.page = old_page
                # preserve the new sibling order based on tree widget index
                #if item.parent() is None:
                #    new_idx = self.root.indexOfChild(item)
                #else:
                #    new_idx = item.parent().indexOfChild(item)
                #sp.data.idx = new_idx
                
                # Retrieve the editing description that can be processed by SelectionManager.
                edits.append(EditingData(editing_page=old_page, editing_idx=old_idx, new_selection=sp))
            for k in range(item.childCount()):
                recurse(item.child(k), sel_id)


        # walk root-level children
        for i in range(self.root.childCount()):
            recurse(self.root.child(i), None)
    
        # Manipulate the selections data structure
        self.selections.move_selection_set(edits)

        # Rebuild the tree with new changes and emit data changed signal
        QTimer.singleShot(0, self.rebuild_safe)
        self.data_changed.emit()
