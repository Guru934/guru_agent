import sys
from PyQt6 import sip
import threading
import datetime
import uuid
import html
from typing import Optional, List, Any, Dict

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QComboBox, QTextBrowser, QTextEdit,
    QPushButton, QListWidgetItem, QSplitter, QLabel,
    QScrollArea, QSizePolicy, QFrame, QApplication,
    QMessageBox, QSpacerItem, QStyleFactory, QToolButton, QCheckBox,
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
    transcribe_audio_from_microphone,
    voice_input_status,
)
from utils import get_logger
from memory.sqlite import get_sessions, get_messages, create_session, insert_message, update_session_title, get_sessions_with_counts, get_session_title_preview, get_preference, set_preference
from providers import get_installed_models
from ui.widgets import AutoResizingTextEdit, MarkdownTextBrowser, SessionRowWidget, DummyVisualizerEmitter, MessageBubble
from ui.chat_view import AgentWorker, TranscriptionWorker
from ui.approval_dialog import ApprovalDialog
from agent.capabilities import registry as capability_registry, CapabilityGrant
from agent.planner import AgentOrchestrator
from agent.assistant_bridge import AssistantBridge
from agent.assistant_events import AssistantEvent

# Toggle file for F1/F3 keybind integration
TOGGLE_FILE = "/tmp/guru_agent_toggle"


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
from agent.assistant_events import AssistantEvent

class GlobalAgentListener(QObject):
    event_signal = pyqtSignal(AgentEvent)

    def __init__(self):
        super().__init__()
        bus.subscribe(self.handle_event)
        
    def handle_event(self, event: AgentEvent):
        self.event_signal.emit(event)

    def close(self):
        bus.unsubscribe(self.handle_event)

class AssistantEventListener(QObject):
    """Thread-safe listener for AssistantEvents from the AssistantBridge."""
    assistant_event_signal = pyqtSignal(AssistantEvent)

    def __init__(self):
        super().__init__()

    def handle_event(self, event: AssistantEvent):
        self.assistant_event_signal.emit(event)

    def close(self):
        pass  # No global bus to unsubscribe from

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
        self.voice_in_progress = False
        self.voice_worker: Optional[QThread] = None
        self.voice_cancel_requested = False

        self._setup_toggle_watcher()
        
        self.agent_listener = GlobalAgentListener()
        self.agent_listener.event_signal.connect(self.on_agent_event)
        
        self.task_panels: Dict[str, Dict[str, Any]] = {}
        self.agent_workers: Dict[str, AgentWorker] = {}
        self.agent_worker_threads: Dict[str, threading.Thread] = {}
        self.agent_task_sessions: Dict[str, Optional[str]] = {}
        self.agent_response_bubbles: Dict[str, Any] = {}

        # Assistant Bridge for Gemini Live integration
        self.assistant_bridge = AssistantBridge()
        
        # Thread-safe listener for AssistantEvents
        self.assistant_event_listener = AssistantEventListener()
        self.assistant_event_listener.assistant_event_signal.connect(self._on_assistant_event)
        self.assistant_bridge.register_event_handler(self.assistant_event_listener.handle_event)

        # Gemini Live agent (started on-demand, not auto)
        self.live_agent = None
        self.live_agent_thread = None
        self.voice_assistant_active = False

        self.orchestrator = AgentOrchestrator(default_model="gemini-3.1-flash-lite", safe_mode=(get_preference("safe_mode", "true") == "true"))
        from agent.policy import engine as policy_engine
        policy_engine.safe_mode = self.orchestrator.safe_mode

        self.model_name_map = {
            "gemini-3.8-live": "Gemini 3.8 Live (Primary)",
            "gemini-3.1-flash-live-preview": "Gemini 3.1 Flash Live (Fallback)",
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
        sidebar_layout.addWidget(self.session_list, stretch=1)
        
        # Trust & Safety Panel
        self.trust_safety_panel = self._create_trust_safety_panel()
        sidebar_layout.addWidget(self.trust_safety_panel)
        
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
        
        # Voice Assistant toggle and connection state
        self.voice_assistant_btn = QPushButton("🎤 Voice Assistant")
        self.voice_assistant_btn.setCheckable(True)
        self.voice_assistant_btn.setToolTip("Start/Stop Gemini Live voice assistant")
        self.voice_assistant_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b4261;
                color: #c0caf5;
                border: none;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:checked {
                background-color: #50fa7b;
                color: #1a1b26;
            }
            QPushButton:hover:!checked {
                background-color: #4a5072;
            }
        """)
        self.voice_assistant_btn.clicked.connect(self.toggle_voice_assistant)
        top_bar_layout.addWidget(self.voice_assistant_btn)
        
        self.voice_connection_label = QLabel("🔴 Disconnected")
        self.voice_connection_label.setStyleSheet("color: #ff5555; font-weight: bold; font-size: 11px; margin-left: 5px;")
        top_bar_layout.addWidget(self.voice_connection_label)
        
        # Assistant State Indicator
        self.assistant_state_label = QLabel("🎙️ Idle")
        self.assistant_state_label.setStyleSheet("color: #8be9fd; font-weight: bold; font-size: 11px; margin-left: 10px;")
        top_bar_layout.addWidget(self.assistant_state_label)
        
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
        # If voice assistant is active, route to Gemini Live
        if self.voice_assistant_active and self.live_agent:
            self.live_agent.is_recording = True
            self.set_voice_button_state("recording")
            self.voice_in_progress = True
            return
            
        # Otherwise use local transcription (legacy path)
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
        # If voice assistant is active, route to Gemini Live
        if self.voice_assistant_active and self.live_agent:
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
        self.input_box.setPlainText("Describe what's on screen.")
        self.send_message()

    def on_active_window_snapshot_clicked(self):
        self.input_box.setPlainText("Describe the active window.")
        self.send_message()

    def send_message(self):
        text = self.input_box.toPlainText().strip()
        if not text:
            return

        plan = self.orchestrator.decide(text)
        route_context = self.orchestrator.build_context_instruction(plan)
        enable_tools = plan.route != "direct"

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
            enable_tools = True
            route_context += "\nFor this request, use the describe_current_screen tool to inspect the full screen."


        if any(p in text.lower() for p in ["active window", "current window", "describe window", "window description", "focused window"]):
            enable_tools = True
            route_context += "\nFor this request, use the describe_active_window tool to inspect the active window."


        if text.lower() in ["screenshot", "snapshot", "screen capture", "capture screen"]:
            enable_tools = True
            route_context += "\nFor this request, use the describe_current_screen tool."

        if text.lower().startswith("transcribe ") or "listen" in text.lower():
            self.add_system_message_to_feed(f"Voice capture result: {transcribe_audio_from_microphone(record_seconds=4)}", is_error=False)
            return

        # Auto-create session if none
        if self.current_session_id is None:
            selected_model_display_name = self.model_dropdown.currentText()
            raw_model_id = self.reverse_model_name_map.get(selected_model_display_name, selected_model_display_name or "qwen-6gb:latest")
            self.current_session_id = create_session(raw_model_id)
            self.refresh_sidebar()

        if plan.route in {"delegate", "desktop_action"}:
            route_note = {"role": "system", "content": route_context}
            if route_note not in self.chat_history:
                self.chat_history.append(route_note)
                insert_message(self.current_session_id, "system", route_context)

        self.input_box.clear()
        session_id = self.current_session_id
        history = [
            dict(message)
            for message in self.chat_history
            if message.get("role") in {"user", "assistant"}
        ]

        insert_message(session_id, "user", text)
        self.chat_history.append({"role": "user", "content": text})

        user_bubble = MessageBubble("user", text)
        self.chat_feed_layout.addWidget(user_bubble)
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

        ai_bubble = MessageBubble("assistant", "")
        self.chat_feed_layout.addWidget(ai_bubble)
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

        selected_model_display_name = self.model_dropdown.currentText()
        selected_model_id = self.reverse_model_name_map.get(selected_model_display_name, selected_model_display_name or "qwen-6gb:latest")
        task_id = str(uuid.uuid4())
        worker = AgentWorker(
            selected_model_id,
            text,
            history,
            task_id,
            route_context,
            self.visualizer_state_emitter,
            self.visualizer_glow_emitter,
            enable_tools,
        )
        self.agent_workers[task_id] = worker
        self.agent_task_sessions[task_id] = session_id
        self.agent_response_bubbles[task_id] = ai_bubble
        worker.state_finished.connect(self.on_agent_finished)
        worker_thread = threading.Thread(target=worker.run, daemon=True)
        self.agent_worker_threads[task_id] = worker_thread
        worker_thread.start()

    def on_agent_finished(self, state):
        task_id = state.task_id
        session_id = self.agent_task_sessions.pop(task_id, None)
        bubble = self.agent_response_bubbles.pop(task_id, None)
        self.agent_workers.pop(task_id, None)
        self.agent_worker_threads.pop(task_id, None)

        if state.error:
            if bubble is not None and not sip.isdeleted(bubble.text_display):
                bubble.text_display.setMarkdown(f"**Task failed:** {html.escape(state.error)}")
                bubble.text_display.setProperty("class", "error-bubble")
                bubble.text_display.setStyleSheet(QSS_STYLES)
            return

        response = state.final_answer
        if bubble is not None and not sip.isdeleted(bubble.text_display):
            bubble.text_display.setMarkdown(response)
            bubble.adjust_height()
        if session_id is None:
            self.on_error_occurred("Session Error", "Unable to save the agent response because the session is unavailable.")
            return

        insert_message(session_id, "assistant", response)
        if self.current_session_id == session_id:
            self.chat_history.append({"role": "assistant", "content": response})

        sessions = get_sessions_with_counts()
        current_session = next((item for item in sessions if item["id"] == session_id), None)
        if current_session and current_session["title"] == "New Chat":
            user_messages = [
                message["content"]
                for message in self.chat_history
                if message.get("role") == "user"
            ] if self.current_session_id == session_id else []
            if user_messages:
                new_title = " ".join(user_messages[0].split()[:5]).replace("\n", " ")
                if new_title.strip():
                    update_session_title(session_id, new_title)
                    if self.current_session_id == session_id:
                        self.refresh_sidebar()

    def on_error_occurred(self, title: str, message: str):
        error_box = ErrorBox(title, message)
        self.chat_feed_layout.addWidget( error_box)
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))
    def add_system_message_to_feed(self, system_msg: str, is_error: bool):
        if self.current_session_id is None:
            print("Warning: Attempted to add system message with no active session.")
            return

        self.chat_history.append({"role": "system", "content": system_msg})
        insert_message(self.current_session_id, "system", system_msg)
        system_bubble = MessageBubble("system", system_msg, is_error=is_error)
        self.chat_feed_layout.addWidget( system_bubble)
        QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))

    def on_safe_mode_changed(self, state):
        is_safe = self.safe_mode_checkbox.isChecked()
        set_preference("safe_mode", "true" if is_safe else "false")
        self.orchestrator.safe_mode = is_safe
        from agent.policy import engine as policy_engine
        policy_engine.safe_mode = is_safe
        mode_text = "enabled. I will no longer rewrite files or run shell commands without being explicitly commanded as a local tool." if is_safe else "disabled. I now have agentic write/shell permissions again."
        self.add_system_message_to_feed(f"Safe Mode {mode_text}", is_error=False)



    def _setup_toggle_watcher(self):
        """Set up file watcher for F1/F3 keybind toggle."""
        from PyQt6.QtCore import QFileSystemWatcher
        
        # Create toggle file if it doesn't exist
        try:
            with open(TOGGLE_FILE, 'w') as f:
                f.write("0")
        except Exception:
            pass
        
        self._toggle_watcher = QFileSystemWatcher([TOGGLE_FILE], self)
        self._toggle_watcher.fileChanged.connect(self._on_toggle_file_changed)
        self._last_toggle_time = 0
        print(f"[Toggle] Watching {TOGGLE_FILE} for visibility toggle requests", flush=True)

    def _on_toggle_file_changed(self, path: str):
        """Handle toggle file change - toggle window visibility."""
        import time
        current_time = time.time()
        # Debounce: ignore changes within 500ms
        if current_time - self._last_toggle_time < 0.5:
            return
        self._last_toggle_time = current_time
        
        try:
            with open(path, 'r') as f:
                content = f.read().strip()
            # Toggle on any content change
            print(f"[Toggle] File changed, toggling visibility", flush=True)
            self.toggle_window_visibility()
        except Exception as e:
            print(f"[Toggle] Error reading toggle file: {e}", flush=True)

    from PyQt6.QtCore import pyqtSlot

    @pyqtSlot(AgentEvent)
    def on_agent_event(self, event: AgentEvent):
        if event.type == "LOG":
            msg = event.payload.get("msg", "")
            self.heavy_agent_status_label.setText(f"Status: {msg}")
            return

        task_id = event.task_id
        if event.type == "TASK_STARTED":
            desc = event.payload.get("description", "Unknown Task")
            self.heavy_agent_status_label.setText("Status: Executing Task...")
            bubble = MessageBubble("system", "", is_error=False)
            self.task_panels[task_id] = {
                "bubble": bubble,
                "description": desc,
                "steps": [],
                "status": "running",
            }
            self.chat_feed_layout.addWidget(bubble)
            self._render_task_panel(task_id)
            QTimer.singleShot(10, lambda: self.chat_feed_scroll_area.verticalScrollBar().setValue(self.chat_feed_scroll_area.verticalScrollBar().maximum()))
            return

        panel = self.task_panels.get(task_id)
        if event.type in {"TOOL_REQUESTED", "TOOL_FINISHED", "APPROVAL_REQUIRED", "APPROVAL_GRANTED", "APPROVAL_REJECTED", "APPROVAL_TIMEOUT"} and panel:
            tool_name = event.payload.get("tool_name", "")
            steps = panel["steps"]

            if event.type == "TOOL_REQUESTED":
                steps.append({"name": tool_name, "status": "running"})
                self.heavy_agent_status_label.setText(f"Status: Tool Requested -> {tool_name}")
            elif event.type == "TOOL_FINISHED":
                status = event.payload.get("status", "unknown")
                for step in reversed(steps):
                    if step["name"] == tool_name and step["status"] in ["running", "pending_approval"]:
                        step["status"] = "success" if status == "success" else "error"
                        break
            elif event.type == "APPROVAL_REQUIRED":
                for step in reversed(steps):
                    if step["name"] == tool_name and step["status"] == "running":
                        step["status"] = "pending_approval"
                        break
            elif event.type == "APPROVAL_GRANTED":
                for step in reversed(steps):
                    if step["status"] == "pending_approval":
                        step["status"] = "running"
                        break
            elif event.type in {"APPROVAL_REJECTED", "APPROVAL_TIMEOUT"}:
                for step in reversed(steps):
                    if step["status"] == "pending_approval":
                        step["status"] = "error"
                        break
            self._render_task_panel(task_id)

        if event.type == "APPROVAL_REQUIRED":
            approval_id = event.payload.get("approval_id")
            tool_name = event.payload.get("tool_name", "")
            reason = event.payload.get("reason", "")
            risk_level = event.payload.get("risk_level", "medium")
            arguments = event.payload.get("arguments", {})
            self.heavy_agent_status_label.setText(f"Status: Waiting for Approval ({tool_name})")
            if not isinstance(approval_id, str):
                self.on_error_occurred("Approval Error", "Approval request did not include a valid identifier.")
                return
            dlg = ApprovalDialog(
                f"Approval Required: {tool_name}",
                reason,
                repr(arguments),
                risk_level,
                parent=self,
            )
            from agent.approvals import manager
            from agent.capabilities import registry as capability_registry
            from agent.capabilities import CapabilityGrant
            import uuid
            from datetime import datetime
            try:
                if dlg.exec():
                    if dlg.is_always_allow_checked():
                        # Create capability grant with constraints matching tool argument names
                        constraint_dict = {}
                        if tool_name == "open_application":
                            constraint_dict["app_name"] = arguments.get("app_name", "")
                        elif tool_name == "open_website":
                            constraint_dict["url"] = arguments.get("url", "")
                        elif tool_name in {"set_volume", "set_brightness"}:
                            # Use the actual argument name with range constraints
                            arg_name = "level_percent" if tool_name == "set_volume" else "level_percent"
                            constraint_dict[arg_name] = {"min": 0, "max": 100}
                        
                        grant = CapabilityGrant(
                            id=str(uuid.uuid4()),
                            capability=tool_name,
                            constraints=constraint_dict,
                            scope="persistent",
                            enabled=True,
                            created_at=datetime.now().isoformat()
                        )
                        capability_registry.register_grant(grant)
                        self._refresh_trust_safety_panel()
                        self.add_system_message_to_feed(f"Capability granted: {tool_name} (persistent)", is_error=False)
                    manager.approve(approval_id)
                else:
                    manager.reject(approval_id)
            except (KeyError, ValueError) as error:
                self.add_system_message_to_feed(f"Approval request could not be resolved: {error}", is_error=True)
        elif event.type == "TASK_COMPLETED":
            self.heavy_agent_status_label.setText("Status: Task Completed")
            if panel:
                panel["status"] = "completed"
                self._render_task_panel(task_id)
        elif event.type == "TASK_FAILED":
            err = event.payload.get("error", "Unknown error")
            self.heavy_agent_status_label.setText("Status: Task Failed")
            if panel:
                panel["status"] = "failed"
                panel["error"] = err
                self._render_task_panel(task_id)

    def _render_task_panel(self, task_id: str):
        panel = self.task_panels.get(task_id)
        if not panel or sip.isdeleted(panel["bubble"]):
            return

        status = html.escape(panel["status"])
        description = html.escape(str(panel["description"]))
        
        # Determine Assistant status based on task state
        assistant_status = "Idle"
        agent_status = "Idle"
        
        if panel["status"] == "running":
            assistant_status = "Working on that..."
            if panel["steps"]:
                current_step = panel["steps"][-1]
                step_status = current_step.get("status", "running")
                if step_status == "pending_approval":
                    agent_status = f"Waiting for approval: {current_step['name']}"
                elif step_status == "running":
                    agent_status = f"Executing: {current_step['name']}"
                elif step_status == "success":
                    agent_status = f"Completed: {current_step['name']}"
                elif step_status == "error":
                    agent_status = f"Error in: {current_step['name']}"
            else:
                agent_status = "Starting..."
        elif panel["status"] == "completed":
            assistant_status = "Task completed"
            agent_status = "Done"
        elif panel["status"] == "failed":
            assistant_status = "Task failed"
            agent_status = "Error"
        
        rendered = [
            f"<b>Task ({status}):</b> {description}",
            f"<div style='margin-top:5px;padding:5px;background:#1a1b26;border-radius:4px;'>",
            f"  <span style='color:#7aa2f7;'><b>Assistant:</b> {html.escape(assistant_status)}</span><br>",
            f"  <span style='color:#50fa7b;'><b>Agent:</b> {html.escape(agent_status)}</span>",
            f"</div>",
            "<ul style='list-style-type:none;padding-left:10px;margin-top:5px;'>"
        ]
        for step in panel["steps"]:
            icon = {
                "success": "✅",
                "error": "❌",
                "pending_approval": "⚠️",
            }.get(step["status"], "⏳")
            rendered.append(f"<li>{icon} {html.escape(str(step['name']))}</li>")
        if panel.get("error"):
            rendered.append(f"<li>❌ {html.escape(str(panel['error']))}</li>")
        rendered.append("</ul>")
        panel["bubble"].text_display.setHtml("".join(rendered))

    def closeEvent(self, event):
        # Stop voice assistant if running
        if self.voice_assistant_active:
            self.toggle_voice_assistant()
        
        for worker in tuple(self.agent_workers.values()):
            worker.cancel()
        self.agent_listener.close()
        super().closeEvent(event)

    @pyqtSlot()
    def finish_voice_capture_sig(self):
        self.finish_voice_capture(force_cancel=False)

    def toggle_voice_assistant(self):
        """Toggle the Gemini Live voice assistant on/off."""
        if self.voice_assistant_active:
            # Stop the voice assistant
            self.voice_assistant_active = False
            self.voice_assistant_btn.setChecked(False)
            self.voice_assistant_btn.setText("🎤 Voice Assistant")
            self.voice_connection_label.setText("🔴 Disconnected")
            self.voice_connection_label.setStyleSheet("color: #ff5555; font-weight: bold; font-size: 11px; margin-left: 5px;")
            
            if self.live_agent:
                self.live_agent.stop_event.set()
                self.live_agent = None
            if self.live_agent_thread and self.live_agent_thread.is_alive():
                self.live_agent_thread.join(timeout=5.0)
                self.live_agent_thread = None
            
            self.add_system_message_to_feed("Voice assistant stopped.", is_error=False)
        else:
            # Start the voice assistant
            try:
                from providers.gemini_live import start_agent_in_thread
            except Exception as error:
                self.voice_assistant_active = False
                self.voice_assistant_btn.setChecked(False)
                self.voice_assistant_btn.setText("🎤 Voice Assistant")
                self._update_connection_state("error")
                self.add_system_message_to_feed(
                    f"Voice assistant could not start: {error}",
                    is_error=True,
                )
                return

            self.voice_assistant_active = True
            self.voice_assistant_btn.setChecked(True)
            self.voice_assistant_btn.setText("🛑 Stop Voice Assistant")
            self.voice_connection_label.setText("🟡 Connecting...")
            self.voice_connection_label.setStyleSheet("color: #ffb86c; font-weight: bold; font-size: 11px; margin-left: 5px;")

            # The Live provider owns its own asyncio loop. The UI only owns the
            # background thread that runs it.
            global_agent_ref = [None]

            def run_live_agent():
                try:
                    start_agent_in_thread(
                        volume_cb=self._on_volume_update,
                        text_cb=self._on_live_text,
                        state_cb=self._on_live_state,
                        bubble_cb=self._on_live_bubble,
                        glow_cb=self._on_live_glow,
                        assistant_bridge=self.assistant_bridge,
                        global_agent_ref=global_agent_ref,
                    )
                except Exception as error:
                    logger = get_logger("ui")
                    logger.error(f"Gemini Live thread error: {error}", exc_info=True)
                    QTimer.singleShot(
                        0,
                        lambda: self._handle_live_start_failure(str(error)),
                    )

            def capture_agent():
                agent = global_agent_ref[0]
                if agent is not None:
                    self.live_agent = agent
                    self._update_connection_state(agent.get_connection_state())
                    return

                if self.live_agent_thread is not None and not self.live_agent_thread.is_alive():
                    self._handle_live_start_failure("Gemini Live thread exited before establishing a connection.")
                    return

                QTimer.singleShot(250, capture_agent)

            self.live_agent_thread = threading.Thread(target=run_live_agent, daemon=True)
            self.live_agent_thread.start()
            QTimer.singleShot(250, capture_agent)
            self.add_system_message_to_feed("Starting voice assistant...", is_error=False)

    def _handle_live_start_failure(self, message: str):
        self.voice_assistant_active = False
        self.voice_assistant_btn.setChecked(False)
        self.voice_assistant_btn.setText("🎤 Voice Assistant")
        self._update_connection_state("error")
        if hasattr(self, "assistant_state_label"):
            self.assistant_state_label.setText("🔴 Voice error")
        self.add_system_message_to_feed(f"Voice assistant error: {message}", is_error=True)

    def _update_connection_state(self, state: str):
        """Update the connection state indicator."""
        state_colors = {
            "disconnected": ("🔴 Disconnected", "#ff5555"),
            "connecting": ("🟡 Connecting...", "#ffb86c"),
            "connected": ("🟢 Connected", "#50fa7b"),
            "reconnecting": ("🔄 Reconnecting...", "#ffb86c"),
            "error": ("🔴 Error", "#ff5555"),
        }
        text, color = state_colors.get(state, (state, "#c0caf5"))
        self.voice_connection_label.setText(text)
        self.voice_connection_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px; margin-left: 5px;")

    @pyqtSlot(AssistantEvent)
    def _on_assistant_event(self, event: AssistantEvent):
        """Handle events from the AssistantBridge."""
        if event.type == "approval_required":
            # Show approval request in chat
            msg = f"⚠️ **Approval Required**\nTask: {event.summary}\nRisk: {event.risk}\nApproval ID: {event.approval_id}"
            self.add_system_message_to_feed(msg, is_error=False)
        elif event.type == "task_started":
            self.add_system_message_to_feed(f"🤖 Agent started: {event.summary}", is_error=False)
        elif event.type == "task_completed":
            self.add_system_message_to_feed(f"✅ Agent completed: {event.summary}", is_error=False)
        elif event.type == "task_failed":
            self.add_system_message_to_feed(f"❌ Agent failed: {event.summary}", is_error=True)
        elif event.type == "tool_progress":
            if event.progress:
                self.add_system_message_to_feed(f"⚙️ {event.progress}", is_error=False)
        
        # Also forward to Gemini Live if connected
        if self.live_agent:
            self.live_agent.inject_agent_event(event)

    def _on_volume_update(self, volume: float):
        pass  # Volume updates from Gemini Live

    def _on_live_text(self, role: str, text: str):
        """Handle text from Gemini Live session."""
        if role == "model":
            self.add_system_message_to_feed(f"🎤 {text}", is_error=False)
        elif role == "user":
            pass  # User input is handled via push-to-talk
        elif role == "system":
            self.add_system_message_to_feed(text, is_error=False)

    def _on_live_state(self, state: str):
        """Handle connection state changes from Gemini Live."""
        self._update_connection_state(state)
        
        # Update assistant state indicator
        state_map = {
            "idle": ("🎙️ Idle", "#8be9fd"),
            "listening": ("🎙️ Listening", "#50fa7b"),
            "thinking": ("🤔 Thinking", "#ffb86c"),
            "talking": ("🔊 Speaking", "#ff79c6"),
            "connecting": ("🔄 Connecting...", "#ffb86c"),
            "reconnecting": ("🔄 Reconnecting...", "#ffb86c"),
            "connected": ("🎙️ Ready", "#50fa7b"),
            "disconnected": ("🔴 Disconnected", "#ff5555"),
            "error": ("🔴 Error", "#ff5555"),
        }
        text, color = state_map.get(state, (state, "#c0caf5"))
        if hasattr(self, 'assistant_state_label'):
            self.assistant_state_label.setText(text)
            self.assistant_state_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px; margin-left: 10px;")

    def _on_live_bubble(self, text: str):
        """Handle bubble messages from Gemini Live."""
        pass

    def _on_live_glow(self, state: str):
        """Handle glow state from Gemini Live - sync with visualizer."""
        if self.visualizer_glow_emitter:
            self.visualizer_glow_emitter.glow_changed.emit(state)
        # Also update assistant state from glow
        glow_to_state = {
            "connected": "idle",
            "connecting": "connecting",
            "thinking": "thinking",
            "vision": "thinking",
        }
        if state in glow_to_state and hasattr(self, 'assistant_state_label'):
            mapped_state = glow_to_state[state]
            state_map = {
                "idle": ("🎙️ Idle", "#8be9fd"),
                "listening": ("🎙️ Listening", "#50fa7b"),
                "thinking": ("🤔 Thinking", "#ffb86c"),
                "talking": ("🔊 Speaking", "#ff79c6"),
                "connecting": ("🔄 Connecting...", "#ffb86c"),
            }
            text, color = state_map.get(mapped_state, (mapped_state, "#c0caf5"))
            self.assistant_state_label.setText(text)
            self.assistant_state_label.setStyleSheet(f"color: {color}; font-weight: bold; font-size: 11px; margin-left: 10px;")

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

    # --- Trust & Safety Panel ---
    def _create_trust_safety_panel(self):
        """Create the Trust & Safety panel for capability grant management."""
        from PyQt6.QtWidgets import QGroupBox, QVBoxLayout, QLabel, QPushButton, QScrollArea, QWidget
        
        group = QGroupBox("🛡️ Trust & Safety")
        group.setStyleSheet("""
            QGroupBox {
                color: #7aa2f7;
                font-weight: bold;
                border: 1px solid #3b4261;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        layout = QVBoxLayout(group)
        layout.setContentsMargins(10, 20, 10, 10)
        layout.setSpacing(8)
        
        # Always Allowed section
        self.always_allowed_label = QLabel("<b>Always Allowed</b>")
        self.always_allowed_label.setStyleSheet("color: #50fa7b; font-size: 12px;")
        layout.addWidget(self.always_allowed_label)
        
        self.always_allowed_container = QWidget()
        self.always_allowed_layout = QVBoxLayout(self.always_allowed_container)
        self.always_allowed_layout.setContentsMargins(0, 0, 0, 0)
        self.always_allowed_layout.setSpacing(4)
        layout.addWidget(self.always_allowed_container)
        
        # Ask When Needed section
        self.ask_needed_label = QLabel("<b>Ask When Needed</b>")
        self.ask_needed_label.setStyleSheet("color: #ffb86c; font-size: 12px;")
        layout.addWidget(self.ask_needed_label)
        
        self.ask_needed_container = QWidget()
        self.ask_needed_layout = QVBoxLayout(self.ask_needed_container)
        self.ask_needed_layout.setContentsMargins(0, 0, 0, 0)
        self.ask_needed_layout.setSpacing(4)
        layout.addWidget(self.ask_needed_container)
        
        # Blocked section
        self.blocked_label = QLabel("<b>Blocked</b>")
        self.blocked_label.setStyleSheet("color: #ff5555; font-size: 12px;")
        layout.addWidget(self.blocked_label)
        
        self.blocked_container = QWidget()
        self.blocked_layout = QVBoxLayout(self.blocked_container)
        self.blocked_layout.setContentsMargins(0, 0, 0, 0)
        self.blocked_layout.setSpacing(4)
        layout.addWidget(self.blocked_container)
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #3b4261;
                color: #c0caf5;
                border: none;
                border-radius: 6px;
                padding: 6px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4a5072;
            }
        """)
        refresh_btn.clicked.connect(self._refresh_trust_safety_panel)
        layout.addWidget(refresh_btn)
        
        self._refresh_trust_safety_panel()
        return group

    def _refresh_trust_safety_panel(self):
        """Refresh the Trust & Safety panel with current capability grants."""
        # Clear existing widgets
        for layout in [self.always_allowed_layout, self.ask_needed_layout, self.blocked_layout]:
            while layout.count():
                item = layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        
        from agent.capabilities import registry as capability_registry
        grants = capability_registry.get_all_grants()
        
        # Capabilities that are considered "Always Allowed" (have grants)
        granted_capabilities = set(g.capability for g in grants)
        
        # All desktop capabilities
        all_capabilities = {
            "open_application": "Open Application",
            "open_website": "Open Website",
            "set_volume": "Set Volume",
            "set_brightness": "Set Brightness",
            "get_clipboard": "Get Clipboard",
            "search_and_play_youtube": "Search & Play YouTube",
        }
        
        # Always Allowed - capabilities with active grants
        for cap_id, cap_name in all_capabilities.items():
            if cap_id in granted_capabilities:
                grant = next(g for g in grants if g.capability == cap_id)
                scope_badge = " [Persistent]" if grant.scope == "persistent" else " [Session]"
                btn = QPushButton(f"✅ {cap_name}{scope_badge}")
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #1a2a1a;
                        color: #50fa7b;
                        border: 1px solid #50fa7b;
                        border-radius: 4px;
                        padding: 4px 8px;
                        font-size: 11px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background-color: #2a3a2a;
                    }
                """)
                btn.setProperty("grant_id", grant.id)
                btn.clicked.connect(lambda checked, gid=grant.id: self._revoke_grant(gid))
                self.always_allowed_layout.addWidget(btn)
        
        # Ask When Needed - capabilities without grants (medium/high risk)
        ask_needed = {"open_application", "open_website", "search_and_play_youtube"}
        for cap_id in ask_needed:
            if cap_id not in granted_capabilities:
                cap_name = all_capabilities[cap_id]
                btn = QPushButton(f"⚠️ {cap_name}")
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2a2a1a;
                        color: #ffb86c;
                        border: 1px solid #ffb86c;
                        border-radius: 4px;
                        padding: 4px 8px;
                        font-size: 11px;
                        text-align: left;
                    }
                    QPushButton:hover {
                        background-color: #3a3a2a;
                    }
                """)
                btn.setProperty("capability", cap_id)
                btn.clicked.connect(lambda checked, cid=cap_id: self._show_grant_dialog(cid))
                self.ask_needed_layout.addWidget(btn)
        
        # Low risk capabilities that don't typically need approval
        low_risk = {"set_volume", "set_brightness", "get_clipboard"}
        for cap_id in low_risk:
            if cap_id not in granted_capabilities:
                cap_name = all_capabilities[cap_id]
                btn = QPushButton(f"⚠️ {cap_name} (auto-approved in safe mode)")
                btn.setStyleSheet("""
                    QPushButton {
                        background-color: #2a2a1a;
                        color: #ffb86c;
                        border: 1px solid #ffb86c;
                        border-radius: 4px;
                        padding: 4px 8px;
                        font-size: 11px;
                        text-align: left;
                    }
                """)
                btn.setEnabled(False)
                self.ask_needed_layout.addWidget(btn)
        
        # Blocked - shell commands, file writes, etc.
        blocked_items = [
            ("execute_shell", "Execute Shell Commands"),
            ("write_file", "Write Files"),
            ("read_file", "Read Files (outside workspace)"),
        ]
        for cap_id, cap_name in blocked_items:
            btn = QPushButton(f"🚫 {cap_name}")
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2a1a1a;
                    color: #ff5555;
                    border: 1px solid #ff5555;
                    border-radius: 4px;
                    padding: 4px 8px;
                    font-size: 11px;
                    text-align: left;
                }
            """)
            btn.setEnabled(False)
            self.blocked_layout.addWidget(btn)

    def _revoke_grant(self, grant_id: str):
        """Revoke a capability grant."""
        from agent.capabilities import registry as capability_registry
        if capability_registry.revoke_grant(grant_id):
            self._refresh_trust_safety_panel()
            self.add_system_message_to_feed(f"Capability grant revoked: {grant_id}", is_error=False)

    def _show_grant_dialog(self, capability: str):
        """Show dialog to grant a capability."""
        from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton, QHBoxLayout
        from datetime import datetime, timedelta
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Grant Capability: {capability}")
        dialog.setStyleSheet("background-color: #1a1b26; color: #c0caf5;")
        layout = QVBoxLayout(dialog)
        
        layout.addWidget(QLabel(f"Grant permission for: <b>{capability}</b>"))
        
        scope_combo = QComboBox()
        scope_combo.addItem("Session Only (expires on restart)", "session")
        scope_combo.addItem("Persistent (survives restart)", "persistent")
        layout.addWidget(QLabel("Scope:"))
        layout.addWidget(scope_combo)
        
        # Constraints based on capability
        constraints = {}
        if capability == "open_application":
            from PyQt6.QtWidgets import QLineEdit
            app_input = QLineEdit()
            app_input.setPlaceholderText("App name (e.g., chrome) - leave empty for any")
            layout.addWidget(QLabel("Constraint - App Name:"))
            layout.addWidget(app_input)
            constraints["app_input"] = app_input
        elif capability == "open_website":
            from PyQt6.QtWidgets import QLineEdit
            url_input = QLineEdit()
            url_input.setPlaceholderText("Domain/URL (e.g., youtube.com) - leave empty for any")
            layout.addWidget(QLabel("Constraint - URL/Domain:"))
            layout.addWidget(url_input)
            constraints["url_input"] = url_input
        elif capability in {"set_volume", "set_brightness"}:
            from PyQt6.QtWidgets import QSpinBox
            min_spin = QSpinBox()
            min_spin.setRange(0, 100)
            min_spin.setValue(0)
            max_spin = QSpinBox()
            max_spin.setRange(0, 100)
            max_spin.setValue(100)
            layout.addWidget(QLabel("Min Value:"))
            layout.addWidget(min_spin)
            layout.addWidget(QLabel("Max Value:"))
            layout.addWidget(max_spin)
            constraints["min_spin"] = min_spin
            constraints["max_spin"] = max_spin
        
        btn_layout = QHBoxLayout()
        grant_btn = QPushButton("Grant")
        grant_btn.setStyleSheet("background-color: #50fa7b; color: #1a1b26; font-weight: bold; padding: 8px; border-radius: 6px;")
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("background-color: #ff5555; color: white; padding: 8px; border-radius: 6px;")
        btn_layout.addWidget(grant_btn)
        btn_layout.addWidget(cancel_btn)
        layout.addLayout(btn_layout)
        
        def on_grant():
            from agent.capabilities import registry as capability_registry
            import uuid
            
            constraint_dict = {}
            if capability == "open_application":
                val = constraints["app_input"].text().strip()
                if val:
                    constraint_dict["app_name"] = val
            elif capability == "open_website":
                val = constraints["url_input"].text().strip()
                if val:
                    constraint_dict["url"] = val
            elif capability in {"set_volume", "set_brightness"}:
                constraint_dict["min"] = constraints["min_spin"].value()
                constraint_dict["max"] = constraints["max_spin"].value()
            
            grant = CapabilityGrant(
                id=str(uuid.uuid4()),
                capability=capability,
                constraints=constraint_dict,
                scope=scope_combo.currentData(),
                enabled=True,
                created_at=datetime.now().isoformat()
            )
            capability_registry.register_grant(grant)
            self._refresh_trust_safety_panel()
            self.add_system_message_to_feed(f"Capability granted: {capability}", is_error=False)
            dialog.accept()
        
        grant_btn.clicked.connect(on_grant)
        cancel_btn.clicked.connect(dialog.reject)
        
        dialog.exec()
