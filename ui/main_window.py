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

from tools.browser import (
    analyze_screen_image,
    build_approval_message,
    capture_screen_snapshot,
    describe_active_window,
    describe_current_screen,
    transcribe_audio_from_microphone,
    voice_input_status,
)
from memory.sqlite import get_sessions, get_messages, create_session, insert_message, update_session_title, get_sessions_with_counts, get_session_title_preview, get_preference, set_preference
from tools.desktop import handle_desktop_action
from providers import get_installed_models, chat_completion_stream
from ui.widgets import AutoResizingTextEdit, MarkdownTextBrowser, SessionRowWidget, DummyVisualizerEmitter, MessageBubble
from ui.chat_view import ChatWorker, TranscriptionWorker
from ui.approval_dialog import ApprovalDialog
from agent.planner import AgentOrchestrator


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




from agent.events import bus, AgentEvent

class GlobalAgentListener(QObject):
    event_signal = pyqtSignal(AgentEvent)

    def __init__(self):
        super().__init__()
        bus.subscribe(self.handle_event)
        
    def handle_event(self, event: AgentEvent):
        self.event_signal.emit(event)

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

        self._setup_unix_signals()
        
        self.agent_listener = GlobalAgentListener()
        self.agent_listener.event_signal.connect(self.on_agent_event)
        
        self.current_task_bubble = None
        self.current_task_steps = []


        
        # Standalone GeminiLive background auto-connection was removed in Phase 5.
        # Primary pipeline is Microphone UI toggle -> Transcription -> Standard AgentRuntime.
        self.live_agent = None

        self.orchestrator = AgentOrchestrator(default_model="gemini-3.1-flash-lite", safe_mode=(get_preference("safe_mode", "true") == "true"))

        self.model_name_map = {
            "gemini-3.1-flash-live-preview": "Gemini Live (Cloud)",
            "gemini-3.1-flash-lite": "Gemini 3.1 Flash Lite (Heavy)",
            "gemini-2.5-flash-lite": "Gemini 2.5 Flash Lite (Heavy)",
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
        
        self.heavy_agent_status_label = QLabel("● Heavy Agent: Idle")
        self.heavy_agent_status_label.setStyleSheet("color: #a6adc8; font-weight: bold;")
        top_bar_layout.addWidget(self.heavy_agent_status_label)
        
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

        # QSplitter to allow resizing the terminal drawer

        self.chat_splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Move scroll area into splitter
        self.chat_splitter.addWidget(self.chat_feed_scroll_area)
        
        # Terminal Drawer
        self.terminal_drawer = QWidget()
        self.terminal_drawer.setMinimumHeight(40)
        self.terminal_drawer.setStyleSheet("background-color: #1e1e2e; border-top: 1px solid #313244;")
        terminal_layout = QVBoxLayout(self.terminal_drawer)
        terminal_layout.setContentsMargins(0, 0, 0, 0)
        terminal_layout.setSpacing(0)
        
        self.terminal_toggle_btn = QPushButton("▼ Heavy Agent Logs")
        self.terminal_toggle_btn.setStyleSheet("text-align: left; padding: 5px; background: #313244; color: #cdd6f4; border: none;")
        self.terminal_toggle_btn.clicked.connect(self.toggle_terminal_drawer)
        terminal_layout.addWidget(self.terminal_toggle_btn)
        
        self.terminal_text_area = MarkdownTextBrowser()
        self.terminal_text_area.setStyleSheet("background-color: #11111b; color: #a6adc8; padding: 5px; font-family: monospace;")
        self.terminal_text_area.hide()
        terminal_layout.addWidget(self.terminal_text_area)
        
        self.chat_splitter.addWidget(self.terminal_drawer)
        self.chat_splitter.setSizes([800, 40]) # Default closed size
        
        chat_layout.addWidget(self.chat_splitter, stretch=1)
        
        # Polling timer for heavy agent logs
        from PyQt6.QtCore import QTimer
        self.last_log_size = 0

        
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
        from memory.sqlite import delete_session
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
        import os
        os.environ["HEAVY_AGENT_MODEL"] = raw_model_id
        
        # If it's a live API model, let's also update the live agent and reconnect if needed later
        if hasattr(self, 'live_agent') and self.live_agent:
            if "live" in raw_model_id and self.live_agent.current_model != raw_model_id:
                self.live_agent.switch_model(raw_model_id)

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
        if hasattr(self, 'live_agent') and self.live_agent:
            self.live_agent.is_recording = True
            self.set_voice_button_state("recording")
            self.voice_in_progress = True
            return
            
        if self.voice_in_progress:

            return
        
        self.voice_in_progress = True
        self.voice_cancel_requested = False
        self.set_voice_button_state("recording")
        
        from tools.browser import start_continuous_recording
        self.voice_recording_proc, self.voice_audio_path = start_continuous_recording()

        # Fallback if no backend
        if not self.voice_recording_proc:
            self.voice_in_progress = False
            self.set_voice_button_state("idle")
            self.add_system_message_to_feed("Voice capture failed. Missing `arecord`, `ffmpeg`, or `sox`.", is_error=True)
            return

        self.voice_start_time = datetime.datetime.now()

    def on_voice_worker_finished(self, transcript: str):
        if not self.voice_in_progress:
            return

        self.voice_in_progress = False
        if self.voice_cancel_requested:
            self.set_voice_button_state("idle")
            self.add_system_message_to_feed("Voice capture cancelled.", is_error=False)
            self.voice_cancel_requested = False
            return

        self.set_voice_button_state("idle")

        clean_transcript = (transcript or "").strip()
        if clean_transcript:
            if clean_transcript.lower().startswith(("no microphone", "voice input", "speech-to-text", "transcription failed", "no valid", "no clear")):
                self.add_system_message_to_feed(f"Voice status: {clean_transcript}", is_error=False)
            else:
                self.input_box.setPlainText(clean_transcript)
                self.add_system_message_to_feed(f"Voice capture result: {clean_transcript}", is_error=False)
                # Auto send to the assistant flow!
                self.send_message()
        else:
            self.add_system_message_to_feed("Voice capture ended without a transcript.", is_error=False)


    def finish_voice_capture(self, force_cancel: bool = False):
        if hasattr(self, 'live_agent') and self.live_agent:
            self.live_agent.is_recording = False
            self.set_voice_button_state("idle")
            self.voice_in_progress = False
            return
            
        if not self.voice_in_progress:

            return

        from tools.browser import stop_continuous_recording

        if hasattr(self, 'voice_recording_proc'):
            stop_continuous_recording(self.voice_recording_proc)

        start_time = getattr(self, 'voice_start_time', datetime.datetime.now())
        elapsed = (datetime.datetime.now() - start_time).total_seconds()

        if force_cancel or elapsed < 0.5:
            self.voice_cancel_requested = True
            self.voice_in_progress = False
            self.set_voice_button_state("idle")
            self.add_system_message_to_feed("Voice capture cancelled (held too briefly).", is_error=False)
            return

        self.set_voice_button_state("processing")
        self.voice_in_progress = False

        audio_path = getattr(self, 'voice_audio_path', None)
        if not audio_path:
            self.add_system_message_to_feed("Voice capture failed: no audio file was generated.", is_error=True)
            return

        self.transcription_worker = TranscriptionWorker(audio_path=audio_path)
        self.transcription_worker.finished_signal.connect(self.on_voice_worker_finished)
        self.transcription_worker.start()

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
            ctx = f"### 🖥️ Full Screen Analysis\n\n{describe_current_screen()}"
            self.add_system_message_to_feed(ctx, is_error=False)
            # Do NOT return. Let the AI process it.
            if "route_context" not in locals() and "route_context" not in globals():
                route_context = ctx
            else:
                route_context += f"\n\n{ctx}"


        if any(p in text.lower() for p in ["active window", "current window", "describe window", "window description", "focused window"]):
            ctx = f"### 🪟 Active Window Content\n\n{describe_active_window()}"
            self.add_system_message_to_feed(ctx, is_error=False)
            # Do NOT return. Let the AI process it.
            if "route_context" not in locals() and "route_context" not in globals():
                route_context = ctx
            else:
                route_context += f"\n\n{ctx}"


        if text.lower() in ["screenshot", "snapshot", "screen capture", "capture screen"]:
            ctx = f"### 🖥️ Screen Analysis\n\n{describe_current_screen()}"
            self.add_system_message_to_feed(ctx, is_error=False)
            # Do NOT return.

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

    def on_safe_mode_changed(self, state):
        is_safe = self.safe_mode_checkbox.isChecked()
        set_preference("safe_mode", "true" if is_safe else "false")
        self.orchestrator.safe_mode = is_safe
        mode_text = "enabled. I will no longer rewrite files or run shell commands without being explicitly commanded as a local tool." if is_safe else "disabled. I now have agentic write/shell permissions again."
        self.add_system_message_to_feed(f"Safe Mode {mode_text}", is_error=False)



    def _setup_unix_signals(self):
        import signal
        from PyQt6.QtCore import QTimer, QMetaObject, Qt, pyqtSlot
        
        self._signal_timer = QTimer(self)
        self._signal_timer.timeout.connect(lambda: None)
        self._signal_timer.start(100)
        
        def sigusr1_handler(signum, frame):
            QTimer.singleShot(0, self.start_voice_capture)
            
        def sigusr2_handler(signum, frame):
            QTimer.singleShot(0, self.finish_voice_capture_sig)
            
        def sigrtmin_handler(signum, frame):
            QTimer.singleShot(0, self.toggle_window_visibility)

        try:
            signal.signal(signal.SIGUSR1, sigusr1_handler)
            signal.signal(signal.SIGUSR2, sigusr2_handler)
            
            if hasattr(signal, 'SIGRTMIN'):
                signal.signal(signal.SIGRTMIN, sigrtmin_handler)
            else:
                signal.signal(signal.SIGWINCH, sigrtmin_handler)
        except Exception as e:
            print(f"Could not bind UNIX signals: {e}")

    from PyQt6.QtCore import pyqtSlot

    @pyqtSlot(AgentEvent)
    def on_agent_event(self, event: AgentEvent):
        # Update status bar
        if event.type == "LOG":
            msg = event.payload.get("msg", "")
            self.heavy_agent_status_label.setText(f"Status: {msg}")
            
        elif event.type == "TASK_STARTED":
            desc = event.payload.get("description", "Unknown Task")
            self.heavy_agent_status_label.setText("Status: Executing Task...")
            self.current_task_steps = []
            
            # Create a dedicated layout widget for the Task Panel
            from ui.chat_view import MessageBubble
            self.current_task_bubble = MessageBubble("system", f"<b>Task:</b> {desc}<br><ul></ul>", is_error=False)
            self.chat_feed_layout.addWidget(self.current_task_bubble)
            QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

        elif event.type in ["TOOL_REQUESTED", "TOOL_FINISHED", "APPROVAL_REQUIRED", "APPROVAL_GRANTED", "APPROVAL_REJECTED"]:
            tool_name = event.payload.get("tool_name", "")
            
            if event.type == "TOOL_REQUESTED":
                self.current_task_steps.append({"name": tool_name, "status": "running"})
                self.heavy_agent_status_label.setText(f"Status: Tool Requested -> {tool_name}")
                
            elif event.type == "TOOL_FINISHED":
                status = event.payload.get("status", "unknown")
                for step in reversed(self.current_task_steps):
                    if step["name"] == tool_name and step["status"] in ["running", "pending_approval"]:
                        step["status"] = "success" if status == "success" else "error"
                        break
                        
            elif event.type == "APPROVAL_REQUIRED":
                for step in reversed(self.current_task_steps):
                    if step["name"] == tool_name and step["status"] == "running":
                        step["status"] = "pending_approval"
                        break
                        
            elif event.type == "APPROVAL_GRANTED":
                for step in reversed(self.current_task_steps):
                    if step["status"] == "pending_approval":
                        step["status"] = "running"
                        break
                        
            elif event.type == "APPROVAL_REJECTED":
                for step in reversed(self.current_task_steps):
                    if step["status"] == "pending_approval":
                        step["status"] = "error"
                        break
            
            # Redraw the task bubble
            if self.current_task_bubble:
                html = "<b>Task Progress:</b><br><ul style='list-style-type: none; padding-left: 10px;'>"
                for step in self.current_task_steps:
                    icon = "⏳"
                    if step["status"] == "success": icon = "✅"
                    elif step["status"] == "error": icon = "❌"
                    elif step["status"] == "pending_approval": icon = "⚠️"
                    html += f"<li>{icon} {step['name']}</li>"
                html += "</ul>"
                self.current_task_bubble.text_browser.setHtml(html)

        if event.type == "APPROVAL_REQUIRED":
            approval_id = event.payload.get("approval_id")
            tool_name = event.payload.get("tool_name")
            reason = event.payload.get("reason", "")
            risk_level = event.payload.get("risk_level", "medium")
            arguments = event.payload.get("arguments", {})
            self.heavy_agent_status_label.setText(f"Status: Waiting for Approval ({tool_name})")
            
            from ui.approval_dialog import ApprovalDialog
            details = repr(arguments)
            dlg = ApprovalDialog(f"Approval Required: {tool_name}", reason, details, risk_level, parent=self)
            if dlg.exec():
                from agent.approvals import manager
                try:
                    res = manager.approve(approval_id)
                except Exception as e:
                    self.add_system_message_to_feed(f"Failed to execute approved action: {e}", is_error=True)
            else:
                from agent.approvals import manager
                try:
                    manager.reject(approval_id)
                except:
                    pass

        elif event.type == "TASK_COMPLETED":
            self.heavy_agent_status_label.setText("Status: Task Completed")
            res = event.payload.get("result", "")
            if res:
                self.add_system_message_to_feed(res, is_error=False)
            self.current_task_bubble = None

        elif event.type == "TASK_FAILED":
            err = event.payload.get("error", "Unknown error")
            self.heavy_agent_status_label.setText(f"Status: Task Failed")
            self.add_system_message_to_feed(f"Task Failed: {err}", is_error=True)
            self.current_task_bubble = None


            err = event.payload.get("error", "Unknown error")
            self.heavy_agent_status_label.setText(f"Status: Task Failed")
            self.add_system_message_to_feed(f"Task Failed: {err}", is_error=True)

    @pyqtSlot()
    def finish_voice_capture_sig(self):
        self.finish_voice_capture(force_cancel=False)

    def toggle_window_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.show()
            self.activateWindow()

    def toggle_terminal_drawer(self):
        visible = not self.terminal_text_area.isVisible()
        self.terminal_text_area.setVisible(visible)
        self.terminal_toggle_btn.setText("▼ Heavy Agent Logs" if visible else "▶ Heavy Agent Logs")
