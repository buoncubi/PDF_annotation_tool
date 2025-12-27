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

import os
import datetime

from dataclasses import dataclass
from typing import Optional

from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QFrame, QFileDialog, QMessageBox


# The data got when a new document is opened. It is given by `PDFOpenDialog`
@dataclass
class OpeningData:
    """
    Data structure containing configuration for opening a new PDF document project.
    
    Stores all necessary paths, settings, and options for initializing a PDF annotation
    project including input/output files and processing preferences.
    
    Attributes:
        project_name (str): Name of the project
        working_directory (str): Base directory for project files
        input_pdf_path (str): Path to input PDF file or URL
        input_json_path (str): Path to existing JSON file to import (optional)
        output_json_path (str): Path for saving output JSON file
        should_export_images (bool): Whether to export extracted images
        should_auto_save (bool): Whether to auto-save on page changes
    """
    
    project_name: str
    working_directory: str
    input_pdf_path: str
    input_json_path: str
    output_json_path: str
    should_export_images: bool
    should_auto_save: bool
    
    # TODO add "This would replace file, do you want to continue" for all file paths
        
        
    def is_input_from_file(self) -> bool:
        """
        Check if input PDF path refers to a local file rather than a URL.
        
        Returns:
            bool: True if input is a local file path, False if URL
        """
        
        s = self.input_pdf_path
        return os.path.exists(s) or os.path.isabs(s) # True: from file, False: from url.
    
    
    def get_working_directory(self) -> str:
        """
        Get the full working directory path combining base directory and project name.
        
        Returns:
            str: Complete working directory path
        """
        
        return os.path.join(self.working_directory, self.project_name)

    
    def get_input_pdf_name(self, with_extension: bool = True) -> str:
        """
        Extract the PDF filename from the input path.
        
        Args:
            with_extension (bool): Whether to include .pdf extension
            
        Returns:
            str: PDF filename with or without extension
        """
        
        base_name = os.path.basename(self.input_pdf_path)
        if with_extension:
            if base_name.endswith(".pdf"):
                return base_name
            else:
                return f"{base_name}.pdf"
        else:
            return os.path.splitext(base_name)[0]
        
        
    def get_output_json_name(self, with_extension: bool = True) -> str:
        """
        Extract the JSON output filename.
        
        Args:
            with_extension (bool): Whether to include .json extension
            
        Returns:
            str: JSON filename with or without extension
        """
        
        base_name = os.path.basename(self.get_output_json_path())
        if with_extension:
            return base_name
        else:
            return os.path.splitext(base_name)[0]


    def get_output_json_path(self) -> str:
        """
        Get the complete output JSON file path, generating default if empty.
        
        Returns:
            str: Full path to output JSON file
        """
        
        path = self.output_json_path
        if path == "":
            return os.path.join(self.get_working_directory(), f"{self.get_input_pdf_name(with_extension=False)}.json")
        if os.path.dirname(path) == "": # then, it is only a file name.
            return os.path.join(self.get_working_directory(), path)
        return path
    
    
    def get_export_images_path(self) -> Optional[str]:
        """
        Get the path for exporting images if enabled.
        
        Returns:
            Optional[str]: Images export path if enabled, None otherwise
        """
        
        if self.should_export_images:
            return os.path.join(self.get_working_directory(), "images", f"{self.get_output_json_name(with_extension=False)}")
        return None


    
# Manages the dialog to get the files and folders to work with.
class PDFOpenDialog(QDialog):
    """
    Dialog for configuring PDF project opening options.
    
    Provides UI for selecting project name, working directory, input PDF file/URL,
    optional input JSON, output JSON path, and processing options like image export
    and auto-save functionality.
    """
    
    
    def __init__(self):
        """
        Initialize the PDF opening dialog with all UI components and default values.
        """
        
        def add_separator(layout):
            """ Add some space and an horizontal layout fro the graphic form. """
            # Add some space above the separator
            layout.addSpacing(10)
            # Create a horizontal line
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            layout.addWidget(line)
            # Add some space below the separator
            layout.addSpacing(10)
         
                    
        super().__init__()
        self.setWindowTitle("PDF Import Options")
        self.resize(400, 200)

        self.folder_path = ""
        self.pdf_path = ""
        self.json_path = ""
        self.export_figures = False
        self.auto_save = False

        layout = QVBoxLayout()

        # Project name
        project_name_layout = QHBoxLayout()
        self.project_name_label = QLabel("Project name:")
        self.project_name_editor = QLineEdit()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.project_name_editor.setText(timestamp)
        project_name_layout.addWidget(self.project_name_label)
        project_name_layout.addWidget(self.project_name_editor)
        layout.addLayout(project_name_layout)
        add_separator(layout)

        # Working Directory Selection
        self.dir_label = QLabel("Not selected")
        btn_dir = QPushButton("Select Working Directory")
        btn_dir.clicked.connect(self.select_directory)
        layout.addWidget(self.dir_label)
        layout.addWidget(btn_dir)
        add_separator(layout)
        
        # PDF Selection (File or URL)
        self.pdf_input = QLineEdit()
        self.pdf_input.setPlaceholderText("Chose PDF file or enter a web URL")
        btn_pdf = QPushButton("Browse PDF Files")
        btn_pdf.clicked.connect(self.select_pdf)
        layout.addWidget(self.pdf_input)
        layout.addWidget(btn_pdf)
        add_separator(layout)

        # JSON Input Selection (optional)
        self.json_in = QLineEdit()
        self.json_in.setPlaceholderText("Optionally, import extracted JSON file (leave empty to create a new project)")
        btn_json_in = QPushButton("Browse Input JSON Files")
        btn_json_in.clicked.connect(self.select_json_in)
        layout.addWidget(self.json_in)
        layout.addWidget(btn_json_in)
        add_separator(layout)

        # JSON Output Selection (empty creates a default name)
        self.json_out = QLineEdit()
        self.json_out.setPlaceholderText("Chose extracted JSON file (leave empty to create a new file in the working directory)")
        btn_json_out = QPushButton("Browse Output JSON Files")
        btn_json_out.clicked.connect(self.select_json_out)
        layout.addWidget(self.json_out)
        layout.addWidget(btn_json_out)
        add_separator(layout)

        # Checkboxes
        self.chk_export = QCheckBox("Export Figures")
        self.chk_autosave = QCheckBox("Auto Save on Page Change")
        layout.addWidget(self.chk_export)
        layout.addWidget(self.chk_autosave)

        # Proceed / Cancel buttons
        btn_layout = QHBoxLayout()
        btn_ok = QPushButton("Open New")
        btn_cancel = QPushButton("Cancel")
        btn_ok.clicked.connect(self.on_proceed) # Custom `self.accept` function
        btn_cancel.clicked.connect(self.reject) # Default `self.reject` function
        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

        self.setLayout(layout)


    def select_directory(self) -> None:
        """ Open directory selection dialog and update working directory path. """
        
        dir_path = QFileDialog.getExistingDirectory(self, "Select Working Directory")
        if dir_path:
            self.folder_path = dir_path
            self.dir_label.setText(f"{self.folder_path}")


    def select_pdf(self) -> None:
        """ Open PDF file selection dialog and update input PDF path. """
        
        file_path, _ = QFileDialog.getOpenFileName(self, "Select PDF File", "", "PDF Files (*.pdf)")
        if file_path:
            self.pdf_input.setText(file_path)


    def select_json_out(self) -> None:
        """ Open JSON save dialog and update output JSON path. """
        
        file_path, _ = QFileDialog.getSaveFileName(self, "Select JSON Output File", "", "JSON Files (*.json)") # TODO warn if a file is going to be overwritten
        if file_path:
            self.json_out.setText(file_path)
        
            
    def select_json_in(self) -> None:
        """ Open JSON file selection dialog and update input JSON path. """
        
        file_path, _ = QFileDialog.getOpenFileName(self, "Select JSON Input File", "", "JSON Files (*.json)")
        if file_path:
            self.json_in.setText(file_path)


    def get_results(self) -> OpeningData:
        """
        Collect all dialog inputs and return as OpeningData object.
        
        Returns:
            OpeningData: Configuration object with all dialog settings
        """
        
        return PDFOpenDialog.get_input_setup_programmatically(
            project_name = self.project_name_editor.text(),
            working_directory = self.folder_path,
            input_pdf_path = self.pdf_input.text().strip(),
            input_json_path = self.json_in.text().strip(),
            output_json_path = self.json_out.text().strip(),
            should_export_figures = self.chk_export.isChecked(), 
            should_auto_save = self.chk_autosave.isChecked() 
        )


    def on_proceed(self) -> None:
        """
        Validate required inputs and accept dialog if all fields are valid.
        Shows warning messages for missing required fields.
        """
        
        if self.project_name_editor.text().strip() == "":
            QMessageBox.warning(self, "Missing Input", "Please select a project name.")
            return
        if not self.folder_path:
            QMessageBox.warning(self, "Missing Input", "Please select a working directory.")
            return
        if not self.pdf_input.text().strip():
            QMessageBox.warning(self, "Missing Input", "Please select or enter a PDF file/URL.")
            return
        # everything ok → accept dialog
        self.accept()


    @staticmethod
    def get_input_setup_programmatically(
        project_name: str, 
        working_directory: str, 
        input_pdf_path: str, 
        input_json_path: Optional[str] = None, 
        output_json_path: str = "", 
        should_export_figures: bool = False, 
        should_auto_save: bool = False
    ) -> OpeningData:
        """
        Create OpeningData object programmatically without dialog interaction.
        
        Args:
            project_name (str): Name of the project
            working_directory (str): Base working directory
            input_pdf_path (str): Path to input PDF file or URL
            input_json_path (Optional[str]): Path to input JSON file
            output_json_path (str): Path for output JSON file
            should_export_figures (bool): Whether to export images
            should_auto_save (bool): Whether to enable auto-save
            
        Returns:
            OpeningData: Configured opening data object
        """
        
        return OpeningData(
            project_name=project_name,
            working_directory = working_directory,
            input_pdf_path = input_pdf_path,
            input_json_path = input_json_path,
            output_json_path = output_json_path,
            should_export_images = should_export_figures,
            should_auto_save = should_auto_save
        )




class FileDialog(QDialog): # TODO use this class for all file opening?!
    """
    Generic file selection dialog for JSON files with browse functionality.
    
    Provides a reusable dialog for selecting JSON files with options for
    opening existing files or creating new ones, with working directory context.
    """
    
    def __init__(
        self, 
        default_path: str = "", 
        working_dir: str = "", 
        parent: Optional[QDialog] = None, 
        title: str = "File Selection", 
        allow_create_file: bool = False
    ):
        """
        Initialize file selection dialog.
        
        Args:
            default_path (str): Default file path to display
            working_dir (str): Working directory for file operations
            parent (Optional[QDialog]): Parent dialog widget
            title (str): Dialog window title
            allow_create_file (bool): Whether to allow creating new files
        """
        
        super().__init__(parent)
        self.setWindowTitle(title)#"Select JSON File")
        self.resize(800, 140)
        self._allow_create_file = allow_create_file

        self.working_dir = working_dir

        # Line edit with default path
        self.line_edit = QLineEdit(self)
        self.line_edit.setText(default_path)

        # Buttons
        self.browse_button = QPushButton("Browse", self)
        self.ok_button = QPushButton("OK", self)
        self.cancel_button = QPushButton("Cancel", self)

        # Layouts
        h_layout = QHBoxLayout()
        h_layout.addWidget(self.line_edit)
        h_layout.addWidget(self.browse_button)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.cancel_button)
        button_layout.addWidget(self.ok_button)

        main_layout = QVBoxLayout()
        main_layout.addLayout(h_layout)
        main_layout.addLayout(button_layout)

        self.setLayout(main_layout)

        # Connections
        self.browse_button.clicked.connect(self.browse_file)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)


    def browse_file(self) -> None:
        """ Open file browser dialog and update path field with selected file. """
        
        # Extract folder from current line edit text
        current_path = self.line_edit.text()
        if current_path == "":
            current_path = self.working_dir
        start_dir = os.path.dirname(current_path) if current_path else ""

        if self._allow_create_file:
            file_path, _ = QFileDialog.getSaveFileName(self, "Select JSON file", start_dir, "JSON Files (*.json)")
        else:
            file_path, _ = QFileDialog.getOpenFileName(self, "Select JSON file", start_dir,  "JSON Files (*.json)")
        if file_path:
            self.line_edit.setText(file_path)


    def warn_file_overwriting(self, file_path: str) -> Optional[str]:
        """
        Show warning dialog if file exists and confirm overwrite.
        
        Args:
            file_path (str): Path to file that might be overwritten
            
        Returns:
            Optional[str]: File path if overwrite confirmed, None if cancelled
        """
        
        if os.path.exists(file_path):
            reply = QMessageBox.warning(
                self,
                "Overwrite File?",
                f"The file '{file_path}' already exists.\nDo you want to overwrite it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                return  None# cancel overwrite
        return file_path
          
            
    def get_path(self) -> Optional[str]:
        """
        Execute dialog and return selected file path.
        
        Returns:
            Optional[str]: Selected file path if accepted, None if cancelled
        """
        
        if self.exec_() == QDialog.Accepted:
            file_path = self.line_edit.text()
            if self._allow_create_file:
                file_path = self.warn_file_overwriting(file_path)
                if file_path is None:
                    return None
            return file_path
        return None
