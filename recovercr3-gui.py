import sys
import os
import platform
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QPushButton, QSpinBox,
    QCheckBox, QTextEdit, QFileDialog, QLabel, QGroupBox
)
from PyQt6.QtCore import QProcess, Qt, QStandardPaths, QFileInfo
from PyQt6.QtGui import QFont, QColor

# --- Configuration ---
# Set the path to the recovercr3.py script
FIXED_SCRIPT_PATH = str(Path(__file__).parent / "recovercr3.py") 
# Determine the command to execute Python (handle common OS differences)
PYTHON_COMMAND = "python" if platform.system() == "Windows" else "python3" 

class CarvingApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CR3 File Carving Tool")
        self.setGeometry(100, 100, 600, 600)
        self.setStyleSheet(self._get_dark_stylesheet())

        # QProcess object to run the script asynchronously
        self.process = QProcess(self)
        self.process.readyReadStandardOutput.connect(self._handle_stdout)
        self.process.readyReadStandardError.connect(self._handle_stderr)
        self.process.finished.connect(self._process_finished)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.layout = QVBoxLayout(self.central_widget)
        
        # --- UI Setup ---
        self._setup_settings_form()
        self._setup_controls()
        self._setup_logging_area()

    def _get_dark_stylesheet(self):
        """Returns a modern dark mode CSS-like stylesheet."""
        # Colors used:
        # Background: #2e2e2e (Dark Gray)
        # Foreground/Text: #e0e0e0 (Light Gray)
        # Accent/Button: #007bff (Blue)
        # Log Background: #1e1e1e (Very Dark Gray/Black)
        
        return """
            QMainWindow, QWidget { 
                background-color: #2e2e2e; 
                color: #e0e0e0; 
            }
            QLabel { color: #e0e0e0; }

            QGroupBox { 
                font-weight: bold; 
                border: 1px solid #4a4a4a; /* Dark border */
                border-radius: 5px; 
                margin-top: 10px;
                padding-top: 10px;
            }
            
            /* Inputs */
            QLineEdit, QTextEdit, QSpinBox {
                background-color: #3e3e3e; /* Slightly lighter dark background for input fields */
                color: #e0e0e0;
                border: 1px solid #5a5a5a;
                padding: 5px;
                border-radius: 4px;
            }
            
            /* Buttons */
            QPushButton {
                background-color: #007bff; 
                color: white; 
                border: none; 
                padding: 8px 15px; 
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover { background-color: #0056b3; }
            QPushButton:pressed { background-color: #003d7a; }
            
            /* Main Start Button (larger) */
            QPushButton#StartButton {
                font-size: 12pt;
                padding: 15px;
                border-radius: 6px;
                background-color: #007bff;
            }
            QPushButton#StartButton:hover { background-color: #0056b3; }
            QPushButton:disabled { background-color: #4a4a4a; color: #999999; }
            
            /* Log Area - Matches image background */
            QTextEdit#LogArea { 
                background-color: #1e1e1e; /* Very dark/black background */
                color: #e0e0e0; 
                font-family: monospace;
                border: 1px solid #4a4a4a;
            }
        """

    def _setup_settings_form(self):
        settings_group = QGroupBox("Carving Configuration")
        form_layout = QFormLayout(settings_group)
        form_layout.setSpacing(15)

        # --- Input File ---
        self.input_file_edit = QLineEdit()
        self.input_browse_btn = QPushButton("Browse")
        self.input_browse_btn.clicked.connect(self._browse_input)
        input_layout = self._create_h_layout(self.input_file_edit, self.input_browse_btn)
        form_layout.addRow("Input Dump File:", input_layout)

        # --- Output Directory ---
        default_out_dir = str(Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)) / "Carved_CR3s")
        self.output_dir_edit = QLineEdit(default_out_dir)
        self.output_browse_btn = QPushButton("Browse")
        self.output_browse_btn.clicked.connect(self._browse_output)
        output_layout = self._create_h_layout(self.output_dir_edit, self.output_browse_btn)
        form_layout.addRow("Output Directory:", output_layout)

        # --- Carving Options ---
        self.max_chunks_spin = QSpinBox()
        self.max_chunks_spin.setRange(0, 9999) # 0 means use last chunk
        self.max_chunks_spin.setToolTip("Set to 0 to use the Last Chunk Name option.")
        form_layout.addRow("Max Chunks (0=Default):", self.max_chunks_spin)
        
        self.last_chunk_edit = QLineEdit("mdat")
        self.last_chunk_edit.setToolTip("Name of the final CR3 atom (e.g., 'mdat'). Used if Max Chunks is 0.")
        form_layout.addRow("Last Chunk Name:", self.last_chunk_edit)
        
        self.verbose_check = QCheckBox()
        self.verbose_check.setStyleSheet("QCheckBox { spacing: 10px; }") # Spacing for better look
        form_layout.addRow("Verbose Logging (-v):", self.verbose_check)

        self.layout.addWidget(settings_group)

    def _setup_controls(self):
        control_widget = QWidget()
        control_layout = QHBoxLayout(control_widget)
        control_layout.setContentsMargins(0, 0, 0, 0)
        
        self.start_button = QPushButton("START CARVING")
        self.start_button.setObjectName("StartButton") # For stylesheet targeting
        self.start_button.clicked.connect(self._start_carving)
        
        control_layout.addWidget(self.start_button)
        self.layout.addWidget(control_widget)

    def _setup_logging_area(self):
        log_group = QGroupBox("Process Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_area = QTextEdit()
        self.log_area.setObjectName("LogArea") # For stylesheet targeting
        self.log_area.setReadOnly(True)
        self.log_area.setText("Ready. Select input file and click START CARVING.")
        
        log_layout.addWidget(self.log_area)
        self.layout.addWidget(log_group)

    def _create_h_layout(self, *widgets):
        """Helper to create a horizontal box layout for form fields"""
        h_widget = QWidget()
        h_layout = QHBoxLayout(h_widget)
        h_layout.setContentsMargins(0, 0, 0, 0)
        for widget in widgets:
            h_layout.addWidget(widget)
        return h_widget

    # --- File/Dir Browsing ---
    def _browse_input(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Input Dump File")
        if file_name:
            self.input_file_edit.setText(file_name)

    def _browse_output(self):
        dir_name = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_dir_edit.text())
        if dir_name:
            self.output_dir_edit.setText(dir_name)

    # --- Process Control ---
    def _start_carving(self):
        self.log_area.clear()
        
        input_path = self.input_file_edit.text()
        output_path = self.output_dir_edit.text()

        # Basic Validation
        if not Path(input_path).is_file():
            self.log_area.append(f"<span style='color: red;'>ERROR: Input file not found or path is invalid: {input_path}</span>")
            return
        if not output_path:
            self.log_area.append("<span style='color: red;'>ERROR: Output directory must be specified.</span>")
            return

        # Build command line arguments
        args = [
            FIXED_SCRIPT_PATH,
            "--input", input_path,
            "--outdir", output_path
        ]

        max_chunks = self.max_chunks_spin.value()
        if max_chunks > 0:
            args.extend(["--maxchunks", str(max_chunks)])
        else:
            last_chunk = self.last_chunk_edit.text().strip()
            if last_chunk:
                 args.extend(["--lastchunk", last_chunk])

        if self.verbose_check.isChecked():
            args.append("-v")

        # Display command and start process
        command_line = f"{PYTHON_COMMAND} " + " ".join(args)
        self.log_area.append(f"<span style='color: yellow;'>Starting command:</span> {command_line}\n---")
        self.start_button.setEnabled(False)
        
        # Start the process using the determined python command
        self.process.start(PYTHON_COMMAND, args)

    # --- Process Output Handlers ---
    def _handle_stdout(self):
        data = self.process.readAllStandardOutput().data().decode().strip()
        if data:
            # Color-code based on logging level (assuming recovercr3.py uses standard logging format)
            if "[ERROR]" in data:
                 self.log_area.append(f"<span style='color: red;'>{data}</span>")
            elif "[WARNING]" in data:
                 self.log_area.append(f"<span style='color: orange;'>{data}</span>")
            elif "[INFO]" in data:
                 self.log_area.append(f"<span style='color: lightgreen;'>{data}</span>")
            elif "[DEBUG]" in data:
                 self.log_area.append(f"<span style='color: #88aadd;'>{data}</span>") # Light blue for debug
            else:
                 self.log_area.append(data)
    
    def _handle_stderr(self):
        # Catches OS-level errors (like "python not found") or unhandled script exceptions
        data = self.process.readAllStandardError().data().decode().strip()
        if data:
            self.log_area.append(f"<span style='color: red; font-weight: bold;'>PROCESS ERROR: {data}</span>")

    def _process_finished(self, exit_code, exit_status):
        self.start_button.setEnabled(True)
        if exit_code == 0:
            self.log_area.append("\n<span style='color: lightgreen; font-weight: bold;'>--- Carving FINISHED successfully! ---</span>")
        else:
            self.log_area.append(f"\n<span style='color: red; font-weight: bold;'>--- Carving FAILED with exit code {exit_code} ---</span>")

if __name__ == '__main__':
    # Ensure recovercr3.py exists before starting the GUI
    if not QFileInfo(FIXED_SCRIPT_PATH).exists():
        print(f"Error: The recovercr3.py script was not found at {FIXED_SCRIPT_PATH}")
        sys.exit(1)
        
    app = QApplication(sys.argv)
    window = CarvingApp()
    window.show()
    sys.exit(app.exec())
