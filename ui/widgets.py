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

from memory.sqlite import get_sessions, get_messages, create_session, insert_message, update_session_title, get_sessions_with_counts, get_session_title_preview, get_preference, set_preference


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
                color: {COLORS['error_fg']};
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
