from typing import List, Dict, Optional
import json
import os
import ast

class ReadSourceCode:
    def __init__(self, config_path: str = None):
        with open(config_path, "r") as f:
            self.config = json.load(f)

    def get_code(self, server_name: str) -> List[str]:
        source_path = self.extract_source_code_path(server_name)
        if not source_path:
            return []
        tool_functions = self.get_mcp_tool_functions(source_path)
        return tool_functions
              
    def extract_source_code_path(self, server_name: str) -> Optional[str]:
        """
        从 Server 的 args 中提取源代码文件（.py）的绝对路径
        :param self.config: Server 的 args 列表（如 ["--directory", "/path", "server.py"]）
        :param command: Server 的 command（如 "uv"、"python3.11"，辅助判断参数逻辑）
        :return: 源代码绝对路径（None 表示未找到）
        """
        try:
            server_args = self.config["mcpServers"][server_name]['args']

            source_file = None
            work_dir = os.getcwd()  # 默认工作目录（当前目录）

            for i, arg in enumerate(server_args):
                if arg == "--directory" and i + 1 < len(server_args):
                    work_dir = server_args[i + 1]
                    work_dir = os.path.abspath(work_dir)
                    break

            for arg in server_args:
                if arg.endswith(".py"):
                    source_file = arg
                    break

            if not source_file:
                print("未在 args 中找到 .py 源代码文件")
                return None

            if os.path.isabs(source_file):
                # 若已是绝对路径，直接使用
                absolute_path = source_file
            else:
                # 相对路径 → 拼接工作目录
                absolute_path = os.path.join(work_dir, source_file)

            # 验证文件是否存在
            if os.path.exists(absolute_path):
                return absolute_path
            else:
                print(f"源代码文件不存在：{absolute_path}")
                return None
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_mcp_tool_functions(self, source_path: str) -> Dict[str, str]:
        """
        解析源代码文件，提取被 @mcp.tool() 装饰的函数名和对应函数代码
        :param source_path: 源代码文件路径（.py）
        :return: 字典，键为函数名，值为函数完整代码字符串
        $$$待修改
        """
        
        tool_functions = {}  # 改为字典存储函数名和代码

        # 读取源代码内容
        with open(source_path, "r", encoding="utf-8") as f:
            source_code = f.read()

        # 用 ast 解析抽象语法树
        tree = ast.parse(source_code)
        # 遍历语法树，找到函数定义并检查装饰器
        for node in ast.walk(tree):
            # 只处理函数定义节点（def 函数）
            if isinstance(node, ast.FunctionDef):
                # 检查函数是否有 @mcp.tool() 装饰器
                for decorator in node.decorator_list:
                    # 处理两种装饰器形式：@mcp.tool() 或 @mcp.tool(name="xxx")
                    is_mcp_tool = False
                    if isinstance(decorator, ast.Call):
                        # 装饰器带参数（如 @mcp.tool(name="test")）
                        if (isinstance(decorator.func, ast.Attribute) 
                            and decorator.func.value.id == "mcp" 
                            and decorator.func.attr == "tool"):
                            is_mcp_tool = True
                    elif isinstance(decorator, ast.Attribute):
                        # 装饰器不带参数（如 @mcp.tool）
                        if decorator.value.id == "mcp" and decorator.attr == "tool":
                            is_mcp_tool = True

                    if is_mcp_tool:
                        # 提取函数完整代码（包括装饰器、文档字符串和函数体）
                        function_code = ast.get_source_segment(source_code, node)
                        if function_code:
                            tool_functions[node.name] = function_code.strip()
                        break  # 找到匹配的装饰器后跳出循环

        return tool_functions
