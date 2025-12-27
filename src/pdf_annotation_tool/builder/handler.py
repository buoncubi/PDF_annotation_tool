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
import abc
import base64
from io import BytesIO
import fitz  # PyMuPDF
from PIL import Image, ImageDraw, ImageFile
from typing import List, Tuple, TYPE_CHECKING

from PyQt5.QtWidgets import QMessageBox

from shapely import Polygon

from pdf_annotation_tool.builder.dialog import SelectionDialog
from pdf_annotation_tool.manipulation.trees import BaseSelectionTree
from pdf_annotation_tool.selection.data import SelectionData, SelectionCategory
from pdf_annotation_tool.selection.graphic import SelectableRegionItem
if TYPE_CHECKING:
    from pdf_annotation_tool.tool import PDFAnnotationTool


# Base class to extrapolate information from a selected region of a PDF page.
class BaseSelectionHandler:
    """
    Base class to handle selection building for different shapes. 
    It is in charge of the main processing flow, i.e., running the `SelectionDialog` 
    to get user input and extract image and text from the PDF page.
    It provides a `SelectionData` instance or `None` if the selection is not valid 
    or the user cancelled the dialog.
    """
    
    # Constants for selection modes
    SELECT_POLY = "Polynomial" 
    SELECT_RECT = "Rectangular"
    
      
    def __init__(self, main_view: 'PDFAnnotationTool', MAX_SIZE=512):
        self.main_view = main_view # Reference to `MainWindow` instance
        self.MAX_SIZE = MAX_SIZE # Maximum size of the screenshot in pixels
        self.last_title_id = None # Keep track of the last title selected to preselect it in the next selection dialog


    def process_selection(self, selection: SelectableRegionItem) -> SelectionData: 
        """Main processing flow shared by all selection categories. It runs the `SelectionDialog` to get user input and extract image and text from the PDF page.
        It returns a `SelectionData` instance or `None` if the selection is not valid or the user cancelled the dialog. 
        It is called by `SelectableGraphicsView`, and uses `SelectionDialog`."""
        
        # Get the coordinates of the selection in PDF space
        coords = selection.get_pdf_points()
        
        # Avoid create a region even if the user just clicked once
        if BaseSelectionHandler._is_region_small(coords):
            return None
        
        # Ask the user to input selection metadata such as category, id, parent, and image resolution.
        dlg = SelectionDialog(self.main_view, self.last_title_id, initial_selection=self.main_view.selection_to_redraw) #, parent=, default_img_resolution=) 
        if dlg.exec_():
            user_spec = dlg.get_results() # get user specification as SelectionUserSpecific`
            
            # Get the current page number and page object
            page_num = self.main_view.get_page_num()
            page = self.main_view.get_doc_page()
                        
            # take a screenshot of the PDF page based on the selected area and resize it.
            try:
                img = self.extract_image(page, coords)
                img_str = BaseSelectionHandler.resize_image(img, user_spec.image_resolution)
            except Exception:
                traceback.print_exc()
                QMessageBox.warning(self, "Error", "Error taking selection, no data stored.")
                return None
            
            # Copy-paste the available text
            text = self.extract_text(page, coords)
                
            # Take track of previous titles and containers selection to preselect the node for the next selection
            if user_spec.category == SelectionCategory.TITLE or user_spec.category == SelectionCategory.CONTAINER:
                self.last_title_id = user_spec.id_
            elif user_spec.parent_id == BaseSelectionTree.ROOT_ID:
                self.last_title_id = None
            
            # Initialize selection data  
            out_data = SelectionData(
                id_ = user_spec.id_,
                doc = self.main_view.pdf_path,
                page = page_num,
                coords = coords,
                text = text.strip(),
                category = user_spec.category,
                image = img_str,
                parent = user_spec.parent_id,
                children = [],
            )
            
            # Compute the index based on the current selections
            stored_selection = self.main_view._selections.get(page_num)
            if stored_selection:
                idx = len(stored_selection)
            else:
                idx = 0
            out_data.idx = idx
                        
            # Return a new selection to add
            return out_data


    @abc.abstractmethod
    def extract_image(self, page: fitz.Page, coords: List[Tuple[float, float]]) -> ImageFile:
        """Return PIL image extracted from the selection shape, i.e., based on `coords`.
        The `page` is a PyMuPDF page object. It must be implemented in subclasses."""
        
        raise NotImplementedError


    @abc.abstractmethod
    def extract_text(self, page: fitz.Page, coords: List[Tuple[float, float]]) -> str:
        """Return extracted text for the `coords` in the given `page`. The `page` is a PyMuPDF page object. 
        It must be implemented in subclasses."""
        
        raise NotImplementedError


    @staticmethod
    def _is_region_small(points: List[Tuple[float, float]], threshold: float=2) -> bool:
        """Check if the selected region is too small to be considered, i.e., if the region area compute in a list of `points` (i.e., `[[x0,y0],[x1,y1],...]`) is below a given `threshold`."""
        
        poly = Polygon(points)
        return poly.area < threshold


    @staticmethod
    def resize_image(img: ImageFile, image_resolution: Tuple[int, int]) -> str:
       
        """Resize the image `img` to `image_resolution` (`(width, height)`) if it is bigger than the resolution itself. It maintain aspect ratio, and return the image as a base64-encoded PNG string."""
        # Resize the screenshot maintaining aspect ratio (does noting if size is less than `image_resolution`)
        img.thumbnail(image_resolution) # i.e., `(self.MAX_SIZE, self.MAX_SIZE)`
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        return img_str



class PolySelectionHandler(BaseSelectionHandler):
    """Specialization of `BaseSelectionHandler` for polynomial-based selections."""
    
    def extract_image(self, page: fitz.Page, coords: List[Tuple[float, float]]) -> ImageFile:
        """Extract image based on polygonal selection. This method is required by `BaseSelectionHandler` and based on `extract_poly_image`."""
        
        return PolySelectionHandler.extract_poly_image(page, coords)


    @staticmethod
    def extract_poly_image(page: fitz.Page, points: List[Tuple[float, float]]) -> ImageFile:  # Takes a screenshot based on the polygon in the PDF space with a zoom of 1:1
        """Take a screenshot of the `page` based on the polygon defined by `points` (i.e., `[[x0,y0],[x1,y1],...]`) in PDF space with a zoom factor of `1:1`.
        It returns a PIL image with transparent background outside the polygon."""
        
        # Retrieve bounding box of the polygon
        min_x = min(x for x, _ in points)
        max_x = max(x for x, _ in points)
        min_y = min(y for _, y in points)
        max_y = max(y for _, y in points)
        bbox = fitz.Rect(min_x, min_y, max_x, max_y)

        # Take screenshot of the bounding box
        pix = page.get_pixmap(matrix=fitz.Matrix(1, 1), clip=bbox)
        if pix.w <= 0 or pix.h <= 0:
            print(f"Skipping invalid page {page.number}")
            return None
        img = Image.open(BytesIO(pix.tobytes("png"))).convert("RGBA")

        # Mask polygon and set background outside polygon to transparent
        mask = Image.new("L", img.size, 0)
        draw = ImageDraw.Draw(mask)
        shifted_points = [(x - min_x, y - min_y) for x, y in points]
        draw.polygon(shifted_points, fill=255)
        img.putalpha(mask)

        return img


    def extract_text(self, page: fitz.Page, coords: List[Tuple[float, float]]) -> str:
        """Extract text based on polygonal selection. This method is required by `BaseSelectionHandler` and based on `extract_poly_text`."""
        return PolySelectionHandler.extract_poly_text(page, coords, space_threshold=2.0)


    @staticmethod
    def extract_poly_text(page: fitz.Page, coords: List[Tuple[float, float]], space_threshold: float =2.0) -> str:
        """
        Extract text from characters inside the polygon, inserting spaces if horizontal gaps are large.
         - space_threshold: factor of average character width or an absolute gap in points.
         - coords: list of (x, y) tuples defining the polygon in PDF coordinates.
         - page: PyMuPDF page object.
        Returns the extracted text as a string.
        """
        
        # Get the raw text dictionary from the page
        rawdict = page.get_text("rawdict")
        text_lines = []

        for block in rawdict["blocks"]:
            if "lines" not in block:
                # Skip non-text blocks
                continue

            # Process each line in the text block
            for line in block["lines"]:
                line_chars = []
                prev_x2 = None  # right edge of previous char
                prev_width = None

                for span in line["spans"]:
                    for ch in span["chars"]:
                        # Character center point
                        cx = (ch["bbox"][0] + ch["bbox"][2]) / 2
                        cy = (ch["bbox"][1] + ch["bbox"][3]) / 2

                        # Check if the character center is inside the polygon
                        if PolySelectionHandler.point_in_polygon(cx, cy, coords):
                            x0, _, x1, _ = ch["bbox"]
                            char_width = x1 - x0

                            # Insert space if there's a significant gap from the previous character
                            if prev_x2 is not None:
                                gap = x0 - prev_x2
                                
                                # Decide if gap is big enough to count as a space
                                if gap > (space_threshold * (prev_width or char_width)): # if gap > 5:  # 5 points in PDF coordinates
                                    line_chars.append(" ")

                            # Append the character
                            line_chars.append(ch["c"])
                            prev_x2 = x1
                            prev_width = char_width

                text_lines.append("".join(line_chars))

        return "\n".join(l.strip() for l in text_lines if l.strip())


    @staticmethod
    def point_in_polygon(x: float, y: float, polygon: List[Tuple[float, float]]) -> bool:
        """Ray casting algorithm for point-in-polygon check. Returns True if the point (x, y) is inside the `polygon`, which is a list of points `[[x0,y0], [x1,y1], ...]`."""
        
        inside = False
        n = len(polygon)
        px, py = x, y
        for i in range(n):
            # Get the current and next vertex
            x1, y1 = polygon[i]
            x2, y2 = polygon[(i + 1) % n]
            # Check if the ray intersects the edge
            if ((y1 > py) != (y2 > py)) and (px < (x2 - x1) * (py - y1) / (y2 - y1 + 1e-12) + x1):
                inside = not inside
        return inside
