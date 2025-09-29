import logging
import asyncio
import atexit
from typing import Set
import signal
import subprocess
import sys
import os

class DockerContainerRegistry:
    """全局Docker容器注册表，确保程序退出时清理所有容器"""
    _instance = None
    _containers: Set[str] = set()
    _cleanup_lock = asyncio.Lock()
    _initialized = False
    _cleanup_in_progress = False  # 添加清理状态标志
    _signal_count = 0  # 信号计数器
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def initialize(cls):
        """初始化全局清理机制"""
        if cls._initialized:
            return
        
        instance = cls()
        
        atexit.register(instance._sync_cleanup_all)
        
        def signal_handler(signum, frame):
            instance._handle_signal(signum)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        cls._initialized = True
        logging.info("Docker容器注册表已初始化")
    
    def _handle_signal(self, signum):
        """处理信号，避免重复清理"""
        self._signal_count += 1
        
        if self._cleanup_in_progress:
            if self._signal_count <= 2:
                logging.info(f"清理正在进行中，请稍候... (信号计数: {self._signal_count})")
                return
            elif self._signal_count <= 5:
                logging.warning(f"强制中断清理过程... (信号计数: {self._signal_count})")
                return
            else:
                logging.error("多次中断信号，强制退出程序")
                os._exit(1)  
        
        logging.info(f"接收到信号 {signum}，开始清理Docker容器...")
        self._cleanup_in_progress = True
        
        try:
            self._sync_cleanup_all()
        except Exception as e:
            logging.error(f"清理过程中出错: {e}")
        finally:
            logging.info("程序退出")
            sys.exit(0)
    
    def register_container(self, container_name: str):
        """注册容器"""
        self._containers.add(container_name)
        logging.debug(f"注册Docker容器: {container_name}")
    
    def unregister_container(self, container_name: str):
        """注销容器"""
        self._containers.discard(container_name)
        logging.debug(f"注销Docker容器: {container_name}")
    
    def _sync_cleanup_all(self):
        """同步清理所有注册的容器"""
        if not self._containers or self._cleanup_in_progress:
            return
        
        self._cleanup_in_progress = True
        
        try:
            logging.info(f"开始清理 {len(self._containers)} 个Docker容器...")
            containers_to_clean = self._containers.copy()
            
            for container_name in containers_to_clean:
                try:
                    result = subprocess.run(
                        ["docker", "kill", container_name],
                        capture_output=True,
                        text=True,
                        timeout=3  # 减少超时时间
                    )
                    if result.returncode == 0:
                        logging.info(f"成功清理容器: {container_name}")
                        self._containers.discard(container_name)
                    else:
                        logging.warning(f"清理容器失败: {container_name}, {result.stderr}")
                except subprocess.TimeoutExpired:
                    logging.warning(f"清理容器 {container_name} 超时，跳过")
                except Exception as e:
                    logging.error(f"清理容器 {container_name} 出错: {e}")
            
            # 如果还有容器未清理，尝试强制清理
            if self._containers:
                logging.info("尝试强制清理剩余容器...")
                for container_name in list(self._containers):
                    try:
                        subprocess.run(
                            ["docker", "rm", "-f", container_name],
                            capture_output=True,
                            text=True,
                            timeout=2
                        )
                        self._containers.discard(container_name)
                        logging.info(f"强制清理容器: {container_name}")
                    except Exception as e:
                        logging.error(f"强制清理容器 {container_name} 失败: {e}")
            
            logging.info("Docker容器清理完成")
            
        finally:
            self._cleanup_in_progress = False
    
    async def async_cleanup_all(self):
        """异步清理所有容器"""
        if not self._containers:
            return
        
        async with self._cleanup_lock:
            if self._cleanup_in_progress:
                return
            
            self._cleanup_in_progress = True
            
            try:
                containers_to_clean = list(self._containers)
                
                # 并发清理所有容器，但添加超时限制
                tasks = []
                for container_name in containers_to_clean:
                    task = asyncio.create_task(self._async_kill_container(container_name))
                    tasks.append(task)
                
                if tasks:
                    # 设置总体超时时间
                    try:
                        results = await asyncio.wait_for(
                            asyncio.gather(*tasks, return_exceptions=True),
                            timeout=10  # 总体超时10秒
                        )
                        for container_name, result in zip(containers_to_clean, results):
                            if isinstance(result, Exception):
                                logging.error(f"异步清理容器 {container_name} 失败: {result}")
                            else:
                                self.unregister_container(container_name)
                    except asyncio.TimeoutError:
                        logging.warning("异步清理容器超时")
            finally:
                self._cleanup_in_progress = False
    
    async def _async_kill_container(self, container_name: str):
        """异步终止单个容器"""
        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(
                None,
                lambda: subprocess.run(
                    ["docker", "kill", container_name],
                    capture_output=True,
                    text=True,
                    timeout=5  # 减少单个容器的超时时间
                )
            )
            if result.returncode == 0:
                logging.info(f"异步清理容器成功: {container_name}")
                return True
            else:
                logging.warning(f"异步清理容器失败: {container_name}, {result.stderr}")
                return False
        except Exception as e:
            logging.error(f"异步清理容器 {container_name} 出错: {e}")
            return False