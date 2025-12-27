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


import sys
from pdf_annotation_tool.tool import PDFAnnotationTool
from PyQt5.QtWidgets import QApplication

from pdf_annotation_tool.utils.files import PDFOpenDialog


########################################################################
#### Loading Configurations 
#### (Uncomment `window.load` below to use them).

## The optional working directory where project folders are created
WORKSPACE = "resources/annotation_gui"

## The optional project name within the `WORKSPACE`
PROJECT_NAME = "test_project"

## Optional input PDF file or URL path
INPUT_PDF_PATH = "https://arxiv.org/pdf/2505.23990"

## Optional output JSON file path
OUTPUT_JSON_FILE = "extracted_pdf_partition.json" # By default it is save in the path `f"{WORKSPACE}/{PROJECT_NAME}/"`
INPUT_JSON_FILE = None # or `f"{WORKSPACE}/{PROJECT_NAME}/{OUTPUT_JSON_FILE}"`

## Optional flag to export the screenshot of selected PDF area
SHOULD_EXPORT_FIGURES = True

## Optional flag to autosave JSON outcome every time a PDF page is changed
SHOULD_AUTOSAVE = False

########################################################################


def main():
    """
    Entry point of the application.
    
    Initializes the PDF annotation tool with either a programmatically generated input setup
    or by showing a dialog to get user input for opening a PDF.
    """
    
    # Start the GUI
#   mp.set_start_method("spawn", force=True)  # It might be needed on Windows ????
    app = QApplication(sys.argv)
    window = PDFAnnotationTool()
    #window.resize(200, 600)
    window.show()
    
    
    # Initial GUI configuration
    # Uncomment `window.load` below to use this configurations.
    input_setup = PDFOpenDialog.get_input_setup_programmatically(
        project_name=PROJECT_NAME,
        working_directory = WORKSPACE,
        input_pdf_path = INPUT_PDF_PATH,
        input_json_path = INPUT_JSON_FILE,
        output_json_path = OUTPUT_JSON_FILE, 
        should_export_figures = SHOULD_EXPORT_FIGURES,
        should_auto_save = SHOULD_AUTOSAVE
    )
    # Initially configure the GUI
    # Automatic load, uncomment this line to use the `input_setup` configuration defined above
    #window.load(input_setup) 
    
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
    
    
    
    
    
# Outcome JSON usage example
# import json
# def remove_duplicates(input_file, output_file):
#     # Load JSON data from file
#     with open(input_file, "r", encoding="utf-8") as f:
#         data = json.load(f)

#     # Iterate through each list in the JSON
#     seen_ids = set()
#     for key, items in data.items():
#         unique_items = []
#         for item in items:
#             if item["id_"] not in seen_ids:
#                 seen_ids.add(item["id_"])
#                 unique_items.append(item)
#             else:
#                 print(f"Duplicate ID found: {item['id_']} at {item['page']}.{item['idx']}")
#         data[key] = unique_items  # Replace list with filtered version

#     # Save the cleaned JSON back to file
#     with open(output_file, "w", encoding="utf-8") as f:
#         json.dump(data, f, indent=2, ensure_ascii=False)

# if __name__ == "__main__":
#     input_file = f"{WORKSPACE}/{PROJECT_NAME}/{OUTPUT_JSON_FILE}"
#     output_file = f"{WORKSPACE}/{PROJECT_NAME}/{OUTPUT_JSON_FILE}.computed"
#     remove_duplicates(input_file, output_file)
#     print(f"Duplicates removed. Cleaned JSON saved to {output_file}")

