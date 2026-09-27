import asyncio
import random

from google import genai
from google.genai import types


from ui.audio import AudioInterface
from tools.vision import VisionInterface
from utils import get_logger
from ui.earcons import play_earcon

logger = get_logger("cat_talker.agent")

# --- MONKEY PATCH WEBSOCKETS TO DISABLE PING TIMEOUTS FOR STRICT PROXIES ---
import websockets.asyncio.client
_orig_connect = websockets.asyncio.client.connect
def _patched_connect(*args, **kwargs):
    kwargs['ping_interval'] = 20.0
    kwargs['ping_timeout'] = 20.0
    return _orig_connect(*args, **kwargs)
websockets.asyncio.client.connect = _patched_connect
# --------------------------------------------------------------------------

class GeminiDesktopAgent:
    def __init__(self):
        self.client = genai.Client()
        self.audio = None
        self.vision = None
        self.stop_event = asyncio.Event()
        self._is_speaking = False
        self._is_processing = False
        self.synthetic_input_queue = asyncio.Queue()
        self.is_recording = False
        self.loop = None
        self.current_model = "gemini-3.1-flash-live-preview"
        self.fallback_models = ["gemini-3.1-flash-live-preview", "gemini-3.8-live"]
        self.fallback_idx = 0
        
    def switch_model(self, model_id: str):
        self.current_model = model_id
        if model_id not in self.fallback_models:
            self.fallback_models.insert(0, model_id)
            self.fallback_idx = 0
        self.stop_event.set() # This forces the while loop to exit and restart if we added a reconnect wrapper. Wait, actually stop_event kills the thread. 
        # Better: just set a flag that we should reconnect.
        self._force_reconnect = True

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
        self.audio = AudioInterface()
        self.audio.volume_cb = volume_callback
        
        self.vision = VisionInterface()


        logger.info(f"Connecting to Gemini Live API with model: {self.current_model}")

        system_instructions = (
            "You are a voice conversation assistant. This realtime session has no OS tools. "
            "Do not claim to perform desktop actions; explain that actions must be submitted through the main assistant."
        )

        try:
            while not self.stop_event.is_set():
                try:
                    
                    config = types.LiveConnectConfig(
                        response_modalities=["AUDIO"],
                        system_instruction=types.Content(parts=[types.Part(text=system_instructions)]),
                        output_audio_transcription=types.AudioTranscriptionConfig(word_timestamp=False),
                    )

                    self._force_reconnect = False
                    async with self.client.aio.live.connect(model=self.current_model, config=config) as session:
                        logger.info("====================================")
                        logger.info("✅ Session established securely!")
                        logger.info("🎙️ Speak into your microphone now...")
                        logger.info("====================================")
                        if not getattr(self, '_has_connected_once', False):
                            if text_callback:
                                text_callback("system", "Gemini Live Connected! Hold F1 to push-to-talk.")
                            self._has_connected_once = True
                        self._set_state(state_callback, "idle")
                        self._set_glow(glow_callback, "connected")
                        
                        # Reset reconnect attempts on successful connection
                        self._reconnect_attempts = 0

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
                                            self._set_state(state_callback, "listening")
                                            
                                            pass

                                        if hasattr(msg.server_content, 'turn_complete') and msg.server_content.turn_complete:
                                            self._is_speaking = False
                                            self._set_state(state_callback, "listening")
                                            self._set_glow(glow_callback, "connected")
                                            
                                            pass

                                        if msg.server_content.model_turn:
                                            # Model started responding - thinking phase
                                            if not self._is_speaking:
                                                self._is_speaking = True
                                                self._set_state(state_callback, "thinking")
                                                self._set_glow(glow_callback, "thinking")
                                                
                                                pass

                                            for part in msg.server_content.model_turn.parts:
                                                if hasattr(part, "inline_data") and part.inline_data:
                                                    # Audio chunk arriving - speaking phase
                                                    if not self._is_speaking:
                                                        self._is_speaking = True
                                                    self._set_state(state_callback, "talking")
                                                    self._set_glow(glow_callback, "connected")
                                                    self.audio.queue_output(part.inline_data.data)
                                                if hasattr(part, "text") and part.text and text_callback:
                                                    text_callback("model", part.text)
                                                    # Also show in bubble
                                                    self._set_bubble(bubble_callback, part.text)

                                    if hasattr(msg, "client_content") and msg.client_content:
                                        for turn in getattr(msg.client_content, "turns", []):
                                            if turn.role == "user":
                                                for part in turn.parts:
                                                    if hasattr(part, "text") and part.text and text_callback:
                                                        text_callback("user", part.text)
                                                        self._set_state(state_callback, "listening")
                                                        self._set_glow(glow_callback, "connected")

                                    if hasattr(msg, "tool_call") and msg.tool_call:
                                        logger.error("Ignoring a realtime tool call; OS tools are disabled in this provider.")

                            except Exception as e:
                                logger.error(f"Receive interrupted (reconnecting): {e}", exc_info=True)


                        async def synthetic_input_worker():
                            logger.info("Started Synthetic Input Worker...")
                            while not self.stop_event.is_set():
                                try:
                                    action = await self.synthetic_input_queue.get()
                                    if action == "HEAVY_AGENT_DONE":
                                        async with send_lock:
                                            try:
                                                await session.send(input="The heavy agent has just finished its delegated task! Briefly let the user know verbally.")
                                            except AttributeError:
                                                req = types.LiveClientContent(
                                                    turns=[types.Content(role="user", parts=[types.Part(text="The heavy agent has just finished its delegated task! Briefly let the user know verbally.")])]
                                                )
                                                await session.send_client_content(req)
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
                                                try:
                                                    await session.send(input="The user just pressed the active window hotkey. Look at the provided image. What do you see? Or ask the user how you can help with it.")
                                                except AttributeError:
                                                    # Fallback if send doesn't accept input= kwarg
                                                    req = types.LiveClientContent(
                                                        turns=[types.Content(role="user", parts=[types.Part(text="The user just pressed the active window hotkey. Look at the provided image. What do you see?")])]
                                                    )
                                                    await session.send_client_content(req)
                                except Exception as e:
                                    logger.error(f"Synthetic input worker error: {e}", exc_info=True)

                        tasks = [
                            asyncio.create_task(mic_worker()),
                            asyncio.create_task(receive_worker()),
                            asyncio.create_task(synthetic_input_worker())
                        ]

                        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                        for task in pending:
                            task.cancel()

                except Exception as e:
                    err_str = str(e)
                    logger.error(f"Agent connection dropped (auto-reconnecting): {e}", exc_info=True)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str:
                        self.fallback_idx = (self.fallback_idx + 1) % len(self.fallback_models)
                        new_model = self.fallback_models[self.fallback_idx]
                        if self.current_model != new_model:
                            self.current_model = new_model
                            logger.info(f"Auto-switching Live backend to fallback model: {self.current_model}")
                            if bubble_callback: bubble_callback(f"Quota exceeded! Auto-switching to {self.current_model}...")
                    play_earcon("fail")
                    if text_callback:
                        text_callback("system", f"Reconnecting... ({e})")
                    
                    # Exponential backoff with jitter
                    if not hasattr(self, '_reconnect_attempts'):
                        self._reconnect_attempts = 0
                    self._reconnect_attempts += 1
                    max_delay = 60  # Max 60 seconds
                    base_delay = min(2 ** self._reconnect_attempts, max_delay)
                    jitter = random.uniform(0, 1)
                    delay = base_delay + jitter
                    logger.info(f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})...")
                    await asyncio.sleep(delay)
                    
                    # Reset reconnect attempts on successful connection (handled in the while loop restart)

        finally:
            logger.info("Shutting down audio...")
            if self.audio:
                self.audio.close()
                self.audio = None
            if app_quit_callback:
                app_quit_callback()

def start_agent_in_thread(volume_cb, quit_cb=None, text_cb=None, state_cb=None, bubble_cb=None, glow_cb=None, global_agent_ref=None):
    agent = GeminiDesktopAgent()
    if global_agent_ref is not None:
        global_agent_ref.append(agent)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(agent.run_loop(volume_cb, quit_cb, text_cb, state_cb, bubble_cb, glow_cb))
    except KeyboardInterrupt:
        pass
    finally:
        agent.stop_event.set()
        loop.close()
