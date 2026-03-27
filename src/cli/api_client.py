"""API 客户端 - 支持自动刷新 Token"""

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urljoin

import requests
from rich.console import Console
from rich.prompt import Prompt

from src.cli.config import config

console = Console()


class APIClient:
    """RAG API 客户端 - 支持自动刷新 Token"""

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        self.base_url = base_url or config.api_url
        self.timeout = config.api_timeout
        self.token = token or self._load_token()
        
        # 从环境变量读取凭据
        self.username = os.environ.get("RAG_API_USERNAME")
        self.password = os.environ.get("RAG_API_PASSWORD")
        
        # Token 过期时间（默认设置为未来时间，避免每次都认为过期）
        self.token_expires_at = time.time() + 3600  # 默认 1 小时有效

    def _load_token(self) -> Optional[str]:
        """从文件加载 Token"""
        token_file = config.token_file
        if token_file.exists():
            token = token_file.read_text().strip()
            if token:
                # 加载 token 时假设还有 30 分钟有效期（保守估计）
                self.token_expires_at = time.time() + 1800
                return token
        return None

    def _save_token(self, token: str, expires_in: int = 3600):
        """保存 Token 到文件"""
        token_file = config.token_file
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(token)
        token_file.chmod(0o600)
        
        # 记录过期时间
        self.token_expires_at = time.time() + expires_in - 60  # 提前 60 秒刷新

    def _is_token_expired(self) -> bool:
        """检查 Token 是否过期"""
        if not self.token:
            return True
        return time.time() >= self.token_expires_at

    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _url(self, path: str) -> str:
        """构建完整 URL"""
        return urljoin(self.base_url, path)

    def login(self, username: Optional[str] = None, password: Optional[str] = None) -> bool:
        """登录并保存 Token"""
        # 优先使用传入的凭据，其次环境变量
        username = username or self.username
        password = password or self.password
        
        # 如果没有凭据，交互式输入
        if not username:
            username = Prompt.ask("用户名", default="admin")
        if not password:
            password = Prompt.ask("密码", password=True)
        
        try:
            response = requests.post(
                self._url("/api/v1/auth/login"),
                data={"username": username, "password": password},
                timeout=self.timeout,
            )
            
            if response.status_code == 200:
                data = response.json()
                # 处理两种响应格式
                if data.get("success"):
                    token_data = data.get("data", {})
                    token = token_data.get("access_token")
                    expires_in = token_data.get("expires_in", 3600)
                else:
                    # 直接返回 token 的格式
                    token = data.get("access_token")
                    expires_in = data.get("expires_in", 3600)
                
                if token:
                    self._save_token(token, expires_in)
                    self.token = token
                    # 保存凭据供自动刷新使用
                    self.username = username
                    self.password = password
                    console.print("[green]✓ 登录成功[/green]")
                    return True
            
            console.print("[red]✗ 登录失败: 用户名或密码错误[/red]")
            return False
            
        except requests.RequestException as e:
            console.print(f"[red]登录失败: {e}[/red]")
            return False

    def _auto_refresh_token(self) -> bool:
        """自动刷新 Token"""
        if not self.username or not self.password:
            console.print("[yellow]未配置自动登录凭据，请手动执行 'ragctl login'[/yellow]")
            return False
        
        console.print("[dim]Token 已过期，正在自动刷新...[/dim]")
        return self.login(self.username, self.password)

    def get(self, path: str, params: Optional[Dict] = None, retry: bool = True) -> Optional[Dict]:
        """GET 请求"""
        # 检查并自动刷新 Token
        if self._is_token_expired() and self.username and self.password:
            self._auto_refresh_token()
        
        try:
            response = requests.get(
                self._url(path),
                headers=self._get_headers(),
                params=params,
                timeout=self.timeout,
            )
            
            # 如果 401，尝试自动刷新后重试
            if response.status_code == 401 and retry:
                if self._auto_refresh_token():
                    return self.get(path, params, retry=False)
            
            return self._handle_response(response)
            
        except requests.RequestException as e:
            console.print(f"[red]请求失败: {e}[/red]")
            return None

    def post(self, path: str, data: Optional[Dict] = None, json_data: Optional[Dict] = None, retry: bool = True) -> Optional[Dict]:
        """POST 请求"""
        # 检查并自动刷新 Token
        if self._is_token_expired() and self.username and self.password:
            self._auto_refresh_token()
        
        try:
            kwargs = {"headers": self._get_headers(), "timeout": self.timeout}
            if json_data:
                kwargs["json"] = json_data
            elif data:
                kwargs["data"] = data

            response = requests.post(self._url(path), **kwargs)
            
            # 如果 401，尝试自动刷新后重试
            if response.status_code == 401 and retry:
                if self._auto_refresh_token():
                    return self.post(path, data, json_data, retry=False)
            
            return self._handle_response(response)
            
        except requests.RequestException as e:
            console.print(f"[red]请求失败: {e}[/red]")
            return None

    def delete(self, path: str, retry: bool = True) -> Optional[Dict]:
        """DELETE 请求"""
        # 检查并自动刷新 Token
        if self._is_token_expired() and self.username and self.password:
            self._auto_refresh_token()
        
        try:
            response = requests.delete(
                self._url(path),
                headers=self._get_headers(),
                timeout=self.timeout,
            )
            
            # 如果 401，尝试自动刷新后重试
            if response.status_code == 401 and retry:
                if self._auto_refresh_token():
                    return self.delete(path, retry=False)
            
            return self._handle_response(response)
            
        except requests.RequestException as e:
            console.print(f"[red]请求失败: {e}[/red]")
            return None

    def _handle_response(self, response: requests.Response) -> Optional[Dict]:
        """处理响应"""
        if response.status_code == 401:
            console.print("[red]认证失败，请先登录 (ragctl login)[/red]")
            return None

        try:
            return response.json()
        except json.JSONDecodeError:
            return {"success": response.status_code == 200, "data": response.text}

    def upload_file(self, path: str, file_path: Path, metadata: Optional[Dict] = None, retry: bool = True) -> Optional[Dict]:
        """上传文件"""
        # 检查并自动刷新 Token
        if self._is_token_expired() and self.username and self.password:
            self._auto_refresh_token()
        
        try:
            with open(file_path, "rb") as f:
                files = {"file": (file_path.name, f)}
                data = {"metadata": json.dumps(metadata or {})}
                headers = {}
                if self.token:
                    headers["Authorization"] = f"Bearer {self.token}"

                response = requests.post(
                    self._url(path),
                    headers=headers,
                    files=files,
                    data=data,
                    timeout=self.timeout * 2,
                )
                
                # 如果 401，尝试自动刷新后重试
                if response.status_code == 401 and retry:
                    if self._auto_refresh_token():
                        return self.upload_file(path, file_path, metadata, retry=False)
                
                return self._handle_response(response)
                
        except requests.RequestException as e:
            console.print(f"[red]上传失败: {e}[/red]")
            return None


# 全局 API 客户端实例
api_client = APIClient()