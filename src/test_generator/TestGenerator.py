import json
import datetime
import uuid
import re
import os
from typing import List
from ..llm.LLM import LLMClient
from ..type.types_def import ToolDefinition, TestCase
from ..prompts.tool_prompt import tool_prompt
from ..prompts.eval_prompt import eval_prompt
from ..client.Session import Configuration
from ..client.MCPClient import MCPClient
from ..utils.read_source_code import ReadSourceCode

class TestGenerator:
    """
    Generator for test cases using Large Language Model
    """
    
    def __init__(self, api_key: str = None, config_path: str = None):
        """
        Create a new test generator
        
        Args:
            api_key: API key for the language model
        """
        Config_class = Configuration()
        self.config = Config_class.load_config(config_path)
        self.llm = LLMClient(api_key)
        self.readsc = ReadSourceCode(config_path)
    async def run(self):
        # load config

        servers = [MCPClient(name, srv_config) for name, srv_config in self.config["mcpServers"].items()]
        tests_per_tool = self.config["numTestsPerTool"]
        for server in servers:

            # connect server
            print("\n========================================")
            print(f"Testing server: {server.name}")
            print("========================================\n")
            await server.initialize()  
            
            # Get available tools
            tools = await server.list_tools()
            if not tools:
                Warning('No tools found in the MCP server. Nothing to test.')
            print(f"Found {len(tools)} tools:")
            print("\n".join([f"{tool.format_for_llm()}" for tool in tools]))

            # Generate tests
            print(f"Generating {tests_per_tool} tests per tool...")
            test_cases = await self.generate_tests_for_each_server(tools, tests_per_tool,server.name)
            print(f"Generated {len(test_cases)} test cases in total.")   

            self.save_to_file(server.name, test_cases)

            await server.cleanup()


    async def generate_tests_for_each_server(
        self, 
        tools: List[ToolDefinition], 
        tests_per_tool: int,
        server_name: str
    ) -> List[TestCase]:
        """
        Generate test cases for the given tools
        
        Args:
            server_name: Name of the MCP server
            tools: Tool definitions to generate tests for
            config: Tester configuration
            
        Returns:
            List of generated test cases
        """
        all_tests: List[TestCase] = []
        tool_functions = self.readsc.get_code(server_name)
        for tool in tools:
            try:
                print(f"Generating tests for tool interface: {tool.name}")
                
                tool_prompt_formatted = self.create_tool_prompt(tool, tests_per_tool, tool_functions[tool.name])
                
                response = self.llm.get_response(
                    [{"role": "user", "content": tool_prompt_formatted}]

                )
                
                if response:
                    test_cases = self.parse_response(response, tool.name)
                    
                    # Generate natural language queries for each test case
                    for test_case in test_cases:
                        print(f"Generating natural language query for {tool.name}")
                        eval_prompt_formatted = self.create_eval_prompt(tool, test_case)
                        try:
                            test_case.query = self.llm.get_response(
                                [{"role":"user","content": eval_prompt_formatted}]
                            )
                        except Exception as err:
                            print(f"Failed to generate natural language query for {tool.name}: {err}")
                            test_case.query = ''
                    
                    all_tests.extend(test_cases)
                    print(f"Generated {len(test_cases)} tests for {tool.name}")
                
                else:
                    print(f"No response received for {tool.name}")
                    
            except Exception as error:
                print(f"Error generating tests for tool {tool.name}: {error}")
        
        return all_tests
    
    def create_tool_prompt(self, tool: ToolDefinition, tests_per_tool: int, tool_function_str: str) -> str:
        """
        Create a prompt for the LLM to generate test cases for testing tool exeucation
        
        Args:
            tool: Tool definition to generate tests for
            tests_per_tool: Number of tests to generate per tool
            
        Returns:
            Formatted prompt string
        """
        # Extract input schema properties safely
        input_properties = {}
        if tool.input_schema and hasattr(tool.input_schema, 'properties'):
            input_properties = json.dumps(input_properties, indent=2)
        
        formatted_prompt = tool_prompt.format(
                                tool=tool,
                                input_properties=input_properties,
                                tests_per_tool=tests_per_tool,
                                tool_function_str=tool_function_str
                            )
        return formatted_prompt
        
    def create_eval_prompt(self, tool: ToolDefinition, test_case: TestCase) -> str:
        """
        Create a prompt for the LLM to generate test cases for end-to-end agent running
        
        Args:
            tool: Tool definition to generate tests for
            tests_per_tool: Number of tests to generate per tool
            
        Returns:
            Formatted prompt string
        """

        input = {}
        if test_case.input:
            input = json.dumps(test_case.input, indent=2)

        formatted_prompt = eval_prompt.format(tool=tool, test_case=test_case, test_case_inputs = input)
        return formatted_prompt


    def parse_response(self, response_text: str, tool_name: str) -> List[TestCase]:
        """
        Parse LLM's response into test cases
        
        Args:
            response_text: LLM's response text
            tool_name: Name of the tool being tested
            
        Returns:
            List of parsed test cases
        """
        json_content = response_text
        
        try:
            # Extract JSON content between backticks if present
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
            if json_match and json_match.group(1):
                json_content = json_match.group(1)
            else:
                # Attempt to gracefully handle cases where the LLM might forget the backticks
                print(f"[{tool_name}] LLM response did not contain JSON within backticks. Attempting to parse directly.")
            
            # Parse JSON
            try:
                parsed_json = json.loads(json_content)
            except json.JSONDecodeError as parse_error:
                print(f"[{tool_name}] Failed to parse JSON from LLM response. Error: {parse_error}")
                print(f"[{tool_name}] Raw response text was: {response_text}")
                return []  # Return empty if JSON parsing fails
            
            # Ensure parsed_json is a list
            if not isinstance(parsed_json, list):
                print(f"[{tool_name}] Parsed JSON is not an array. LLM response might be malformed. Raw response: {response_text}")
                # If it's a single object that looks like a test case, wrap it in an array
                if (isinstance(parsed_json, dict) and 
                    'description' in parsed_json and 
                    'input' in parsed_json and 
                    'expect' in parsed_json):
                    print(f"[{tool_name}] Attempting to recover by wrapping single test case object in an array.")
                    parsed_json = [parsed_json]
                else:
                    return []
            
            valid_test_cases: List[TestCase] = []
            
            for index, test in enumerate(parsed_json):
                # Basic validation for essential fields
                if not isinstance(test, dict):
                    print(f"[{tool_name}] Test case at index {index} is not a valid object. Skipping.")
                    continue
                
                if not test.get('description') or not isinstance(test['description'], str):
                    print(f"[{tool_name}] Test case at index {index} is missing or has an invalid 'description'. Skipping: {json.dumps(test)}")
                    continue
                
                if 'input' not in test or not isinstance(test['input'], dict):
                    print(f"[{tool_name}] Test case \"{test['description']}\" is missing or has invalid 'inputs'. Skipping: {json.dumps(test)}")
                    continue
                
                if not test.get('expect') or not isinstance(test['expect'], dict):
                    print(f"[{tool_name}] Test case \"{test['description']}\" is missing or has invalid 'expect'. Skipping: {json.dumps(test)}")
                    continue
                
                expected_outcome = test['expect']
                if (not expected_outcome.get('status') or 
                    expected_outcome['status'] not in ['success', 'error']):
                    print(f"[{tool_name}] Test case \"{test['description']}\" has missing or invalid 'expectedOutcome.status'. Skipping: {json.dumps(test)}")
                    continue

                # Create test case
                test_case = TestCase(
                    id=str(uuid.uuid4()),
                    toolName=tool_name,
                    description=test['description'],
                    query='',
                    input=test['input'],
                    expect={
                        "status":expected_outcome['status'],
                        "validation_rules": expected_outcome.get('validationRules', []) or []
                    }
                    )
                valid_test_cases.append(test_case)
            return valid_test_cases
            
        except Exception as error:
            # Catch any other unexpected errors during processing
            print(f"[{tool_name}] Unexpected error in parse_response: {error}")
            print(f"[{tool_name}] Response text was: {response_text}")
            return []


    def testcases_to_dict(self, testcases: List[TestCase])-> List:
        res = []
        for case in testcases:
            res.append( {
                "id": case.id,
                "toolName": case.toolName,
                "description": case.description,
                "query": case.query,
                "input": case.input,
                "expect": case.expect
            })
        return res

    def save_to_file(self, server_name: str, testcases: List[TestCase]):
        """
        save test cases (array of JSON) to file
        """
        testcases = self.testcases_to_dict(testcases)
        try:
            if not isinstance(testcases, list):
                raise ValueError("input data should be an array of JSON")
            
            current_timestamp = datetime.datetime.utcnow().isoformat()
            safe_timestamp = current_timestamp.replace(":", "-").replace(".", "-")
            
            folerpath = os.path.join(".logs",f'{server_name}_{safe_timestamp}')
            if not os.path.exists(folerpath):
                os.mkdir(folerpath)
            
            filename = f"testcases.json"
            filepath = os.path.join(folerpath,filename)
            with open(filepath, 'w', encoding='utf-8') as file:
                json.dump(testcases, file, ensure_ascii=False, indent=4)
            print(f"{server_name} test cases are successfully saved into {filepath}")
            return True
        
        except IOError as e:
            print(f"文件操作错误: {e}")
        except ValueError as e:
            print(f"数据格式错误: {e}")
        except Exception as e:
            print(f"发生未知错误: {e}")
        
        return False