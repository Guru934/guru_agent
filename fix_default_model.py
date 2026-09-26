path = "/home/guru/guru_agent/ui_scratchpad.py"
with open(path, "r") as f:
    text = f.read()

# Change default model selection config to Gemini Live
text = text.replace('self.orchestrator = AgentOrchestrator(default_model="qwen-6gb:latest"', 'self.orchestrator = AgentOrchestrator(default_model="gemini-3.1-flash-live-preview"')
text = text.replace('self.model_dropdown.setCurrentText(self.model_name_map.get("qwen-6gb:latest"))', 'self.model_dropdown.setCurrentText(self.model_name_map.get("gemini-3.1-flash-live-preview"))')

with open(path, "w") as f:
    f.write(text)

