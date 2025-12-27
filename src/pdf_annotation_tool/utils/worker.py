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

from typing import Callable, Optional, Any, Dict

from multiprocessing import Process, Queue, Event

from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QMessageBox, QDialog, QProgressBar
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QCloseEvent



# Allow running a function asynchronously with a progressing bar and a cancel button.
class ProgressingRunner(QDialog): 
    """
    Allow running a function in a different process and get back result while showing a loading bar and a cancel button.
    
    Examples of function that run asynchronously
        ```
        def long_api_cooperative(returning_queue, stop_event):
            try:
                result = []
                for i in range(10): # You need a loop for cooperative functions
                    if stop_event.is_set(): # Check if the user wants to cancel
                        # Prepare the cancel outcome
                        ProgressingRunner.add_cancel(returning_queue)
                        return
                    # Do something
                    time.sleep(1), result.append(i)
                # Prepare the returned values
                ProgressingRunner.add_outcome(returning_queue, result)
            except Exception as e:
                # Return errors if necessary
                ProgressingRunner.add_error(returning_queue, e)
                traceback.print_exc()
        ```
        
        ```
        def long_api_non_cooperative(returning_queue, my_input):
            # The `cancel` outcome is managed by ProgressingRunner, which kills the process that runs this function
            try:
                # Do something
                print(my_input)
                time.sleep(10) 
                #Prepare the returned value
                ProgressingRunner.add_outcome(returning_queue, "Non-cooperative finished")
            except Exception as e:
                # Return errors if necessary
                ProgressingRunner.add_error(returning_queue, e)
                traceback.print_exc()
        ```
        
    Example of how to run them:
        ```
        def run_cooperative(self):
            def on_cooperative_result(results):
                print(f"On cooperative result: `{results}`.")
                
            def on_cooperative_cancel(results):
                print(f"On cooperative cancel: `{results}`.")
            
            def on_cooperative_error(results):
                print(f"On cooperative error: `{results}`.")
                
            dialog = ProgressingRunner(long_api_cooperative, self, cooperative=True)
            dialog.start(on_cooperative_result, on_cooperative_cancel, on_cooperative_error)        
        ```
        
        ```
        def run_non_cooperative(self):
            def on_non_cooperative_result(results):
                print(f"On non cooperative result: `{results}`.")
                
            def on_non_cooperative_cancel(results):
                print(f"On non cooperative cancel: `{results}`.")
            
            def on_non_cooperative_error(results):
                print(f"On non cooperative error: `{results}`.")
            
            dialog = ProgressingRunner(long_api_non_cooperative, self, cooperative=False)
            dialog.start(
                on_result=on_non_cooperative_result, 
                on_cancel=on_non_cooperative_cancel, 
                on_error=on_non_cooperative_error,
                my_input="My input
            )
        ```
    """
    
    # The key given as output to the asynchronous caller. They are used to identify the output type.
    ERROR_KEY = "error"
    CANCEL_KEY = "cancel"
    OUTCOME_KEY = "result"
    GENERIC_ERROR = "Generic error"
    GENERIC_CANCEL = "Cancelled by the user"


    def __init__(self, api_function: Callable, parent: Optional[QWidget] = None, cooperative: bool = True) -> None:
        """
        Initializes the dialog for processing tasks with cooperative (i.e., the job can be cancelled within a loop),
        or not cooperative (i.e., we can only kill the job) cancellation.
        
        Args:
            api_function (callable): The function to be executed in the background process.
            parent (QWidget, optional): The parent widget for this dialog. Defaults to None.
            cooperative (bool, optional): If True, enables cooperative cancellation using an event. Defaults to True.
        Attributes:
            api_function (callable): The function to execute.
            cooperative (bool): Indicates if cooperative cancellation is enabled.
            queue (Queue): Queue for inter-process communication.
            stop_event (Event or None): Event to signal process termination if cooperative is True.
            process (Process or None): The background process instance.
            timer (QTimer or None): Timer for UI updates.
            result (Any): Stores the result of the background process.
            label (QLabel): Label displaying status message.
            progress_bar (QProgressBar): Indeterminate progress bar.
            cancel_button (QPushButton): Button to cancel the process.
        """
        
        super().__init__(parent)
        self.setWindowTitle("Processing...")
        self.setModal(True)

        self.api_function = api_function
        self.cooperative = cooperative

        self.queue = Queue()
        self.stop_event = Event() if cooperative else None
        self.process = None
        self.timer = None
        self.result = None

        # UI
        layout = QVBoxLayout()
        self.label = QLabel("Please wait...")
        layout.addWidget(self.label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel_process)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_button)
        layout.addLayout(btn_layout)

        self.setLayout(layout)


    def start(self, on_result: Optional[Callable[[Dict], None]] = None, 
              on_cancel: Optional[Callable[[Dict], None]] = None, 
              on_error: Optional[Callable[[Dict], None]] = None, 
              show_alert_error: bool = True, show_alert_cancel: bool = False, 
              **api_kwargs: Any) -> Optional[Dict[str, Any]]:
        """
        Starts the process for executing the API function in a separate process, monitors its progress,
        and handles the result, cancellation, or error via provided callbacks.
        Args:
            on_result (Optional[Callable[[Dict], None]]): Callback function to be called when the process completes successfully.
            on_cancel (Optional[Callable[[Dict], None]]): Callback function to be called if the process is cancelled.
            on_error (Optional[Callable[[Dict], None]]): Callback function to be called if an error occurs during execution.
            show_alert_error (bool): Whether to show an alert dialog on error. Defaults to True.
            show_alert_cancel (bool): Whether to show an alert dialog on cancellation. Defaults to False.
            **api_kwargs (Any): Additional keyword arguments to pass to the API function running in the subprocess.
        Returns:
            Optional[Dict[str, Any]]: The result dictionary containing the outcome, error, or cancellation information.
        """
        
        # base positional args always passed to the worker
        args = (self.queue, self.stop_event) if self.cooperative else (self.queue,)
        
        # Important: pass api_kwargs to the spawned process
        try:
            self.process = Process(target=self.api_function, args=args, kwargs=api_kwargs)
            self.process.start()
        except Exception as e:
            traceback.print_exc()
            QMessageBox.critical(self, "Error", f"Failed to partition PDF: {e}")
            
    
        self.timer = QTimer()
        self.timer.timeout.connect(self.check_result)
        self.timer.start(100)

        self.exec_()
        
        cancel = ProgressingRunner.get_cancel(self.result) 
        if cancel is not None:
            #print(f"Cancelling with outcomes: `{cancel}`.")
            if on_cancel is not None:
                if show_alert_cancel:
                    QMessageBox.warning(self, "Cancelled", f"Task cancelled by the user.")
                on_cancel(self.result)
            
        error = ProgressingRunner.get_error(self.result) 
        if error is not None:
            #print(f"Got error: `{error}`.")
            if on_error is not None:
                if show_alert_error:
                    QMessageBox.critical(self, "Error", f"Error while executing task on a subprocess.\n`{error}`")
                on_error(self.result)
        
        outcome = ProgressingRunner.get_outcome(self.result) 
        if outcome is not None:
            #print(f"Got outcome: `{outcome}`.")
            if on_result is not None:
                on_result(self.result)
        
        return self.result


    def check_result(self) -> None:
        """
        Checks if the widget is visible and processes the result from the queue.

        If the widget is visible and the queue is not empty, retrieves the result from the queue,
        performs cleanup, and accepts the result.

        Returns:
            None
        """
        
        if not self.isVisible():
            return
        if self.queue and not self.queue.empty():
            self.result = self.queue.get()
            self.cleanup()
            self.accept()


    def cancel_process(self) -> None:
        """
        Cancels the currently running process.

        If a process is active, attempts to cancel it either cooperatively (by setting a stop event)
        or forcefully (by terminating the process), depending on the cooperative flag.
        Performs cleanup operations after cancellation.
        If no result is set, assigns a cancellation result.
        Finally, rejects the current operation.
        """
        
        if self.process and self.process.is_alive():
            if self.cooperative:
                self.stop_event.set()  # cooperative cancellation
            else:
                self.process.terminate()  # forced kill (non cooperative cancellation)
        self.cleanup()
        if not self.result:
            self.result = ProgressingRunner.build_cancel()
        self.reject()


    def cleanup(self) -> None:
        """
        Cleans up resources used by the importer.

        Stops and removes the timer if it exists, joins and removes the process if it exists,
        and sets the queue and stop_event to None to release references.
        """

        if self.timer:
            self.timer.stop()
            self.timer = None
        if self.process:
            self.process.join()
            self.process = None
        self.queue = None
        self.stop_event = None


    def closeEvent(self, event: QCloseEvent) -> None:
        """
        Handles the close event for the window.

        Cancels any ongoing process before accepting the close event to ensure proper cleanup.
        
        Args:
            event (QCloseEvent): The close event triggered when the window is about to close.
        """
        
        self.cancel_process()
        event.accept()


    @staticmethod
    def build_error(outcome: Optional[str] = None) -> Dict[str, str]:
        """
        Builds an error dictionary with a specified outcome message.

        Args:
            outcome (Optional[str]): The error message to include. If None, a generic error message is used.

        Returns:
            Dict[str, str]: A dictionary containing the error key and the outcome message.
        """
        
        if outcome is None:
            outcome = ProgressingRunner.GENERIC_ERROR
        return {ProgressingRunner.ERROR_KEY: outcome}
    
    
    @staticmethod
    def build_cancel(outcome: Optional[str] = None) -> Dict[str, str]:
        """
        Builds a cancellation result dictionary for a progressing runner.

        Args:
            outcome (Optional[str]): The outcome message or code to associate with the cancellation.
                If None, a generic cancellation value is used.

        Returns:
            Dict[str, str]: A dictionary containing the cancellation key and outcome.
        """
        
        if outcome is None:
            outcome = ProgressingRunner.GENERIC_CANCEL
        return {ProgressingRunner.CANCEL_KEY: outcome}
    
    
    @staticmethod
    def build_outcome(outcome: Any) -> Dict[str, Any]:
        """
        Constructs a dictionary representing an outcome for a progressing runner.

        Args:
            outcome (Any): The outcome value to be stored.

        Returns:
            Dict[str, Any]: A dictionary with the outcome stored under the OUTCOME_KEY.
        """
        
        return {ProgressingRunner.OUTCOME_KEY: outcome}


    @staticmethod
    def add_error(queue: Queue, outcome: Optional[str] = None) -> None:
        """
        Adds an error message to the provided queue.
        Args:
            queue (Queue): The queue to which the error message will be added.
            outcome (Optional[str], optional): An optional string describing the error outcome. Defaults to None.
        Returns:
            None
        """
        
        queue.put(ProgressingRunner.build_error(outcome))

        
    @staticmethod
    def add_cancel(queue: Queue, outcome: Optional[str] = None) -> None:
        """
        Adds a cancel event to the provided queue.
        This function puts a cancellation signal, constructed by `ProgressingRunner.build_cancel`,
        into the given queue. Optionally, an outcome string can be provided to describe the reason
        for cancellation.
        Args:
            queue (Queue): The queue to which the cancel event will be added.
            outcome (Optional[str], optional): An optional string describing the outcome or reason
                for cancellation. Defaults to None.
        Returns:
            None
        """
        
        queue.put(ProgressingRunner.build_cancel(outcome))

        
    @staticmethod
    def add_outcome(queue: Queue, outcome: Any) -> None:
        """
        Adds an outcome to the provided queue after processing it with ProgressingRunner.build_outcome.

        Args:
            queue (Queue): The queue to which the processed outcome will be added.
            outcome (Any): The outcome to be processed and added to the queue.

        Returns:
            None
        """
        
        queue.put(ProgressingRunner.build_outcome(outcome))


    @staticmethod
    def get_error(outcome: Dict) -> Optional[str]:
        """
        Retrieves the error message from the given outcome dictionary, if present.

        Args:
            outcome (Dict): A dictionary containing the outcome of a process, potentially including an error message.

        Returns:
            Optional[str]: The error message if it exists in the outcome dictionary; otherwise, None.
        """

        return outcome.get(ProgressingRunner.ERROR_KEY, None)

    
    @staticmethod
    def get_cancel(outcome: Dict) -> Optional[str]:
        """
        Retrieves the cancellation reason from the outcome dictionary.

        Args:
            outcome (Dict): A dictionary containing outcome information.

        Returns:
            Optional[str]: The cancellation reason if present, otherwise None.
        """

        return outcome.get(ProgressingRunner.CANCEL_KEY, None)
    

    @staticmethod
    def get_outcome(outcome: Dict) -> Any:
        """
        Retrieves the outcome value from the provided dictionary using the OUTCOME_KEY.

        Args:
            outcome (Dict): A dictionary containing outcome data.

        Returns:
            Any: The value associated with ProgressingRunner.OUTCOME_KEY if present, otherwise None.
        """
        
        return outcome.get(ProgressingRunner.OUTCOME_KEY, None)
