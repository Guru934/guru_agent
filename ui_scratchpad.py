import sys
from PyQt6 import sip
import threading
import datetime
import re
import uuid
from typing import Optional, List, Any, Dict

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QComboBox, QTextBrowser, QTextEdit,
    QPushButton, QListWidgetItem, QSplitter, QLabel,
    QScrollArea, QSizePolicy, QFrame, QApplication,
    QMessageBox, QSpacerItem, QStyleFactory, QToolButton, QDialog, QCheckBox,
    QGridLayout, QStyle
)
from PyQt6.QtCore import QThread, Qt, pyqtSignal, QObject, QSize, QTimer, QPropertyAnimation, QEasingCurve, QSizeF
from PyQt6.QtGui import QFont, QTextCursor, QPalette, QColor, QSyntaxHighlighter, QTextCharFormat, QBrush

# External dependencies
import markdown
from pygments import highlight
from pygments.lexers import get_lexer_by_name, guess_lexer
from pygments.formatters import HtmlFormatter
from pygments.styles import get_style_by_name 

from cat_talker.agentic_tools import read_file, ripgrep_search, execute_bash, write_file, approve_action, reject_action, SCRATCHPAD_PENDING_ACTIONS
from cat_talker.assistant_features import (
    analyze_screen_image,
    build_approval_message,
    capture_screen_snapshot,
    describe_active_window,
    describe_current_screen,
    transcribe_audio_from_microphone,
    voice_input_status,
)
from cat_talker.db import get_sessions, get_messages, create_session, insert_message, update_session_title, get_sessions_with_counts, get_session_title_preview, get_preference, set_preference
from cat_talker.desktop_actions import handle_desktop_action
from cat_talker.llm_router import get_installed_models, chat_completion_stream
from cat_talker.orchestrator import AgentOrchestrator


# --- Constants & Style (Dracula theme colors) --
# https://draculatheme.com/contribute
COLORS = {
    "background": "#282a36",
    "current_line": "#44475a",
    "foreground": "#f8f8f2",
    "comment": "#6272a4",
    "cyan": "#8be9fd",
    "green": "#50fa7b",
    "orange": "#ffb86c",
    "pink": "#ff79c6",
    "purple": "#bd93f9",
    "red": "#ff5555",
    "yellow": "#f1fa8c",
    "user_bubble_bg": "#44475a",
    "ai_bubble_bg": "#282a36",
    "system_bubble_bg": "#6272a4",
    "error_bg": "#ff5555",
    "error_fg": "#f8f8f2",
    "warning_bg": "#ffb86c",
    "warning_fg": "#44475a",
    "border": "#45475a",
    "selection": "#313244",
}

# Define QSS styles directly in a string constant
QSS_STYLES = f"""
QMainWindow {{
    background-color: rgba(22, 22, 30, 0.98);
    color: {COLORS['foreground']};
    border: 1px solid rgba(255, 255, 255, 0.1); 
    border-radius: 14px;
}}

QWidget#sidebar {{
    background-color: #121218;
    border-right: 1px solid rgba(255, 255, 255, 0.06);
}}

QPushButton#new_chat_btn {{
    background-color: {COLORS['purple']};
    color: {COLORS['background']};
    font-weight: bold;
    border-radius: 8px;
    padding: 10px;
    border: none;
}}
QPushButton#new_chat_btn:hover {{
    background-color: {COLORS['pink']};
}}

QListWidget {{
    border: none;
    outline: none;
    background-color: transparent;
    color: {COLORS['foreground']};
}}
QListWidget::item {{
    padding: 8px 5px;
    border-radius: 5px;
    margin-bottom: 2px;
}}
QListWidget::item:selected {{
    background-color: {COLORS['selection']};
}}
QListWidget::item:hover:!selected {{
    background-color: {COLORS['current_line']};
}}
QListWidget::item[whatsThis="active-session"] {{
    background-color: {COLORS['current_line']};
    border: 1px solid {COLORS['purple']};
}}

QWidget#top_bar {{
    background-color: transparent;
    padding: 5px 15px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}}

QComboBox {{
    background-color: #1f2335;
    color: #c0caf5;
    border: 1px solid #3b4261;
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 500;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    background-color: #1a1b26;
    color: #c0caf5;
    selection-background-color: #3d59a1;
    border: 1px solid #3b4261;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}

QScrollArea#chat_feed_scroll_area {{
    border: none;
    background-color: transparent;
}}

QTextBrowser {{ 
    background-color: transparent;
    border: none;
    color: {COLORS['foreground']};
    font-size: 14px;
    padding: 5px;
}}
QTextBrowser.user-bubble {{
    background-color: #2b3a5c; 
    color: #ffffff; 
    border-radius: 14px; 
    padding: 10px 14px;
}}
QTextBrowser.ai-bubble {{
    background-color: transparent; 
    color: #e0e6f8; 
    border: none;
    padding: 6px 12px;
}}
QTextBrowser.system-bubble {{
    background-color: {COLORS['system_bubble_bg']};
    border-radius: 12px;
    padding: 10px 14px;
    color: {COLORS['foreground']};
}}
QTextBrowser.error-bubble {{
    background-color: {COLORS['error_bg']};
    color: {COLORS['error_fg']};
    border-radius: 12px;
    padding: 10px 14px;
    border: 1px solid {COLORS['red']};
}}

QFrame#input_bar_widget {{
    background-color: #16161e;
    border-top: 1px solid rgba(255, 255, 255, 0.06);
}}

QTextEdit#input_box {{
    background-color: #1f2335; 
    border: 1px solid #3b4261; 
    border-radius: 12px; 
    padding: 10px 14px; 
    color: #fff;
    font-family: inherit;
}}

QPushButton#send_btn {{
    background-color: #7aa2f7; 
    color: #15161e; 
    border-radius: 8px; 
    font-weight: bold;
    padding: 10px 15px;
    border: none;
}}
QPushButton#send_btn:hover {{
    background-color: {COLORS['cyan']};
}}

/* Pygments code highlighting styles for QTextBrowser (embedded directly) */
.codehilite {{
    background-color: {COLORS['background']};
    color: {COLORS['foreground']};
    padding: 10px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 13px;
}}
.hll {{ background-color: {COLORS['current_line']} }}
.c {{ color: {COLORS['comment']} }}
.err {{ color: {COLORS['red']} }}
.k {{ color: {COLORS['pink']} }}
.o {{ color: {COLORS['pink']} }}
.ch {{ color: {COLORS['comment']} }}
.cm {{ color: {COLORS['comment']} }}
.cp {{ color: {COLORS['purple']} }}
.cpf {{ color: {COLORS['comment']} }}
.c1 {{ color: {COLORS['comment']} }}
.cs {{ color: {COLORS['comment']} }}
.gd {{ color: {COLORS['red']} }}
.ge {{ font-style: italic }}
.gh {{ font-weight: bold }}
.gi {{ color: {COLORS['green']} }}
.gp {{ color: {COLORS['comment']} }}
.gs {{ font-weight: bold }}
.gu {{ color: {COLORS['purple']} }}
.kc {{ color: {COLORS['pink']} }}
.kd {{ color: {COLORS['cyan']} }}
.kn {{ color: {COLORS['pink']} }}
.kp {{ color: {COLORS['purple']} }}
.kr {{ color: {COLORS['pink']} }}
.kt {{ color: {COLORS['cyan']} }}
.m {{ color: {COLORS['purple']} }}
.s {{ color: {COLORS['yellow']} }}
.na {{ color: {COLORS['cyan']} }}
.nb {{ color: {COLORS['green']} }}
.nc {{ color: {COLORS['green']} }}
.no {{ color: {COLORS['cyan']} }}
.nd {{ color: {COLORS['green']} }}
.ni {{ color: {COLORS['orange']} }}
.ne {{ color: {COLORS['red']} }}
.nf {{ color: {COLORS['green']} }}
.nl {{ color: {COLORS['cyan']} }}
.nn {{ color: {COLORS['cyan']} }}
.nx {{ color: {COLORS['green']} }}
.py {{ color: {COLORS['foreground']} }}
.nt {{ color: {COLORS['pink']} }}
.nv {{ color: {COLORS['cyan']} }}
.ow {{ color: {COLORS['pink']} }}
.w {{ color: {COLORS['foreground']} }}
.mb {{ color: {COLORS['purple']} }}
.mf {{ color: {COLORS['purple']} }}
.mh {{ color: {COLORS['purple']} }}
.mi {{ color: {COLORS['purple']} }}
.mo {{ color: {COLORS['purple']} }}
.sa {{ color: {COLORS['yellow']} }}
.sb {{ color: {COLORS['yellow']} }}
.sc {{ color: {COLORS['yellow']} }}
.dl {{ color: {COLORS['yellow']} }}
.sd {{ color: {COLORS['yellow']} }}
.s2 {{ color: {COLORS['yellow']} }}
.se {{ color: {COLORS['purple']} }}
.sh {{ color: {COLORS['yellow']} }}
.si {{ color: {COLORS['yellow']} }}
.sx {{ color: {COLORS['green']} }}
.sr {{ color: {COLORS['yellow']} }}
.s1 {{ color: {COLORS['yellow']} }}
.ss {{ color: {COLORS['orange']} }}
.bp {{ color: {COLORS['green']} }}
.fm {{ color: {COLORS['green']} }}
.vc {{ color: {COLORS['cyan']} }}
.vg {{ color: {COLORS['cyan']} }}
.vi {{ color: {COLORS['cyan']} }}
.vm {{ color: {COLORS['cyan']} }}
.il {{ color: {COLORS['purple']} }}
"""


class PygmentsHtmlFormatter(HtmlFormatter):
    def __init__(self, **options):
        super().__init__(**options)
        self.cssclass = "codehilite" 
        self.noclasses = True 

# Global formatter instance
html_formatter = PygmentsHtmlFormatter(full=False, style=get_style_by_name('dracula'))


class SessionRowWidget(QWidget):
    delete_clicked = pyqtSignal(str)

    def __init__(self, session_id, title, is_active, parent=None):
        super().__init__(parent)
        self.session_id = session_id
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 8, 6)
        layout.setSpacing(8)
        
        # Session title label
        self.label = QLabel(title)
        if is_active:
            self.label.setStyleSheet("color: #bd93f9; font-size: 13px; font-weight: bold;")
        else:
            self.label.setStyleSheet("color: #c0caf5; font-size: 13px; font-weight: 500;")
        layout.addWidget(self.label, stretch=1)
        
        # Delete action button
        self.delete_btn = QPushButton("✕")
        self.delete_btn.setFixedSize(22, 22)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: #565f89;
                border: none;
                border-radius: 4px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #f7768e;
                color: #ffffff;
            }
        """)
        self.delete_btn.clicked.connect(lambda: self.delete_clicked.emit(self.session_id))
        layout.addWidget(self.delete_btn, stretch=0)
        
        self.setFixedHeight(38)
        # Replaced

class MarkdownTextBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenExternalLinks(True)
        self.setOpenLinks(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth) 
        self.document().setDefaultStyleSheet(QSS_STYLES) 

    def setMarkdown(self, markdown_text):
        html = markdown.markdown(markdown_text, extensions=['fenced_code', 'codehilite', 'nl2br'])
        final_html = self._highlight_code_blocks(html)
        self.setHtml(final_html)

    def _highlight_code_blocks(self, html_content):
        def replace_func(match):
            code = match.group(2)
            lang_match = re.search(r'language-([a-zA-Z0-9]+)', match.group(1) or '')
            lang = lang_match.group(1) if lang_match else 'text'
            
            try:
                lexer = get_lexer_by_name(lang)
            except Exception:
                lexer = guess_lexer(code) 
            
            return highlight(code, lexer, html_formatter)
        
        return re.sub(r'<pre><code(?: class="(.*?)")?>(.*?)</code></pre>', replace_func, html_content, flags=re.DOTALL)


class MessageBubble(QWidget):
    def __init__(self, role: str, content: str, is_error: bool = False, parent=None):
        super().__init__(parent)
        self.role = role
        self.content = content
        self.is_error = is_error
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5) 

        self.text_display = MarkdownTextBrowser()
        self.text_display.setReadOnly(True)
        self.text_display.setMarkdown(self.content)
        self.text_display.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_display.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.text_display.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)

        if self.role == "user":
            self.text_display.setProperty("class", "user-bubble")
            spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            layout.addSpacerItem(spacer)
            layout.addWidget(self.text_display)
        elif self.role == "assistant":
            if self.is_error:
                self.text_display.setProperty("class", "error-bubble")
                layout.addWidget(self.text_display, 85)
                spacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
                layout.addSpacerItem(spacer)
            else:
                self.text_display.setProperty("class", "ai-bubble")
                layout.addWidget(self.text_display, 100)
        elif self.role == "system":
            self.text_display.setProperty("class", "system-bubble")
            spacer1 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            layout.addSpacerItem(spacer1)
            layout.addWidget(self.text_display, 60)
            spacer2 = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
            layout.addSpacerItem(spacer2)
        
        self.text_display.setStyleSheet(QSS_STYLES) 
        self.setLayout(layout)
        
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.MinimumExpanding)

    def adjust_height(self):
        if self.text_display is None: return
        doc = self.text_display.document()
        doc.setTextWidth(self.text_display.viewport().width())
        height = int(doc.size().height()) + 20
        self.text_display.setMinimumHeight(height)
        self.text_display.setMaximumHeight(height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_height()


class AutoResizingTextEdit(QTextEdit):
    text_changed_height = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(50) 
        self.document().contentsChanged.connect(self.update_height)
        self.setPlaceholderText("Type a message or tool command...")
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("input_box") # For QSS styling


    submit_pressed = pyqtSignal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Return and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.submit_pressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def update_height(self):
        doc_height = self.document().size().height() # Returns QSizeF.height()
        new_height = int(doc_height + self.fontMetrics().lineSpacing() * 2) 
        if new_height < 50: 
            new_height = 50
        elif new_height > 200: 
            new_height = 200
        
        if self.height() != new_height:
            self.setFixedHeight(new_height)
            self.text_changed_height.emit() 

class DummyVisualizerEmitter(QObject):
    state_signal = pyqtSignal(str)
    glow_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.state_signal.connect(lambda s: print(f"Visualizer State: {s}"))
        self.glow_signal.connect(lambda s: print(f"Visualizer Glow: {s}"))


class ErrorBox(QFrame):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        self.title = title
        self.content = content
        self.is_expanded = False
        self.init_ui()
        self.setObjectName("error_box") # For QSS styling

    def init_ui(self):
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        self.setStyleSheet(f"""
            QFrame#error_box {{ 
                background-color: {COLORS['error_bg']}; 
                border: 1px solid {COLORS['red']};
                border-radius: 8px;
                padding: 5px;
            }}
            QFrame#error_box QLabel {{ color: {COLORS['error_fg']}; }}
            QFrame#error_box QToolButton {{
                background-color: {COLORS['red']}; 
                border: none; 
                color: {COLORS['error_fg']}}};
            }}
            QFrame#error_box QToolButton::hover {{ background-color: {COLORS['pink']}; }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(5, 5, 5, 5)

        header_layout = QHBoxLayout()
        self.title_label = QLabel(f"<b>{self.title}</b>")
        self.title_label.setStyleSheet("color: white;") # Inline for specific label
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()

        self.toggle_button = QToolButton(self)
        self.toggle_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))
        self.toggle_button.clicked.connect(self.toggle_content)
        header_layout.addWidget(self.toggle_button)
        main_layout.addLayout(header_layout)

        self.content_widget = QWidget(self)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(5, 0, 5, 5)

        self.content_label = QLabel(self.content)
        self.content_label.setWordWrap(True)
        self.content_label.setStyleSheet("color: white;")
        self.content_layout.addWidget(self.content_label)
        self.content_widget.hide()

        main_layout.addWidget(self.content_widget)

    def toggle_content(self):
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)
        if self.is_expanded:
            self.toggle_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp))
        else:
            self.toggle_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowDown))


class ChatWorker(QObject):
    chunk_received = pyqtSignal(str)
    finished = pyqtSignal(str) 
    error_occurred = pyqtSignal(str, str) 
    visualizer_state_signal = pyqtSignal(str)
    visualizer_glow_signal = pyqtSignal(str)

    def __init__(self, model_id: str, messages: List[Dict[str, Any]], visualizer_state_emitter: Optional[QObject] = None, visualizer_glow_emitter: Optional[QObject] = None):
        super().__init__()
        self.model_id = model_id
        self.messages = messages
        self.visualizer_state_emitter = visualizer_state_emitter
        self.visualizer_glow_emitter = visualizer_glow_emitter
        
    def run(self):
        full_response = ""
        try:
            if self.visualizer_state_emitter:
                self.visualizer_state_emitter.emit("thinking")
            if self.visualizer_glow_emitter:
                self.visualizer_glow_emitter.emit("thinking")

            for chunk in chat_completion_stream(self.model_id, self.messages):
                full_response += chunk
                self.chunk_received.emit(chunk)
        except Exception as e:
            error_title = "API Error"
            error_message = str(e)
            if "ConnectionRefusedError" in error_message or "Could not connect" in error_message:
                error_message = "Could not connect to the Ollama server. Please ensure Ollama is running."
                error_title = "Ollama Connection Error"
            self.error_occurred.emit(error_title, error_message)
            full_response = f"ERROR: {error_message}" 
        finally:
            if self.visualizer_state_emitter:
                self.visualizer_state_emitter.emit("idle")
            if self.visualizer_glow_emitter:
                self.visualizer_glow_emitter.emit("connected")
            self.finished.emit(full_response)



class VoiceCaptureWorker(QThread):
    finished_signal = pyqtSignal(str)

    def __init__(self, record_seconds=4):
        super().__init__()
        self.record_seconds = record_seconds

    def run(self):
        from cat_talker.assistant_features import transcribe_audio_from_microphone
        transcript = transcribe_audio_from_microphone(record_seconds=self.record_seconds)
        self.finished_signal.emit(transcript)


class ApprovalDialog(QDialog):
    def __init__(self, title: str, summary: str, details: str, risk_level: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Approve Action")
        self.setFixedSize(500, 350)
        
        self.setStyleSheet("""
            QDialog {
                background-color: #1e1e2e;
                color: #cdd6f4;
            }
            QLabel#title_label {
                font-size: 16px;
                font-weight: bold;
                color: #cdd6f4;
            }
            QLabel#risk_high {
                background-color: #f38ba8;
                color: #11111b;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QLabel#risk_medium {
                background-color: #f9e2af;
                color: #11111b;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QLabel#risk_low {
                background-color: #a6e3a1;
                color: #11111b;
                padding: 4px 8px;
                border-radius: 4px;
                font-weight: bold;
            }
            QTextEdit {
                background-color: #181825;
                color: #a6adc8;
                border: 1px solid #313244;
                border-radius: 8px;
                padding: 8px;
                font-family: monospace;
            }
            QPushButton {
                background-color: #313244;
                color: #cdd6f4;
                padding: 8px 16px;
                border-radius: 6px;
                border: none;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45475a;
            }
            QPushButton#btn_allow {
                background-color: #a6e3a1;
                color: #11111b;
            }
            QPushButton#btn_allow:hover {
                background-color: #94e2d5;
            }
            QPushButton#btn_reject {
                background-color: #f38ba8;
                color: #11111b;
            }
            QPushButton#btn_reject:hover {
                background-color: #eba0ac;
            }
        """)

        layout = QVBoxLayout(self)

        # Header: Title and Risk
        header_layout = QHBoxLayout()
        title_label = QLabel(title)
        title_label.setObjectName("title_label")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        risk_label = QLabel(f"Risk: {risk_level.capitalize()}")
        if risk_level.lower() == "high":
            risk_label.setObjectName("risk_high")
        elif risk_level.lower() == "medium":
            risk_label.setObjectName("risk_medium")
        else:
            risk_label.setObjectName("risk_low")
        header_layout.addWidget(risk_label)
        
        layout.addLayout(header_layout)

        # Summary
        summary_label = QLabel(summary)
        summary_label.setWordWrap(True)
        layout.addWidget(summary_label)

        # Details Box
        details_box = QTextEdit()
        details_box.setReadOnly(True)
        details_box.setPlainText(details)
        layout.addWidget(details_box)

        # Always Allow Checkbox
        self.always_allow_checkbox = QCheckBox("Always allow this kind of action")
        layout.addWidget(self.always_allow_checkbox)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        reject_btn = QPushButton("Reject")
        reject_btn.setObjectName("btn_reject")
        reject_btn.clicked.connect(self.reject)
        
        allow_btn = QPushButton("Allow")
        allow_btn.setObjectName("btn_allow")
        allow_btn.clicked.connect(self.accept)
        
        button_layout.addWidget(reject_btn)
        button_layout.addWidget(allow_btn)
        
        layout.addLayout(button_layout)
        
    def is_always_allow_checked(self) -> bool:
        return self.always_allow_checkbox.isChecked()


class ScratchpadWindow(QMainWindow):
    def __init__(self, visualizer_state_emitter: Optional[QObject] = None, visualizer_glow_emitter: Optional[QObject] = None):
        super().__init__()
        
        self.visualizer_state_emitter = visualizer_state_emitter
        self.visualizer_glow_emitter = visualizer_glow_emitter

        self.setWindowTitle("AI Workspace")
        self.setObjectName("cat-talker-workspace")

        screen = QApplication.primaryScreen()
        if screen is not None:
            screen_geo = screen.availableGeometry()
            x = max(screen_geo.x() + 60, 40)
            y = max(screen_geo.y() + 60, 40)
            max_x = max(screen_geo.x(), screen_geo.right() - 1100)
            max_y = max(screen_geo.y(), screen_geo.bottom() - 780)
            x = min(x, max_x)
            y = min(y, max_y)
            self.setGeometry(x, y, 1000, 700)
        else:
            self.resize(1000, 700)
            self.move(80, 80)

        self.setStyleSheet(QSS_STYLES) 
        self.current_session_id: Optional[str] = None # Explicitly type as Optional[str]
        self.chat_history: List[Dict[str, Any]] = []
        self.pending_action_id: Optional[str] = None
        self.chat_worker_thread: Optional[threading.Thread] = None
        self.current_ai_response_bubble_text_display: Optional[MarkdownTextBrowser] = None
        self.current_ai_response_content: str = ""
        self.voice_in_progress = False
        self.voice_worker: Optional[QThread] = None
        self.voice_cancel_requested = False
        self.orchestrator = AgentOrchestrator(default_model="qwen-6gb:latest", safe_mode=(get_preference("safe_mode", "true") == "true"))

        self.model_name_map = {
            "gemini-3.1-flash-live-preview": "Gemini Live (Cloud)",
            "qwen-6gb:latest": "Qwen 2.5 (Local)",
            "llama3": "Llama 3 (Local)",
            "phi3": "Phi-3 (Local)",
        }
        self.reverse_model_name_map = {v: k for k, v in self.model_name_map.items()}
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)
        
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- Sidebar ---
        self.sidebar_widget = QWidget()
        sidebar_widget = self.sidebar_widget
        sidebar_widget.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar_widget)
        sidebar_layout.setContentsMargins(10,10,10,10)
        
        new_chat_btn = QPushButton("＋ New Chat")
        new_chat_btn.setObjectName("new_chat_btn")
        new_chat_btn.clicked.connect(self.start_new_chat)
        sidebar_layout.addWidget(new_chat_btn)
        
        self.session_list = QListWidget()
        self.session_list.setObjectName("session_list")
        self.session_list.itemClicked.connect(self.load_selected_session)
        sidebar_layout.addWidget(self.session_list)
        
        splitter.addWidget(sidebar_widget)
        
        # --- Chat Area ---
        chat_widget = QWidget()
        chat_layout = QVBoxLayout(chat_widget)
        chat_layout.setContentsMargins(0,0,0,0)
        
        # Top Bar
        top_bar_widget = QWidget()
        top_bar_widget.setObjectName("top_bar")
        top_bar_layout = QHBoxLayout(top_bar_widget)
        top_bar_layout.setContentsMargins(15, 10, 15, 10)
        
        
        self.sidebar_toggle_btn = QPushButton("☰")
        self.sidebar_toggle_btn.setObjectName("sidebar_toggle_btn")
        self.sidebar_toggle_btn.setStyleSheet("QPushButton { background: transparent; border: none; font-size: 18px; color: #c0caf5; margin-right: 10px; } QPushButton:hover { color: #ffffff; }")
        self.sidebar_toggle_btn.clicked.connect(self.toggle_sidebar)
        top_bar_layout.addWidget(self.sidebar_toggle_btn)

        self.session_title_label = QLabel("<b>Chat with Assistant</b>")
        self.session_title_label.setStyleSheet("color: #c0caf5; font-size: 14px;")
        top_bar_layout.addWidget(self.session_title_label)
        
        top_bar_layout.addStretch()
        
        self.model_dropdown = QComboBox()
        self.model_dropdown.setObjectName("model_dropdown")
        self.populate_model_dropdown()
        top_bar_layout.addWidget(self.model_dropdown)
        
        self.safe_mode_checkbox = QCheckBox("Safe Mode")
        self.safe_mode_checkbox.setStyleSheet("color: #c0caf5; font-weight: bold; margin-left: 10px;")
        self.safe_mode_checkbox.setToolTip("Disable file writing and shell command tools completely.")
        is_safe = get_preference("safe_mode", "true") == "true"
        self.safe_mode_checkbox.setChecked(is_safe)
        self.safe_mode_checkbox.stateChanged.connect(self.on_safe_mode_changed)
        top_bar_layout.addWidget(self.safe_mode_checkbox)

        chat_layout.addWidget(top_bar_widget)
        
        # Main Message Feed (QScrollArea with QVBoxLayout)
        self.chat_feed_scroll_area = QScrollArea()
        self.chat_feed_scroll_area.setObjectName("chat_feed_scroll_area")
        self.chat_feed_scroll_area.setWidgetResizable(True)
        self.chat_feed_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_feed_scroll_area.viewport().setStyleSheet("background-color: #16161e;")

        self.chat_feed_content_widget = QWidget()
        self.chat_feed_content_widget.setObjectName("chat_container")
        self.chat_feed_layout = QVBoxLayout(self.chat_feed_content_widget)
        self.chat_feed_layout.setContentsMargins(10, 10, 10, 10)
        self.chat_feed_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
         
        self.chat_feed_scroll_area.setWidget(self.chat_feed_content_widget)
        chat_layout.addWidget(self.chat_feed_scroll_area, stretch=1)
        
        # Input Bar
        input_bar_widget = QFrame()
        input_bar_widget.setObjectName("input_bar_widget")
        input_bar_layout = QHBoxLayout(input_bar_widget)
        input_bar_layout.setContentsMargins(18, 10, 18, 16)

        self.input_box = AutoResizingTextEdit()
        self.input_box.text_changed_height.connect(self.adjust_input_bar_height)
        self.input_box.submit_pressed.connect(self.send_message)
        self.input_box.setFixedHeight(50) 
        input_bar_layout.addWidget(self.input_box)
        
        self.voice_btn = QPushButton("🎙")
        self.voice_btn.setObjectName("voice_btn")
        self.voice_btn.setFixedSize(40, 40)
        self.voice_btn.setCheckable(True)
        self.voice_btn.setToolTip("Hold to talk")
        self.voice_btn.pressed.connect(self.start_voice_capture)
        self.voice_btn.released.connect(self.finish_voice_capture)
        self.voice_btn.setStyleSheet("QPushButton { background: #3b4261; color: white; border: none; border-radius: 10px; } QPushButton:checked { background: #ff5555; }")
        input_bar_layout.addWidget(self.voice_btn)

        self.screen_btn = QPushButton("📸")
        self.screen_btn.setObjectName("screen_btn")
        self.screen_btn.setFixedSize(40, 40)
        self.screen_btn.setToolTip("Describe the current screen")
        self.screen_btn.clicked.connect(self.on_screen_snapshot_clicked)
        input_bar_layout.addWidget(self.screen_btn)

        self.window_btn = QPushButton("🪟")
        self.window_btn.setObjectName("window_btn")
        self.window_btn.setFixedSize(40, 40)
        self.window_btn.setToolTip("Describe the active window")
        self.window_btn.clicked.connect(self.on_active_window_snapshot_clicked)
        input_bar_layout.addWidget(self.window_btn)

        self.send_btn = QPushButton("➤")
        self.send_btn.setObjectName("send_btn")
        self.send_btn.setFixedSize(40, 40)
        self.send_btn.clicked.connect(self.send_message)
        input_bar_layout.addWidget(self.send_btn)
        
        chat_layout.addWidget(input_bar_widget, stretch=0)
        splitter.addWidget(chat_widget)
        
        splitter.setSizes([250, 750])
        
        self.refresh_sidebar()
        
        # Load the latest session instead of spamming a new one
        sessions = get_sessions_with_counts()
        if sessions:
            # We must load it properly
            self.current_session_id = sessions[0]["id"]
            # Find the corresponding list item and select it
            for i in range(self.session_list.count()):
                item = self.session_list.item(i)
                if item.data(Qt.ItemDataRole.UserRole) == self.current_session_id:
                    self.session_list.setCurrentItem(item)
                    self.load_selected_session(item)
                    break
        else:
            self.current_session_id = None
            



    def toggle_sidebar(self):
        self.sidebar_widget.setVisible(not self.sidebar_widget.isVisible())

    def delete_session_handler(self, session_id: str):
        from cat_talker.db import delete_session
        delete_session(session_id)
        if self.current_session_id == session_id:
            self.current_session_id = None
            while self.chat_feed_layout.count() > 0:
                item = self.chat_feed_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            self.chat_history = []
            
            self.session_title_label.setText("<b>Chat with Assistant</b>")
            
            sessions = get_sessions_with_counts()
            if sessions:
                self.current_session_id = sessions[0]["id"]
                messages = get_messages(self.current_session_id)
                self.chat_history = messages
                display_title = sessions[0]["title"]
                if display_title == "New Chat":
                    display_title = get_session_title_preview(self.current_session_id, max_len=24)
                self.session_title_label.setText(f"<b>{display_title}</b>")
                
                # Render messages
                while self.chat_feed_layout.count() > 0:
                    item = self.chat_feed_layout.takeAt(0)
                    if item.widget():
                        item.widget().deleteLater()
                        
                for msg in messages:
                    is_error_msg = msg["content"].startswith("ERROR:")
                    bubble = MessageBubble(msg["role"], msg["content"], is_error=is_error_msg)
                    self.chat_feed_layout.addWidget( bubble)
                
                QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))
        
        self.refresh_sidebar()

    def adjust_input_bar_height(self):
        pass # Layout handles this dynamically
    


    def populate_model_dropdown(self):
        self.model_dropdown.clear()
        models = get_installed_models()
        display_models = []
        for model_id in models:
            display_models.append(self.model_name_map.get(model_id, model_id)) 
        self.model_dropdown.addItems(display_models)
        
        saved_model = get_preference("default_model", "")
        if saved_model:
            display_name = self.model_name_map.get(saved_model, saved_model)
            index = self.model_dropdown.findText(display_name)
            if index >= 0:
                self.model_dropdown.setCurrentIndex(index)
        
        # Connect change event
        try: self.model_dropdown.currentTextChanged.disconnect()
        except: pass
        self.model_dropdown.currentTextChanged.connect(self.on_model_changed)

    def on_model_changed(self, model_display_name):
        raw_model_id = self.reverse_model_name_map.get(model_display_name, model_display_name)
        set_preference("default_model", raw_model_id)

    def refresh_sidebar(self):

        self.session_list.clear()
        sessions = get_sessions_with_counts()
        
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        
        today_sessions = []
        yesterday_sessions = []
        older_sessions = []

        for s in sessions:
            session_date = datetime.datetime.strptime(s["created_at"], "%Y-%m-%d %H:%M:%S").date()
            if session_date == today:
                today_sessions.append(s)
            elif session_date == yesterday:
                yesterday_sessions.append(s)
            else:
                older_sessions.append(s)
        
        def add_session_group(title: str, session_list_data: List[Dict[str, Any]]):
            if session_list_data:
                group_item = QListWidgetItem()
                group_item.setFlags(group_item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
                self.session_list.addItem(group_item)
                group_widget = QLabel(f"-- {title} --")
                group_widget.setStyleSheet("color: #7aa2f7; font-size: 11px; font-weight: bold; padding: 6px 5px; background: transparent;")
                group_item.setSizeHint(QSize(200, 30))
                self.session_list.setItemWidget(group_item, group_widget)
                
                for s in session_list_data:
                    display_title = s["title"]
                    if display_title == "New Chat":
                        display_title = get_session_title_preview(s["id"], max_len=24)
                    
                    item = QListWidgetItem(self.session_list)
                    item.setData(Qt.ItemDataRole.UserRole, s["id"])
                    is_active = (s["id"] == self.current_session_id)
                    if is_active:
                        item.setData(Qt.ItemDataRole.WhatsThisRole, "active-session")
                    row_widget = SessionRowWidget(s["id"], display_title, is_active)
                    row_widget.delete_clicked.connect(self.delete_session_handler)
                    item.setSizeHint(QSize(row_widget.sizeHint().width(), 38))
                    self.session_list.setItemWidget(item, row_widget)

        add_session_group("Today", today_sessions)
        add_session_group("Yesterday", yesterday_sessions)
        add_session_group("Older", older_sessions)


    def start_new_chat(self):
        # Don't create if current is already empty to prevent spam
        if self.current_session_id is not None and not self.chat_history:
            return
            
        selected_model_display_name = self.model_dropdown.currentText()
        raw_model_id = self.reverse_model_name_map.get(selected_model_display_name, selected_model_display_name or "qwen-6gb:latest")
        self.current_session_id = create_session(raw_model_id)
        
        while self.chat_feed_layout.count() > 0:
            item = self.chat_feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.chat_history = []
        self.refresh_sidebar()
         


    def load_selected_session(self, item: QListWidgetItem):
        session_id = item.data(Qt.ItemDataRole.UserRole)
        if session_id is None: 
            return
        if not isinstance(session_id, str):
            return # Should not happen with current data types, but for safety

        self.current_session_id = session_id
        self.session_title_label.setText(f"<b>{item.text()}</b>")
        messages = get_messages(session_id)
        self.chat_history = messages
        
        while self.chat_feed_layout.count() > 0:
            item = self.chat_feed_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for msg in messages:
            is_error_msg = msg["content"].startswith("ERROR:")
            bubble = MessageBubble(msg["role"], msg["content"], is_error=is_error_msg)
            self.chat_feed_layout.addWidget( bubble)
        
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))
        self.refresh_sidebar() 


    def set_voice_button_state(self, state: str):
        state = state.lower()
        if state == "recording":
            self.voice_btn.setChecked(True)
            self.voice_btn.setText("🔴 Recording")
            self.voice_btn.setToolTip("Recording audio... release to stop")
            self.voice_btn.setStyleSheet("QPushButton { background: #ff5555; color: white; border: none; border-radius: 10px; padding-left: 5px; padding-right: 5px; }")
            self.input_box.setDisabled(True)
            self.input_box.setPlaceholderText("Listening...")
            return

        if state == "processing":
            self.voice_btn.setChecked(True)
            self.voice_btn.setText("⏳ Processing")
            self.voice_btn.setToolTip("Transcribing audio...")
            self.voice_btn.setStyleSheet("QPushButton { background: #ffb86c; color: #11111b; border: none; border-radius: 10px; padding-left: 5px; padding-right: 5px; }")
            self.input_box.setDisabled(True)
            self.input_box.setPlaceholderText("Transcribing...")
            return

        self.voice_btn.setChecked(False)
        self.voice_btn.setText("🎙")
        self.voice_btn.setToolTip("Hold to talk")
        self.voice_btn.setStyleSheet("QPushButton { background: #3b4261; color: white; border: none; border-radius: 10px; }")
        self.input_box.setDisabled(False)
        self.input_box.setPlaceholderText("Type a message or use commands like 'open browser'...")

    def start_voice_capture(self):
        if self.voice_in_progress:
            return
        self.voice_in_progress = True
        self.voice_cancel_requested = False
        self.set_voice_button_state("recording")

        self.voice_worker = VoiceCaptureWorker(record_seconds=4)
        self.voice_worker.finished_signal.connect(self.on_voice_worker_finished)
        self.voice_worker.start()

    def on_voice_worker_finished(self, transcript: str):
        if not self.voice_in_progress:
            return

        self.voice_in_progress = False
        if self.voice_cancel_requested:
            self.set_voice_button_state("idle")
            self.add_system_message_to_feed("Voice capture cancelled.", is_error=False)
            self.voice_cancel_requested = False
            return

        self.set_voice_button_state("processing")
        QTimer.singleShot(250, lambda: self.set_voice_button_state("idle"))

        clean_transcript = (transcript or "").strip()
        if clean_transcript:
            if clean_transcript.lower().startswith(("no microphone", "voice input", "speech-to-text backend", "transcription failed", "no valid recording")):
                self.add_system_message_to_feed(f"Voice status: {clean_transcript}", is_error=False)
            else:
                self.input_box.setPlainText(clean_transcript)
                self.add_system_message_to_feed(f"Voice capture result: {clean_transcript}", is_error=False)
        else:
            self.add_system_message_to_feed("Voice capture ended without a transcript.", is_error=False)

    def finish_voice_capture(self, transcript: str = ""):
        if not self.voice_in_progress:
            return

        self.voice_cancel_requested = True
        self.set_voice_button_state("idle")
        self.voice_in_progress = False

        if self.voice_worker is not None and self.voice_worker.isRunning():
            self.voice_worker.wait(250)

        if transcript and transcript.strip():
            self.on_voice_worker_finished(transcript)
            return

        self.add_system_message_to_feed("Voice capture cancelled before transcription completed.", is_error=False)

    def on_voice_status_clicked(self):
        self.start_voice_capture()
    def on_screen_snapshot_clicked(self):
        summary = describe_current_screen()
        self.add_system_message_to_feed(f"### 🖥️ Full Screen Analysis\n\n{summary}", is_error=False)

    def on_active_window_snapshot_clicked(self):
        summary = describe_active_window()
        self.add_system_message_to_feed(f"### 🪟 Active Window Content\n\n{summary}", is_error=False)

    def send_message(self):
        text = self.input_box.toPlainText().strip()
        if not text:
            return

        plan = self.orchestrator.decide(text)
        route_context = self.orchestrator.build_context_instruction(plan)

        if self.pending_action_id:
            action_id = self.pending_action_id
            self.pending_action_id = None
            self.input_box.clear()

            response_bubble = MessageBubble("user", text)
            self.chat_feed_layout.addWidget(response_bubble)
            QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

            if text.lower() in ['y', 'yes']:
                try:
                    res = approve_action(action_id)
                    system_msg = f"Action Executed. Result:\n```\n{res}\n```"
                    self.add_system_message_to_feed(system_msg, is_error=False)
                except Exception as e:
                    self.on_error_occurred("Tool Execution Error", f"Failed to execute approved action: {e}")
            else:
                reject_action(action_id)
                self.add_system_message_to_feed("Action Rejected by user.", is_error=False)
            return

        if text.lower() in ["voice", "voice status", "microphone", "check voice"]:
            self.add_system_message_to_feed(voice_input_status(), is_error=False)
            return

        screen_phrases = [
            "describe what's on screen",
            "describe what is on screen",
            "what's on screen",
            "what is on screen",
            "describe screen",
            "analyze screen",
            "look at the screen",
            "screen description",
        ]
        if any(p in text.lower() for p in screen_phrases):
            self.add_system_message_to_feed(f"### 🖥️ Full Screen Analysis\n\n{describe_current_screen()}", is_error=False)
            return

        if any(p in text.lower() for p in ["active window", "current window", "describe window", "window description", "focused window"]):
            self.add_system_message_to_feed(f"### 🪟 Active Window Content\n\n{describe_active_window()}", is_error=False)
            return

        if text.lower() in ["screenshot", "snapshot", "screen capture", "capture screen"]:
            self.on_screen_snapshot_clicked()
            return

        if text.lower().startswith("transcribe ") or "listen" in text.lower():
            self.add_system_message_to_feed(f"Voice capture result: {transcribe_audio_from_microphone(record_seconds=4)}", is_error=False)
            return

        if plan.route == "desktop_action":
            self.input_box.clear()
            lower = text.lower()
            if any(marker in lower for marker in ["open website", "go to ", "visit ", "open browser"]):
                target = text
                if "go to" in lower:
                    target = text.split("go to", 1)[1].strip()
                elif "visit" in lower:
                    target = text.split("visit", 1)[1].strip()
                elif "open website" in lower:
                    target = text.split("open website", 1)[1].strip()
                self.confirm_action(
                    title="Open website",
                    prompt=f"Open website: {target}",
                    details=f"This will launch {target} in the default browser.",
                    action=lambda: handle_desktop_action(text),
                )
                return

            if "open file" in lower or ("open " in lower and "." in lower):
                target = text.replace("open file", "", 1).replace("open ", "", 1).strip()
                self.confirm_action(
                    title="Open file",
                    prompt=f"Open file: {target}",
                    details=f"This will launch the file on disk: {target}",
                    action=lambda: handle_desktop_action(text),
                )
                return

            result = handle_desktop_action(text)
            self.add_system_message_to_feed(f"Desktop action result:\n```\n{result}\n```", is_error=False)
            return

        # Auto-create session if none
        if self.current_session_id is None:
            selected_model_display_name = self.model_dropdown.currentText()
            raw_model_id = self.reverse_model_name_map.get(selected_model_display_name, selected_model_display_name or "qwen-6gb:latest")
            self.current_session_id = create_session(raw_model_id)
            self.refresh_sidebar()

        if plan.route == "delegate":
            route_note = {"role": "system", "content": route_context}
            if route_note not in self.chat_history:
                self.chat_history.append(route_note)
                insert_message(self.current_session_id, "system", route_context)

        self.input_box.clear()

        insert_message(self.current_session_id, "user", text)
        self.chat_history.append({"role": "user", "content": text})

        user_bubble = MessageBubble("user", text)
        self.chat_feed_layout.addWidget(user_bubble)
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

        ai_bubble = MessageBubble("assistant", "")
        self.chat_feed_layout.addWidget(ai_bubble)
        self.current_ai_response_bubble_text_display = ai_bubble.text_display
        self.current_ai_response_content = ""

        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

        selected_model_display_name = self.model_dropdown.currentText()
        selected_model_id = self.reverse_model_name_map.get(selected_model_display_name, selected_model_display_name or "qwen-6gb:latest")

        self.chat_worker = ChatWorker(
            selected_model_id,
            self.chat_history,
            visualizer_state_emitter=self.visualizer_state_emitter,
            visualizer_glow_emitter=self.visualizer_glow_emitter,
        )
        self.chat_worker_thread = threading.Thread(target=self.chat_worker.run, daemon=True)

        self.chat_worker.chunk_received.connect(self.on_chunk)
        self.chat_worker.finished.connect(self.on_finished)
        self.chat_worker.error_occurred.connect(self.on_error_occurred)

        self.chat_worker_thread.start()

    def on_chunk(self, chunk: str):
        self.current_ai_response_content += chunk
        if self.current_ai_response_bubble_text_display and not sip.isdeleted(self.current_ai_response_bubble_text_display):
            self.current_ai_response_bubble_text_display.setMarkdown(self.current_ai_response_content)
            # Find the parent bubble and adjust its height
            parent_bubble = self.current_ai_response_bubble_text_display.parent()
            if hasattr(parent_bubble, 'adjust_height'):
                parent_bubble.adjust_height()
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))


    def on_finished(self, full_response: str):
        if self.current_session_id is None:
            # This should ideally not happen if start_new_chat is called correctly
            print("Warning: on_finished called with no active session_id.")
            return
            
        insert_message(self.current_session_id, "assistant", full_response)
        self.chat_history.append({"role": "assistant", "content": full_response})
        
        sessions = get_sessions_with_counts()
        current_session = next((s for s in sessions if s["id"] == self.current_session_id), None)
        if current_session and current_session["title"] == "New Chat":
            if self.chat_history:
                first_user_message = next((msg["content"] for msg in self.chat_history if msg["role"] == "user"), "")
                if first_user_message:
                    title_words = first_user_message.split()[:5] 
                    new_title = " ".join(title_words).replace("\n", " ")
                    if len(new_title.strip()) > 0:
                        update_session_title(self.current_session_id, new_title)
                        self.refresh_sidebar()

        resp = full_response
        read_match = re.search(r'<read>(.*?)</read>', resp, re.DOTALL)
        if read_match:
            try:
                res = read_file(read_match.group(1).strip())
                self.add_system_message_to_feed(f"Read file result:\n```\n{res}\n```", is_error=False)
            except Exception as e:
                self.on_error_occurred("Tool Error", f"Failed to read file: {e}")
            return
            
        search_match = re.search(r'<search>(.*?)</search>', resp, re.DOTALL)
        if search_match:
            try:
                res = ripgrep_search(search_match.group(1).strip())
                self.add_system_message_to_feed(f"Search result:\n```\n{res}\n```", is_error=False)
            except Exception as e:
                self.on_error_occurred("Tool Error", f"Failed to perform search: {e}")
            return
            
        bash_match = re.search(r'<bash>(.*?)</bash>', resp, re.DOTALL)
        if bash_match:
            cmd = bash_match.group(1).strip()
            action_id = str(uuid.uuid4())
            prompt = execute_bash(action_id, cmd)
            self.present_approval(action_id, prompt)
            return
            
        write_match = re.search(r'<write path="(.*?)">(.*?)</write>', resp, re.DOTALL)
        if write_match:
            path = write_match.group(1).strip()
            content = write_match.group(2).strip()
            action_id = str(uuid.uuid4())
            prompt = write_file(action_id, path, content)
            self.present_approval(action_id, prompt)
            return

    def on_error_occurred(self, title: str, message: str):
        error_box = ErrorBox(title, message)
        self.chat_feed_layout.addWidget( error_box)
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))
        if self.current_ai_response_bubble_text_display:
            self.current_ai_response_bubble_text_display.setProperty("class", "error-bubble")
            self.current_ai_response_bubble_text_display.setStyleSheet(QSS_STYLES) 


    def add_system_message_to_feed(self, system_msg: str, is_error: bool):
        if self.current_session_id is None:
            print("Warning: Attempted to add system message with no active session.")
            return

        self.chat_history.append({"role": "system", "content": system_msg})
        insert_message(self.current_session_id, "system", system_msg)
        system_bubble = MessageBubble("system", system_msg, is_error=is_error)
        self.chat_feed_layout.addWidget( system_bubble)
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

        if not is_error:
            selected_model_display_name = self.model_dropdown.currentText()
            selected_model_id = self.reverse_model_name_map.get(selected_model_display_name, selected_model_display_name or "qwen-6gb:latest")
            
            ai_bubble = MessageBubble("assistant", "")
            self.chat_feed_layout.addWidget( ai_bubble)
            self.current_ai_response_bubble_text_display = ai_bubble.text_display
            self.current_ai_response_content = ""

            self.chat_worker = ChatWorker(
                selected_model_id, 
                self.chat_history, 
                visualizer_state_emitter=self.visualizer_state_emitter, 
                visualizer_glow_emitter=self.visualizer_glow_emitter
            )
            self.chat_worker_thread = threading.Thread(target=self.chat_worker.run, daemon=True)
            self.chat_worker.chunk_received.connect(self.on_chunk)
            self.chat_worker.finished.connect(self.on_finished)
            self.chat_worker.error_occurred.connect(self.on_error_occurred)
            self.chat_worker_thread.start()


    def confirm_action(self, title: str, prompt: str, details: str, action):
        from PyQt6.QtWidgets import QDialog
        
        kind = "unknown"
        risk_level = "low"
        if "bash" in title.lower() or "shell" in title.lower() or "command" in title.lower():
            risk_level = "high"
            kind = "bash"
        elif "write file" in title.lower() or "delete" in title.lower() or "open file" in title.lower():
            risk_level = "medium"
            kind = "write"
        elif "open website" in title.lower():
            kind = "browser"

        if kind != "unknown" and get_preference(f"allow_{kind}", "false") == "true":
            try:
                response = action()
                self.add_system_message_to_feed(f"Auto-approved. Result:\n```\n{response}\n```", is_error=False)
            except Exception as exc:
                self.on_error_occurred("Action Error", f"Failed to complete auto-approved action: {exc}")
            return
            
        dialog = ApprovalDialog(title, prompt, details, risk_level, self)
        result = dialog.exec()

        if result == QDialog.DialogCode.Accepted:
            if dialog.is_always_allow_checked() and kind != "unknown":
                set_preference(f"allow_{kind}", "true")
                self.add_system_message_to_feed(f"Saved preference: always allow {kind} actions.", is_error=False)
            try:
                response = action()
                self.add_system_message_to_feed(f"Action confirmed. Result:\n```\n{response}\n```", is_error=False)
            except Exception as exc:
                self.on_error_occurred("Action Error", f"Failed to complete approved action: {exc}")
            return

        self.add_system_message_to_feed("Action cancelled by user.", is_error=False)

    def present_approval(self, action_id: str, prompt: str):
        if self.current_session_id is None:
            print("Warning: Attempted to present approval with no active session.")
            return

        approval_msg = f"Approval Needed:\n{prompt}"
        approval_bubble = MessageBubble("system", approval_msg, is_error=False)
        self.chat_feed_layout.addWidget(approval_bubble)
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

        dialog = QMessageBox(self)
        dialog.setWindowTitle("Approve action")
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText("Review this action before it runs")
        dialog.setInformativeText(prompt)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)

        result = dialog.exec()
        self.pending_action_id = action_id

        if result == QMessageBox.StandardButton.Ok:
            try:
                res = approve_action(action_id)
                self.pending_action_id = None
                self.add_system_message_to_feed(f"Action Executed. Result:\n```\n{res}\n```", is_error=False)
            except Exception as e:
                self.pending_action_id = None
                self.on_error_occurred("Tool Execution Error", f"Failed to execute approved action: {e}")
            return

        reject_action(action_id)
        self.pending_action_id = None
        self.add_system_message_to_feed("Action Rejected by user.", is_error=False)

    def on_safe_mode_changed(self, state):
        is_safe = self.safe_mode_checkbox.isChecked()
        set_preference("safe_mode", "true" if is_safe else "false")
        self.orchestrator.safe_mode = is_safe
        mode_text = "enabled. I will no longer rewrite files or run shell commands without being explicitly commanded as a local tool." if is_safe else "disabled. I now have agentic write/shell permissions again."
        self.add_system_message_to_feed(f"Safe Mode {mode_text}", is_error=False)


def run_app():
    app = QApplication(sys.argv)
    dummy_emitter = DummyVisualizerEmitter()
    w = ScratchpadWindow(
        visualizer_state_emitter=dummy_emitter.state_signal,
        visualizer_glow_emitter=dummy_emitter.glow_signal,
    )
    w.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(run_app())
