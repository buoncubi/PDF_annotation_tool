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
import base64

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGraphicsScene, QGraphicsView, QSlider, QMessageBox



# Show an image from a base 64 str in a new window
class ImageWindow(QWidget):
    """
    A QWidget subclass for displaying a base64-encoded image with zoom functionality.

    This window provides a QGraphicsView to show the image, a horizontal slider to control zoom,
    and a label to display the current zoom percentage. Images are decoded from base64 strings.

    Args:
        base64_str (str): Base64-encoded image data to display.
        parent (QWidget, optional): Parent widget.

    Methods:
        set_zoom(value):
            Sets the zoom level of the image view based on the slider value.

        img_from_str(base64_str):
            Decodes a base64 string into a QPixmap. Returns None if decoding fails.

        save_image(base64_str, file_path, delete_previous_images=True):
            Saves the decoded image to the specified file path as PNG.
            Optionally deletes previous PNG images in the directory before saving.

    Attributes:
        scene (QGraphicsScene): The graphics scene containing the image.
        view (QGraphicsView): The view for displaying the scene.
        zoom_slider (QSlider): Slider for adjusting zoom.
        zoom_label (QLabel): Label showing current zoom percentage.
    """
    
        
    def __init__(self, base64_str: str, parent=None):
        """
        Initializes the ImageWindow with a base64-encoded image and zoom controls.
        
        Args:
            base64_str (str): Base64-encoded image data to display in the window.
            parent (QWidget, optional): Parent widget. Defaults to None.
            
        Side Effects:
            - Creates a 700x700 window with title "Base64 Image Viewer with Zoom Bar".
            - Sets up a QGraphicsView with the decoded image and scroll/drag functionality.
            - Adds a horizontal zoom slider (1-400%) with default 100% zoom.
            - Returns early if the base64 string cannot be decoded to a valid image.
        """
        
        super().__init__(parent, Qt.Window)
        self.setWindowTitle("Base64 Image Viewer with Zoom Bar")
        self.resize(700, 700)

        pixmap = self.img_from_str(base64_str)
        if pixmap is None or pixmap.isNull():
            return

        # Graphics Scene/View setup
        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene, self)
        #self.view.setRenderHint(self.view.renderHints())
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self.scene.addPixmap(pixmap)

        # Zoom slider setup
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(1, 400)   # 1% to 300%
        self.zoom_slider.setValue(100)      # default 100% zoom
        self.zoom_slider.valueChanged.connect(self.set_zoom)

        self.zoom_label = QLabel("100%")

        zoom_layout = QHBoxLayout()
        zoom_layout.addWidget(QLabel("Zoom:"))
        zoom_layout.addWidget(self.zoom_slider)
        zoom_layout.addWidget(self.zoom_label)

        # Layout
        layout = QVBoxLayout()
        layout.addWidget(self.view)
        layout.addLayout(zoom_layout)
        self.setLayout(layout)


    def set_zoom(self, value: int) -> None:
        """
        Sets the zoom level of the view to the specified percentage.
        Args:
            value (int): The desired zoom level as a percentage (e.g., 100 for 100%).
        Side Effects:
            - Resets any existing transformations on the view.
            - Scales the view according to the specified zoom percentage.
            - Updates the zoom label to reflect the current zoom level.
        """
        
        scale_factor = value / 100.0
        self.view.resetTransform()
        self.view.scale(scale_factor, scale_factor)
        self.zoom_label.setText(f"{value}%")


    @staticmethod
    def img_from_str(base64_str: str) -> QPixmap:
        """
        Converts a base64-encoded string to a QPixmap object.
        
        Args:
            base64_str (str): Base64-encoded image data string.
            
        Returns:
            QPixmap: The decoded image as a QPixmap object, or None if decoding fails.
            
        Raises:
            Shows an alert dialog if the base64 string is invalid or cannot be decoded.
        """
    
        try:
            image_data = base64.b64decode(base64_str)
        except Exception:
            print(f"Not valid image data: \"{base64_str}\" ")
            if base64_str is not None:
                limit = 10
                log = base64_str if len(base64_str) <= limit else base64_str[:limit] + "..."
            else:
                log = "None"
            QMessageBox.warning(None, "Not valid data", f"Cannot show image with data `{log}`.")
            return None
        pixmap = QPixmap()
        pixmap.loadFromData(image_data)
        return pixmap


    @staticmethod
    def save_image(base64_str: str, file_path: str, delete_previous_images=False) -> bool:
        """
        Saves a base64-encoded image to a file as PNG format.
        
        Args:
            base64_str (str): Base64-encoded image data string.
            file_path (str): Target file path where the image will be saved.
            delete_previous_images (bool, optional): If True, deletes all existing PNG files 
                in the target directory before saving. Defaults to False.
        
        Returns:
            bool: True if the image was saved successfully, False otherwise.
            
        Side Effects:
            - Creates the target directory if it doesn't exist.
            - Optionally removes existing PNG files from the directory.
            - Shows alert dialogs on errors (directory creation, file deletion, invalid image).
        """
    
        directory = os.path.dirname(file_path)
        if directory and not os.path.exists(directory):
            try:
                os.makedirs(directory, exist_ok=True)
            except Exception as e:
                QMessageBox.warning(None, "Image Saving Error", f"Failed to create directory {directory}: {e}")
                return False      

        if delete_previous_images:
            for filename in os.listdir(directory):
                if filename.lower().endswith(".png"):
                    filepath = os.path.join(directory, filename)
                    try:
                        os.remove(filepath)
                    except Exception as e:
                        QMessageBox.warning(None, "Image Deleting Error", f"Failed to delete {filepath}: {e}")
                        return False

        pixmap = ImageWindow.img_from_str(base64_str)
        if not pixmap or pixmap.isNull():
            QMessageBox.warning(None, "Image Error", "No valid image to save.")
            return False
        return pixmap.save(file_path, "PNG")
