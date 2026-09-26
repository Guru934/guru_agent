path = "/home/guru/guru_agent/cat_talker/gemini_live_agent.py"
with open(path, "r") as f:
    text = f.read()

action_done_block = """                                    elif action == "HEAVY_AGENT_DONE":
                                        async with send_lock:
                                            try:
                                                await session.send(input="The heavy agent has just finished its delegated task! Briefly let the user know verbally.")
                                            except AttributeError:
                                                req = types.LiveClientContent(
                                                    turns=[types.Content(role="user", parts=[types.Part(text="The heavy agent has just finished its delegated task! Briefly let the user know verbally.")])]
                                                )
                                                await session.send_client_content(req)"""

search_point = """                                    if action == "ACTIVE_WINDOW":"""
text = text.replace(search_point, action_done_block + "\n" + search_point)

with open(path, "w") as f:
    f.write(text)

