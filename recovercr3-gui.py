import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QPushButton, 
                             QFileDialog, QLabel, QCheckBox, QSpinBox, QProgressBar, QTextEdit)
from PyQt6.QtCore import pyqtSignal, QObject
from pathlib import Path
import subprocess
import threading

class Communicate(QObject):
    update_progress = pyqtSignal(int)

class RecoverCR3GUI(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.comm = Communicate()
        self.comm.update_progress.connect(self.set_progress)

    def initUI(self):
        layout = QVBoxLayout()

        form_layout = QFormLayout()
        
        self.input_path = QLineEdit()
        self.input_button = QPushButton('Browse')
        self.input_button.clicked.connect(self.browse_input)
        input_layout = QHBoxLayout()
        input_layout.addWidget(self.input_path)
        input_layout.addWidget(self.input_button)
        form_layout.addRow('Input Path:', input_layout)
        
        self.outdir_path = QLineEdit()
        self.outdir_button = QPushButton('Browse')
        self.outdir_button.clicked.connect(self.browse_outdir)
        outdir_layout = QHBoxLayout()
        outdir_layout.addWidget(self.outdir_path)
        outdir_layout.addWidget(self.outdir_button)
        form_layout.addRow('Output Directory:', outdir_layout)
        
        self.ext = QLineEdit("cr3")
        self.numwidth = QSpinBox()
        self.numwidth.setValue(0)
        self.verbose = QCheckBox()
        self.lastchunk = QLineEdit("mdat")
        self.maxchunks = QSpinBox()
        self.maxchunks.setMinimum(0)

        form_layout.addRow('File Extension:', self.ext)
        form_layout.addRow('Number Width:', self.numwidth)
        form_layout.addRow('Verbose:', self.verbose)
        form_layout.addRow('Last Chunk:', self.lastchunk)
        form_layout.addRow('Max Chunks:', self.maxchunks)

        layout.addLayout(form_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(100)
        layout.addWidget(self.progress_bar)

        self.verbose_text = QTextEdit()
        self.verbose_text.setReadOnly(True)
        layout.addWidget(self.verbose_text)

        self.run_button = QPushButton('Run')
        self.run_button.clicked.connect(self.run_recover)
        layout.addWidget(self.run_button)

        self.setLayout(layout)
        self.setWindowTitle('Recover CR3 GUI')

    def browse_input(self):
        file_path, _ = QFileDialog.getOpenFileName(self, 'Select Input File')
        if file_path:
            self.input_path.setText(file_path)

    def browse_outdir(self):
        dir_path = QFileDialog.getExistingDirectory(self, 'Select Output Directory')
        if dir_path:
            self.outdir_path.setText(dir_path)

    def run_recover(self):
        input_path = self.input_path.text()
        outdir_path = self.outdir_path.text()
        ext = self.ext.text()
        numwidth = self.numwidth.value()
        verbose = self.verbose.isChecked()
        lastchunk = self.lastchunk.text()
        maxchunks = self.maxchunks.value()

        # Construct the command to call recovercr3.py with the provided parameters
        cmd = [
            'python3', 'recovercr3.py',
            '--input', input_path,
            '--outdir', outdir_path,
            '--ext', ext,
            '--numwidth', str(numwidth),
            '--lastchunk', lastchunk
        ]

        if verbose:
            cmd.append('--verbose')
        if maxchunks > 0:
            cmd.extend(['--maxchunks', str(maxchunks)])

        # Run the command in a separate thread to avoid blocking the UI
        threading.Thread(target=self.run_command, args=(cmd,)).start()

    def run_command(self, cmd):
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        total_output = []
        while True:
            output = process.stdout.readline()
            if not output and process.poll() is not None:
                break
            if output:
                total_output.append(output.strip())
                self.verbose_text.append(output.strip())
                self.update_progress_bar(output.strip())
        retcode = process.poll()
        return retcode, total_output

    def update_progress_bar(self, output):
        # Assuming the output contains progress information, extract the progress value
        # Example: output = "Progress: 45%" -> progress = 45
        if "Progress:" in output:
            progress = int(output.split("Progress:")[1].strip().replace("%", ""))
            self.comm.update_progress.emit(progress)

    def set_progress(self, value):
        self.progress_bar.setValue(value)
        # Display the percentage inside the progress bar
        self.progress_bar.setFormat(f'{value}%')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    gui = RecoverCR3GUI()
    gui.show()
    sys.exit(app.exec())
