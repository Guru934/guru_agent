import time
import logging
import uuid
from typing import Optional
from google import genai
from google.genai import types

from agent.state import TaskState
from agent.events import emit
from agent.executor import ToolExecutor
from agent.tool_registry import registry

class AgentRuntime:
    def __init__(self, model_id: str = "gemini-2.5-flash"):
        self.model_id = model_id
        self.executor = ToolExecutor(registry)
        self.client = genai.Client()
        self._cancellation_tokens = set()

    def cancel_task(self, task_id: str):
        self._cancellation_tokens.add(task_id)

    def run(self, request: str, task_id: str = None) -> TaskState:
        if not task_id:
            task_id = str(uuid.uuid4())
            
        state = TaskState(task_id=task_id, original_request=request)
        emit("TASK_STARTED", task_id, {"description": request})
        
        system_instruction = (
            "You are a local autonomous desktop agent. You execute OS and codebase operations safely."
            "Think systematically. First you PLAN, then you ACT by calling tools."
            "If the tool execution output shows an issue, adapt your plan."
            "When the final goal is met, respond normally in plain text to end the session."
        )


        from google.genai.types import FunctionDeclaration, Type, Schema
        
        declarations = []
        for spec in registry.get_all_specs():
            # Build schema mapping
            props = {}
            for prop_name, prop_val in spec.input_schema["properties"].items():
                p_type = Type.STRING if prop_val["type"] == "STRING" else Type.STRING
                props[prop_name] = Schema(type=p_type)
                
            decl = FunctionDeclaration(
                name=spec.name,
                description=spec.description,
                parameters=Schema(
                    type=Type.OBJECT,
                    properties=props,
                    required=spec.input_schema["required"]
                )
            )
            declarations.append(decl)

        tools = [types.Tool(function_declarations=declarations)]

        chat = self.client.chats.create(
            model=self.model_id,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                tools=tools,
                temperature=0.0
            )
        )
        
        try:
            emit("LOG", task_id, {"msg": f"Starting agent runtime for prompt: {request}"})
            response = chat.send_message(request)

            while not state.completed:
                if task_id in self._cancellation_tokens:
                    state.error = "Task cancelled by user."
                    state.completed = True
                    break
                    
                if state.step_count >= state.max_steps:
                    state.error = f"Task exceeded maximum steps ({state.max_steps})."
                    state.completed = True
                    break

                if response.function_calls:
                    for fn_call in response.function_calls:
                        action = fn_call.name
                        # unpack dictionary of arguments safely
                        args = {k: v for k, v in fn_call.args.items()} 

                        result = self.executor.execute(action, args, {"task_id": task_id})
                        is_error = result.status in ["denied", "error"]
                        result_text = str(result.output)
                        
                        state.add_observation(action, args, result_text, is_error=is_error)
                        
                        # Tell Gemini the observation
                        # In the new genai API, responding to a function call usually means passing a Part with FunctionResponse
                        emit("LOG", task_id, {"msg": f"Tool '{action}' resulted in: {result_text[:100]}..."})
                    
                    state.step_count += 1
                    
                    # Pass the aggregated function responses back to the bot
                    # (Google genai requires passing FunctionResponses properly to the history or via send_message)
                    # For simplicity, we can pass it as a normal message for now, though best practice is types.Part.from_function_response
                    function_responses = []
                    for fn_call in response.function_calls:
                        for obs in state.observations[-len(response.function_calls):]: # get the most recent ones
                            if obs.tool_name == fn_call.name:
                                resp_dict = {"output": obs.result}
                                function_responses.append(
                                    types.Part.from_function_response(
                                        name=fn_call.name,
                                        response=resp_dict
                                    )
                                )
                                break
                    
                    response = chat.send_message(function_responses)
                
                else:
                    # No function calls means it gave a standard final text answer!
                    state.final_answer = response.text
                    state.completed = True

        except Exception as e:
            state.error = f"Agent runtime crash: {e}"
            state.completed = True
            
        if state.error:
            emit("TASK_FAILED", task_id, {"error": state.error})
        else:
            emit("TASK_COMPLETED", task_id, {"result": state.final_answer})
            
        return state
