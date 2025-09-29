import re
import json
def parse_evaluation_json(response_text):
    """
    从LLM的响应文本中解析评估结果的JSON对象
    
    参数:
        response_text: LLM返回的原始文本
        tool_name: 工具名称，用于日志输出
        
    返回:
        解析后的评估结果字典，如果解析失败则返回None
    """
    # 尝试提取反引号之间的JSON内容
    json_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
    if json_match and json_match.group(1):
        json_content = json_match.group(1)
    else:
        # 未找到反引号时，使用整个响应文本尝试解析
        json_content = response_text
    
    try:
        # 解析JSON
        parsed_json = json.loads(json_content)
        return parsed_json
        
    except json.JSONDecodeError as parse_error:
        print(f"JSON解析失败: {parse_error}")
        print(f"尝试解析的内容: {json_content}")
    
    return None  # 解析失败返回None