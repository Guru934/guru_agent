import asyncio
import random
import json
import threading
import os
from typing import Optional, Callable, Any, Literal
from dataclasses import dataclass, field
from dotenv import load_dotenv

from google import genai
from google.genai import types

from ui.audio import AudioInterface
from tools.vision import VisionInterface
from utils import get_logger
from ui.earcons import play_earcon
from agent.assistant_bridge import AssistantBridge
from agent.assistant_events import AssistantEvent

logger = get_logger("cat_talker.agent")

# Load environment variables from .env file
load_dotenv()

# --- MONKEY PATCH WEBSOCKETS TO DISABLE PING TIMEOUTS FOR STRICT PROXIES ---
import websockets.asyncio.client
_orig_connect = websockets.asyncio.client.connect
def _patched_connect(*args, **kwargs):
    kwargs['ping_interval'] = 20.0
    kwargs['ping_timeout'] = 20.0
    return _orig_connect(*args, **kwargs)
websockets.asyncio.client.connect = _patched_connect
# --------------------------------------------------------------------------


# Tool schemas for Gemini Live API
LIVE_TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="delegate_to_agent",
        description="Delegate a complex task to the execution agent. Use for multi-step tasks like coding, file operations, searching, fixing tests, etc. Returns a task_id immediately - the agent runs in background.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "task_description": types.Schema(
                    type=types.Type.STRING,
                    description="Natural language description of the task to delegate"
                ),
            },
            required=["task_description"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_agent_status",
        description="Get status of a delegated task or all active tasks.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "task_id": types.Schema(
                    type=types.Type.STRING,
                    description="Specific task ID to query, or omit for all active tasks"
                ),
            },
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="approve_pending_action",
        description="Approve a pending action that requires user permission. Only use when the assistant has explicitly asked for approval and provided an approval_id.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "approval_id": types.Schema(
                    type=types.Type.STRING,
                    description="The approval ID provided by the assistant when asking for permission"
                ),
            },
            required=["approval_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="reject_pending_action",
        description="Reject a pending action that requires user permission. Only use when the assistant has explicitly asked for approval and provided an approval_id.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "approval_id": types.Schema(
                    type=types.Type.STRING,
                    description="The approval ID provided by the assistant when asking for permission"
                ),
            },
            required=["approval_id"],
        ),
    ),
    types.FunctionDeclaration(
        name="get_project_context",
        description="Get current project/workspace context including project name, files, and git status.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={},
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="get_task_history",
        description="Get recent task history (completed/failed tasks with summaries).",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "limit": types.Schema(
                    type=types.Type.INTEGER,
                    description="Number of recent tasks to retrieve (default: 5)"
                ),
            },
            required=[],
        ),
    ),
    types.FunctionDeclaration(
        name="find_task_by_description",
        description="Find a task by description query (e.g., 'Chrome task', 'test task'). Returns task status and progress.",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={
                "description": types.Schema(
                    type=types.Type.STRING,
                    description="Natural language query to find the task"
                ),
            },
            required=["description"],
        ),
    ),
]


ConnectionState = Literal["disconnected", "connecting", "connected", "reconnecting", "error"]
VoiceState = Literal["sleeping", "listening", "thinking", "speaking"]
TaskState = Literal["idle", "running", "waiting_approval", "error"]

# Inactivity timeout before auto-sleep (seconds)
INACTIVITY_TIMEOUT = 50.0

@dataclass
class VoiceStateManager:
    state: VoiceState = "sleeping"
    callbacks: list[Callable[[VoiceState], None]] = field(default_factory=list)
    _sleep_timer: Optional[asyncio.TimerHandle] = None
    _loop: Optional[asyncio.AbstractEventLoop] = None
    _mute_event: Optional[threading.Event] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    def set_mute_event(self, mute_event: threading.Event):
        self._mute_event = mute_event

    def add_callback(self, cb: Callable[[VoiceState], None]):
        self.callbacks.append(cb)

    def set_state(self, new_state: VoiceState):
        if self.state == new_state:
            return
        old_state = self.state
        self.state = new_state

        # Auto-sleep logic
        if self._sleep_timer:
            self._sleep_timer.cancel()
            self._sleep_timer = None

        # Start inactivity timer when entering LISTENING state
        if new_state == "listening" and self._loop:
            # Sleep after INACTIVITY_TIMEOUT of no user speech
            self._sleep_timer = self._loop.call_later(INACTIVITY_TIMEOUT, self._auto_sleep)

        # When user starts speaking (we detect via voice input), reset timer
        # This is called from wake_voice() or when user audio is detected
        
        for cb in self.callbacks:
            try:
                cb(new_state)
            except Exception as e:
                import logging
                logging.getLogger("cat_talker.agent").error(f"Voice callback error: {e}")

    def _auto_sleep(self):
        if self.state == "listening":
            logger.info("Inactivity timeout reached, transitioning to SLEEPING")
            self.set_state("sleeping")
            if self._mute_event:
                self._mute_event.set()

    def on_user_speech_detected(self):
        """Call when user speech is detected to reset inactivity timer."""
        if self.state == "listening" and self._loop:
            if self._sleep_timer:
                self._sleep_timer.cancel()
            self._sleep_timer = self._loop.call_later(INACTIVITY_TIMEOUT, self._auto_sleep)


class GeminiDesktopAgent:
    def __init__(self, assistant_bridge: Optional[AssistantBridge] = None):
        self.client = None
        self.audio = None
        self.vision = None
        self.stop_event = threading.Event()
        self._is_speaking = False
        self._is_processing = False
        self.synthetic_input_queue = None
        self.is_recording = False
        self.loop = None
        self.current_model = "gemini-3.8-live"
        self.fallback_models = ["gemini-3.8-live", "gemini-3.1-flash-live-preview"]
        self.fallback_idx = 0
        self._force_reconnect = False
        self._has_connected_once = False
        self._reconnect_attempts = 0
        
        # Assistant Bridge integration
        self.assistant_bridge = assistant_bridge
        self._pending_tool_calls = {}
        
        # States
        self._connection_state: ConnectionState = "disconnected"
        self.voice_state = VoiceStateManager()
        self._task_state: TaskState = "idle"
        
        self.connection_callbacks = []
        self.task_callbacks = []
        
        self._state_callback_ref = None # Legacy support
        self._glow_callback_ref = None
        self._active_session = None
        self._greeting_sent = False
        
        # Microphone control - starts muted (sleeping)
        self._mic_mute_event = threading.Event()
        self._mic_mute_event.set()
        self.voice_state.set_mute_event(self._mic_mute_event)
        
    def set_mic_muted(self, muted: bool):
        """Thread-safe microphone mute control."""
        if muted:
            self._mic_mute_event.set()
        else:
            self._mic_mute_event.clear()
        logger.debug(f"Voice: mic {'muted (sleep)' if muted else 'unmuted (listen)'}")

    def add_connection_callback(self, cb: Callable[[ConnectionState], None]):
        self.connection_callbacks.append(cb)

    def add_voice_callback(self, cb: Callable[[VoiceState], None]):
        self.voice_state.add_callback(cb)

    def add_task_callback(self, cb: Callable[[TaskState], None]):
        self.task_callbacks.append(cb)

    def wake_voice(self):
        """Wake voice assistant from sleep - called by F2 or UI."""
        logger.info("Waking voice assistant")
        self.set_mic_muted(False)
        self.voice_state.set_state("listening")
        # Reset inactivity timer
        self.voice_state.on_user_speech_detected()

    def sleep_voice(self):
        """Put voice assistant to sleep - called after inactivity or manually."""
        logger.info("Sleeping voice assistant")
        self.set_mic_muted(True)
        self.voice_state.set_state("sleeping")

    def switch_model(self, model_id: str):
        self.current_model = model_id
        if model_id not in self.fallback_models:
            self.fallback_models.insert(0, model_id)
            self.fallback_idx = 0
        self._force_reconnect = True

    def _set_connection_state(self, state: ConnectionState):
        self._connection_state = state
        logger.info(f"Gemini Live connection state: {state}")
        
        # Legacy
        if self._state_callback_ref:
            self._state_callback_ref(state)
            
        for cb in self.connection_callbacks:
            try: cb(state)
            except Exception as e: logger.error(f"Conn cb error: {e}")
            
        if self._glow_callback_ref:
            if state == "connected":
                self._glow_callback_ref("connected")
            elif state == "connecting" or state == "reconnecting":
                self._glow_callback_ref("connecting")
            else:
                self._glow_callback_ref("disconnected")

    def _set_state(self, state_callback, state: str):
        if state_callback:
            state_callback(state)

    def _set_bubble(self, bubble_callback, text: str):
        if bubble_callback:
            bubble_callback(text)

    def _set_glow(self, glow_callback, state: str):
        if glow_callback:
            glow_callback(state)

    async def run_loop(self, volume_callback=None, app_quit_callback=None, text_callback=None,
                       state_callback=None, bubble_callback=None, glow_callback=None):
        self.loop = asyncio.get_running_loop()
        self.voice_state.set_loop(self.loop)
        self.synthetic_input_queue = asyncio.Queue()
        # Pass the mic mute event to AudioInterface for push-to-talk
        self.audio = AudioInterface(mic_mute_event=self._mic_mute_event)
        self.audio.volume_cb = volume_callback
        
        self.vision = VisionInterface()
        
        # Store callbacks for connection state updates
        self._state_callback_ref = state_callback
        self._glow_callback_ref = glow_callback
        self._set_connection_state("connecting")

        # System instructions dynamically built inside the loop

        # Create client here for proper error handling
        try:
            self.client = genai.Client()
        except Exception as e:
            logger.error(f"Failed to create Gemini client: {e}", exc_info=True)
            self._set_connection_state("error")
            if text_callback:
                text_callback("system", f"Failed to initialize Gemini client: {e}")
            if app_quit_callback:
                app_quit_callback()
            return

        try:
            while not self.stop_event.is_set():
                try:
                    base_instructions = self._build_system_instructions()
                    system_instructions = base_instructions
                    
                    if self.assistant_bridge:
                        if self._has_connected_once:
                            # On reconnect: append context to system instructions silently
                            context = self.assistant_bridge.get_context_for_resumption()
                            import json
                            context_str = json.dumps(context, indent=2, default=str)
                            system_instructions += f"\n\nSESSION CONTEXT (for reference, do not acknowledge):\n{context_str}"
                        else:
                            # First connection: append session context to system instructions
                            context = self.assistant_bridge.get_session_context()
                            system_instructions += f"\n\nSystem context:\n{context}"
                            
                    config = types.LiveConnectConfig(
                        response_modalities=["AUDIO"],
                        system_instruction=types.Content(parts=[types.Part(text=system_instructions)]),
                        output_audio_transcription=types.AudioTranscriptionConfig(word_timestamp=False),
                        tools=[types.Tool(function_declarations=LIVE_TOOL_DECLARATIONS)],
                    )

                    self._force_reconnect = False
                    async with self.client.aio.live.connect(model=self.current_model, config=config) as session:
                        self._active_session = session  # Store reference for event injection
                        logger.info("====================================")
                        logger.info("✅ Session established securely!")
                        logger.info("🎙️ Speak into your microphone now...")
                        logger.info("====================================")
                        is_reconnect = self._has_connected_once
                        if not is_reconnect:
                            if text_callback:
                                text_callback("system", "Gemini Live Connected!")
                            self._has_connected_once = True
                        # On first connect, enter LISTENING state so user can speak after greeting
                        # (mic will be muted while model is speaking via is_playing check)
                        if not is_reconnect:
                            self.voice_state.set_state("listening")
                        else:
                            # On reconnect, stay in current state or default to sleeping
                            if self.voice_state.state == "sleeping":
                                self.voice_state.set_state("sleeping")
                        self._set_glow(glow_callback, "connected")
                        self._set_connection_state("connected")
                        
                        # Reset reconnect attempts on successful connection
                        self._reconnect_attempts = 0

                        # On first connect: trigger spoken greeting by sending user turn
                        if not is_reconnect:
                            async def send_greeting():
                                await asyncio.sleep(0.5)  # Brief delay for session to stabilize
                                try:
                                    async with send_lock:
                                        await session.send_client_content(
                                            turns=types.Content(
                                                role="user",
                                                parts=[types.Part(text="Hello")],
                                            ),
                                            turn_complete=True,
                                        )
                                except Exception as e:
                                    logger.error(f"Failed to send greeting: {e}")
                            asyncio.create_task(send_greeting())


                        send_lock = asyncio.Lock()

                        async def mic_worker():
                            logger.info("Started Mic Stream...")
                            while not self.stop_event.is_set():
                                chunk = await self.audio.audio_in_queue.get()
                                try:
                                    async with send_lock:
                                        await session.send_realtime_input(
                                            audio=types.Blob(data=chunk, mime_type='audio/pcm;rate=16000')
                                        )
                                except Exception as e:
                                    logger.error(f"Mic send error (reconnecting): {e}", exc_info=True)
                                    break

                        async def receive_worker():
                            try:
                                async for msg in session.receive():
                                    if msg.server_content:
                                        if hasattr(msg.server_content, "interrupted") and msg.server_content.interrupted:
                                            self.audio.clear_output_queue()
                                            self._is_speaking = False
                                            self.voice_state.set_state("listening")
                                            self._set_glow(glow_callback, "connected")
                                            
                                            pass

                                        if hasattr(msg.server_content, 'turn_complete') and msg.server_content.turn_complete:
                                            self._is_speaking = False
                                            # After model turn completes, go back to LISTENING
                                            self.voice_state.set_state("listening")
                                            self._set_glow(glow_callback, "connected")
                                            if text_callback:
                                                text_callback("model_turn_complete", "")
                                            pass

                                        if msg.server_content.model_turn:
                                            # Model started responding - thinking phase
                                            if not self._is_speaking:
                                                self._is_speaking = True
                                                self.voice_state.set_state("thinking")
                                                self._set_glow(glow_callback, "thinking")
                                                
                                                pass

                                            for part in msg.server_content.model_turn.parts:
                                                if hasattr(part, "inline_data") and part.inline_data:
                                                    # Audio chunk arriving - speaking phase
                                                    if not self._is_speaking:
                                                        self._is_speaking = True
                                                    self.voice_state.set_state("speaking")
                                                    self._set_glow(glow_callback, "connected")
                                                    self.audio.queue_output(part.inline_data.data)
                                                if hasattr(part, "text") and part.text and text_callback:
                                                    text_callback("model", part.text)

                                    if hasattr(msg, "client_content") and msg.client_content:
                                        for turn in getattr(msg.client_content, "turns", []):
                                            if turn.role == "user":
                                                for part in turn.parts:
                                                    if hasattr(part, "text") and part.text and text_callback:
                                                        text_callback("user", part.text)
                                                        self.voice_state.set_state("listening")
                                                        self._set_glow(glow_callback, "connected")
                                                        # Reset inactivity timer on user speech
                                                        self.voice_state.on_user_speech_detected()

                                    if hasattr(msg, "tool_call") and msg.tool_call:
                                        await self._handle_tool_call(session, msg.tool_call, send_lock, text_callback, bubble_callback, glow_callback)

                            except Exception as e:
                                logger.error(f"Receive interrupted (reconnecting): {e}", exc_info=True)

                        async def synthetic_input_worker():
                            logger.info("Started Synthetic Input Worker...")
                            while not self.stop_event.is_set():
                                try:
                                    action = await self.synthetic_input_queue.get()
                                    if action == "HEAVY_AGENT_DONE":
                                        async with send_lock:
                                            await session.send_client_content(
                                                turns=types.Content(
                                                    role="user",
                                                    parts=[types.Part(text="The heavy agent has just finished its delegated task! Briefly let the user know verbally.")],
                                                ),
                                                turn_complete=True,
                                            )
                                    elif action == "ACTIVE_WINDOW":
                                        region = self.vision.get_active_window_region()
                                        frame = self.vision.capture_frame(region=region)
                                        if frame:
                                            self._set_bubble(bubble_callback, "📸 Captured Active Window")
                                            self._set_glow(glow_callback, "vision")
                                            async with send_lock:
                                                # Send the image
                                                await session.send_realtime_input(video=types.Blob(data=frame, mime_type='image/jpeg'))
                                                # Send text prompt
                                                await session.send_client_content(
                                                    turns=types.Content(
                                                        role="user",
                                                        parts=[types.Part(text="The user just pressed the active window hotkey. Look at the provided image. What do you see? Or ask the user how you can help with it.")],
                                                    ),
                                                    turn_complete=True,
                                                )
                                except Exception as e:
                                    logger.error(f"Synthetic input worker error: {e}", exc_info=True)

                        tasks = [
                            asyncio.create_task(mic_worker()),
                            asyncio.create_task(receive_worker()),
                            asyncio.create_task(synthetic_input_worker()),
                        ]

                        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in pending:
                            task.cancel()

                    # Clear active session reference when session ends
                    self._active_session = None

                except Exception as e:
                    err_str = str(e)
                    logger.error(f"Agent connection dropped (auto-reconnecting): {e}", exc_info=True)
                    self._set_connection_state("reconnecting")
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str:
                        self.fallback_idx = (self.fallback_idx + 1) % len(self.fallback_models)
                        new_model = self.fallback_models[self.fallback_idx]
                        if self.current_model != new_model:
                            self.current_model = new_model
                            logger.info(f"Auto-switching Live backend to fallback model: {self.current_model}")
                            # Don't send to chat - only update connection state
                    
                    play_earcon("fail")
                    # Silent reconnect - NO chat messages, only connection state update
                    
                    # Exponential backoff with jitter
                    self._reconnect_attempts += 1
                    max_delay = 60  # Max 60 seconds
                    base_delay = min(2 ** self._reconnect_attempts, max_delay)
                    jitter = random.uniform(0, 1)
                    delay = base_delay + jitter
                    logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})...")
                    await asyncio.sleep(delay)
                    
                    # Add retry ceiling - after 10 failed attempts, stop auto-reconnecting
                    if self._reconnect_attempts >= 10:
                        logger.warning("Max reconnect attempts reached, stopping auto-reconnect")
                        self._set_connection_state("error")
                        if text_callback:
                            text_callback("system", "Connection failed after multiple attempts. Please check your connection and restart voice assistant.")
                        break
                    
                    # Reset reconnect attempts on successful connection (handled in the while loop restart)

        finally:
            self._set_connection_state("disconnected")
            logger.info("Shutting down audio...")
            if self.audio:
                self.audio.close()
                self.audio = None
            if app_quit_callback:
                app_quit_callback()

    def _build_system_instructions(self) -> str:
        base = (
            "You are a voice conversation assistant - the user's always-available AI companion. "
            "You have access to an execution agent that can perform complex tasks on the desktop. "
            "\n\nYour role:"
            "\n- Answer questions, chat, explain concepts directly (no delegation needed)"
            "\n- For complex multi-step tasks (coding, file operations, searching, fixing tests, desktop automation), delegate to the execution agent"
            "\n- Narrate progress from the execution agent back to the user"
            "\n- Ask for user approval when the execution agent needs it"
            "\n- Report results when tasks complete"
            "\n\nAvailable delegation tools:"
            "\n- delegate_to_agent(task_description): Start a background task, returns task_id immediately"
            "\n- get_agent_status(task_id?): Check progress of a task or all active tasks"
            "\n- approve_pending_action(approval_id): Approve a pending action (only when explicitly asked)"
            "\n- reject_pending_action(approval_id): Reject a pending action (only when explicitly asked)"
            "\n\nApproval Workflow (CRITICAL):"
            "\n- When you receive an 'approval_required' system event, you MUST narrate it to the user naturally"
            "\n- Example: 'The execution agent needs your approval to open Chrome and navigate to YouTube. Shall I allow it?'"
            "\n- Wait for user's verbal response: 'Yes'/'Allow it'/'Approve' → call approve_pending_action(approval_id)"
            "\n- 'No'/'Deny'/'Cancel' → call reject_pending_action(approval_id)"
            "\n- If MULTIPLE approvals are pending, list them: 'There are two pending approvals. First: open Chrome. Second: write project file. Which should I approve?'"
            "\n- NEVER invent approval IDs - only use IDs provided in the approval_required event"
            "\n- Voice approval ONLY resolves existing approvals - cannot create new actions"
            "\n\nGuidelines:"
            "\n- Keep responses conversational and brief"
            "\n- Don't claim to perform OS actions yourself - you delegate"
            "\n- When delegating, describe what you're delegating in natural language"
            "\n- When asked for approval, clearly explain what action needs approval and why"
            "\n- Never invent approval IDs - only use ones provided by the system"
        )
        return base

    async def _handle_tool_call(self, session, tool_call, send_lock, text_callback, bubble_callback, glow_callback):
        """Handle tool calls from Gemini Live API."""
        for func_call in tool_call.function_calls:
            name = func_call.name
            args = dict(func_call.args)
            call_id = func_call.id
            
            logger.info(f"Gemini Live tool call: {name}({args})")
            
            try:
                if name == "delegate_to_agent":
                    result = await self._delegate_to_agent(args)
                elif name == "get_agent_status":
                    result = await self._get_agent_status(args)
                elif name == "approve_pending_action":
                    result = await self._approve_pending_action(args)
                elif name == "reject_pending_action":
                    result = await self._reject_pending_action(args)
                elif name == "get_project_context":
                    result = await self._get_project_context(args)
                elif name == "get_task_history":
                    result = await self._get_task_history(args)
                elif name == "find_task_by_description":
                    result = await self._find_task_by_description(args)
                else:
                    result = {"error": f"Unknown function: {name}"}
                
                # Send function response back to Gemini Live
                async with send_lock:
                    try:
                        # Use the current SDK method: send_tool_response
                        await session.send_tool_response(
                            function_responses=[
                                types.FunctionResponse(
                                    name=name,
                                    response=result,
                                    id=call_id,
                                )
                            ]
                        )
                    except AttributeError:
                        # Fallback for older API versions
                        try:
                            response = types.LiveClientToolResponse(
                                function_responses=[
                                    types.FunctionResponse(
                                        name=name,
                                        response=result,
                                        id=call_id,
                                    )
                                ]
                            )
                            await session.send_client_tool_response(response)
                        except AttributeError:
                            req = types.LiveClientContent(
                                turns=[types.Content(role="user", parts=[types.Part(text=f"Tool {name} result: {json.dumps(result)}")])]
                            )
                            await session.send_client_content(req)
                            
            except Exception as e:
                logger.error(f"Tool call {name} error: {e}", exc_info=True)
                async with send_lock:
                    try:
                        await session.send_tool_response(
                            function_responses=[
                                types.FunctionResponse(
                                    name=name,
                                    response={"error": str(e)},
                                    id=call_id,
                                )
                            ]
                        )
                    except AttributeError:
                        try:
                            response = types.LiveClientToolResponse(
                                function_responses=[
                                    types.FunctionResponse(
                                        name=name,
                                        response={"error": str(e)},
                                        id=call_id,
                                    )
                                ]
                            )
                            await session.send_client_tool_response(response)
                        except AttributeError:
                            pass

    async def _delegate_to_agent(self, args: dict) -> dict:
        """Delegate a task to the execution agent."""
        if not self.assistant_bridge:
            return {"error": "Assistant bridge not available"}
        
        task_description = args.get("task_description", "")
        if not task_description:
            return {"error": "task_description is required"}
        
        # Pass current model and context for better delegation
        task_id = self.assistant_bridge.delegate_task(
            task_description,
            model_id=self.current_model,
            # Could also pass history/context if available
        )
        return {"task_id": task_id, "message": f"Delegated task: {task_description}"}

    async def _get_agent_status(self, args: dict) -> dict:
        """Get status of a delegated task."""
        if not self.assistant_bridge:
            return {"error": "Assistant bridge not available"}
        
        task_id = args.get("task_id")
        if task_id:
            status = self.assistant_bridge.get_task_status(task_id)
            if status:
                return status
            return {"error": f"Task {task_id} not found"}
        else:
            tasks = self.assistant_bridge.get_active_tasks()
            return {"active_tasks": tasks}

    async def _approve_pending_action(self, args: dict) -> dict:
        """Approve a pending action."""
        if not self.assistant_bridge:
            return {"error": "Assistant bridge not available"}
        
        approval_id = args.get("approval_id")
        if not approval_id:
            return {"error": "approval_id is required"}
        
        result = self.assistant_bridge.approve_pending_action(approval_id)
        return {"result": result}

    async def _reject_pending_action(self, args: dict) -> dict:
        """Reject a pending action."""
        if not self.assistant_bridge:
            return {"error": "Assistant bridge not available"}
        
        approval_id = args.get("approval_id")
        if not approval_id:
            return {"error": "approval_id is required"}
        
        result = self.assistant_bridge.reject_pending_action(approval_id)
        return {"result": result}

    async def _get_project_context(self, args: dict) -> dict:
        """Get project/workspace context on demand."""
        if not self.assistant_bridge:
            return {"error": "Assistant bridge not available"}
        return {"project_context": self.assistant_bridge.get_project_context()}

    async def _get_task_history(self, args: dict) -> dict:
        """Get recent task history on demand."""
        if not self.assistant_bridge:
            return {"error": "Assistant bridge not available"}
        limit = args.get("limit", 5)
        history = self.assistant_bridge.get_recent_task_history(limit)
        return {"task_history": history}

    async def _find_task_by_description(self, args: dict) -> dict:
        """Find a task by description query."""
        if not self.assistant_bridge:
            return {"error": "Assistant bridge not available"}
        description = args.get("description", "")
        if not description:
            return {"error": "description is required"}
        result = self.assistant_bridge.find_task_by_description(description)
        if result:
            return {"task": result}
        return {"error": f"No task found matching: {description}"}

    def inject_agent_event(self, event: AssistantEvent):
        """Inject an agent event into the Gemini Live session as a system message."""
        if not self.loop or self.stop_event.is_set():
            return
        
        # Format event as system message
        if event.type == "approval_required":
            message = (
                f"SYSTEM: Execution agent needs approval:\n"
                f"task_id={event.task_id}\n"
                f"action={event.current_tool}\n"
                f"summary={event.summary}\n"
                f"risk={event.risk}\n"
                f"approval_id={event.approval_id}\n"
                f"Please ask the user for approval and call approve_pending_action or reject_pending_action with the approval_id."
            )
        elif event.type == "task_started":
            message = f"SYSTEM: Execution agent started task: {event.summary}"
        elif event.type == "task_completed":
            message = f"SYSTEM: Execution agent completed task: {event.summary}"
        elif event.type == "task_failed":
            message = f"SYSTEM: Execution agent task failed: {event.summary}"
        elif event.type == "tool_progress":
            message = f"SYSTEM: Execution agent progress: {event.progress}"
        else:
            message = f"SYSTEM: Execution agent update: {event.summary}"
        
        # Schedule the message injection on the event loop
        asyncio.run_coroutine_threadsafe(
            self._inject_system_message_to_session(message),
            self.loop
        )

    async def _inject_system_message(self, session, message: str):
        """Inject a non-realtime text turn into an active Live session."""
        await session.send_client_content(
            turns=types.Content(
                role="user",
                parts=[types.Part(text=message)],
            ),
            turn_complete=True,
        )

    async def _inject_system_message_to_session(self, message: str):
        """Inject system message to current session - called from event loop."""
        if self._active_session:
            await self._inject_system_message(self._active_session, message)

    def get_connection_state(self) -> str:
        return self._connection_state


def start_agent_in_thread(volume_cb, quit_cb=None, text_cb=None, state_cb=None, voice_state_cb=None, bubble_cb=None, glow_cb=None, global_agent_ref=None, assistant_bridge=None):
    agent = GeminiDesktopAgent(assistant_bridge=assistant_bridge)
    if global_agent_ref is not None:
        global_agent_ref[0] = agent  # Store agent at index 0
    if state_cb:
        agent.add_connection_callback(state_cb)
    if voice_state_cb:
        agent.add_voice_callback(voice_state_cb)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(agent.run_loop(volume_cb, quit_cb, text_cb, state_cb, bubble_cb, glow_cb))
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop_event.set()
        loop.close()