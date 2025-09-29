env_prompt = """You have received a debugging task: a test case has failed its validation due to not meeting specific environmental requirements. 
The specific reason is: {reason}. Your job is to write a Bash script that configures the environment to satisfy these special requirements.

**Important Notes:**
- The default environment already has Anaconda, Python, and the following common dependencies pre-installed:
  {dependencies}
  **Do not include redundant commands for these in your script.**
- Carefully review the test case's description field to identify any additional environment setup needed beyond the standard baseline.
- **Target Specifics**: Focus only on additional setup needed to address the failure, as indicated in the test case description. Examples include:
   - Enabling/disabling services (e.g., stopping Docker if the test requires it to be unavailable)
   - Creating required directories/files with specific structures or contents
   - Installing/removing packages not in the pre-installed list
- Minimal Steps: Only include core commands needed to meet the special requirements—no extra configurations, optimizations, or redundant checks.
- The target operating system is openEuler. Please ensure:
    - Use yum or dnf instead of apt-get
    - Employ commands suitable for RHEL/CentOS series

### Input Example  
Test case(s):  
{testcases}  

Test output and validation results:  
output: {output}  
validation_results: {validation_results}  

### Output Format  
Wrap your bash script between the following tags:
```plaintext
<script>
# Your Bash script here
</script>
```
"""

not_pass_judge_prompt = """# Debugging Task Instructions  

You have received a debugging task for a test case that failed its validation rules. Please follow these steps to identify the root cause:  

### 1. Identify the Test Case Type  
- Before identification, check the `expect` field of the test case:  
  - If the value is `"Success"`, the test case is **expected to succeed** (i.e., it is a normal/happy-path scenario).  
  - If the value is `"Error"`, the test case is **intentionally designed to fail** (i.e., it validates error-handling logic).  

### 2. Confirm Environmental Requirements  
- Standard Testing Environment Baseline: The default environment already includes pre-installed Anaconda, Python, and the common dependencies
{dependencies}
Check for Special Requirements: Read the test case's description field to determine if it needs additional environmental setup beyond the standard baseline. 
For additional environmental setup, examples include:
   - Enabling/disabling services (e.g., stopping Docker if the test requires it to be unavailable)
   - Creating required directories/files with specific structures or contents
   - Installing/removing packages not in the pre-installed list

### 3. The definition of rule type
    - **contains**: Verify the response includes an **exact, static substring** (max 4 words/fragments).  
        - `value`: `"[exact_text_fragment]"`(wrap in double quotes; use single quotes inside for clarity, e.g., `" 'Python 3.11 installed' "`) 
    - **equals**: Verify the **entire response** matches an exact, fixed value. (fixed numbers, short strings, booleans).  
        - `value`: For strings: `"[exact_string]"`; for numbers/booleans: `[exact_value]`(no quotes)  
    - **schema**: Validate JSON structure/data types (required fields, value types).  
        - `value`: `[valid_json_schema]` 
    - **llm**: For semantic validation requiring human-like judgment (e.g., summary accuracy).  
        - `value`: `Natural language specifying semantic criteria.`

### 4. Analyze the Failure Cause  
- Review the `output` (actual result of the test) and `validation_results` (details of failed/passed rules):  
  - Judge if the failure stems from **unmet special environmental requirements** (e.g., unstopped Docker service, or unconfigured simulation that the test depends on).  
  - Or if the failure is caused by **issues with the validation rule itself** (e.g., incorrect expected values, or too tightly strict validation rules).  
- Base your judgment on the known standard testing environment (do not assume unstated configurations).  

### Input Example  
Test case(s):  
{testcases}  

Test output and validation results:  
output: {output}  
validation_results: {validation_results}  

### Output Format  
Provide a clear, direct answer using the following JSON format (do not include extra content):  

```json
{{
  "option": "a. Unmet special environmental requirement" or "b. Issue with the validation rule itself",
  "reason": "Concise, specific explanation (e.g., 'The test requires an nginx process running on port 80, but the standard environment lacks this setup' or 'The validation rule expects Python 3.8, but the test uses Python 3.9—an unreasonable mismatch')"
}}
```
"""
