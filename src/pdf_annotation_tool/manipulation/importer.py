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

import base64
import traceback
import fitz

from PIL import Image
from io import BytesIO

from multiprocessing import Queue

from typing import List, Optional, Any, Dict, Tuple, TYPE_CHECKING

from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QFileDialog, QLineEdit, QMessageBox, QDialog, QFrame, QDialogButtonBox
from PyQt5.QtGui import QPolygonF
from PyQt5.QtCore import QPointF

from shapely import Polygon, unary_union

from pdf_annotation_tool.builder.dialog import SelectionDialog
from pdf_annotation_tool.builder.handler import BaseSelectionHandler, PolySelectionHandler
from pdf_annotation_tool.utils.worker import ProgressingRunner
if TYPE_CHECKING:
    from pdf_annotation_tool.tool import PDFAnnotationTool

from unstructured.partition.pdf import partition_pdf
from unstructured.documents.elements import Element
from unstructured.staging.base import elements_to_json, elements_from_json

from pdf_annotation_tool.selection.data import SelectionCategory, SelectionData, UnstructuredCategory
from pdf_annotation_tool.selection.graphic import SelectablePolyItem



# Dialog to ask the user how to import Unstructured PDF partitions
class UnstructuredDialog(QDialog):
    """
    A dialog for importing, computing, and saving unstructured PDF partition data using JSON files.
    This dialog provides the following functionality:
    - Load partition data from a JSON file.
    - Compute partitions from a PDF file using an external process.
    - Save computed or loaded partitions to a JSON file.
    - Import partitioned regions into the application.
    Attributes:
        unstructured_partitions: The final partitioned regions after import.
        document: The fitz.Document instance representing the PDF (optional).
        pdf_partition_tree: The loaded or computed partition tree.
        loaded: Flag indicating if partition data was loaded from JSON.
        computed: Flag indicating if partition data was computed from PDF.
    Methods:
        add_separator(layout): Adds a visual separator to the dialog layout.
        load_json(): Loads partition data from a JSON file.
        compute_data(): Computes partition data from a PDF file.
        on_unstructured_result(results): Handles results from the compute process.
        invoke_unstructured_into_process(returning_queue, file_path): Worker for computing partitions.
        save_json(): Saves the current partition tree to a JSON file.
        import_data(): Imports partitioned regions into the application.
        on_import_result(results): Handles results from the import process.
        import_from_unstructured(returning_queue, document_name, pdf_partition_tree, resolution_text): Worker for importing partitions.
        update_buttons(): Updates the enabled/disabled state of dialog buttons based on current mode.
    """
    
    
    def __init__(self, document: Optional[fitz.Document] = None) -> None:
        """
        Initializes the UnstructuredDialog.
        Args:
            document (Optional[fitz.Document]): The PDF document to be processed. Defaults to None.
        Sets up the dialog window for importing, computing, and saving PDF partition data using JSON.
        Initializes UI components including buttons for loading JSON, computing partitions, saving JSON,
        and standard dialog actions (Import/Cancel). Also sets up input for image resolution and manages
        the enabled state of relevant buttons.
        """

        super().__init__()
        self.setWindowTitle("JSON Utility Dialog")
        self.unstructured_partitions = None
        self.document = document
        self.pdf_partition_tree = None
        self.loaded = False
        self.computed = False

        # Layout
        layout = QVBoxLayout()

        # Action buttons
        self.load_btn = QPushButton("Load Partition from JSON")
        self.load_btn.clicked.connect(self.load_json)

        # Compute partition an image resolution
        self.image_res_label = QLabel("Max Image Resolution (WxH):")
        default_img_resolution = SelectionDialog.MAX_IMAGE_RESOLUTION
        self.image_res_input = QLineEdit(default_img_resolution)
        res_layout = QHBoxLayout()
        res_layout.addWidget(self.image_res_label)
        res_layout.addWidget(self.image_res_input)
        self.compute_btn = QPushButton("Compute Partitions")
        self.compute_btn.clicked.connect(self.compute_data)
        
        self.save_btn = QPushButton("Save Partitions to JSON")
        self.save_btn.clicked.connect(self.save_json)
        self.save_btn.setEnabled(False)

        # Dialog standard buttons (OK = Import, Cancel = Cancel)
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.import_data)  # "Import"
        self.button_box.rejected.connect(self.reject)  # "Cancel"

        # Initially disable OK
        self.import_btn = self.button_box.button(QDialogButtonBox.Ok)
        self.import_btn.setText("Import")
        self.import_btn.setEnabled(False)

        # Add buttons to layout
        layout.addWidget(self.load_btn)
        UnstructuredDialog.add_separator(layout)
        layout.addLayout(res_layout)
        layout.addWidget(self.compute_btn)
        UnstructuredDialog.add_separator(layout)
        layout.addWidget(self.save_btn)
        UnstructuredDialog.add_separator(layout)
        layout.addWidget(self.button_box)

        self.setLayout(layout)


    @staticmethod
    def add_separator(layout: QVBoxLayout) -> None:
        """
        Adds a horizontal separator line with spacing above and below to the given QVBoxLayout.

        Args:
            layout (QVBoxLayout): The layout to which the separator will be added.

        Returns:
            None
        """

        # Add some space above the separator
        layout.addSpacing(10)
        # Create a horizontal line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        # Add some space below the separator
        layout.addSpacing(10)


    def load_json(self) -> None:
        """
        Opens a file dialog for the user to select a JSON file and loads its contents
        into the application's PDF partition tree. Updates the application state and
        UI accordingly. Displays a success message upon successful import, or an error
        message if loading fails.

        Returns:
            None
        """
        
        file_path, _ = QFileDialog.getOpenFileName(self, "Select JSON File", "", "JSON Files (*.json)") # TODO set default path from "" to working directory
        if file_path:
            try:
                self.pdf_partition_tree = UnstructuredImporter.load_unstructured_results(file_path)
                self.loaded = True
                self.computed = False
                QMessageBox.information(self, "Success", f"Data imported from {file_path}")
                self.update_buttons()
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load JSON: {e}")


    def compute_data(self) -> None:
        """
        Computes and processes data from a PDF document.
        If no document is currently loaded, prompts the user to select a PDF file.
        Initiates a background process to handle the selected PDF file using an unstructured data processor.
        Handles the result of the processing via the `on_unstructured_result` callback.
        Returns:
            None
        """
        
        if self.document is None:
            file_path, _ = QFileDialog.getSaveFileName(self, "Open PDF File", "", "PDF Files (*.pdf)")
        else:
            file_path = self.document.name
            
        if file_path:
            dialog = ProgressingRunner(UnstructuredDialog.invoke_unstructured_into_process, self, cooperative=False)
            dialog.start(
                file_path=file_path,
                on_result=self.on_unstructured_result, 
                #on_cancel=self.on_unstructured_cancel, 
                #on_error=self.on_unstructured_error
            )   
            

    def on_unstructured_result(self, results: Dict[str, Any]) -> None:
        """
        Handles the outcome of an unstructured data processing operation.

        This method processes the results dictionary, extracts the outcome using
        ProgressingRunner.get_outcome, and updates the internal state of the importer
        accordingly. If the outcome is None, the method returns early. Otherwise, it
        sets the PDF partition tree, marks the computation as complete, resets the
        loaded flag, and updates the UI buttons.

        Args:
            results (Dict[str, Any]): The results from the unstructured data processing operation.

        Returns:
            None
        """
        
        res = ProgressingRunner.get_outcome(results)
        if res is None:
            return
        self.pdf_partition_tree = res
        self.computed = True
        self.loaded = False
        self.update_buttons()
        #print(f"On non cooperative result: `{results}`.")
    # def on_unstructured_cancel(self, results):
    #     print(f"On non cooperative cancel: `{results}`.")
    # def on_unstructured_error(self, results):
    #     print(f"On non cooperative error: `{results}`.")


    @staticmethod
    def invoke_unstructured_into_process(returning_queue: Queue, file_path: str) -> None:
        """
        Invokes the UnstructuredImporter to process a PDF file and communicates the result or error via a queue.

        Args:
            returning_queue (Any): The queue to which the outcome or error will be added.
            file_path (str): The path to the PDF file to be processed.

        Returns:
            None

        Side Effects:
            - Adds the processed PDF partition to the returning_queue on success.
            - Adds the error to the returning_queue and prints the traceback on failure.
        """
        
        try:
            pdf_partition = UnstructuredImporter.invoke_unstructured(file_path)
            ProgressingRunner.add_outcome(returning_queue, pdf_partition)
        except Exception as e:
            # Return errors if necessary
            ProgressingRunner.add_error(returning_queue, e)
            traceback.print_exc()
      
            
    def save_json(self) -> None:
        """
        Saves the current PDF partition tree data to a JSON file.

        This method checks if there is data available in `self.pdf_partition_tree`. If not, it displays a warning message.
        If data is available, it opens a file dialog for the user to select a location to save the JSON file.
        The data is then saved using `UnstructuredImporter.save_unstructured_partitions`.
        Success and error messages are displayed to the user accordingly.

        Raises:
            Exception: If saving the JSON file fails.
        """
        
        if not self.pdf_partition_tree:
            QMessageBox.warning(self, "Warning", "No data to save!")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Save JSON File", "", "JSON Files (*.json)")
        if file_path:
            try:
                UnstructuredImporter.save_unstructured_partitions(self.pdf_partition_tree, file_path)
                QMessageBox.information(self, "Success", f"Data saved to {file_path}")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save JSON: {e}")


    def import_data(self) -> None:
        """
        Imports data into the application by running the UnstructuredDialog.import_from_unstructured
        method in a separate thread using ProgressingRunner. Displays a progress dialog during the import
        process and handles the result via the on_import_result callback.

        Parameters:
            None

        Side Effects:
            - Initiates an import process for the current document.
            - Passes the document name, PDF partition tree, and image resolution text to the import function.
            - Handles the import result through the on_import_result method.
        """
        
        dialog = ProgressingRunner(UnstructuredDialog.import_from_unstructured, self, cooperative=False)
        dialog.start(
            document_name=self.document.name,
            pdf_partition_tree = self.pdf_partition_tree,
            resolution_text = self.image_res_input.text(),
            on_result=self.on_import_result, 
            #on_cancel=self.on_import_cancel, 
            #on_error=self.on_import_error
        )   


    def on_import_result(self, results: Dict[str, Any]) -> None:
        """
        Handles the result of an import operation.

        Retrieves the outcome from the provided results dictionary using ProgressingRunner.
        If a valid outcome is found, assigns it to `self.unstructured_partitions` and accepts the result.
        If no outcome is found, the method returns early.

        Args:
            results (Dict[str, Any]): The results dictionary containing import operation data.

        Returns:
            None
        """
        
        res = ProgressingRunner.get_outcome(results)
        if res is None:
            return
        self.unstructured_partitions = res
        self.accept()
        #print(f"On non cooperative result: `{results}`.")
    #def on_import_cancel(self, results):
    #    print(f"On non cooperative cancel: `{results}`.")
    #def on_import_error(self, results):
    #    print(f"On import error: `{results}`.") # TODO make alert


    @staticmethod
    def import_from_unstructured(returning_queue: Queue, document_name: str, pdf_partition_tree: List[Element], resolution_text: str) -> None:
        """
        Imports and partitions a PDF document using unstructured data.

        Args:
            returning_queue (Queue): Queue to return results or errors.
            document_name (str): Path to the PDF document to import.
            pdf_partition_tree (List[Element]): List representing the partition tree of PDF elements.
            resolution_text (str): Text specifying the desired image resolution.

        Returns:
            None

        Raises:
            Any exceptions encountered during import are added to the returning_queue and printed to stderr.

        Side Effects:
            - Adds partitioned regions or errors to the returning_queue.
            - Closes the PDF document after processing.
        """
        try: 
            document = fitz.Document(document_name)
            max_resolution = SelectionDialog.parse_image_resolution(resolution_text)
            result = UnstructuredImporter(document, pdf_partition_tree, max_resolution)
            partitions = result.get_partitioned_regions()
            ProgressingRunner.add_outcome(returning_queue, partitions)
        except Exception as e:
            # Return errors if necessary
            ProgressingRunner.add_error(returning_queue, e)
            traceback.print_exc()
        finally:
            document.close()


    def update_buttons(self) -> None:
        """
        Updates the enabled/disabled state of UI buttons based on the current status of the importer.
        - If the importer is loaded (`self.loaded` is True), disables the load, compute, and image resolution input buttons,
          and enables the save and import buttons.
        - If the importer is computed (`self.computed` is True), disables the load, compute, and image resolution input buttons,
          and enables the save and import buttons.
        - Otherwise (initial state), enables the load, compute, and image resolution input buttons,
          disables the save button, and enables the import button.
        """
        
        if self.loaded:
            self.load_btn.setEnabled(False)
            self.compute_btn.setEnabled(False)
            self.image_res_input.setEnabled(False)
            self.save_btn.setEnabled(True)
            self.import_btn.setEnabled(True)
        elif self.computed:
            self.load_btn.setEnabled(False)
            self.compute_btn.setEnabled(False)
            self.image_res_input.setEnabled(False)
            self.save_btn.setEnabled(True)
            self.import_btn.setEnabled(True)
        else:
            # Initial state
            self.load_btn.setEnabled(True)
            self.compute_btn.setEnabled(True)
            self.image_res_input.setEnabled(True)
            self.save_btn.setEnabled(False)
            self.import_btn.setEnabled(True)




# Generates selection based on the Unstructured library.
class UnstructuredImporter:
    """
    Imports and processes PDF partition data generated by the Unstructured library.
    This class provides utilities to:
    - Parse and transform Unstructured partition elements into internal selection data.
    - Convert coordinates from Unstructured's reference frame to PDF space.
    - Handle images and tables extracted from PDFs, including resizing images.
    - Recursively traverse partition trees and build a mapping of PDF regions.
    - Save and load partition data to/from JSON files.
    - Generate selection items for use in GUI applications.
    Attributes:
        KEY_ID (str): Key for element ID in Unstructured data.
        KEY_TEXT (str): Key for element text in Unstructured data.
        KEY_CATEGORY (str): Key for element category in Unstructured data.
        KEY_METADATA (str): Key for element metadata in Unstructured data.
        KEY_IMAGE (str): Key for base64 image data in Unstructured data.
        KEY_PAGE_NUMBER (str): Key for page number in metadata.
        KEY_TABLE_TEXT (str): Key for table HTML text in metadata.
        KEY_ORIG_ELEMENTS (str): Key for child elements in metadata.
        KEY_COORDINATES (str): Key for coordinates in metadata.
        KEY_POINTS (str): Key for coordinate points.
        KEY_SYSTEM (str): Key for coordinate system.
        KEY_WIDTH (str): Key for system width.
        KEY_HEIGHT (str): Key for system height.
        KEY_ORIENTATION (str): Key for system orientation.
        KEY_VALUE (str): Key for orientation value.
        MAX_IMAGE_RESOLUTION_DEFAULT (tuple): Default max image resolution for resizing.
    Methods:
        __init__(document, partitions_tree, max_image_resolution):
            Initializes the importer with a PDF document and partition tree.
        to_pages_sizes(document):
            Returns a mapping of page numbers to their sizes (width, height).
        invoke_unstructured(pdf_path):
            Runs Unstructured's partition_pdf on the given PDF and returns elements.
        save_unstructured_partitions(partition_tree, filepath):
            Saves partition tree to a JSON file.
        save_unstructured(filepath):
            Saves the current partition tree to a JSON file.
        load_unstructured_results(filepath):
            Loads partition data from a JSON file.
        _parse_unstructured_item(elem, attribute, should_log=True, datapath=""):
            Safely extracts an attribute from an Unstructured element.
        _parse_unstructured_coordinates(elem):
            Extracts and parses coordinate metadata from an element.
        _coords_to_pdf(elem, page_size):
            Converts Unstructured coordinates to PDF reference frame.
        enclosing_polygon(bboxes):
            Computes the tightest polygon enclosing a list of bounding boxes.
        resize_base64_image_if_needed(b64_str, max_size):
            Resizes a base64-encoded image if it exceeds max_size.
        _visit_partition_tree(elem, parent_id):
            Recursively traverses and processes the partition tree.
        get_partitioned_regions():
            Returns the mapping of page numbers to selection data.
        get_parsed_selections(main_view, partitions):
            Generates selectable region items for GUI display.
    """
    
    # The keys of the result obtained by the Unstructured library.
    KEY_ID = "id"                         # It is in the root object   
    KEY_TEXT = "text"                     # It is in the root object   
    KEY_CATEGORY = "category"             # It is in the root object   
    KEY_METADATA = "metadata"             # It is in the root object   
    KEY_IMAGE = "image_base64"            # It is inside "metadata.image" (It might exists only for category `image`)
    KEY_PAGE_NUMBER = "page_number"       # It is inside "metadata.page_number"
    KEY_TABLE_TEXT = "text_as_html"       # It is inside "metadata.text_as_html"  (It might exists only for category `table`)
    KEY_ORIG_ELEMENTS = "orig_elements"   # It is inside "metadata.orig_elements"
    KEY_COORDINATES = "coordinates"       # It is inside "metadata.coordinates"
    KEY_POINTS = "points"                 # It is inside "metadata.coordinates.points"
    KEY_SYSTEM = "system"                 # It is inside "metadata.coordinates.system"
    KEY_WIDTH = "width"                   # It is inside "metadata.coordinates.system.width"
    KEY_HEIGHT = "height"                 # It is inside "metadata.coordinates.system.height"
    KEY_ORIENTATION = "orientation"       # It is inside "metadata.coordinates.system.orientation"
    KEY_VALUE = "value"                   # It is inside "metadata.coordinates.system.orientation.value"

    # # Unstructured possible categories (i.e., possible strings assignable to "KEY_CATEGORY") Defined in `data.py`
    # CATEGORY_FIGURE_CAPTION = "FigureCaption"
    # CATEGORY_NARRATIVE_TEXT = "NarrativeText"
    # CATEGORY_LIST_ITEM = "ListItem"
    # CATEGORY_TITLE = "Title"
    # CATEGORY_ADDRESS = "Address"
    # CATEGORY_TABLE = "Table"
    # CATEGORY_IMAGE = "Image"
    # CATEGORY_HEADER = "Header"
    # CATEGORY_FOOTER = "Footer"
    # CATEGORY_FORMULA = "Formula"
    # CATEGORY_COMPOSITE_ELEMENT = "CompositeElement"
    # CATEGORY_PAGE_BREAK = "PageBreak"
    # CATEGORY_UNCATEGORIZED_TEXT = "UncategorizedText"

    MAX_IMAGE_RESOLUTION_DEFAULT = (512, 512)

    def __init__(self, document: fitz.Document, partitions_tree: List[Element], max_image_resolution: Tuple[int, int] = MAX_IMAGE_RESOLUTION_DEFAULT):
        """
        Initializes the UnstructuredImporter instance with a PDF document, its partition tree, and optional maximum image resolution.
        Args:
            document (fitz.Document): The PDF document to be imported.
            partitions_tree (List[Element]): A list representing the partition tree structure of the document.
            max_image_resolution (Tuple[int, int], optional): The maximum allowed image resolution. Defaults to MAX_IMAGE_RESOLUTION_DEFAULT.
        Attributes:
            pdf_partitions (Dict[int, List[Dict[str, Any]]]): Stores partitioned PDF data by page number.
            _pdf_path (str): Path to the PDF file.
            _pages_sizes (List[Tuple[float, float]]): List of page sizes for the document.
            _max_image_resolution (Tuple[int, int]): Maximum allowed image resolution.
            _document (fitz.Document): The PDF document object.
            partitions_tree (List[Element]): The partition tree structure.
        Raises:
            Exception: If an error occurs while importing partitions, an alert is shown and the exception is printed.
        """
        
        self.pdf_partitions: Dict[int, List[SelectionData]] = {}
        self._pdf_path = document.name
        self._pages_sizes = UnstructuredImporter.to_pages_sizes(document)
        self._max_image_resolution = max_image_resolution
        self._document = document
        
        try:
            self.partitions_tree = partitions_tree
            if partitions_tree:    
                for e in partitions_tree: # `visit` the list
                    self._visit_partition_tree(e, parent_id=None)#, inherited_page=None)
        except Exception as e:
            traceback.print_exc()
            QMessageBox.warning(self, "Error", f"Error while importing `Unstructured` partitions: {e}")
           
                    
    @staticmethod
    def to_pages_sizes(document: fitz.Document) -> Dict[int, Tuple[float, float]]:
        """
        Extracts the width and height of each page in a PDF document.
        Args:
            document (fitz.Document): The PDF document to extract page sizes from.
        Returns:
            Dict[int, Tuple[float, float]]: A dictionary mapping page numbers (starting from 1)
                to a tuple containing the width and height of each page in PDF points.
        """
        
        page_sizes: Dict[int, Tuple[float, float]] = {}
        for i in range(len(document)):
            r = document[i].rect
            page_sizes[i + 1] = (float(r.width), float(r.height)) # store width,height in PDF points
        return page_sizes


    @staticmethod
    def invoke_unstructured(pdf_path: str) -> List[Element]: 
        """
        Invokes the Unstructured library's `partition_pdf` function to extract structured elements from a PDF file.
        Args:
            pdf_path (str): The path to the PDF file to be processed.
        Returns:
            List[Element]: A list of elements extracted from the PDF, where each element may represent text, titles, tables, images, or composite elements.
                Each element contains metadata such as page number, coordinates, and may include nested child elements.
        Example:
            The returned elements may include metadata fields like `page_number`, `coordinates`, and `orig_element` for nested structures.
            Coordinates are provided as a list of points and may include system information about pixel space and orientation.
        Note:
            The function uses high-resolution strategy and infers table structure. It also extracts image and table blocks, chunking text by title,
            and combines or splits text blocks based on character limits.
        """
        
        # Example data structure returned from Unstructured with `partition_pdf`
        # partitioned_pdf = 
        #     [
        #        { // Object of type `unstructured.documents.elements.CompositElement`, or  `unstructured.documents.elements.Text`, or `unstructured.documents.elements.Title`, etc.
        #         ....
        #         id = "....",
        #         text = "....",
        #         metadata { // Object of type `unstructured.documents.elements.ElementMetadata`
        #             page_number = 1
        #             coordinates = [ // Object of type `unstructured.documents.elements.CoordinatesMetadata`. It might not exists
        #                  "points": [
        #                       [135.98, 1702.33],  // Object of type `np.float64`
        #                       [135.98, 1996.48],  // Object of type `np.float64`
        #                       [837.52, 1996.48],  // Object of type `np.float64`
        #                       [837.52, 1702.33],  // Object of type `np.float64`
        #                  ],
        #                  "system" = { // Object of type `unstructured.documents.coordinates.PixelSpace``
        #                       "height": 2200,
        #                       "width": 1700,
        #                       "orientation": {
        #                           "name": "SCREEN",
        #                           "width": 1700,
        #                           "value": [1, -1]
        #                       }
        #                  }
        #             ] 
        #             orig_element { // It contain the children (which have the same datastructure). This field do not exists if empty.
        #                 [
        #                     {id = "...", text = "...", metadata = { ..., orig_element = {...}}, ...}, // Object of type `unstructured.documents.elements.CompositElement`
        #                     {...}, // Object of type `unstructured.documents.elements.Text`
        #                     {...}, // Object of type `unstructured.documents.elements.Title`
        #                     {...}, // Object of type `unstructured.documents.elements.NarrativeText`
        #                     ...
        #                 ]
        #             }
        #         },
        #         {...}
        #     ]
        #  
        
        partitions = partition_pdf(
            filename=pdf_path,
            strategy="hi_res",
            infer_table_structure=True,
            extract_image_block_types=["Image", "Table"],
            extract_image_block_to_payload=True,
            chunking_strategy="by_title",
            max_characters=10000,
            combine_text_under_n_chars=2000,
            new_after_n_chars=6000,
        )
        return partitions


    @staticmethod
    def save_unstructured_partitions(partition_tree: List[Element], filepath: str) -> None:
        """
        Serializes a list of Unstructured Elements to JSON and saves it to the specified file.
        Args:
            partition_tree (List[Element]): The list of Unstructured Elements to serialize.
            filepath (str): The path to the file where the JSON will be saved.
        Returns:
            None
        Raises:
            ValueError: If no elements are serialized to JSON.
            Exception: For any other errors encountered during saving.
        Side Effects:
            Writes serialized JSON to the specified file.
            Prints status and error messages to the console.
        """
    
        if partition_tree is None or filepath is None:
            return None
        try:
            print(f"saving Unstructured elements to {filepath}") # TODO make alert
            json_str = elements_to_json(partition_tree)
            if not json_str or json_str == "[]":
                raise ValueError("No elements serialized to JSON. Check your partitioned PDF.") # TODO make alert
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(json_str)
        except Exception as e:
            print(f"Error saving Unstructured PDF partitions in {filepath}.") # TODO make alert
            traceback.print_exc()


    def save_unstructured(self, filepath: str) -> None:
        """
        Saves the current unstructured partitions tree to the specified file.
        Args:
            filepath (str): The path to the file where the unstructured partitions will be saved.
        Returns:
            None
        """
        
        UnstructuredImporter.save_unstructured_partitions(self.partitions_tree, filepath)


    @staticmethod
    def load_unstructured_results(filepath: str) -> Optional[List[Element]]:
        """
        Loads and returns a list of Element objects from a JSON file containing unstructured PDF partition results.
        Args:
            filepath (str): The path to the JSON file containing unstructured results.
        Returns:
            Optional[List[Element]]: A list of Element objects if loading is successful, otherwise None.
        Raises:
            Prints an error message and stack trace if an exception occurs during loading.
        """
        
        if filepath is None: 
            return None
        try:
            return elements_from_json(filepath)
        except Exception as e:
            print(f"Error loading Unstructured PDF partitions from {filepath}.") # TODO make alert
            traceback.print_exc()
            return None


    @staticmethod
    def _parse_unstructured_item(elem: Element, attribute: str, should_log: bool = True, datapath: str = "") -> Any:
        """
        Extracts the value of a specified attribute from an Element object, with optional logging if the attribute is missing.

        Args:
            elem (Element): The object from which to retrieve the attribute.
            attribute (str): The name of the attribute to extract.
            should_log (bool, optional): Whether to log an error message if the attribute is missing. Defaults to True.
            datapath (str, optional): The data path prefix for logging purposes. Defaults to "".

        Returns:
            Any: The value of the specified attribute if present, otherwise None.
        """
        
        data = getattr(elem, attribute, None)
        if data is None:
            if should_log:
                error_log = f"{attribute}" if datapath == "" else f"{datapath}.{attribute}"
                print(f"No `{error_log}` found in Unstructured item.")
            return None
        return data


    @staticmethod
    def _parse_unstructured_coordinates(elem: Element) -> Optional[Tuple[List[Tuple[float, float]], List[float], float, float]]:
        """
        Parses unstructured coordinate data from an XML/Element object.
        Traverses the element's metadata to extract coordinate points, orientation, width, and height.
        Returns None if any required field is missing.
        Args:
            elem (Element): The XML/Element object containing unstructured coordinate data.
        Returns:
            Optional[Tuple[List[Tuple[float, float]], List[float], float, float]]:
                A tuple containing:
                    - pts (List[Tuple[float, float]]): List of (x, y) coordinate points.
                    - orientation (List[float]): Orientation values.
                    - sys_w (float): System width.
                    - sys_h (float): System height.
                Returns None if any required field is missing.
        """

        # element -> `metadata`
        metadata = UnstructuredImporter._parse_unstructured_item(elem, UnstructuredImporter.KEY_METADATA)
        if metadata is None: return None
        
        # element -> `metadata.coordinates` (It might not exists, e.g., for meta chunks)
        coords = UnstructuredImporter._parse_unstructured_item(metadata, UnstructuredImporter.KEY_COORDINATES, should_log=False)
        if coords is None: return None
        
        # element -> `metadata.coordinates.points`
        pts = UnstructuredImporter._parse_unstructured_item(coords, UnstructuredImporter.KEY_POINTS)
        if pts is None: return None
        pts = [(float(x), float(y)) for (x, y) in pts]
        
        # element -> `metadata.coordinates.points.system`
        system = UnstructuredImporter._parse_unstructured_item(coords, UnstructuredImporter.KEY_SYSTEM)
        if system is None: return None
        
        # element -> `metadata.coordinates.points.system.width`
        sys_w = UnstructuredImporter._parse_unstructured_item(system, UnstructuredImporter.KEY_WIDTH)
        if sys_w is None: return None
        sys_w = float(sys_w)
        
        # element -> `metadata.coordinates.points.system.height`
        sys_h = UnstructuredImporter._parse_unstructured_item(system, UnstructuredImporter.KEY_HEIGHT)
        if sys_h is None: return None
        sys_h = float(sys_h)
        
        # element -> `metadata.coordinates.points.system.orientation`
        orientation = UnstructuredImporter._parse_unstructured_item(system, UnstructuredImporter.KEY_ORIENTATION)
        if orientation is None: return None
        
        # element -> `metadata.coordinates.points.system.orientation.value`
        orientation = UnstructuredImporter._parse_unstructured_item(orientation, UnstructuredImporter.KEY_VALUE)
        if orientation is None: return None
        orientation = list(orientation)
        
        return pts, orientation, sys_w, sys_h


    @staticmethod
    def _coords_to_pdf(elem: Element, page_size: Tuple[float, float]) -> Optional[List[Tuple[float,float]]]:
        """
        Converts element coordinates from a custom system to PDF coordinates based on the page size.
        Returns a list of points `[[x1,y1],[x2,y2],...[...]].
        
        
        Args:
            elem (Element): The element containing coordinates and orientation information.
            page_size (Tuple[float, float]): The size of the PDF page as (width, height).
        Returns:
            Optional[List[Tuple[float,float]]]: A list of mapped coordinates in PDF units, or None if parsing fails.
        Notes:
            - Coordinates are proportionally mapped from the element's system to the PDF page.
            - If the orientation indicates a negative y-axis, the y-coordinates are inverted to match PDF origin.
        """
        
        
        parsed = UnstructuredImporter._parse_unstructured_coordinates(elem)
        if parsed is None:
            return
        pts, orientation, sys_w, sys_h = parsed
        
        # If we have sys_w/sys_h, perform proportional mapping to page_width/page_height
        page_width, page_height = page_size
        mapped = []
        invert_y = False
        if float(orientation[1]) < 0:
            invert_y = True

        for (x, y) in pts:
            x_pdf = (x / sys_w) * page_width 
            y_pdf = (y / sys_h) * page_height
            if not invert_y: # TODO why it works on the opposite way round? It should be `invert_y` instead of `not invert_y`.
                # orientation had negative y: flip
                y_pdf = page_height - y_pdf
            # At this point (x_pdf, y_pdf) are in PDF units but with origin at bottom-left if we didn't invert
            mapped.append([float(x_pdf), float(y_pdf)])

        return mapped     


    @staticmethod
    def enclosing_polygon(bboxes: List[List[Tuple[float, float]]]) -> List[Tuple[float, float]]:
        """
        Given a list of bounding boxes (each defined by 4 (x,y) points),
        return the vertices of the tightest polygon (possibly concave)
        enclosing them all.
        
        Parameters:
            bboxes (list): List of bounding boxes,
                        where each box = [(x1,y1), (x2,y2), (x3,y3), (x4,y4)]
        
        Returns:
            list: Vertices of the enclosing polygon in counterclockwise order
        """
        
        # Convert each box into a Polygon
        polys = [Polygon(box) for box in bboxes]
        # Merge them into one shape
        merged = unary_union(polys)
        # If result is a MultiPolygon, take the outer boundary of the union
        if merged.geom_type == "MultiPolygon":
            merged = merged.convex_hull  # or cascaded_union for all
        # Get the exterior boundary (outer polygon)
        exterior_coords = list(merged.exterior.coords)
        return exterior_coords
       
       
    @staticmethod 
    def resize_base64_image_if_needed(b64_str: str, max_size: Tuple[int, int] = MAX_IMAGE_RESOLUTION_DEFAULT) -> str:
        """
        Decodes a base64-encoded image, resizes it if its dimensions exceed the specified maximum size 
        (while preserving aspect ratio), and returns the resized image as a base64-encoded string.
        Args:
            b64_str (str): The base64-encoded string representing the image.
            max_size (Tuple[int, int], optional): The maximum allowed (width, height) for the image. 
                Defaults to MAX_IMAGE_RESOLUTION_DEFAULT.
        Returns:
            str: The base64-encoded string of the resized image. If the image is already within the 
                maximum size, the original image is returned (re-encoded).
        """

        # Decode base64 string to bytes
        img_data = base64.b64decode(b64_str)
        # Open the image
        img = Image.open(BytesIO(img_data))
        # Resize only if larger than max_size (preserve aspect ratio)
        img_copy = img.copy()  # avoid modifying the original
        img_copy.thumbnail(max_size, Image.LANCZOS)
        # Save resized (or original if no resize) to bytes
        buffer = BytesIO()
        img_copy.save(buffer, format=img.format)
        resized_bytes = buffer.getvalue()
        # Encode back to base64
        b64_resized = base64.b64encode(resized_bytes).decode("utf-8")
        
        # Print comparison
        #print(f"Original size        : {img.size}")
        #print(f"Resized size         : {img_copy.size}")
        #print(f"Original base64 chars: {len(b64_str)}")
        #print(f"New base64 chars     : {len(b64_resized)}")
            
        return b64_resized
    
    
    def _visit_partition_tree(self, elem: Element, parent_id: Optional[str]) -> None:
        """
        Recursively traverses a partition tree structure, extracting relevant data from each element and its metadata,
        and populates the `pdf_partitions` dictionary with `SelectionData` nodes for each partition.
        Args:
            elem (Element): The current element in the partition tree to process.
            parent_id (Optional[str]): The ID of the parent partition, or None if the current element is the root.
        Behavior:
            - Extracts metadata, ID, category, text, page number, children, coordinates, and image for the current partition.
            - Handles special cases for tables and images, including coordinate inference and image resizing.
            - Recursively visits child elements in the partition tree.
            - Populates a `SelectionData` node with the extracted information and appends it to the `pdf_partitions` dictionary,
              grouped by page number.
        """
            
        # Get data ref
        metadata = UnstructuredImporter._parse_unstructured_item(elem, UnstructuredImporter.KEY_METADATA)
        if metadata is None:
            print("Cannot extrapolate metadata from selection")

        # Get the partition's ID
        elem_id = UnstructuredImporter._parse_unstructured_item(elem, UnstructuredImporter.KEY_ID)
        
        # Get the partition's category
        category = UnstructuredImporter._parse_unstructured_item(elem, UnstructuredImporter.KEY_CATEGORY)
        category = SelectionCategory.category_from_unstructured(category)
        
        # Get the partition's text
        text =UnstructuredImporter._parse_unstructured_item(elem, UnstructuredImporter.KEY_TEXT)
        if category == UnstructuredCategory.TABLE:
            text = UnstructuredImporter._parse_unstructured_item(metadata, UnstructuredImporter.KEY_TABLE_TEXT)
        
        # Get the partition's page number
        page_number = UnstructuredImporter._parse_unstructured_item(metadata, UnstructuredImporter.KEY_PAGE_NUMBER)

        # Get the partition's children
        if metadata is None:
            children = []
        else:
            # element -> `metadata.orig_elements` (it might not exists, e.g., for leafs)
            orig_elements = UnstructuredImporter._parse_unstructured_item(metadata, UnstructuredImporter.KEY_ORIG_ELEMENTS, should_log=False)
            if orig_elements is None:
                children = []
            else:
                children = orig_elements
        child_ids = [UnstructuredImporter._parse_unstructured_item(c, UnstructuredImporter.KEY_ID) for c in children]
        
        # Visit children recursively
        for child in children:
            self._visit_partition_tree(child, parent_id=elem_id)
            
        # Get partition's coordinates
        coords = self._coords_to_pdf(elem, self._pages_sizes[page_number]) # Coordinate transformation from Scene space to PDF space.
        # If coords is missing, infer it from children
        if not coords and child_ids and page_number in self.pdf_partitions:
            boxes = []
            for child in self.pdf_partitions[page_number]:
                child_data = child#.pdf_partition_tree
                if child_data.id_ in child_ids and child_data.coords:
                    boxes.append(child_data.coords)
            coords = UnstructuredImporter.enclosing_polygon(boxes)
        
        
        # Get partition's image
        image = None
        if category == UnstructuredCategory.IMAGE: 
            # Try to get data from Unstructured   
            image = UnstructuredImporter._parse_unstructured_item(metadata, UnstructuredImporter.KEY_IMAGE)
            if image is not None:
                image = self.resize_base64_image_if_needed(image, self._max_image_resolution)
        if image is None:
            # Get the image as a screenshot
            page_ref = self._document[page_number - 1]
            image = PolySelectionHandler.extract_poly_image(page_ref, coords)
            if image is not None:
                image = BaseSelectionHandler.resize_image(image, self._max_image_resolution) 
        
        # Populate data
        node = SelectionData(
            id_ = elem_id,
            doc = self._pdf_path, # It will be reassigned later since it does not contain the URL if the PDF is opened from web (instead, it contains the path to the downloaded file)
            page = page_number,
            coords = coords,
            text = text,
            category = category,
            image = image,
            parent = parent_id,
            children = child_ids,
            description = "",  # Eventually, it will be added by the LLM
            # idx = -1, # It cannot be set since the GUI will take care of it
        )
        self.pdf_partitions.setdefault(page_number, []).append(node)


    def get_partitioned_regions(self) -> Dict[int, List[SelectionData]]:
        """
        Returns the partitioned regions of the PDF as a dictionary.

        Each key in the dictionary represents a partition index (int), and the corresponding value is a list of
        SelectionData objects that belong to that partition.

        Returns:
            Dict[int, List[SelectionData]]: A mapping from partition indices to lists of SelectionData objects.
        """
        
        return self.pdf_partitions


    @staticmethod
    def get_parsed_selections(main_view: 'PDFAnnotationTool', partitions: Dict[int, List[Element]]):
        """
        Parses partitioned PDF elements and creates selectable polygon items for annotation.

        Args:
            main_view (PDFAnnotationTool): The main PDF annotation tool view, providing context and PDF path.
            partitions (Dict[int, List[Element]]): A dictionary mapping partition indices to lists of Element objects, each representing a region in the PDF.

        Returns:
            List[SelectablePolyItem]: A list of SelectablePolyItem instances, each corresponding to a parsed region from the partitions.
        """
        
        to_add = []
        for _, elements in partitions.items():
            for node in elements:
                region = QPolygonF([QPointF(x, y) for x, y in node.coords])
                selection_item = SelectablePolyItem(main_view, region, do_transform = False)
                node.doc = main_view.pdf_path
                selection_item.data = node
                to_add.append(selection_item)
        return to_add
        
