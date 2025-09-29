import asyncio
import sys
import logging
import subprocess
import os
import time
import shutil
import docker  
from docker.errors import NotFound, APIError
from contextlib import AsyncExitStack
from typing import Any, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from ..utils.parse_json import parse_evaluation_json
from .DockerRegistry import DockerContainerRegistry

class MCPClient:
    """MCP Client, 支持可靠的Docker生命周期管理"""

    def __init__(self, name: str, config: dict[str, Any], env_script: str = "", use_docker: bool = False) -> None:
        self.name: str = name
        self.config: dict[str, Any] = config
        self.session: Optional[ClientSession] = None
        self._cleanup_lock: asyncio.Lock = asyncio.Lock()
        self.exit_stack: AsyncExitStack = AsyncExitStack()

        self.env_script = env_script
    
        
        # 状态管理
        self._is_initialized = False
        self._is_cleaning_up = False
        self._cleanup_completed = asyncio.Event()

        # Docker相关配置
        self.use_docker = use_docker
        self.abs_script_path = self.get_command_script_path()
        self.host_mcp_path = self.abs_script_path.split('src')[0] if self.abs_script_path else ""
        self.container_mcp_path = "/app/"
        self.server_port = config.get("port", 8080)

        # Docker进程管理
        self.docker_process = None
        self.container_id = None
        self.container_name = None

        self.client = docker.from_env()
        
        # 初始化全局容器注册表
        if use_docker:
            DockerContainerRegistry.initialize()
            self._registry = DockerContainerRegistry()
    
    async def initialize(self) -> None:
        """初始化服务器"""
        if self._is_initialized:
            logging.warning(f"服务器 {self.name} 已经初始化")
            return
        
        try:
            logging.info(f"开始初始化服务器 {self.name}")
            
            if self.use_docker:
                await self._initialize_docker()
            else:
                await self._initialize_host_server()
            
            self._is_initialized = True
            
        except Exception as e:
            logging.error(f"初始化失败: {e}")
            await self.cleanup()
            raise

    async def _initialize_host_server(self) -> None:
        """在主机上启动MCP服务器"""
        command = shutil.which("npx") if self.config["command"] == "npx" else self.config["command"]
        if command is None:
            raise ValueError(f"主机命令不存在: {self.config['command']}")

        server_params = StdioServerParameters(
            command=command,
            args=self.config["args"],
            env={**os.environ, **self.config["env"]} if self.config.get("env") else None,
        )

        try:
            stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self.session = session
            logging.info(f"主机上的MCP服务器 {self.name} 已初始化")
        except Exception as e:
            logging.error(f"主机服务器初始化失败: {e}")
            raise

    def _build_docker_command(self) -> list[str]:
        """构建Docker运行命令"""
        self.container_name = f"mcp-server-{self.name}-{int(time.time())}"
        
        docker_cmd = [
            "docker", "run",
            "--rm",
            "-i",
            "--name", self.container_name,
            "--workdir", self.container_mcp_path,
        ]
        
        # 挂载主机MCP代码目录到容器
        docker_cmd.extend([
            "-v", f"{self.host_mcp_path}:{self.container_mcp_path}"
        ])
        
        # 添加环境变量
        env_vars = {
            "PYTHONPATH": self.container_mcp_path,
            "PYTHONUNBUFFERED": "1",
            "PIP_ROOT_USER_ACTION": "ignore",
        }
        env_vars.update(self.config.get("env", {}))

        for key, value in env_vars.items():
            docker_cmd.extend(["-e", f"{key}={value}"])
        
        docker_cmd.extend(["-a", "stdout", "-a", "stderr"])

        # 添加Docker镜像
        self.docker_image = "val:latest"
        docker_cmd.append(self.docker_image)
        
        startup_script = self._build_correct_bash_script()
        docker_cmd.extend(["bash", "-c", startup_script])
        
        return docker_cmd
    def get_command_script_path(self) -> str:
        """获取命令脚本路径"""
        try:
            server_args = self.config['args']
            source_file = None
            work_dir = os.getcwd()
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
                logging.warning("未在 args 中找到 .py 源代码文件")
                return None

            if os.path.isabs(source_file):
                absolute_path = source_file
            else:
                absolute_path = os.path.join(work_dir, source_file)

            if os.path.exists(absolute_path):
                return absolute_path
            else:
                logging.error(f"源代码文件不存在：{absolute_path}")
                return None
        except Exception as e:
            logging.error(f"获取脚本路径出错: {e}")
            return None
    def _build_correct_bash_script(self) -> str:
        """构建启动脚本"""
        container_command = self._get_container_command()
        script = f'''set -e

    echo "=== 快速环境检查 ==="
    echo "Python版本: $(python --version)"
    echo "工作目录: $(pwd)"
    echo "文件列表:"
    ls -la
    echo ""

    # 只安装项目特定的新依赖
    echo "=== 检查并安装项目依赖 ==="
    if [ -f requirements.txt ]; then
        echo "发现requirements.txt文件"
        pip install -qq --upgrade-strategy only-if-needed -r requirements.txt
        if [ $? -eq 0 ]; then
            echo "依赖安装完成（无异常）"
        else
            echo "依赖安装失败！（可去掉 -qq 参数重新执行查看详细错误）"
        fi
    else
        echo "未找到requirements.txt文件"
    fi

    echo "=== 执行自定义环境部署 ==="
    {self.env_script}

    echo "=== 启动MCP服务器 ==="
    echo "执行命令: {container_command}"
    exec {container_command}'''

        return script

    def _get_container_command(self) -> str:
        """获取容器内的命令字符串"""
        command = self.config.get("command", "python")
        if command == "uv":
            command = "uv run"
        script_rel_path = 'src'+self.abs_script_path.split('src')[-1]
        return command + " " + script_rel_path


    async def _initialize_docker(self):
        """初始化Docker中的MCP服务器，支持输出显示"""
        original_docker_command = self._build_docker_command()
        
        # 修改Docker命令，使用tee同时输出到终端和MCP
        docker_command = self._add_output_redirection(original_docker_command)
        
        logging.info(f"启动Docker命令: {' '.join(docker_command)}")

        # 注册容器到全局注册表
        if self.container_name:
            self._registry.register_container(self.container_name)

        # 清理可能存在的同名容器
        await self._cleanup_existing_container()

        # 使用修改后的命令建立MCP连接（只启动一个进程）
        server_params = StdioServerParameters(
            command=docker_command[0],
            args=docker_command[1:],
            env=None
        )

        try:
            stdio_transport = await self.exit_stack.enter_async_context(
                stdio_client(server_params))
                
            read, write = stdio_transport
            session = await self.exit_stack.enter_async_context(
                ClientSession(read, write)
            )

            # 等待容器稳定
            await asyncio.sleep(3)
            self.search_for_container()

            # 启动监控任务
            monitor_task = await self._start_container_monitoring(session)
            
            # 注册清理回调
            self._register_cleanup_callback(monitor_task)
            
            self.session = session
            logging.info(f"Docker MCP服务器 {self.name} 已初始化")
            
            return session

        except Exception as e:
            logging.error(f"Docker MCP服务器初始化失败: {str(e)}")
            raise

    def _add_output_redirection(self, docker_command):
        """为Docker命令添加输出重定向"""
        # 找到bash脚本部分
        if len(docker_command) >= 3 and docker_command[-2] == "-c":
            # 修改bash脚本，添加tee命令
            original_script = docker_command[-1]
            
            # 将输出同时发送到stderr（显示在终端）和stdout（给MCP）
            modified_script = f'''
    # 设置输出重定向
    exec > >(tee /dev/stderr)
    exec 2>&1

    # 原始脚本
    {original_script}
    '''
            new_command = docker_command[:-1] + [modified_script]
            return new_command
        
        return docker_command

    async def _cleanup_existing_container(self):
        """清理可能存在的同名容器"""
        if not self.container_name:
            return
            
        try:
            import subprocess
            stop_cmd = f"docker stop {self.container_name} 2>/dev/null || true"
            remove_cmd = f"docker rm {self.container_name} 2>/dev/null || true"
            
            subprocess.run(stop_cmd, shell=True, capture_output=True)
            subprocess.run(remove_cmd, shell=True, capture_output=True)
            
            logging.debug(f"已清理可能存在的容器: {self.container_name}")
        except Exception as e:
            logging.warning(f"清理现有容器时出错: {str(e)}")

    async def _start_container_monitoring(self, session):
        """启动容器监控和会话初始化"""
        try:
            # 创建监控任务
            async def monitor():
                """容器状态监控循环"""
                try:
                    while True:
                        await asyncio.sleep(2)
                        self.search_for_container()
                except asyncio.CancelledError:
                    logging.debug("监控任务被取消")
                    raise
                except Exception as e:
                    logging.error(f"监控任务错误: {str(e)}")
                    raise
            
            # 启动初始化和监控任务
            init_task = asyncio.create_task(session.initialize())
            monitor_task = asyncio.create_task(monitor())
            
            try:
                # 等待任务完成
                done, pending = await asyncio.wait(
                    [init_task, monitor_task], 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # 取消还在运行的任务
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                
                # 检查完成的任务是否有异常
                for task in done:
                    await task
                
                # 返回监控任务引用
                return monitor_task
                
            except Exception as e:
                # 清理任务
                for task in [init_task, monitor_task]:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                raise
                
        except Exception as e:
            logging.error(f"启动容器监控失败: {str(e)}")
            raise

    def _register_cleanup_callback(self, monitor_task):
        """注册清理回调函数"""
        def cleanup():
            """清理所有资源"""
            try:
                # 清理监控任务
                if monitor_task and not monitor_task.done():
                    monitor_task.cancel()
            except Exception as cleanup_error:
                logging.warning(f"清理过程中出现错误: {str(cleanup_error)}")

        self.exit_stack.callback(cleanup)

    def search_for_container(self):    
        try:
            container = self.client.containers.get(self.container_name) 
            if container.status != "running":
                raise RuntimeError(f"容器{self.container_name}未处于运行状态，当前状态: {container.status}")
        except NotFound:
            raise RuntimeError(f"容器{self.container_name}不存在")
        except APIError as e:
            raise RuntimeError(f"Docker API错误: {str(e)}")
        
    async def list_tools(self) -> list[Any]:
        """列出可用工具"""
        if not self.session:
            raise RuntimeError(f"Server {self.name} not initialized")

        tools_response = await self.session.list_tools()
        tools = []

        for item in tools_response:
            if isinstance(item, tuple) and item[0] == "tools":
                tools.extend(Tool(tool.name, tool.description, tool.inputSchema) for tool in item[1])

        return tools

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        retries: int = 1,
        delay: float = 1.0,
    ) -> list[Any]:
        """执行工具"""
        if not self.session:
            raise RuntimeError(f"Server {self.name} not initialized")

        attempt = 0
        while attempt < retries:
            try:
                logging.info(f"Executing {tool_name}...")
                result = await self.session.call_tool(tool_name, arguments)
                tool_result = []
                for rc in result.content:
                    if rc.type == "text":
                        if '{' and '}' in rc.text:
                            try:
                                # 假设parse_evaluation_json函数存在
                                rc_text_json = parse_evaluation_json(rc.text)
                                tool_result.append(rc_text_json)
                            except:
                                tool_result.append(rc.text)
                        else:
                            tool_result.append(rc.text)
                    elif rc.type == "image":
                        logging.warning("Image result is not supported yet")
                    elif rc.type == "resource":
                        logging.warning("Resource result is not supported yet")
                return tool_result
            except Exception as e:
                attempt += 1
                logging.warning(f"Error executing tool: {e}. Attempt {attempt} of {retries}.")
                if attempt < retries:
                    await asyncio.sleep(delay)
                else:
                    logging.error("Max retries reached. Failing.")
                    raise

    async def _force_kill_docker_container_async(self) -> bool:
        """异步强制终止Docker容器"""
        if not self.container_name:
            return True
        
        loop = asyncio.get_event_loop()
        try:
            # 使用线程池执行同步的docker命令
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["docker", "kill", self.container_name],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            )
            
            if result.returncode == 0:
                logging.info(f"成功强制终止容器: {self.container_name}")
                return True
            else:
                logging.warning(f"终止容器失败: {result.stderr}")
                return False
                
        except Exception as e:
            logging.error(f"强制终止容器出错: {e}")
            return False

    async def cleanup(self) -> None:
        """清理服务器资源"""
        async with self._cleanup_lock:
            if self._is_cleaning_up:
                # 等待之前的清理完成
                await self._cleanup_completed.wait()
                return
            
            self._is_cleaning_up = True
            self._cleanup_completed.clear()

        try:
            logging.info(f"开始清理服务器 {self.name}")
            
            # 1. 标记为未初始化
            self._is_initialized = False
            
            # 2. 如果是Docker模式，先强制终止容器
            if self.use_docker and self.container_name:
                success = await self._force_kill_docker_container_async()
                if success:
                    # 从注册表中移除
                    self._registry.unregister_container(self.container_name)
                    await asyncio.sleep(0.5)

            self.session = None
            self.stdio_context = None
            
            try:
                await self.exit_stack.aclose()
                logging.debug("exit_stack清理完成")
            except Exception as e:
                logging.warning(f"exit_stack清理出错: {e}")
            finally:
                self.exit_stack = AsyncExitStack()

            self.docker_process = None
            self.container_id = None
            if self.use_docker:
                self.container_name = None  # 重置容器名，允许下次重新创建
            
            logging.info(f"服务器 {self.name} 清理完成")

        except Exception as e:
            logging.error(f"清理过程出错: {e}")
        finally:
            self._is_cleaning_up = False
            self._cleanup_completed.set()

    async def wait_for_cleanup(self) -> None:
        """等待清理完成"""
        if self._is_cleaning_up:
            await self._cleanup_completed.wait()

    def is_ready_for_reuse(self) -> bool:
        """检查是否可以重新使用"""
        return not self._is_cleaning_up and not self._is_initialized

    def __del__(self):
        """析构函数，确保Docker容器被清理"""
        if self.use_docker and self.container_name:
            try:
                subprocess.run(
                    ["docker", "kill", self.container_name], 
                    capture_output=True, 
                    timeout=5
                )
                # 从注册表中移除
                self._registry.unregister_container(self.container_name)
            except:
                pass

class Tool:
    """Represents a tool with its properties and formatting."""

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        title: str | None = None,
    ) -> None:
        self.name: str = name
        self.title: str | None = title
        self.description: str = description
        self.input_schema: dict[str, Any] = input_schema

    def format_for_llm(self) -> str:
        """Format tool information for LLM.

        Returns:
            A formatted string describing the tool.
        """
        args_desc = []
        if "properties" in self.input_schema:
            for param_name, param_info in self.input_schema["properties"].items():
                arg_desc = f"- {param_name}: {param_info.get('description', 'No description')}"
                if param_name in self.input_schema.get("required", []):
                    arg_desc += " (required)"
                args_desc.append(arg_desc)

        # Build the formatted output with title as a separate field
        output = f"Tool: {self.name}\n"

        # Add human-readable title if available
        if self.title:
            output += f"User-readable title: {self.title}\n"

        output += f"""Description: {self.description}
Arguments:
{chr(10).join(args_desc)}
"""

        return output