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

import abc
import copy
from typing import Self, List, Tuple, Union, Optional, TYPE_CHECKING
import fitz  # PyMuPDF

from PyQt5.QtCore import Qt, QPointF, QRectF
from PyQt5.QtGui import QPolygonF, QPen, QPainter
from PyQt5.QtWidgets import QGraphicsPolygonItem, QMenu, QAction, QToolTip, QGraphicsRectItem, QGraphicsSceneContextMenuEvent, QAbstractGraphicsShapeItem, QWidget, QStyleOptionGraphicsItem

from pdf_annotation_tool.selection.data import SelectionData
if TYPE_CHECKING:
    from pdf_annotation_tool.tool import PDFAnnotationTool


# The graphic related to a selected area in a PDF page, it defines the menu on left click. It is used by `SelectablePolygonItem`.
class SelectableRegionItem: #(QAbstractGraphicsShapeItem):
    """The base class for all selectable region items in the PDF view. It defines the `data` attribute of type `SelectionData`, and it implements the type of elements in the selection dictionary.
    It takes care of the context menu (i.e., left-click) and the conversion between scene coordinates and PDF coordinates.
    It is an abstract class, and it must be inherited by a concrete class that implements the shape-specific methods.
    """
    
    def __init__(self, main_view: 'PDFAnnotationTool'):
        #TODO remove `main_view` from this class and manage Q`parent` properly.
        QAbstractGraphicsShapeItem.__init__(self, parent=None)
        
        # Common initialization for all selectable items
        self.setFlags(self.ItemIsSelectable)  # | self.ItemIsMovable
        self.setAcceptHoverEvents(True)
        
        self.main_view = main_view # The `PDFView` instance that contains this item.
        self.data = None # The data associated with this selection, of type `SelectionData`.
        self.converted_to_pdf_space = False # Whether the points in `self.data.coords` are in PDF space or in scene space. At the beginning they are in scene space, and they are converted to PDF space when the selection is created.

    def contextMenuEvent(self, event: QGraphicsSceneContextMenuEvent) -> None:
        """Define the left-click menu for the selectable region, encompassing: find in tree, edit selection, delete selection, move in page, move among pages and redraw."""
        menu = QMenu()
        
        # Find action
        action_find = menu.addAction("Find in Trees")
        action_find.setToolTip("The node relative to this region will be highlighted in both the trees on the left-hand side.")
        action_find.triggered.connect(self.find_in_trees)

        # Edit selection
        action_edit = menu.addAction("Edit Selection")
        action_edit.setToolTip("Open a dialog where you can view all the selection's metadata and edit some of them.")
        action_edit.triggered.connect(self.edit_selection)
        
        # Delete selection using menu
        action_delete = menu.addAction("Delete")
        action_delete.setToolTip("Delete a selection and link its parent with its children.")
        action_delete.triggered.connect(self.delete_selection)
        
        # Move selection using menu
        action_move = QMenu("Move in Page")
        action_move.setToolTip("Set the `idx` field of the selection, i.e., the index in the selection list for this page.")
        for i in range(len(self.main_view._selections.get(self.main_view.get_page_num(), default=[]))):
            if self.data is None:
                return
            if i == self.data.idx:
                continue
            sub_move_action = QAction(str(i), action_move)
            sub_move_action.triggered.connect(lambda checked, target_index=i: self.move_selection_idx(target_index))
            action_move.addAction(sub_move_action)
        menu.addMenu(action_move)
        
        action_move_page = QMenu("Move Among Pages")
        action_move_page.setToolTip("Set the `page` field of the selection, i.e., the page number in which the selection appears.")
        for i in range(len(self.main_view._doc)):
            pg = i + 1
            if pg == self.data.page:
                continue
            sub_move_action_page = QAction(str(pg), action_move_page)
            sub_move_action_page.triggered.connect(lambda checked, target_page=pg: self.move_selection_page(target_page))
            action_move_page.addAction(sub_move_action_page)
        menu.addMenu(action_move_page)
        
        # Redraw selection
        action_redraw = menu.addAction("Redraw")
        action_redraw.setToolTip("The metadata of this region will be changed based on your next selection in a PDF page.")
        action_redraw.triggered.connect(self.redraw_selection)

        def show_tip(action):
            if action.toolTip():
                # Get the rect of the hovered action inside the menu
                rect = menu.actionGeometry(action)
                # Convert it to global screen coordinates
                global_pos = menu.mapToGlobal(rect.topRight())
                # Offset so tooltip is slightly to the right of the menu item
                QToolTip.showText(global_pos + QPointF(10, 0).toPoint(), action.toolTip(), menu)

        menu.hovered.connect(show_tip)
        menu.exec_(event.screenPos())


    def delete_selection(self) -> None:
        """The action associated with the 'delete selection' item in the context menu of this selection.
        It reassign a parent to the children of the deleted selection, if any."""
        
        self.main_view.remove_selection(self)

        
    def find_in_trees(self) -> None:
        """The action associated with the 'find in trees' item in the context menu of this selection."""
        
        if self.data is None:
            return
        self.main_view.trees_panel.expand_and_select_by_id(self.data.id_)


    def edit_selection(self) -> None:
        """The action associated with the 'edit selection' item in the context menu of this selection."""
        
        if self.data is None:
            return
        sel_id = self.data.id_
        self.main_view.trees_panel.hier_tree.open_selection_editor_by_id(sel_id)


    def move_selection_idx(self, target_index: int) -> None:
        """The action associated with the 'move in page' item in the context menu of this selection."""
        
        self.main_view.move_selection(self, target_index=target_index)
    
        
    def move_selection_page(self, target_page: int) -> None:
        """The action associated with the 'move among pages' item in the context menu of this selection."""
        
        self.main_view.move_selection(self, target_page=target_page)


    def redraw_selection(self) -> None:
        """The action associated with the 'redraw' item in the context menu of this selection. It does not perform any manipulation but sets this selection as 
        the one to be redrawn on the next selection in the PDF view (i.e., it store `self` in `self.main_view.selection_to_redraw`)."""
        
        self.main_view.selection_to_redraw = self


    def to_pdf_points(self, scene_points: List[QPolygonF]) -> List[Tuple[float, float]]:
        """Convert a list of `QPointF` in scene coordinates, and return it as a list of `[x, y]` in PDF coordinates."""
        
        inverse_matrix = self.main_view.pdf_to_scene_transform
        pdf_points = []
        for i in range(scene_points.size()):
            pdf_x, pdf_y = self.scene_to_pdf_coords(scene_points[i].x(), scene_points[i].y(), inverse_matrix)
            pdf_points.append([pdf_x, pdf_y])
        return pdf_points


    @staticmethod
    def scene_to_pdf_coords(scene_x: float, scene_y: float, inverse_matrix: fitz.Matrix) -> Tuple[float, float]:
        """Convert a point `(scene_x, scene_y)` from scene coordinates into PDF coordinates using the inverse transformation matrix.
        It returns the point as `(pdf_x, pdf_y)`."""
        
        point = fitz.Point(scene_x, scene_y).transform(inverse_matrix)
        pdf_x = point.x
        pdf_y = point.y
        return pdf_x, pdf_y


    @staticmethod
    def pdf_to_scene_coords(pdf_x: float, pdf_y: float, pdf_zoom: float) -> Tuple[float, float]:
        """Convert a point `(pdf_x, pdf_y)` from PDF coordinates into scene coordinates using the `pdf_zoom` factor.
        It returns the point as `(scene_x, scene_y)`."""
        
        scene_x = pdf_x * pdf_zoom
        scene_y = pdf_y * pdf_zoom
        return scene_x, scene_y 


    def get_pdf_points(self) -> List[Tuple[float, float]]: 
        """Get the points of this selection in PDF coordinates as a list of `[[x1, y1], [x2, y2], ...]`.
        If the points have not been converted to PDF space yet, it performs the conversion using `to_pdf_points`.
        Otherwise, it returns the points already stored in `self.data.coords`."""
        
        if not self.converted_to_pdf_space:
            return self.to_pdf_points(self._get_qt_points())
        else:
            return [[ptn.x(), ptn.y()] for ptn in self._get_qt_points()]
    
    
    def _get_scene_points(self, pdf_zoom: float) -> List[Tuple[float, float]]:
        """Get the points of this selection in the scene coordinates as a list of `[[x1, y1], [x2, y2], ...]`.
        This method is in charge of converting the points from PDF space to scene space using the `pdf_zoom` factor.
        If the points have not been converted to PDF space yet (based on `self.converted_to_pdf_space`), it performs 
        the conversion using `get_pdf_points`."""
        
        if not self.converted_to_pdf_space: 
            # Transform point to PDF space and return an array based on them. 
            # It should go here only the first time the selection is created.
            pdf_coords = self.get_pdf_points()
            self.converted_to_pdf_space = True
        else:
            # Get an array of points already transformed into the PDF space.
            pdf_coords = self.data.coords
            
        
        # Convert the points from PDF space to scene space.
        scene_points = []
        for i in range(len(pdf_coords)):
            scene_x, scene_y = self.pdf_to_scene_coords(pdf_coords[i][0], pdf_coords[i][1], pdf_zoom)
            scene_points.append([scene_x, scene_y])
        return scene_points
    
        
    @abc.abstractmethod    
    def _get_qt_points(self) -> List[QPointF]:
        """Must be implemented by subclass to return shape-specific points."""

        raise NotImplementedError
    
    
    @abc.abstractmethod
    def transform_selected_region(self, pdf_zoom: float) -> None:
        """Must be implemented by subclass to transform the PDF coordinates into a shape in the scene coordinate based on `pdf_zoom`."""
        
        raise NotImplementedError


    @abc.abstractmethod
    def copy(self, data: SelectionData = None) -> Self: #SelectableRegionItem
        """Must be implemented by subclass to return a copy of this item, with the same shape and a deep copy of `data`."""
        
        raise NotImplementedError


    @staticmethod
    def rect_to_polygon(rect: Union[List[List[float]], QGraphicsRectItem, QRectF]) -> List[List[float]]:
        """Convert a rectangle defined as `[[x0, y0], [x1, y1]]` (the opposite vertexes) or as `QGraphicsRectItem` or as `QRectF` into a 
        polygon defined as  `[[x0, y0], [x1, y1], [x2, y2], [x3, y3]]`."""
        
        if isinstance(rect, list):
            [x0, y0], [x1, y1] = rect
        if isinstance(rect, QGraphicsRectItem):
            rect = rect.rect()
        if isinstance(rect, QRectF):
            [x0, y0] = [rect.topLeft().x(), rect.topLeft().y()]
            [x1, y1] = [rect.bottomRight().x(), rect.bottomRight().y()]
            
        # define the four corners in clockwise order
        return [
            [x0, y0],
            [x1, y0],
            [x1, y1],
            [x0, y1]
        ]


    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self.data})"
    
    def __repr__(self):
        return self.__str__()
    


# For info see `SelectableRegionItem` and `QGraphicsPolygonItem`.
class SelectablePolyItem(SelectableRegionItem, QGraphicsPolygonItem):
    """Implements a selectable polygon item in the PDF view, inheriting from `SelectableRegionItem` and `QGraphicsPolygonItem`."""
    
    def __init__(self, main_view: 'PDFAnnotationTool', polygon: QPolygonF = None, do_transform: bool = True):
        """Initialize the selectable polygon item. If `polygon` is given, it is used to initialize the `QGraphicsPolygonItem`, otherwise an empty polygon is created.
        If `do_transform` is `False`, the points in `polygon` are assumed to be already in PDF coordinates, and no conversion will be performed when the selection is created."""
        
        if polygon:
            QGraphicsPolygonItem.__init__(self, polygon, parent=None)
        else:
            QGraphicsPolygonItem.__init__(self, parent=None)
        SelectableRegionItem.__init__(self, main_view)
        
        self.setFlag(QGraphicsPolygonItem.ItemIsSelectable, True)

        if not do_transform:
            self.converted_to_pdf_space = True # data is already given as PDF coordinates

     
    def _get_qt_points(self) -> List[QPointF]:
        """Return the points of the polygon as a list of `QPointF`. This method is required by `SelectableRegionItem`."""
        
        return self.polygon()
    

    def transform_selected_region(self, pdf_zoom : float) -> None:
        """Transform the polygon points from PDF coordinates (i.e., retrieved with `_get_scene_points`) to scene coordinates using the `pdf_zoom` factor.
        This method is required by `SelectableRegionItem`."""
        
        scene_points = self._get_scene_points(pdf_zoom)
        new_poly = QPolygonF([QPointF(x, y) for x, y in scene_points])
        self.setPolygon(new_poly)

   
    def copy(self, data: SelectionData = None) -> Self: #SelectableRegionItem
        """Return a copy of this item, with the same polygon and a deep copy of `data`. This method is required by `SelectableRegionItem`."""
        
        c = SelectablePolyItem(self.main_view, self.polygon(), do_transform=False)
        if data is None:
            data = self.data
        c.data = copy.deepcopy(data)
        return c

    
    def set_poly_from_rect(self, rect: Union[List[List[float]], QGraphicsRectItem, QRectF]) -> None:
        """Set the polygon of this item from a rectangle `rect` based on `rect_to_polygon`."""
        
        points = SelectableRegionItem.rect_to_polygon(rect)
        new_poly = QPolygonF([QPointF(x, y) for x, y in points])
        self.setPolygon(new_poly)
        
    
    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget]=None):
        """Render the polygon, and if selected, draw a custom highlight overlay."""
        
        super().paint(painter, option, widget)
        if self.isSelected():
            # draw a custom highlight overlay
            pen = QPen(Qt.black, 4, Qt.DashDotLine)
            painter.setPen(pen)
            painter.drawPolygon(self.polygon())

    def __str__(self) -> str:
        return SelectableRegionItem.__str__(self)
    
    def __repr__(self):
        return self.__str__()