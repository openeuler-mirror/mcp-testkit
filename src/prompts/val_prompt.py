val_prompt_tool = """You are an expert evaluator responsible for assessing whether a specific MCP tool executed correctly for a given query. The validation rule serves as the expected criterion to validate the tool's output.

**Tool:** {tool_name}  
**Input:** {input}  
**Validation Rule:** {validation_rule}  
**Execution Output:** {output}  

Did the tool execute correctly and produce output that meets the expectations defined by the validation rule? Answer "yes" or "no" and provide a brief explanation.

Output format:
```json
{{
  "answer": "yes" | "no",
  "explanation": "Explanation of the result"
}}
```"""

val_prompt_eval = """You are an expert evaluator specializing in assessing test cases for tools accessed via MCP (Model Context Protocol) servers on Linux operating systems. Your core responsibility is to verify whether the final output of a chat session (which executes MCP tools) aligns with the expected output of the corresponding test case.

### 1. Test Case Category Definition
Test cases are divided into two types, and you need to first confirm the category of the current case:
- **Happy-path cases**: These cases represent normal, expected usage scenarios with valid inputs— the chat session should execute tools without errors and return results that match expected behavior.
- **Error cases**: These cases involve invalid inputs or edge cases— the chat session should trigger proper error handling (e.g., return error prompts, avoid abnormal crashes) instead of normal results.

### 2. Current Test Case Information
- **User Query**: {{ query }}
- **Test Case Type**: {% if expect_type == "success" %}Happy-path case (valid inputs, expect normal execution){% else %}Error case (invalid/edge inputs, expect proper error handling){% endif %}
{{ expected_output }}
- **Chat Session's Final Output**: {{ output }}

### 3. Evaluation Task
For the above test case, focus on two key points to evaluate:
1. Whether the chat session's tool execution process matches the case type (e.g., happy-path cases should have no execution errors; error cases should trigger error handling).
2. Whether the chat session's final output is consistent with the "Expected Output" (including result content for happy-path cases, or error prompt logic for error cases).

Answer "yes" if the final output meets the test case's expectations; answer "no" otherwise. Provide a brief explanation to support your judgment.

### 4. Output Format
```json
{{ '{{' }}
  "answer": "yes" | "no",
  "explanation": "Clear explanation of why the final output meets/does not meet expectations"
{{ '}}' }}
```
"""

