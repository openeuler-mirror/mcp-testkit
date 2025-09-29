eval_prompt = """Create a natural, conversational request for an AI assistant to perform this specific test scenario:

Tool: {tool.name} - {tool.description}
Purpose: {test_case.description}

Parameters to include:
{test_case_inputs}

Craft a single, fluent sentence that naturally incorporates these parameter values as if you're asking for help with this specific task. Make it sound like a real user request rather than a technical specification.

Natural language request:"""