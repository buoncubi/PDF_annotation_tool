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

from collections.abc import Set
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from PyQt5.QtWidgets import QMessageBox
from enum import Enum
import json
import re
import traceback
from typing import List, Optional, Self, Tuple, Any



@dataclass
class CategoryData:
    """The data structure defining an element of the `SelectionCategory` enumerator."""
    
    name: str # The name of the category
    color: str # The color associated to this category (in HEX format)
    shortcut: str # The keyboard shortcut to assign this category to a selection
    unstructured_names: Set[str] = field(default_factory=set) # The list of names used by Unstructured library to refer to this category


class UnstructuredCategory:
    """The types of categories that the Unstructured library can extract, see 
    `pdf_annotation_tool.manipulation.importer.UnstructuredImporter`."""
    
    # Unstructured possible categories (i.e., possible strings assignable to "KEY_CATEGORY")
    FIGURE_CAPTION = "FigureCaption"
    NARRATIVE_TEXT = "NarrativeText"
    LIST_ITEM = "ListItem"
    TITLE = "Title"
    ADDRESS = "Address"
    TABLE = "Table"
    IMAGE = "Image"
    HEADER = "Header"
    FOOTER = "Footer"
    FORMULA = "Formula"
    COMPOSITE_ELEMENT = "CompositeElement"
    PAGE_BREAK = "PageBreak"
    UNCATEGORIZED_TEXT = "UncategorizedText"


# The enumerator of possible selection's category in the `SelectionData`
class SelectionCategory(Enum):
    """The types of selections `category` that can be extracted from a PDF page and encoded in `SelectionData`."""
    
    CAPTION = CategoryData("caption", "#1f77b4", "C", [UnstructuredCategory.FIGURE_CAPTION])
    TEXT = CategoryData("text", "#2ca02c", "T", [UnstructuredCategory.NARRATIVE_TEXT])
    LIST_ITEM = CategoryData("listItem", "#ff7f0e", "L", [UnstructuredCategory.LIST_ITEM])
    TITLE = CategoryData("title", "#9467bd", "I", [UnstructuredCategory.TITLE])
    CONTACT = CategoryData("contact", "#8c564b", "O", [UnstructuredCategory.ADDRESS])
    TABLE = CategoryData("table", "#e377c2", "B", [UnstructuredCategory.TABLE])
    IMAGE = CategoryData("image", "#17becf", "M", [UnstructuredCategory.IMAGE])
    HEADER = CategoryData("header", "#ffbb78", "H", [UnstructuredCategory.HEADER])
    FOOTER = CategoryData("footer", "#bcbd22", "F", [UnstructuredCategory.FOOTER])
    FORMULA = CategoryData("formula", "#550A21", "R", [UnstructuredCategory.FORMULA])
    CONTAINER = CategoryData("container", "#aec7e8", "N", [UnstructuredCategory.COMPOSITE_ELEMENT])
    UNKNOWN = CategoryData("unknown", "#7f7f7f", "U", [UnstructuredCategory.PAGE_BREAK, UnstructuredCategory.UNCATEGORIZED_TEXT])

    @staticmethod
    def category_form_string(category_str: str) -> Self:
        """Map a string to a `SelectionCategory` enumerator value. If the string does not match any category, it returns `SelectionCategory.UNKNOWN`."""
        for _, c in enumerate(SelectionCategory):
            if category_str == c.value.name:
                return c
        print(f"Unstructured partition category unknown: {category_str}") # TODO make alert
        return SelectionCategory.UNKNOWN

    @staticmethod
    def category_from_unstructured(category_unstructured: str) -> Self:
        """Map an Unstructured category string to a `SelectionCategory` enumerator value. If the string does not match any category, it returns `SelectionCategory.UNKNOWN`."""
        for _, c in enumerate(SelectionCategory):
            if category_unstructured in c.value.unstructured_names:
                return c
        print(f"Unstructured partition category unknown: {category_unstructured}") # TODO make alert
        return SelectionCategory.UNKNOWN




def add_json_keys(cls):
    """A decorator to add JSON key constants to the `SelectionData` class. It is used to define JSON keys for each field in the dataclass."""
    
    props = [f.name for f in fields(cls)]
    ( # order them according with their definition in `SelectionData`
        cls.JSON_KEY_ID,
        cls.JSON_KEY_DOC,
        cls.JSON_KEY_PAGE,
        cls.JSON_KEY_IDX,
        cls.JSON_KEY_COORDS,
        cls.JSON_KEY_TEXT,
        cls.JSON_KEY_CATEGORY,
        cls.JSON_KEY_IMAGE,
        cls.JSON_KEY_PARENT,
        cls.JSON_KEY_CHILDREN,
        cls.JSON_KEY_DESCRIPTION
    ) = props  
    return cls



@add_json_keys
@dataclass
class SelectionData:
    """The data structure that represents a selected area in a PDF page."""
    
    id_: str # The section UUID
    doc: str # The file path or url to the PDF document
    page: int # The PDF page related to this selection
    idx: int = field(init=False, default=-1) # The index of this selection into the array of selections for this page
    coords: List[Tuple[int, int]] # The coordinates of selection's polygon vertex. The points are in the PDF-based coordinates and represented as `[[x1,y1][x2,y2],...]`.
    text: str # The text extracted from the PDF page within the selection coordinates.
    category: SelectionCategory  # The type of the selection among the `SelectionCategory` enumerator (e.g., "Title", "Text", "Table", "Image" etc.)
    image: str # The screenshot within the selection coordinates. It is an image encoded as a base64 string.
    parent: Optional[str] = None # Parent selection ID (`None` if it is the root)
    children: List[str] = field(default_factory=list) # Children selection ID (`[]` if it is a leaf)
    description: str = "" # The optional LLM-based description of this selection
    
    
    def to_json(self) -> str:
        """Convert this dataclass to a JSON string."""
        return json.dumps(asdict(self))
    
    
    def to_dict(self) -> dict:
        """Convert this dataclass to a dictionary."""
        return SelectionData._to_dict(self)
    
    
    @staticmethod
    def get_fields_name() -> List[str]:
        """Get the list of field names defined in this dataclass."""
        return list(SelectionData.__dataclass_fields__.keys())
    
    
    @staticmethod
    def _to_dict(obj) -> dict:  
        """Convert each field recursively and transform `CategoryData` objects into a string.
        Inputs can either be a `SelectionData` another data class, or an object as list, dict, etc."""
        
        if isinstance(obj, SelectionCategory):
            return obj.value.name  
        elif is_dataclass(obj):
            return {k: SelectionData._to_dict(v) for k, v in asdict(obj).items()}
        elif isinstance(obj, (list, tuple)):
            return [SelectionData._to_dict(v) for v in obj]
        elif isinstance(obj, dict):
            return {k: SelectionData._to_dict(v) for k, v in obj.items()}
        return obj
    
    
    @staticmethod
    def from_dict(data: dict) -> Optional["SelectionData"]:
        """Create a `SelectionData` object from a dictionary. Returns `None` if an error occurs."""
        
        try:
            out = SelectionData(
                id_ = data[SelectionData.JSON_KEY_ID],
                doc = data[SelectionData.JSON_KEY_DOC],
                page = int(data[SelectionData.JSON_KEY_PAGE]), 
                coords = data[SelectionData.JSON_KEY_COORDS],
                text = data[SelectionData.JSON_KEY_TEXT],
                category = SelectionCategory.category_form_string(data[SelectionData.JSON_KEY_CATEGORY]),
                image = data[SelectionData.JSON_KEY_IMAGE],
                parent = data[SelectionData.JSON_KEY_PARENT],
                children = data[SelectionData.JSON_KEY_CHILDREN],
                description = data[SelectionData.JSON_KEY_DESCRIPTION]
            )
            out.idx = int(data[SelectionData.JSON_KEY_IDX])
            return out
        except Exception: # TODO make an alert
            print('Error on loading selection data from dictionary.')
            traceback.print_exc()
            return None
     
        
    @staticmethod # NOT USED
    def set_attr(obj: any, path: str, value: any) -> None:
        """
        Set attribute given code and string-like properties name.
         - `obj`: A property related to this data class (e.g., `selection.coords`)
         - `path`: The property related to this data class as a string (e.g., `coords.x`)
         - `vale`: The new value to set.
        For instance `set_attr(selection.coords, "[1].data", 12)` will be equal to `selection.coords[1].data = 12`.
        """
        
        try:
            parts = re.findall(r'\w+|\[\d+\]|\[["\'].*?["\']\]', path)
            target = obj
            
            for i, part in enumerate(parts):
                # Handle attribute
                if re.match(r'^\w+$', part):
                    if i == len(parts) - 1:
                        setattr(target, part, value)
                        return
                    target = getattr(target, part)
                
                # Handle list index
                elif re.match(r'^\[\d+\]$', part):
                    idx = int(part[1:-1])
                    if i == len(parts) - 1:
                        target[idx] = value
                        return
                    target = target[idx]
                
                # Handle dict key
                elif re.match(r'^\[["\'].*?["\']\]$', part):
                    key = part[2:-2]
                    if i == len(parts) - 1:
                        target[key] = value
                        return
                    target = target[key]
        except Exception as e:
            traceback.print_exc()
            QMessageBox.warning(None, "Error", f"Cannot set JSON property {path}.\n`{e}`")


    @staticmethod
    def get_attr(obj: any, path:str) -> any:
        """
        Get attribute given object and string-like properties path.
         - `obj`: A property related to this data class (e.g., `selection.coords`)
         - `path`: The property related to this data class as a string (e.g., `coords.x`)
        For instance `get_attr(selection.coords, "[1].data")` will be equal to `selection.coords[1].data`.
        It returns `None` if the attribute is not found.
        """
        
        try:
            parts = re.findall(r'\w+|\[\d+\]|\[["\'].*?["\']\]', path)
            target = obj
            
            for part in parts:
                # Handle attribute
                if re.match(r'^\w+$', part):
                    target = getattr(target, part)
                
                # Handle list index
                elif re.match(r'^\[\d+\]$', part):
                    idx = int(part[1:-1])
                    target = target[idx]
                
                # Handle dict key
                elif re.match(r'^\[["\'].*?["\']\]$', part):
                    key = part[2:-2]
                    target = target[key]
            
            return target
        except Exception as e:
            traceback.print_exc()
            QMessageBox.warning(None, "Error", f"Cannot get JSON property {path}.\n`{e}`")
            return None


    @staticmethod
    def has_property(prop: str) -> Optional[str]:
        """
        Check if prop is a valid attribute of the dataclass.
        Returns the field name if valid, otherwise None.
        """
        
        field_names = [f.name for f in fields(SelectionData)]
        return prop if prop in field_names else None

    @staticmethod
    def _limit_str(s: Any, limit: int, should_encode = True) -> str:
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

    def __str__(self):
        id_ = SelectionData._limit_str(self.id_, limit=3)
        text = SelectionData._limit_str(self.text, limit=20)
        description = SelectionData._limit_str(self.description, limit=20)
        image = SelectionData._limit_str(self.image, limit=4)
        parent = SelectionData._limit_str(self.parent, limit=3)
        children = []
        for c in self.children:
            children.append(SelectionData._limit_str(c, limit=3))
        return f"id={id_}, page={self.page}, idx={self.idx}, coords={self.coords}, text={text}, category={self.category}, image={image}, parent={parent}, children={children}, description={description})"

    def __repr__(self):
        return self.__str__()

