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

from typing import TYPE_CHECKING

from PyQt5.QtWidgets import QGraphicsView, QGraphicsRectItem, QGraphicsLineItem, QGraphicsPolygonItem, QMessageBox
from PyQt5.QtGui import QPen, QColor, QPolygonF, QMouseEvent, QKeyEvent
from PyQt5.QtCore import Qt, QRectF, QPointF

from pdf_annotation_tool.builder.handler import BaseSelectionHandler, PolySelectionHandler
from pdf_annotation_tool.selection.graphic import SelectablePolyItem
from pdf_annotation_tool.selection.data import SelectionData

if TYPE_CHECKING:
    from pdf_annotation_tool.tool import PDFAnnotationTool


# The custom view where PDF pages are shown, it uses `SelectablePolygonItem` and `PolySelectionHandler`; and it is used by `PDFAnnotationTool`.
# It invokes `add_selection` in the main view and actually stores selection data into a dictionary.
class SelectableGraphicsView(QGraphicsView):
    """A custom QGraphicsView to handle selection of rectangular and polygonal regions on a PDF page. In particular, rectangles are generalized as polygons,
    and their data is represented as `SelectablePolyItem` (which encode `SelectionData`) by `PolySelectionHandler` (which extract the data).
    It is used by `PDFAnnotationTool` to manage user selections into a dictionary by the means of `SelectionManager`, and invoke the `SelectionDialog`
    to make user input specifications. This class manages mouse events to allow drawing and editing shapes on the PDF page.    
    Rectangular selections are drawn by clicking and dragging the mouse, while polygonal selections are created by clicking to add points and double-clicking to close the polygon.
    """
    
    
    def __init__(self, main_view: 'PDFAnnotationTool'):
        
        # Initialize the QGraphicsView with the scene from the main view
        super().__init__(main_view.scene)
        
        # Class properties
        self.main_view = main_view
        self._last_selected_index = -1 # Store cycling array to manipulate focus and select polygon that are not on foreground
        self.poly_selection_handler = PolySelectionHandler(main_view)  # Initialize the class that extracts data from polygonal selections        
        self.main_view.mode_selector.currentIndexChanged.connect(self._on_drawing_shape_changed) # Trigger function when user changes drawing shape form rectangular to polygonal  (TODO Use QSignalConnect selection mode change signal instead of accessing main_view directly)
        self.selected_shape = self.main_view.mode_selector.itemData(0) # Initialize the selected shape based on the first item in the mode selector (i.e., rectangular)
        
        # Initialize selection graphics items and state variables
        self.init()


    def init(self) -> None:
        """Initialize the selection graphics items and state variables. This method is called by `PDFAnnotationTool` when a new PDF page is loaded, such to clear the scene and allow for a new selection."""
        
        # Rectangle selection
        self.selection_rect = QGraphicsRectItem()
        self.selection_rect.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
        self.selection_rect.setBrush(QColor(255, 0, 0, 50))
        self.selection_rect.setZValue(1)
        self.scene().addItem(self.selection_rect)
        self.selection_rect.hide()

        # Polygon selection
        self.selection_poly = SelectablePolyItem(self.main_view)
        self.selection_poly.setPen(QPen(QColor(255, 0, 0), 2, Qt.SolidLine))
        self.selection_poly.setBrush(QColor(255, 0, 0, 50))
        self.selection_poly.setZValue(1)
        self.scene().addItem(self.selection_poly)
        self.selection_poly.hide()

        # Temporary preview line to show the edge from the last polygon point to the current mouse position
        self.temp_line = QGraphicsLineItem()
        self.temp_line.setPen(QPen(QColor(255, 255, 0), 2, Qt.DashLine))
        self.temp_line.setZValue(2)
        self.scene().addItem(self.temp_line)
        self.temp_line.hide()

        # State restored at each new selection
        self.origin = QPointF() # Starting point for rectangle selection
        self.is_selecting = False # Flag to indicate if a rectangle selection is in progress
        self.polygon_points = [] # List of points for polygon selection
        self.polygon_selecting = False # Flag to indicate if a polygon selection is in progress
        
        
    def _on_drawing_shape_changed(self, index: int) -> None:
        """Get the selected drawing shape from the mode selector in `PDFAnnotationTool`. It can either be rectangular or polygonal."""
        
        self.selected_shape = self.main_view.mode_selector.itemData(index)
        
        
    def make_points_within_page(self, pose: QPointF) -> QPointF:
        """Ensure that the point selected with the mouse is within the bounds of the current PDF page. If the point is outside the page, the returned point is clamped to the nearest edge."""
        
        # Map the mouse position to scene coordinates
        point = self.mapToScene(pose)
        pixmap = self.main_view.get_doc_page().get_pixmap()
        
        # Get the maximum x and y coordinates based on the pixmap size and zoom level
        img_max_x = pixmap.width * self.main_view.pdf_zoom
        img_max_y = pixmap.height * self.main_view.pdf_zoom
        
        # Clamp the point coordinates to be within the image bounds
        if point.x() < 0:
            point.setX(0)
        elif point.x() > img_max_x:
            point.setX(img_max_x)
            
        if point.y() < 0:
            point.setY(0)
        elif point.y() > img_max_y:
            point.setY(img_max_y)
        
        # Return clamped point
        return point
        
    
    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press events to start drawing a rectangle or adding points to a polygon."""
        
        # Start rectangle selection
        if self.selected_shape == BaseSelectionHandler.SELECT_RECT:
            if event.button() == Qt.LeftButton:
                self.origin = self.make_points_within_page(event.pos())
                self.selection_rect.setRect(QRectF(self.origin, self.origin))
                self.selection_rect.show()
                self.is_selecting = True

        # Start polygon selection
        elif self.selected_shape == BaseSelectionHandler.SELECT_POLY:
            if event.button() == Qt.LeftButton:
                point = self.make_points_within_page(event.pos())
                self.polygon_points.append(point)
                poly = QPolygonF(self.polygon_points)
                self.selection_poly.setPolygon(poly)
                self.selection_poly.show()
                self.polygon_selecting = True
                self.temp_line.show()

        super().mousePressEvent(event)


    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move events to update the rectangle or polygon preview while drawing."""
        
        # Update rectangle selection
        if self.is_selecting and self.selected_shape == BaseSelectionHandler.SELECT_RECT:
            current_pos = self.make_points_within_page(event.pos())
            rect = QRectF(self.origin, current_pos).normalized()
            self.selection_rect.setRect(rect)

        # Update polygon selection preview line
        elif self.selected_shape == BaseSelectionHandler.SELECT_POLY and self.polygon_selecting and self.polygon_points:
            current_pos = self.make_points_within_page(event.pos())
            self.temp_line.setLine(
                self.polygon_points[-1].x(),
                self.polygon_points[-1].y(),
                current_pos.x(),
                current_pos.y()
            )

        super().mouseMoveEvent(event)


    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """Handle mouse double-click events to finalize a polygon selection or cycle through overlapping polygon selections in order to highlight them."""
        
        # Finalize polygon selection
        if self.selected_shape == BaseSelectionHandler.SELECT_POLY and self.polygon_selecting and self.selection_poly.polygon().size() > 2: # Polygon show have at least three vertex
            self.polygon_selecting = False
            self.temp_line.hide()
            selected_data = self.poly_selection_handler.process_selection(self.selection_poly) 
            if selected_data is None: 
                self.reject_poly() # Invalid polygon selection
            else:
                self._redraw_or_add(selected_data) # Valid polygon selection
        else:
            # Cycle through overlapping polygon selections to highlight them through double-clicking when needed
            self._circular_selection(event)
            
        super().mouseDoubleClickEvent(event)


    def _circular_selection(self, event: QMouseEvent) -> None: # TODO improve user interaction
        """Cycle through overlapping polygon selections to highlight them. This is done by double-clicking on the overlapping area."""
        
        # Map the mouse position to scene coordinates
        pos = self.mapToScene(event.pos())

        # Get all QGraphicsPolygonItems under the mouse (top-most first)
        items = [i for i in self.scene().items(pos) if isinstance(i, QGraphicsPolygonItem)]
        if not items:
            return

        # Get the last selected index, or -1 if undefined
        last_index = self._last_selected_index

        # Circular increment
        index = (last_index + 1) % len(items)

        # Deselect only the previously selected item if valid
        if 0 <= last_index < len(items):
            items[last_index].setSelected(False)
            items[last_index].update()

        # Select the current item
        items[index].setSelected(True)

        # Bring it to the front so highlight is visible
        z_top = max([i.zValue() for i in self.scene().items()]) + 1
        items[index].setZValue(z_top)

        # Update the item to reflect selection changes
        items[index].update()
        
        # Store index for next double-click
        self._last_selected_index = index

        #print(f"Double-click at {pos}, selected item #{index+1} `{items[index].data.id_}` of {len(items)}")
        

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release events to finalize a rectangle selection."""
        
        if event.button() == Qt.LeftButton and self.is_selecting and self.selected_shape == BaseSelectionHandler.SELECT_RECT:
            self.is_selecting = False
            
            self.selection_poly.set_poly_from_rect(self.selection_rect)
            
            selected_data = self.poly_selection_handler.process_selection(self.selection_poly) 
            if selected_data is None:
                self.reject_rectangle()
            else:
                self.selection_poly.show()
                self._redraw_or_add(selected_data)

        super().mouseReleaseEvent(event)


    def _redraw_or_add(self, selected_data: SelectionData) -> None:
        """Redraw an existing selection or add a new one based on the processed `selected_data`.
        It is based on whether `main_view.selection_to_redraw` is set or not (which is set by `SelectableRegionItem` from its context menu)."""
        
        self.selection_poly.data = selected_data
        if self.main_view.selection_to_redraw is not None:
            # Redraw (i.e., replace) a selection as requested by the user (from the context menu of `SelectableRegionItem`)
            sel_to_update = self.main_view.selection_to_redraw
            self.main_view.selection_to_redraw = None # Reset the variable for future selections
            
            # Ensure that the replacement occurs in the same page
            if self.selection_poly.data.page != sel_to_update.data.page:
                QMessageBox.warning(self, "Warning", "Replace should occur in the same page where the selection was defined.")
                if self.selected_shape == BaseSelectionHandler.SELECT_RECT:
                    self.reject_rectangle()
                else:
                    self.reject_poly()
                return            
            
            # Keep the same id, description and idx of the selection being replaced
            self.selection_poly.data.id_ = sel_to_update.data.id_
            self.selection_poly.data.description = sel_to_update.data.description 
            self.selection_poly.data.idx = sel_to_update.data.idx
            
            # Replace the selection in the main view (with undu/redo support)
            self.main_view.replace_selection(self.selection_poly)
        else:
            # Add a new selection in the main view (with undu/redo support)
            self.main_view.add_selection(self.selection_poly)


    def reject_poly(self) -> None:
        """Reject the current polygon selection, clearing the points and hiding the polygon item."""
        
        self.selection_poly.setPolygon(QPolygonF())
        self.selection_poly.hide()
        
        
    def reject_rectangle(self) -> None:
        """Reject the current rectangle selection, clearing the rectangle and hiding the rectangle item."""
        
        self.selection_rect.setRect(QRectF())
        self.polygon_points.clear()
        self.selection_rect.hide()


    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle key press events to cancel ongoing selections with the Escape key."""
        
        if event.key() == Qt.Key_Escape:
            # Cancel rectangle selection
            if self.is_selecting and self.selected_shape == BaseSelectionHandler.SELECT_RECT:
                self.is_selecting = False
                if self.selection_rect:
                    self.selection_rect.hide()
                    self.selection_rect.setRect(QRectF())

            # Cancel polygon selection
            if self.selected_shape == BaseSelectionHandler.SELECT_POLY and self.polygon_selecting:
                self.polygon_selecting = False
                self.polygon_points.clear()
                self.selection_poly.hide()
                if self.temp_line:
                    self.temp_line.hide()
                    self.temp_line.setLine(0, 0, 0, 0)

            return  # stop event propagation
        
        super().keyPressEvent(event)
