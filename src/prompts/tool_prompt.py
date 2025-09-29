tool_prompt = """
You are an expert in generating comprehensive test cases for tools accessed through MCP (Model Context Protocol) servers on Linux operating systems. Your task is to create diverse, realistic test cases that thoroughly validate tool functionality.
## Tool Definition
Name: {tool.name}
Description: {tool.description}
Parameters: {input_properties}
Tool Source Code: {tool_function_str}
(since the tool may lack a formal outputSchema, the source code is the authoritative reference for output format/structure)

## Instructions
1. Generate {tests_per_tool} diverse test cases covering these categories:
    - Happy Path (80%): Normal, expected usage scenarios with valid inputs
    - Error Cases (20%): Invalid or edge case inputs that should trigger proper error handling 

2. For each test case, provide these fields:
    - `description`: A concise explanation of the scenario and its test intent.
    - `input`: A JSON object with concrete and plausible parameter values. Avoid generic placeholders; use specific, realistic values as users would (e.g., use "3.11" for Python version).
    - `expect`:
      - `status`: "success" for happy path, or "error" if an error is expected.
      - `validationRules`: An **array of assertion rules** to precisely check the tool's response.  **Validation rules are critical for automated testing, so each rule must be clear, unambiguous, and directly translatable to Python test code.**  
        Every rule must include 3 key fields:
        - `type`: One of [`contains`,`equals`,`schema`, `llm`]  
        - `value`: A **machine-parsable value** (no redundant natural language) in the specified format—see below for details.
        - `message`: A helpful description to show if validation fails.
        - **Choose the validation `type` and construct `value` as follows:**
            - **contains**: Verify the response includes an **exact, static substring** (max 4 words/fragments).  
              - `value`: `"[exact_text_fragment]"`(wrap in double quotes; use single quotes inside for clarity, e.g., `" 'Python 3.11 installed' "`) 
           - **equals**: Verify the **entire response** matches an exact, fixed value. (fixed numbers, short strings, booleans).  
              - `value`: For strings: `"[exact_string]"`; for numbers/booleans: `[exact_value]`(no quotes)  
            - **schema**: Validate JSON structure/data types (required fields, value types).  
              - `value`: `[valid_json_schema]` 
            - **llm**: For semantic validation requiring human-like judgment (e.g., summary accuracy).  
              - `value`: `Natural language specifying semantic criteria.`

        - **For successful (“success”) test cases:**  
            - Prefer `schema` if the response is structured. Prefer `contains` for specific fragments, and `equals` only for fixed outputs. Use `llm` for **semantic validation requiring human judgment** (e.g., summary accuracy)

        - **For error (“error”) test cases:**  
            - Validate on the **presence and clarity of error indications** (e.g., specific error messages, error codes, required fields in the error response).
            - Prefer `"contains"` for specific fragments/errors and `"schema"` only if error objects are structured.
            - Make sure the rule can be programmatically checked.

## Output Format

Return a **pure JSON array** of test cases in the following structure:

```json
[
  {{
    "description": "A brief but precise description of the test scenario.",
    "input": {{ /* Concrete parameter values */ }},
    "expect": {{
      "status": "success|error",
      "validationRules": [
        {{
          "type": "contains|equals|schema|llm",
          "value": "xxx",   // See format above; must be directly checkable
          "message": "Custom failure explanation for this rule."
        }}
        /* ... more validation rules as appropriate ... */
      ]
    }}
  }}
  /* ... more test cases ... */
]
```
"""