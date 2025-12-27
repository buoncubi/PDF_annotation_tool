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
import os
import fitz
import requests
import traceback

from typing import Optional, List, Dict

from PyQt5.QtWidgets import (
    QMainWindow, QGraphicsScene, QComboBox, QLabel, QPushButton, 
    QLineEdit, QVBoxLayout, QHBoxLayout, QWidget, QSplitter, QSlider, 
    QGridLayout, QSizePolicy, QMessageBox, QUndoStack, QGraphicsTextItem,
    QUndoStack
)
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPixmap, QImage, QPen, QPolygonF,  QColor, QFont, QCloseEvent

from pdf_annotation_tool.builder.handler import BaseSelectionHandler
from pdf_annotation_tool.builder.selector import SelectableGraphicsView
from pdf_annotation_tool.manipulation.augmenting import AugmentConfigDialog
from pdf_annotation_tool.manipulation.importer import UnstructuredDialog, UnstructuredImporter
from pdf_annotation_tool.manipulation.visualizer import TreesPanel
from pdf_annotation_tool.selection.data import SelectionCategory, SelectionData
from pdf_annotation_tool.selection.graphic import SelectablePolyItem, SelectableRegionItem
from pdf_annotation_tool.selection.manager import EditingData, SelectionsManager
from pdf_annotation_tool.utils.files import FileDialog, OpeningData, PDFOpenDialog
from pdf_annotation_tool.utils.image import ImageWindow


class PDFAnnotationTool(QMainWindow): # The mai GUI view.
    """
    Main GUI application for PDF annotation and selection management.
    
    Provides a complete interface for opening PDFs, creating selections, managing annotations,
    and exporting data. Features include zoom control, page navigation, selection tools,
    undo/redo functionality, and integration with external services like Unstructured.io.
    """
    
    DOWNLOAD_FOLDER = "download" # Default folder name for downloaded PDFs
    
    def __init__(self):
        """
        Initialize the PDF annotation tool with all UI components and data structures.
        
        Sets up the main window, undo stack, selection manager, graphics view,
        control panels, and connects all signal handlers.
        """
        
        print("-----------------------------------------------------------------------------------")
        super().__init__()
        
        # Undo stack
        self.undo_stack = QUndoStack(self)
        self.undo_stack.indexChanged.connect(self._on_undo_stack_changed)
         
        # Define class properties (all should be private)
        self._doc = None # Do not access it, use `get_doc_page` instead.
        self._page_idx = 0 # Is the index in `allowed_pages` that represent the current open page.
        self._allowed_pages = [] # Is a sorted list of page numbers starting from 1 with no repetitions.
        self._selections = SelectionsManager(self.undo_stack) #OrderedDict()#{} # A map of `page_number: [selection_item]`, where the list of selection item contains `SelectablePolygonItem`. Do not modify it, use `add_selection` and `remove_selection` instead.
        
        # Open data, used from `self.load`, and get by `PDFOpenDialog` as a `OpeningData` object.
        self.pdf_path = None # The file path, if opened from file, or the web url, if opened from url
        self.output_json_path = None
        self.working_dir = None
        self.export_images_path = None
        self.should_autosave = False
        self.pdf_zoom = 1
        self.pdf_to_scene_transform = None
        self.selection_to_redraw = None # used by `SelectableRegionItem` and `BaseSelectionHandler` to allow redrawing a selection
        self.set_pdf_to_scene_transformation_matrix() # It sets `self.pdf_to_scene_transform`
       
               
        self.init_graphic()
     
        
    def init_graphic(self) -> None:
        """
        Initialize all GUI components and layout.
        
        Creates the main window layout with PDF viewer, control panels, trees panel,
        zoom controls, selection legend, and menu bar with undo/redo actions.
        """
        
        self.setWindowTitle('PDF Annotation Tool')
        self.resize(1000, 800)

        self.scene = QGraphicsScene(self)
        self.mode_selector = QComboBox()
        self.mode_selector.addItem("Rectangle", BaseSelectionHandler.SELECT_RECT)
        self.mode_selector.addItem("Polygon (double click to close selection)", BaseSelectionHandler.SELECT_POLY)
        self.view = SelectableGraphicsView(self)
        self.view.setMouseTracking(True)

        self.page_label = QLabel("Page: --")

        self.btn_open = QPushButton("New")
        self.btn_unstructured = QPushButton("Unstructured.io")
        self.btn_prev = QPushButton("Previous")
        self.btn_next = QPushButton("Next")
        self.goto_label = QLabel("Go to Page:")
        self.btn_go = QPushButton("Go")
        self.page_input = QLineEdit()
        self.range_input = QLineEdit()
        self.btn_set_range = QPushButton("Set Pages")
        self.btn_open_json = QPushButton("Open JSON")
        self.btn_save_json = QPushButton("Save JSON")
        self.btn_augment = QPushButton("Augment")

        self.btn_open.clicked.connect(self.open)
        self.btn_unstructured.clicked.connect(self.import_from_unstructured)
        self.btn_prev.clicked.connect(self.prev_page)
        self.btn_next.clicked.connect(self.next_page)
        self.btn_go.clicked.connect(self.goto_page)
        self.btn_set_range.clicked.connect(self.set_page_range)
        self.btn_open_json.clicked.connect(self.import_json)
        self.btn_save_json.clicked.connect(lambda: self.save_json(show_dialog=True))
        self.btn_augment.clicked.connect(self.augment)
        self.range_input.returnPressed.connect(self.set_page_range)
        #self.range_input.setMaximumWidth(100)
        self.page_input.returnPressed.connect(self.goto_page)
        #self.page_input.setFixedWidth(50) 

        # Left panel layout (PDF controls)
        left_layout = QVBoxLayout()
        control_layout = QHBoxLayout()
        nav_layout = QHBoxLayout()
    
        control_layout.addWidget(self.btn_open)
        control_layout.addWidget(self.btn_unstructured)
        control_layout.addWidget(self.range_input)
        control_layout.addWidget(self.btn_set_range)
        control_layout.addWidget(self.btn_open_json)
        control_layout.addWidget(self.btn_save_json)
        control_layout.addWidget(self.btn_augment)

        nav_layout.addWidget(self.btn_prev)
        nav_layout.addWidget(self.btn_next)
        nav_layout.addWidget(self.goto_label)
        nav_layout.addWidget(self.page_input)
        nav_layout.addWidget(self.btn_go)
        nav_layout.addWidget(self.page_label)
        nav_layout.addWidget(self.mode_selector)
        
        left_layout.addLayout(control_layout)
        left_layout.addLayout(nav_layout)
        
        left_layout.addWidget(self.view)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # Right panel (JSON editor)
        self.trees_panel = TreesPanel(self._selections, self)
        self.trees_panel.page_tree.find_in_pdf.connect(self.find_in_pdf)
        self.trees_panel.hier_tree.find_in_pdf.connect(self.find_in_pdf)

        # Resizable splitter
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_widget)
        splitter.addWidget(self.trees_panel)
        splitter.setSizes([700, 300])  # Initial width proportions

        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)   

        # Zoom controller        
        controls = QHBoxLayout()
        self.zoom_label = QLabel(f"Zoom: {self.pdf_zoom:.2f}x")
        controls.addWidget(self.zoom_label)
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(50)   # 0.50x
        self.zoom_slider.setMaximum(400)  # 4.0x
        self.zoom_slider.setValue(self.pdf_zoom * 100)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        controls.addWidget(self.zoom_slider)
        main_layout.addLayout(controls)
        
        # Selection legend
        legend_wrapper = QVBoxLayout()
        legend_wrapper.setContentsMargins(0, 0, 0, 0)   # no outer margins
        legend_wrapper.setSpacing(2)                     # small spacing between title and grid
        self._legend_title = QLabel(f"Selection Categories (Total Sections Counter: 0)")
        self._legend_title.setStyleSheet("font-weight: bold;")  # optional styling
        self._legend_title.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # don't expand
        self._legend_title.setContentsMargins(0, 0, 0, 0)  # remove extra padding
        legend_wrapper.addWidget(self._legend_title)
        legend_grid_layout = QGridLayout()
        legend_grid_layout.setContentsMargins(0, 0, 0, 0)
        legend_grid_layout.setSpacing(2)
        for i, category in enumerate(SelectionCategory):
            row, col = divmod(i, 12)
            legend_item = self._createLegendItem(category)
            legend_item.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            legend_grid_layout.addWidget(legend_item, row, col)
        legend_wrapper.addLayout(legend_grid_layout)        
        main_layout.addLayout(legend_wrapper)

        # Show all in the main view
        self_widget = QWidget()
        self_widget.setLayout(main_layout)
        self.setCentralWidget(self_widget)
        
        self.trees_panel.page_tree.data_changed.connect(self._on_page_tree_change)
        
        undo_action = self.undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcuts(["Ctrl+Z", "Meta+Z"])

        redo_action = self.undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcuts(["Ctrl+Shift+Z", "Meta+Shift+Z"])

        menubar = self.menuBar().addMenu("Edit")
        menubar.addAction(undo_action)
        menubar.addAction(redo_action)


    def _on_undo_stack_changed(self) -> None:
        """
        Handle undo stack changes by refreshing the page display and trees panel.
        
        Called when undo/redo operations are performed to update the UI state.
        """
         
        self.show_page()
        self.trees_panel.populate_tree(self._selections)


    def _on_page_tree_change(self) -> None:
        """
        Handle changes in the page tree by refreshing the page display.
        
        Called when the `selections` dictionary is changed from `PageTreeWidget` and `HierarchyTreeWidget`
        """
        
        self.show_page()


    def _createLegendItem(self, category: SelectionCategory) -> QWidget:
        """
        Create a legend item widget for a selection category.
        
        Args:
            category (SelectionCategory): The selection category to create legend for
            
        Returns:
            QWidget: Widget containing color indicator and category name
        """
        
        widget = QWidget()
        widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)  # compact widget

        legend_layout = QHBoxLayout(widget)
        legend_layout.setContentsMargins(0, 0, 0, 0)
        legend_layout.setSpacing(2)

        color_label = QLabel()
        color_label.setFixedSize(12, 12)
        color_label.setStyleSheet(
            f"background-color: {category.value.color}; border: 1px solid black;"
        )
        color_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        text_label = QLabel(category.value.name)
        text_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        legend_layout.addWidget(color_label)
        legend_layout.addWidget(text_label)

        return widget


    def on_zoom_changed(self, value: int) -> None:
        """
        Handle zoom slider changes and update PDF display.
        
        Args:
            value (int): New zoom value as percentage (50-400)
        """
        
        self.pdf_zoom = value / 100.0
        self.zoom_label.setText(f"Zoom: {self.pdf_zoom:.2f}x")
        self.set_pdf_to_scene_transformation_matrix()
        self.show_page()


    def get_page_num(self) -> Optional[int]:
        """
        Get the current page number (1-based indexing).
        
        Returns:
            Optional[int]: Current page number starting from 1, or None if invalid
        """

        if self._page_idx < 0 or self._page_idx >= len(self._allowed_pages):
            return None 
        return self._allowed_pages[self._page_idx]


    def get_doc_page(self)-> Optional['fitz.Page']:
        """
        Get the current PDF page object.
        
        Returns:
            Optional[fitz.Page]: Current page object, or None if no document loaded
        """
        
        if self._doc is None:
            return None
        return self._doc[self.get_page_num() - 1]


    def get_in_allowed_pages(self, data: Optional[Dict] = None) -> Dict:
        """
        Filter data to include only allowed pages.
        
        Args:
            data (Optional[Dict]): Data dictionary to filter, uses self._selections if None
            
        Returns:
            Dict: Filtered data containing only allowed pages
        """
        
        if data is None:
            data = self._selections
        return {k: v for k, v in data.items() if int(k) in self._allowed_pages}
        
        
    def open(self) -> None:
        """
        Open PDF project dialog and load selected configuration.
        
        Shows PDFOpenDialog to get user input and calls load() with the results.
        """
        
        dialog = PDFOpenDialog()
        if dialog.exec_():
            input_setup = dialog.get_results()
            self.load(input_setup)
        
        
    def load(self, input_setup: OpeningData) -> None:
        """
        Load PDF project with given configuration.
        
        Args:
            input_setup (OpeningData): Project configuration including paths and settings
        """
        
        
        def download_pdf(url, working_dir: str) -> str:
            """
            Download a PDF from an URL and save it into the `working_dir`.
            It returns the file path where the PDF has been saved.
            """
            
            response = requests.get(url)
            download_path = f"{working_dir}/{PDFAnnotationTool.DOWNLOAD_FOLDER}/"  
            os.makedirs(download_path, exist_ok=True)
            download_path = f"{download_path}{input_setup.get_input_pdf_name()}"
            with open(download_path, "wb") as f:
                f.write(response.content)
            return download_path
        
        
        # Set up working directory
        self.working_dir = input_setup.get_working_directory() # i.e., `working_directory/project_name/`
        try:
            os.makedirs(self.working_dir)
        except FileExistsError:
            reply = QMessageBox.warning(
                self,
                "Overwrite Folder?",
                f"The folder '{self.working_dir}' already exists.\nDo you want to work in it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return  # cancel overwrite
        print(f"Set working directory: `{self.working_dir}`.")
        
        # Set up input file or url
        self.pdf_path = input_setup.input_pdf_path
        if input_setup.is_input_from_file(): 
            self.load_pdf(self.pdf_path)
            print(f"PDF loading from file: `{self.pdf_path}`.")
        else:
            downloaded_pdf_path = download_pdf(input_setup.input_pdf_path, self.working_dir)
            self.load_pdf(downloaded_pdf_path)
            print(f"Loading PDF URL: `{self.pdf_path}` (downloaded in: `{downloaded_pdf_path}`).")
    
        # Set up optional input json 
        self.input_json_path = input_setup.input_json_path
        if self.input_json_path is not None and self.input_json_path != "":
            self.load_json()
                
        # Set up output json to generate
        self.output_json_path = input_setup.get_output_json_path()
        print(f"Writing output to `{self.output_json_path}`.")
        
        # Store configurations
        images_path = input_setup.get_export_images_path()
        if images_path is not None:
            self.export_images_path = images_path
            print(f"Storing images in: `{self.export_images_path}`.")
        else:
            print("Not storing images")
            
        self.should_autosave = input_setup.should_auto_save
        if self.should_autosave:
            print("Autosaves JSON on page changing enabled.")
        else:
            print("It does not autosave")
        
        print("-----------------------------------------------------------------------------------")
    
    
    def load_pdf(self, path: str) -> None:
        """
        Load PDF document from file path.
        
        Args:
            path (str): Path to PDF file to load
        """
        
        self._doc = fitz.open(path)
        self._page_idx = 0
        self._allowed_pages = range(1, len(self._doc) + 1) # starts from 1
        
        # Clear GUI and lose data if a project was already opened (TODO add not saved alert)
        self._selections.clear() # Delete all selections
        self.trees_panel.populate_tree(self._selections)
        self.show_page()
    
    
    def load_json(self) -> Optional[Dict]:
        """
        Load selections from JSON file.
        
        Returns:
            Optional[Dict]: Loaded JSON data, or None if loading failed
        """
        
        file_path = self.input_json_path
        if not os.path.isfile(file_path):
            self.show_alert(f"File not found: {file_path}")
            return None
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                filtered_data = self.get_in_allowed_pages(data)
                self.add_selections_from_dict(filtered_data)
            else:
                self.show_alert("File content is not a dictionary.")
                return None        
        except json.JSONDecodeError as e:
            self.show_alert(f"Error decoding JSON: {e}")
            traceback.print_exc()
            return None
        except Exception as e:
            self.show_alert(f"Unexpected error: {e}")
            traceback.print_exc()
            return None


    @staticmethod
    def show_alert(message: str, title: str = "Error", level: QMessageBox.Warning = None) -> None:
        """
        Show alert dialog with message.
        
        Args:
            message (str): Alert message to display
            title (str): Dialog title
            level (QMessageBox.Icon): Alert level/icon type
        """
        
        alert = QMessageBox()
        if level is not None:
            alert.setIcon(level)
        alert.setWindowTitle(title)
        alert.setText(message)
        alert.setStandardButtons(QMessageBox.Ok)
        alert.exec_()


    def set_page_range(self) -> None:
        """
        Set the range of pages to display based on user input.
        
        Parses range_input text and updates _allowed_pages list.
        """
        
        text = self.range_input.text().strip()
        pages = self.parse_page_range(text)
        if pages is None:
            return
        self._allowed_pages = list(pages)
        self.show_page()
        self.trees_panel.populate_tree(self._selections)
    
    
    def parse_page_range(self, text: str) -> Optional[List[int]]:
        """
        Parse page range string into list of page numbers.
        
        Args:
            text (str): Range string like "1,3,5-7" or empty for all pages
            
        Returns:
            Optional[List[int]]: List of page numbers, or None if invalid
        """
        
        if not self._doc:
            self.show_alert(f"Open a PDF document before to set the page to show.")
            return None
        
        if text == "":
            return range(1, len(self._doc) + 1) # starts from 1
        
        try:
            pages = set()
            for part in text.split(','):
                if '-' in part:
                    a, b = map(int, part.split('-'))
                    if b < a:
                        self.show_alert(f"Data not valid, rage should be \'a-b\', where 'a < b' (but '{a} > {b}').\nPlease enter valid pages numbers, e.g., \"1, 4, 10-15\".")
                    pages.update(range(a, b+1))
                else:
                    pages.add(int(part))
            
            for page in pages:        
                if not 0 <= page < len(self._doc):
                    self.show_alert(f"Page {page + 1} is not within the document, which has {len(self._doc)} pages.")   
                    return None  
                    
            pages = sorted(pages)
            return pages
        except Exception:
            traceback.print_exc()
            self.show_alert(f"Data \'{text}\' not valid.\nPlease enter valid pages number, e.g., \"1, 4, 10-15\".")
            return None


    # TODO move it into SelectionManager
    def add_selections_from_dict(self, data: Dict) -> None:
        """
        Add selections to the `SelectionManager` from dictionary data.
        
        Args:
            data (Dict): Dictionary containing selection data by page
        """
             
        to_import = []      
        for page_number, selection_list in data.items():
            for selection in selection_list:
                page_number = int(page_number)
                
                # Do not duplicate selections if they have the same ID (e.g., multiple opens)
                sel_id = selection[SelectionData.JSON_KEY_ID]
                if page_number in self._selections.keys():
                    duplication = False
                    for s in self._selections.get(page_number, []):
                        if s.data.id_ == sel_id:
                            duplication = True
                            break
                    if duplication:
                        continue
                        
                # Populate data from JSON 
                sel_points = selection[SelectionData.JSON_KEY_COORDS]
                region = QPolygonF([QPointF(x, y) for x, y in sel_points])
                # Given points are already in the PDF coordinate system, so do not perform any other transformation
                selection_item = SelectablePolyItem(self, region, do_transform=False) 
                selection_item.data = SelectionData.from_dict(selection)
                to_import.append(selection_item)
                
        #self.add_selection(selection_item, update_graphic=False)# page_number, update_graphic=False)
        self._selections.add_selection_set(to_import)
        self.update_graphic()


    # TODO move it into SelectionManager
    def find_selection(self, sel_id: str) -> Optional[SelectionData]:
        """
        Find selection by ID across all pages.
        
        Args:
            sel_id (str): Selection ID to search for
            
        Returns:
            Optional[SelectionData]: Found selection data, or None if not found
        """
        
        for page_items in self._selections.values():
            for sel in page_items:
                if sel.data.id_ == sel_id:
                    return sel.data
        return None


    # TODO move it into SelectionManager
    def _reindex_titles_tree_children_from_sections(self) -> None: # TODO it is always necessary (when used?)
        """
        Rebuild parent-child relationships in selection hierarchy.
        
        Clears existing children lists and rebuilds them from parent references.
        """

        # Clear children lists
        for page_items in self._selections.values():
            for sel in page_items:
                sel.data.children.clear()
                
        # Rebuild from section references
        for page_items in self._selections.values():
            for sel in page_items:
                node = sel.data
                if node.parent:
                    parent = self.find_selection(node.parent)
                    if parent and node.id_ not in parent.children:
                        parent.children.append(node.id_)
      
      
    # TODO move it into SelectionManager  
    def get_selection_by_id(self, id: str) -> Optional[SelectableRegionItem]:
        """
        Find selection item by ID across all pages.
        
        Args:
            id (str): Selection ID to search for
            
        Returns:
            Optional[SelectableRegionItem]: Found selection item, or None if not found
        """
        
        for selections_list in self._selections.values():
            for selection in selections_list:
                if selection.data.id_ == id:
                    return selection
        return None
      
      
    # If page_num is note it adds to the current page number, otherwise it considers the given page number
    def add_selection(self, selection: SelectableRegionItem, update_graphic=True) -> None: 
        """
        Add new selection to the manager.
        
        Args:
            selection (SelectableRegionItem): Selection to add
            update_graphic (bool): Whether to update the display
        """
        
        if not self._doc:
            return
        
        same_selection = self.get_selection_by_id(selection.data.id_)
        if same_selection is not None: 
            return
        
        self._selections.add_selection(selection)#, page_num)
        
        # Update the Titles tree
        if update_graphic:
            self.update_graphic()


    def remove_selection(self, selection: SelectableRegionItem, update_graphic: bool =True) -> None:
        """
        Remove selection from the manager.

        Args:
            selection (SelectableRegionItem): Selection to remove
            update_graphic (bool): Whether to update the display
        """

        if not self._doc:
            return
        # Manage UNDO and use `ordered_insert` for adding the scene
        self._selections.remove_selection(selection) # `remove_by_id` is more robust with respect to `page` and `index`
        
        if update_graphic:
            self.update_graphic()


    def move_selection(self, selection: SelectableRegionItem,  target_page: Optional[int] = None, target_index: Optional[int] = None, update_graphic: bool = True) -> None: 
        """
        Move selection to different page or index.
        If page keys and indexes are None, the value encoded in the `selection` data is used.
        
        Args:
            selection (SelectableRegionItem): Selection to move
            target_page (Optional[int]): Target page number
            target_index (Optional[int]): Target index within page
            update_graphic (bool): Whether to update the display
        """
        
        source_page = selection.data.page
        source_idx = selection.data.idx     
        self._selections.move_section(source_page, source_idx, target_page, target_index)
        
        # Refresh graphic
        if update_graphic:
            self.update_graphic()


    def edit_selection(self, editing_key: int, editing_idx: int, new_selection: SelectableRegionItem) -> None:
        """
        Edit selection at specified position.
        
        Args:
            editing_key (int): Page number of selection to edit
            editing_idx (int): Index of selection within page
            new_selection (SelectableRegionItem): Replacement selection
        """
        
        self._selections.edit_selection(editing_key, editing_idx, new_selection)


    def move_selection_set(self, editing: List[EditingData]) -> None:
        """
        Move multiple selections based on editing operations.
        
        Args:
            editing (List[EditingData]): List of editing operations to perform
        """
        
        self._selections.move_selection_set(editing)


    def replace_selection(self, new_selection: SelectableRegionItem, update_graphic: bool = True) -> None:
        """
        Replace selection at position specified in its data.
        
        Args:
            new_selection (SelectableRegionItem): Replacement selection
            update_graphic (bool): Whether to update the display
        """
        
        self._selections.replace_selection(new_selection)

        # Refresh graphic
        if update_graphic:
            self.update_graphic()


    def set_pdf_to_scene_transformation_matrix(self) -> None:
        """
        Set up transformation matrix for PDF to scene coordinate conversion.
        
        Updates pdf_to_scene_transform based on current zoom level.
        """
        
        self.pdf_to_scene_transform = fitz.Matrix(self.pdf_zoom, self.pdf_zoom)
        self.pdf_to_scene_transform.invert()
    
    
    def update_graphic(self) -> None:
        """
        Update the graphical display and trees panel.
        
        Refreshes hierarchy relationships and redraws the current page.
        """
        
        self._reindex_titles_tree_children_from_sections()
        self.trees_panel.populate_tree(self._selections)
        self.show_page()
    
    
    def show_page(self) -> None:
        """
        Display the current PDF page with all selections.
        
        Clears the scene, renders the PDF page, and draws all selections
        for the current page with their labels and styling.
        """
        
        if not self._doc:
            return
        
        # Clear the `scene`.
        for item in self.scene.items():
            self.scene.removeItem(item)
            # del item # Optionally delete the item explicitly
        
        # Show the PDF page 
        page_num = self.get_page_num()             
        page = self.get_doc_page()
        pix = page.get_pixmap(matrix=fitz.Matrix(self.pdf_zoom, self.pdf_zoom))
        # Convert to QImage
        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888).copy()
        pixmap = QPixmap.fromImage(img)
        self.page_label.setText(f"Page: {page_num}, Length: {len(self._allowed_pages)}")        
        # Setup scene
        self.view.init()        
        self.scene.setSceneRect(QRectF(0, 0, pixmap.width(), pixmap.height()))    
        self.scene.addPixmap(pixmap)
        
        # Add the updated PDF selection to the `scene`
        if page_num in self._selections.keys():
            for region in self._selections.get(page_num, default=[]):
                # Convert region coordinates from PDF-based coordinates considering scene's zoom.
                region.transform_selected_region(self.pdf_zoom)
                pen_color = QColor(region.data.category.value.color)
                brush_color = QColor(pen_color)
                brush_color.setAlpha(80)                    
                # Draw rectangular or polynomial selections
                region.setPen(QPen(pen_color, 5, Qt.SolidLine))
                region.setBrush(brush_color)
                
                # Write the rectangular or polynomial index 
                center_in_scene = region.mapToScene(region.boundingRect().center())
                region_id = f"{region.data.page}.{region.data.idx}"
                region_id_item = QGraphicsTextItem()
                region_id_item.setHtml(f"<span style='background-color: white'>{region_id}</span>")
                region_id_item.setDefaultTextColor(Qt.black) #(pen_color)
                region_id_item.setFont(QFont("Arial", 20, QFont.Bold))
                # Adjust position so the text is centered
                text_rect = region_id_item.boundingRect()
                region_id_item.setPos(center_in_scene.x() - text_rect.width() / 2,
                                      center_in_scene.y() - text_rect.height() / 2)
                # Make the text a child of the region so it moves/scales with it
                self.scene.addItem(region_id_item)
                
                # Show the region
                self.scene.addItem(region)


        cnt = 0    
        for _, selection_list in self._selections.items():
            cnt += len(selection_list)    
        self._legend_title.setText(f"Selection Categories (Total Sections Numbers: {cnt})")
    
                    
    def next_page(self) -> None:
        """
        Navigate to the next page in the allowed pages list.
        
        Wraps to first page if at the end. Triggers autosave if enabled.
        """
        
        if self._page_idx + 1 >= len(self._allowed_pages):
            self._page_idx = 0
        else:
            self._page_idx = self._page_idx + 1
        self.show_page()
        self.autosave_json()


    def prev_page(self) -> None:
        """
        Navigate to the previous page in the allowed pages list.
        
        Wraps to last page if at the beginning. Triggers autosave if enabled.
        """
        
        if self._page_idx - 1 < 0:
            self._page_idx = len(self._allowed_pages) - 1
        else:
            self._page_idx = self._page_idx - 1
        self.show_page()
        self.autosave_json()


    def goto_page(self) -> None:
        """
        Navigate to page number entered in page_input field.
        
        Validates input and shows error if page number is invalid.
        """
        
        try:
            page_str = self.page_input.text().strip()
            page = int(page_str)
        except ValueError:
            traceback.print_exc()
            self.show_alert(f"Page number \'{page_str}\' not valid.\nIt has to be an integer number in [0,{len(self._doc)}] and it should be within the Selected Pages.")
            return
        self.goto_page_number(page)    
        
        
    def goto_page_number(self, page_number: int) -> None:
        """
        Navigate to specific page number.
        
        Args:
            page_number (int): Page number to navigate to (1-based)
        """
        
        try:
            self._page_idx = self._allowed_pages.index(page_number)  # It arise ValueError if the selected page does not exists.
            self.show_page()
            self.autosave_json()
        except ValueError:
            traceback.print_exc()
            self.show_alert(f"Invalid page number: \'{page_number}\'.\nIt has to be an integer number in [0,{len(self._doc)}] and it should be within the Selected Pages.")


    def find_in_pdf(self, page_number: int) -> None:
        """
        Navigate to specific page if not already there.
        
        Args:
            page_number (int): Page number to navigate to
        """
        
        if page_number != self.get_page_num():
            self.goto_page_number(page_number)


    def extract_selection_data(self) -> Dict:
        """
        Extract all selection data for allowed pages.
        
        Returns:
            Dict: Dictionary mapping page numbers to lists of selection data
        """

        selection_data = {}
        allowed_selections = self.get_in_allowed_pages()
        for page_numb, selections_list in allowed_selections.items():
            if page_numb in self._allowed_pages:
                selection_data[page_numb] = []
                for selection in selections_list:
                    selection_data[page_numb].append(selection.data.to_dict())
        return selection_data


    def show_open_dialog(self, default_path: str, title: str, allow_creating_file: bool) -> Optional[str]:
        """
        Show file dialog for opening/saving files.
        
        Args:
            default_path (str): Default file path
            title (str): Dialog title
            allow_creating_file (bool): Whether to allow creating new files
            
        Returns:
            Optional[str]: Selected file path, or None if cancelled
        """
        
        dialog = FileDialog(default_path=default_path, working_dir=self.working_dir, title=title, allow_create_file=allow_creating_file)
        selected_path = dialog.get_path()
        if selected_path:
            return selected_path.strip()
        return None


    def autosave_json(self) -> None:
        """
        Automatically save JSON if autosave is enabled.
        
        Called during page navigation to preserve work.
        """
        
        if self.should_autosave:
            self.save_json(show_dialog=False)


    def save_json(self, show_dialog: bool = True) -> None:
        """
        Save selections to JSON file.
        
        Args:
            show_dialog (bool): Whether to show file selection dialog
        """
        
        if show_dialog:
            saving_path = self.show_open_dialog(default_path=self.output_json_path, title="Export to Json", allow_creating_file=True)
            if saving_path is None or saving_path == "":
                return
        else:
            saving_path = self.output_json_path
        
        self.output_json_path = saving_path
        json_done = self.export_json()
        img_done = False
        if json_done:
            if self.export_images_path is not None:
                img_done = self.export_img()
        
        if show_dialog: # If not, an error alert is shown by `self.export_json()`
            if json_done:
                msg = f'Extracted data saved into JSON file:\n`{self.output_json_path}`.'
                if img_done:
                    msg = f'{msg}.\nScreenshots saved in:\n`{self.export_images_path}`.'
                self.show_alert(msg, "Info", QMessageBox.Information)
      
            
    def export_img(self) -> bool:
        """
        Export selection images to files.
        
        Returns:
            bool: True if export successful, False otherwise
        """
        
        for _, selections in self.get_in_allowed_pages().items():
            for s in selections:
                img_path = os.path.join(self.export_images_path, f"{s.data.id_}.png")
                done = ImageWindow.save_image(s.data.image, img_path) 
                if not done:
                    self.show_alert(f'Error while extracting images.')
                    return False
        return True


    def export_json(self) -> bool:
        """
        Export selections to JSON file.
        
        Returns:
            bool: True if export successful, False otherwise
        """
        
        try:
            with open(self.output_json_path, 'w', encoding='utf-8') as f:
                selection_data = self.extract_selection_data() 
                json.dump(selection_data, f, indent=2)
            return True  
            
        except Exception:
            self.show_alert(f'Error while saving extracted data into JSON file:\n`{self.output_json_path}`.')
            traceback.print_exc()
        return False


    def import_json(self) -> None:
        """
        Import selections from JSON file via dialog.
        
        Shows file dialog and loads selected JSON file.
        """
        
        loading_path = self.show_open_dialog(default_path=self.output_json_path, title="Import to Json", allow_creating_file=False)
        if loading_path is None or loading_path == "":
            return
        
        self.input_json_path = loading_path
        self.load_json()
        self.show_page()
         
            
    def augment(self) -> None:
        """
        Open augmentation dialog for LLM-based description generation.
        
        Shows AugmentConfigDialog for configuring and running augmentation.
        """
        
        dlg = AugmentConfigDialog(self)
        dlg.exec_()
      
      
    def import_from_unstructured(self) -> None:
        """
        Import selections from Unstructured.io processing.
        
        Shows UnstructuredDialog for importing partitioned PDF data.
        """
        
        dlg = UnstructuredDialog(self._doc)
        if dlg.exec_():
            # Import unstructured partitions
            to_add = UnstructuredImporter.get_parsed_selections(self, dlg.unstructured_partitions)
            self._selections.add_selection_set(to_add)
            self.update_graphic()
    
        
    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handle application close event.
        
        Args:
            event (QCloseEvent): Close event to handle
        """
        
        print("--------------------------------------------------------------------------- CLOSING")
        # TODO ask the user to save JSON if not already
        super().closeEvent(event)
