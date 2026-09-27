import os
import threading
from agent.events import emit
from agent.runtime import AgentRuntime

# Global runtime instance mapped to default config
runtime_instance = None

def run_heavy_agent_worker(task_description: str):
    global runtime_instance
    try:
        mod = os.environ.get("HEAVY_AGENT_MODEL", "gemini-2.5-flash")
        runtime_instance = AgentRuntime(model_id=mod)
        runtime_instance.run(task_description)
    except Exception as e:
        emit("LOG", "system", {"msg": f"Agent crashed fundamentally: {e}"})

def execute_task_async(task: str):
    t = threading.Thread(target=run_heavy_agent_worker, args=(task,))
    t.daemon = True
    t.start()
