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

import traceback

from dataclasses import dataclass, field

from typing import Optional, OrderedDict, List, Tuple

from PyQt5.QtWidgets import QUndoStack, QUndoCommand

from pdf_annotation_tool.selection.graphic import SelectableRegionItem
from pdf_annotation_tool.selection.data import SelectionData


@dataclass
class EditingData:
    """Data structure to describe an edit operation on a selection. It is used in `MoveAllCmd` and `SelectionsManager.move_selection_set`."""
    
    editing_page: int # The selection's dictionary key (i.e., page number starting from 1) of the selection to be edited.
    editing_idx: int # The selection's index inside the list at `editing_page` of the selection to be edited.
    new_selection: SelectableRegionItem # The new selection that will replace the the one at `editing_page -> editing_idx`. It will be added at the key and index stored in its `data` field.
    #old_selection: SelectableRegionItem = field(init=False, default=None) # It is filled at `MoveAllCmd` constructor time, it is a copy of the original selection before editing used for undo.

        

class SelectionsManager:
    """The main data structure to manage PDF selections. It is an OrderedDict where: keys are page numbers (starting from 1), values are lists of `SelectableRegionItem` objects. It provides 
    methods to add, remove, edit and move selections, all operations are undoable/redoable via a `QUndoStack`."""
    
    def __init__(self, undo_stack: QUndoStack):
        self._selections = OrderedDict()
        self.undo_stack = undo_stack
        
    @staticmethod
    def find_selection_by_id(dict: OrderedDict, selection_id: str) -> Optional[SelectableRegionItem]:
        """Search for a selection by its unique ID across all pages and return its (`page_number`, `index`, `selection`) if found, otherwise return None.
        Note that `page_number` and index are retrieved from the actual data structure (not from the `data` fields into the `selection`) to ensure consistency."""
        for page_number, page_items in dict.items():
            idx = 0
            for selection in page_items:
                if selection.data.id_ == selection_id:
                    return (page_number, idx, selection) 
                idx += 1
        return None
     
    @staticmethod   
    def _update_all_indexes(selections: OrderedDict) -> None:
        """Update all `page` and `idx` fields in the input data structure. It to ensure consistency with their actual position."""
        for page_number in selections:
            SelectionsManager._update_page_indexes(selections, page_number)
    
    @staticmethod       
    def _update_page_indexes(selections: OrderedDict, page_number: int) -> None:
        """Update all `idx` fields for selections on a specific `page` of the input data structure. It is to ensure consistency with their actual position."""
        cnt = 0
        for selection in selections.get(page_number, []):
            SelectionsManager._update_indexes(selection, page_number, cnt)
            cnt += 1
    
    @staticmethod  
    def _update_indexes(selections: OrderedDict, supposed_page_number: int, supposed_index: int, log_error=False) -> None:
        """Update the `page` and `idx` fields of a single selection to ensure consistency with their actual position."""
        if selections.data.page != supposed_page_number:
            if log_error:
                print(f"Updating `page` from data structure: `page = {selections.data.page} -> {supposed_page_number}`.")
            selections.data.page = supposed_page_number
            
        if selections.data.idx != supposed_index:
            if log_error:
                print(f"Updating `idx` from data structure: `idx = {selections.data.idx} -> {supposed_index}`.")
            selections.data.idx = supposed_index

    def add_selection(self, selection: SelectableRegionItem) -> None:
        """Add a single `selection` to the data structure. The selection is inserted at the position specified in its `data` field. See `InsertCmd` for details."""
        self.undo_stack.push(InsertCmd(self, selection))

    def add_selection_set(self, selections: List[SelectableRegionItem], append = True) -> None:
        """Add a set of `selections` to the data structure. If `append` is True, all selections are appended at the end of their respective page lists, 
        otherwise they are inserted at the position specified in their `data` fields. See `InsertCmd` for details."""
        self.undo_stack.push(InsertAllCmd(self, selections, append))

    def remove_selection(self, selection: SelectableRegionItem) -> None:
        """Remove a single `selection` from the data structure. If the selection has children, they are reparented to the deleted selection's parent 
        (i.e., hierarchy is preserved). See `RemoveCmd` for details."""
        self.undo_stack.push(RemoveCmd(self, selection))

    def remove_selection_set(self, selections: List[SelectableRegionItem]) -> None:
        """Remove a set of `selections` from the data structure. Hierarchy is not preserved, children of deleted selections are not reparented. 
        Selections are removed based on their position (i.e., `page` and `idx`) as defined in their `data` fields. See `RemoveAllCmd` for details."""
        self.undo_stack.push(RemoveAllCmd(self, selections)) # It uses encoded page number and index inside each `selection``, be sure they are robustness

    def edit_selection(self, editing_key: int, editing_idx: int, new_selection: SelectableRegionItem) -> None:
        """Edit a single selection located at `editing_key` (i.e., page number) and `editing_idx` (i.e., index inside the list at `editing_key`) by replacing it 
        with `new_selection`. The edited selection is removed from its original position and added at the position specified in its `data` field. See `EditCmd` for details."""
        self.undo_stack.push(EditCmd(self, editing_key, editing_idx, new_selection))

    def move_selection_set(self, editing: List[EditingData]) -> None:
        """Move a set of selections based on the list of `editing` operations provided. Each operation specifies the original position of the selection to be moved and the replacing selection.
        See `MoveAllCmd` for details."""
        self.undo_stack.push(MoveAllCmd(self, editing))

    def move_section(self, source_page: int, source_idx: int, target_page: int = None, target_idx: int = None) -> None:
        """Move a single selection located at `source_page` (i.e., page number) and `source_idx` (i.e., index inside the list at `source_page`) to a new position specified by
        `target_page` and `target_idx`. If `target_page` is None, the selection remains on the same page. If `target_idx` is None, the selection is appended at the end of the list on `target_page`.
        See `EditCmd` for details."""
        if target_page is None:
            target_page = source_page
        
        if target_idx is None:
            if target_page in self._selections:
                target_idx = len(self._selections[target_page])
            else:
                target_idx = 0
        
        new_selection = self._selections[source_page][source_idx].copy()        
        new_selection.data.page = target_page
        new_selection.data.idx = target_idx
        
        self.edit_selection(source_page, source_idx, new_selection)

    def replace_selection(self, new_selection: SelectableRegionItem) -> None:
        """Replace a single `new_selection` by replacing the existing selection located at the position specified in its `data` field. See `EditCmd` for details."""
        source_page = new_selection.data.page
        source_idx = new_selection.data.idx
        self.edit_selection(source_page, source_idx, new_selection)

    def items(self) -> Tuple[int, List[SelectableRegionItem]]:
        """Return an iterable view of the data structure's items (i.e., (page_number, list_of_selections) pairs)."""
        return self._selections.items()
    
    def keys(self) -> List[int]:
        """Return an iterable view of the data structure's keys (i.e., page numbers)."""
        return self._selections.keys()
    
    def values(self) -> List[List[SelectableRegionItem]]:
        """Return an iterable view of the data structure's values (i.e., lists of selections)."""
        return self._selections.values()
    
    def clear(self) -> None:
        """Clear all selections from the data structure."""
        return self._selections.clear()
    
    def get(self, key: int, default=None) -> Optional[List[SelectableRegionItem]]:
        """Retrieve the list of selections for a given `key` (i.e., page number). If the key does not exist, return `default`."""
        return self._selections.get(key, default)

    # TODO use it everywhere you need to lock for id_
    @staticmethod
    def build_id_lookup(selections_dict: OrderedDict[int, list]) -> dict[str, SelectableRegionItem]:
        """
        Flatten the selections_dict into a mapping from id_ -> SelectionData.
        """
        id_lookup = {}
        for selections in selections_dict.values():         
            for wrapper in selections:           
                sel = wrapper.data
                id_lookup[sel.id_] = sel
        return id_lookup


    def get_selection_path_str(self, selection_id: str, include_last: bool = True) -> str:
        """
        Return the path from root to node_id
        as a list of IDs and a formatted string based on the 'text' fields.
        It is used to generate augmentation prompts.
        If `include_last` is True the text of `selection_id` is also returned.
        """
        # Build an ID lookup since tree is keyed by page numbers
        id_lookup = SelectionsManager.build_id_lookup(self._selections)

        if selection_id not in id_lookup:
            print(f"Node {selection_id} not found in tree") # TODO make an alert
            return ""

        path_ids = []
        current = selection_id

        # climb up parent chain
        while current is not None:
            path_ids.append(current)
            parent = id_lookup[current].parent
            current = parent if parent in id_lookup else None
            
        # reverse to get root -> leaf
        path_ids.reverse()
        # return path_ids # TODO return also the path as a list of nodes IDs.
        last = path_ids.pop()

        # build formatted string
        path_text = " > ".join(id_lookup[n].text for n in path_ids)
        
        if include_last:
            path_text += f" → {id_lookup[last].text}"

        return path_text


    def contextualize_selection(self, selection_id: str, max_nodes_number: int) -> str:
        """
        Build a contextualized string representation of nodes surrounding the given selection.

        Strategy:
        ---------
        1. Start with the siblings of `selection_id` (excluding the node itself).
        2. If not enough, include the parent.
        3. If still not enough, include the parent's siblings.
        4. If still not enough, recurse upward to grandparents and their siblings.
        5. Stop once `max_nodes_number` nodes are collected or the root is reached.

        Rules:
        ------
        - The target node (`selection_id`) is **never included**.
        - Nodes with both empty `text` and `description` are ignored.
        - Order of inclusion: siblings → parent → parent's siblings → higher ancestors.

        Parameters
        ----------
        selection_id : str
            The UUID of the target selection node.
        max_nodes_number : int
            The maximum number of context nodes to include.

        Returns
        -------
        str
            A formatted string where each included node is represented as:
            ```
            - <text>.
              <description>
            ```
        """
        id_lookup = SelectionsManager.build_id_lookup(self._selections) # Dict[str, SelectionData]

        if selection_id not in id_lookup:
            return ""

        collected: List[SelectionData] = []
        visited = set([selection_id])  # exclude target itself

        def add_if_valid(node_id: str):
            """Helper to add node if it has content and not already visited."""
            if node_id in visited:
                return
            node = id_lookup.get(node_id)
            if node and (node.text.strip() or node.description.strip()):
                collected.append(node)
            visited.add(node_id)

        def climb_and_collect(node_id: str):
            """Recursive helper to collect siblings, parent, and then climb up."""
            if len(collected) >= max_nodes_number:
                return
            node = id_lookup.get(node_id)
            if not node or not node.parent:
                return

            parent_id = node.parent
            parent = id_lookup.get(parent_id)
            if not parent:
                return

            # Step 1: add siblings
            for sib_id in parent.children:
                if sib_id != node_id and len(collected) < max_nodes_number:
                    add_if_valid(sib_id)

            # Step 2: add parent
            if len(collected) < max_nodes_number:
                add_if_valid(parent_id)

            # Step 3: climb higher if needed
            if len(collected) < max_nodes_number:
                climb_and_collect(parent_id)

        # Start climbing from the target node
        climb_and_collect(selection_id)

        # Format result
        INDENTATION = "  - "
        formatted = []
        for node in collected[:max_nodes_number]:
            text = node.text.strip()
            description = node.description.strip()
            if text == None or text == "":
                formatted.append(f"{INDENTATION}{description}")
            elif description == None or description == "":
                formatted.append(f"{INDENTATION}{text}")
            else:
                formatted.append(f"{INDENTATION}{node.text.strip()}\n{INDENTATION}{node.description.strip()}")

        return "\n\n".join(formatted)




class BaseCmd(QUndoCommand):
    """The base class for all undoable commands related to `SelectionManager`. It provides a common interface and holds a reference to the selections data structure (i.e., `self.model`)."""
    
    def __init__(self, manager: SelectionsManager, description: str="Base"):
        super().__init__(description)
        self.model = manager._selections # Reference to the selections data structure to be modified
        
    def redo(self) -> None:
        """Do an operation, it is called at construction time to perform the operation the first time."""
        # TODO add QLabel in the main_view for feedback since it might change regions that are not displayed in the current page
        raise NotImplementedError

    def undo(self) -> None:
        """Reverse the operation performed in `redo`."""
        raise NotImplementedError



class InsertCmd(BaseCmd):
    """Add a single selection to the data structure. The selection is inserted at the position specified in its `data` field."""
    
    def __init__(self, manager: SelectionsManager, value: SelectableRegionItem, description: str="Insert"):
        super().__init__(manager, description)
        self.value = value # The selection to be added
        self.key = None # The key where the selection has been added, it is set at `redo` time and used at `undo` time
        self.index = None # The index inside the list at `key` where the selection has been added, it is set at `redo` time and used at `undo` time
    
    def redo(self) -> None: # Called at constructor time
        self.key, self.index = InsertCmd.insert_ordered(self.model, self.value)

    def undo(self) -> None:
        InsertCmd.undo_insert_ordered(self.model, self.key, self.index)
    
    @staticmethod 
    def insert_ordered(dictionary: OrderedDict, value: SelectableRegionItem, key: int = None, idx=None) -> Tuple[int, int]: 
            """
            Insert a single value into the OrderedDict such that keys are kept in sorted order.
            If the key does not exist, create a new list and insert the key. If `idx < 0`, the value is appended to the list at `key`. If `idx >= 0`, the value is inserted at the specified index.
            If `idx == None` or `key == None`, the value is inserted at the position specified in its `data` field.
            Note: This method updates the `page` and `idx` fields of all selections on the affected page to ensure consistency.
            Returns: (final_key, index) of the inserted value.
            """
            if key is None:
                key = value.data.page
            if idx is None:
                idx = value.data.idx
            
            if key not in dictionary:
                # Key does not exist (i.e., the list value is empty), insert in the correct sorted position
                dictionary[key] = [value]  # temporarily add at the end

                # Find keys greater than new key to move to the end
                keys_to_move = [k for k in dictionary if k > key]
                for k in keys_to_move:
                    dictionary.move_to_end(k)

                # The new value is always at index 0 of its new list
                return key, 0
            
            # Insert into the list at the specific `idx`
            if idx < 0:
                dictionary[key].append(value)
                idx = len(dictionary[key]) - 1
            else:
                dictionary[key].insert(idx, value)
            index = idx
            SelectionsManager._update_page_indexes(dictionary, key) # TODO move elsewhere (out of for lops that calls `insert_oriented`) to being more efficient
            return key, index

    @staticmethod
    def undo_insert_ordered(dictionary: OrderedDict, key: int, idx: int) -> None:
        """Undo the insertion of a selection at `key` and `idx`, and update the index of the other selections to assure consistencyd."""
        try:
            dictionary[key].pop(idx)
            # Optionally remove key if list becomes empty
            if not dictionary[key]:
                del dictionary[key]
            
            SelectionsManager._update_page_indexes(dictionary, key)
        except IndexError:
            traceback.print_exc()
            print("Error on UNDO") # TODO make alert?




class InsertAllCmd(BaseCmd):
    """Add a set of selections to the data structure. If `append` is True, all selections are appended at the end of their respective page lists. 
    It is based on multiple `InsertCmd.insert_ordered` operations."""
    
    def __init__(self, manager, values: List[SelectableRegionItem], append = True, description = "InsertAll"):
        super().__init__(manager, description)
        self.values = values # The selections to be added
        self. keys = None # The keys where the selections have been added, it is set at `redo` time and used at `undo` time
        self.indexes = None # The indexes inside the lists at `keys` where the selections have been added, it is set at `redo` time and used at `undo` time
        self.append = append # If True, all selections are appended at the end of their respective page lists, otherwise they are inserted at the position specified in their `data` fields.
        
    def redo(self) -> None: # Called at constructor time
        self.keys = []
        self.indexes = []
        for v in self.values:
            idx = -1 if self.append else v.data.idx 
            k, i = InsertCmd.insert_ordered(self.model, v, idx=idx)  # idx < 0 => append to the current selection and create a new idx
            v.data
            self.keys.append(k)
            self.indexes.append(i)
    
    def undo(self) -> None:
        for i, _ in enumerate(self.values):
            reverse_idx = len(self.values) - (i + 1)
            InsertCmd.undo_insert_ordered(self.model, self.keys[reverse_idx], self.indexes[reverse_idx])
    
    
 
    
class RemoveCmd(BaseCmd):
    """Remove a single selection from the data structure. Selections are removed based on their position (i.e., `page` and `idx`) as defined in their `data` fields.
    If the selection has children, they are reparented to the deleted selection's parent (i.e., hierarchy is preserved)."""
    
    def __init__(self, manager: SelectionsManager, selection: SelectableRegionItem, description: str="Remove"):
        super().__init__(manager, description)
        self.value = selection
        self.node_children = []
        
    def redo(self) -> None: # Called at constructor time
        self.node_children = self.remove_and_relink_children(self.model, self.value)

    def undo(self) -> None:
        InsertCmd.insert_ordered(self.model, self.value)
        
        # Restore hierarchy among the nodes that have been deleted and now are re-inserted
        for child in self.node_children:
            child.data.parent = self.value.data.id_
    
    @staticmethod      
    def remove_and_relink_children(dictionary: OrderedDict, selection: SelectableRegionItem) -> List[SelectableRegionItem]:
        """Remove a single selection from the data structure and reparent its children to the deleted selection's parent.
        Returns the list of children that have been reparented. Note that the index of the other selections on the affected 
        page is updated to ensure consistency."""
        parent_id = selection.data.parent  # May be None
        children = []
        for child_id in list(selection.data.children):
            found = SelectionsManager.find_selection_by_id(dictionary, child_id)
            if found is None:
                # ERROR! child not found
                continue
            _, _, child = found
            child.data.parent = parent_id  # if None => becomes root
            children.append(child)

        # Remove the node object from selections dict
        edited_page = None
        for page, page_items in list(dictionary.items()):
            for sel in list(page_items):
                if sel.data.id_ == selection.data.id_:
                    page_items.remove(sel)
                    if not page_items: # if it is empty
                        del dictionary[page]
                    else: # Update idx only if there was an editing and the dictionary[page] is not empty
                        edited_page = page
                    break
            if edited_page is not None:    
                break
        
        if edited_page is not None:
            SelectionsManager._update_page_indexes(dictionary, edited_page)

        return children # Which parent has been modified since it were cancelled



class RemoveAllCmd(BaseCmd): # Removes a set of selections and does not preserves hierarchy between its children and its parent within the tree
    """Remove a set of selections from the data structure. Hierarchy is not preserved, children of deleted selections are not reparented. 
    Selections are removed based on their position (i.e., `page` and `idx`) as defined in their `data` fields."""
    
    def __init__(self, manager: SelectionsManager, selections: List[SelectableRegionItem], description: str="RemoveAll"):
        super().__init__(manager, description)
        self.values = selections

    def redo(self) -> None: # Called at constructor time
        self.node_children = self.remove_selections(self.model, self.values)

    def undo(self) -> None:
        for value in self.values: 
            InsertCmd.insert_ordered(self.model, value)
        # SelectionsManager._update_indexes(dictionary) # It is done by `insert_ordered`

    @staticmethod
    def remove_selections(dictionary: OrderedDict, selections: List[SelectableRegionItem]) -> None:
        """Remove a set of selections from the data structure. Selections are removed based on their position (i.e., `page` and `idx`) as defined in their `data` fields.
        Note that the index of the other selections on the affected pages is updated to ensure consistency."""
        
        to_remove_id_list = {s.data.id_ for s in selections}  
        for page, page_items in list(dictionary.items()):
            removed = False
            for sel in list(page_items):
                if sel.data.id_ in to_remove_id_list:
                    page_items.remove(sel)
                    if not page_items: # if it is empty
                        del dictionary[page]
                    to_remove_id_list.remove(sel.data.id_)
                    if len(to_remove_id_list) <= 0:
                        return
                    removed = True
            if removed:
                SelectionsManager._update_page_indexes(dictionary, page)
            
        if len(to_remove_id_list) > 0:
            print(f"Error, cannot remove sections: {to_remove_id_list}") # TODO maake alert?




class EditCmd(BaseCmd): #i.e., replace
    """Edit a single selection by replacing it with a new one. The edited selection is removed from its original position (i.e., `edited_key -> edited_idx`), and added at the 
    position specified in its `data` field."""

    def __init__(self, manager: SelectionsManager, editing_key: int, editing_idx: int, new_value: SelectableRegionItem, description="Edit"):
        super().__init__(manager, description)
        self.value = new_value # The edited selection, it encodes target key and idx
        self.editing_key = editing_key # The key where the original selection was
        self.editing_idx = editing_idx # The idx where the original selection was
        self.old_value = None # A copy of the not edited selection for undo

    def redo(self) -> None: # Called at constructor time
        self.old_value = self.model[self.editing_key][self.editing_idx].copy()            
        EditCmd.edit_selection(self.model, self.editing_key, self.editing_idx, self.value)
        
    def undo(self) -> None:
        EditCmd.edit_selection(self.model, self.value.data.page, self.value.data.idx, self.old_value)

    @staticmethod
    def edit_selection(dictionary: OrderedDict, old_key: int, old_idx: int, selection: SelectableRegionItem, replace = True) -> None:
        """Edit a single selection located at `old_key` (i.e., page number) and `old_idx` (i.e., index inside the list at `old_key`) by replacing it 
        with `selection`. The edited selection is removed from its original position and added at the position specified in its `data` field.
        Note that the index of the other selections on the affected pages is updated to ensure consistency."""
        try:
            if replace:
                # Remove edited selection
                dictionary[old_key].pop(old_idx) 
                if len(dictionary[old_key]) <= 0:
                    dictionary.pop(old_key) # Eventually, remove the empty list
                
            # Add the edited selection
            InsertCmd.insert_ordered(dictionary, selection) # Add the edited selection
            
            target_key = selection.data.page
            SelectionsManager._update_page_indexes(dictionary, target_key)
            if target_key != old_key:
                SelectionsManager._update_page_indexes(dictionary, old_key)
        except:
            traceback.print_exc()
            print(f"[ERROR] Cannot edit selection at `key: {old_key}`, `idx: {old_idx}` with a selection encompassing data.") # TODO make alert?



class MoveAllCmd(BaseCmd):
    """Move a set of selections based on the list of `editing` operations provided. Each operation specifies the original position of the selection to be moved and the replacing selection."""

    def __init__(self, manager: SelectionsManager, editing: List[EditingData], description: str="MoveAll"):
        super().__init__(manager, description)
        self.editing = editing  # forward edits
        self.inverse = self._compute_inverse(editing)

    def _compute_inverse(self, editing: List[EditingData]) -> List[EditingData]:
        """Build the inverse edits for undo before applying forward ones."""
       
        inverse = []
        for e in editing:
            if e.editing_page in self.model and 0 <= e.editing_idx < len(self.model[e.editing_page]):
                old_item = self.model[e.editing_page][e.editing_idx]
                old_copy = old_item.copy()
                old_copy.data.page = e.editing_page
                old_copy.data.idx = e.editing_idx
                inverse.append(
                    type(e)(
                        editing_page=e.new_selection.data.page,
                        editing_idx=e.new_selection.data.idx,
                        new_selection=old_copy,
                    )
                )
        return inverse

    def redo(self) -> None: # Called at constructor time
        """Apply the forward edits (normal direction)."""
        MoveAllCmd._apply_edit(self.model, self.editing)

    def undo(self) -> None:
        """Reapply the inverse edits (restore old state)."""
        MoveAllCmd._apply_edit(self.model, self.inverse)
        
    @staticmethod
    def _apply_edit(dictionary: OrderedDict, editing: List[EditingData]) -> None:
        """Apply a set of edits to the data structure. Each edit specifies the original position of the selection to be moved and the replacing selection.
        Note that the index of the other selections on the affected pages is updated to ensure consistency."""
        
        # print(">>> _apply_edit called with:")
        # for e in editing:
        #     print(
        #         f"  from page {e.editing_page} idx {e.editing_idx} "
        #         f"-> new page {e.new_selection.data.page} "
        #         f"idx {e.new_selection.data.idx} id {e.new_selection.data.id_}"
        #     )

        edit_pages = set()

        # Remove by id (not index)
        for e in editing:
            arr = dictionary.get(e.editing_page, [])
            for idx, item in enumerate(arr):
                if item.data.id_ == e.new_selection.data.id_:
                    removed = arr.pop(idx)
                    edit_pages.add(e.editing_page)
                    # print(f"   removed {removed.data.id_} from page {removed.data.page} idx {idx}")
                    break
        
        # Insertions
        for e in editing:
            tgt_page = e.new_selection.data.page
            tgt_idx = e.new_selection.data.idx
            if tgt_page not in dictionary:
                dictionary[tgt_page] = []
            arr = dictionary[tgt_page]
            if tgt_idx < 0 or tgt_idx > len(arr):
                tgt_idx = len(arr)
            arr.insert(tgt_idx, e.new_selection)
            edit_pages.add(tgt_page)
            # print(
            #     f"   inserted {e.new_selection.data.id_} "
            #     f"into page {tgt_page} idx {tgt_idx}"
            # )

        # Recompute idx fields
        #for page, arr in dictionary.items():
        #    for i, item in enumerate(arr):
        #        item.data.page = page
        #        item.data.idx = i
        for page in edit_pages:
            SelectionsManager._update_page_indexes(dictionary, page)

        # print(">>> after edit, selections state:")
        # for p, arr in sorted(self.model.items()):
        #     print(f" page {p}: {[a.data.id_+f'@{a.data.idx}' for a in arr]}")
