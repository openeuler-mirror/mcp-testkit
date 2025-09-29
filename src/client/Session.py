import json
import logging
import os
from typing import Any
from dotenv import load_dotenv
from .MCPClient import MCPClient
from ..llm.LLM import LLMClient
from ..utils.parse_json import parse_evaluation_json

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class Configuration:
    """Manages configuration and environment variables for the MCP client."""

    def __init__(self) -> None:
        """Initialize configuration with environment variables."""
        self.load_env()
        self.api_key = os.getenv("LLM_API_KEY")

    @staticmethod
    def load_env() -> None:
        """Load environment variables from .env file."""
        load_dotenv()

    @staticmethod
    def load_config(file_path: str) -> dict[str, Any]:
        """Load server configuration from JSON file.

        Args:
            file_path: Path to the JSON configuration file.

        Returns:
            Dict containing server configuration.

        Raises:
            FileNotFoundError: If configuration file doesn't exist.
            JSONDecodeError: If configuration file is invalid JSON.
        """
        with open(file_path, "r") as f:
            return json.load(f)

    @property
    def llm_api_key(self) -> str:
        """Get the LLM API key.

        Returns:
            The API key as a string.

        Raises:
            ValueError: If the API key is not found in environment variables.
        """
        if not self.api_key:
            raise ValueError("LLM_API_KEY not found in environment variables")
        return self.api_key


class ChatSession:
    def __init__(self, server: MCPClient, llm_client: LLMClient) -> None:
        self.server = server
        self.llm_client = llm_client

    async def process_llm_response(self, llm_response: str) -> str:
        """Process the LLM response and execute tools if needed.

        Args:
            llm_response: The response from the LLM.

        Returns:
            The result of tool execution or the original response.
        """
        tool_info = {
            "tool_name": "",
            "arguments": {},
        }
        try:
            tool_call = parse_evaluation_json(llm_response)
            if tool_call and "tool" in tool_call and "arguments" in tool_call:
                print(f"Executing tool: {tool_call['tool']}")
                print(f"With arguments: {tool_call['arguments']}")
                tool_info["tool_name"] = tool_call["tool"]
                tool_info["arguments"] = tool_call["arguments"]

                tools = await self.server.list_tools()
                if any(tool.name == tool_call["tool"] for tool in tools):
                    try:
                        result = await self.server.execute_tool(tool_call["tool"], tool_call["arguments"])
                        result_str = f"{result}"
                        if len(result_str) > 500:
                            logging.info(f"The output of tool execution is too long. Only show part of it: {result[:400]}... {result[-100:]}")
                        else:
                            logging.info(f"Tool execution result: {result}")
                        return tool_info, f"Tool execution result: {result}" ###这里有问题，把输出变成str了
                    except Exception as e:
                        error_msg = f"Error executing tool: {str(e)}"
                        print(error_msg)
                        return tool_info, error_msg

                return tool_info, f"No server found with tool: {tool_call['tool']}"
            return tool_info, f"tool call json decode error: {llm_response}"
        except json.JSONDecodeError:
            return tool_info, llm_response
    
    async def handle_query(self, query) -> None:
        all_tools = []
        # for server in self.servers:
        tools = await self.server.list_tools()
        all_tools.extend(tools)

        tools_description = "\n".join([tool.format_for_llm() for tool in all_tools])

        system_message = f"""You are a helpful assistant with access to these tools:
{tools_description}
Choose the appropriate tool based on the user's question. If no tool is needed, reply directly.
IMPORTANT: When you need to use a tool, you must ONLY respond with the exact JSON object format below, nothing else:
```json
{{
    "tool": "tool-name",
    "arguments": {{
        "argument-name": "value"
    }}
}}
```
After receiving a tool's response:
1. Transform the raw data into a natural, conversational response
2. Keep responses concise but informative
3. Focus on the most relevant information
4. Use appropriate context from the user's question
5. Avoid simply repeating the raw data

Please use only the tools that are explicitly defined above."""


        messages = [{"role": "system", "content": system_message}]
        messages.append({"role": "user", "content": "User query:"+query})

        llm_response = self.llm_client.get_response(messages)
        print("\nAssistant: %s", llm_response)

        tool_info, tool_result = await self.process_llm_response(llm_response)
        tool_included_or_not = True if tool_result != llm_response else False
        if tool_included_or_not:
            return tool_included_or_not, tool_info, tool_result
        else:
            return tool_included_or_not, tool_info, 'No tool was used, here is the direct response: '+ llm_response


