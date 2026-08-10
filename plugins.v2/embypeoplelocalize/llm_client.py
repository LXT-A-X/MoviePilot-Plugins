"""
llm_client.py - 大模型客户端
优先使用 openai SDK，失败时降级为纯 requests
"""
import json
import time
import traceback
from typing import Any, Dict, List, Optional

from app.core.config import settings


class LLMClient:
    """大模型客户端（兼容 openai SDK 和纯 requests 双模式）"""

    def __init__(self, base_url: str, api_key: str, model: str,
                 prompt_template: str = "", timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.prompt_template = prompt_template
        self.timeout = timeout
        self._client = None
        self._use_sdk = False
        self._init_client()

    def _init_client(self):
        """初始化 openai SDK 客户端（带代理支持）"""
        try:
            import openai
            import httpx

            # 解析代理
            proxies = self._parse_proxy()

            http_client = None
            if proxies:
                http_client = httpx.Client(
                    proxies=proxies,
                    timeout=self.timeout,
                    verify=False
                )

            self._client = openai.OpenAI(
                base_url=self.base_url,
                api_key=self.api_key,
                http_client=http_client,
            )
            self._use_sdk = True
            print(f"[LLMClient] SDK 模式初始化成功: {self.model}")
        except Exception as e:
            print(f"[LLMClient] SDK 初始化失败，降级为 requests: {e}")
            self._client = None
            self._use_sdk = False

    def _parse_proxy(self) -> Optional[dict]:
        """解析 settings.PROXY 为 httpx/openai 通用格式"""
        try:
            raw = getattr(settings, 'PROXY', None)
            if not raw:
                return None
            if isinstance(raw, dict):
                http = str(raw.get("http") or raw.get("https") or "").strip()
                https = str(raw.get("https") or raw.get("http") or "").strip()
                if http or https:
                    return {"http://": http or https, "https://": https or http}
            elif isinstance(raw, (list, tuple)):
                for item in raw:
                    s = str(item or "").strip()
                    if s.startswith(("http://", "https://", "socks5://")):
                        return {"http://": s, "https://": s}
            else:
                s = str(raw).strip()
                if s.startswith(("http://", "https://", "socks5://")):
                    return {"http://": s, "https://": s}
        except Exception:
            pass
        return None

    # ─────────────────────────────────────
    # 核心翻译方法
    # ─────────────────────────────────────
    def translate_terms(self, title: str, year: Any, terms: List[str]) -> Dict[str, str]:
        """
        翻译一批词条
        返回 {原文: 译文} 字典
        """
        if not terms:
            return {}

        prompt = self._build_prompt(title, year, terms)

        # 优先 SDK
        if self._use_sdk and self._client:
            return self._call_sdk(prompt)
        # 降级 requests
        return self._call_requests(prompt)

    def _build_prompt(self, title: str, year: Any, terms: List[str]) -> str:
        """构建提示词"""
        template = self.prompt_template or self._default_prompt()
        prompt = template
        prompt = prompt.replace("{title_json}", json.dumps(title, ensure_ascii=False))
        prompt = prompt.replace("{year_json}", json.dumps(year, ensure_ascii=False))
        prompt = prompt.replace("{terms_json}", json.dumps(terms, ensure_ascii=False))
        return prompt

    def _default_prompt(self) -> str:
        return """你是影视翻译专家。将以下词条翻译成简体中文。
输入: {terms_json}
输出: JSON 对象，键为原文，值为译文。无法翻译保留原文。
只输出 JSON，不要 markdown。"""

    def _call_sdk(self, prompt: str) -> Dict[str, str]:
        """通过 openai SDK 调用"""
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是影视翻译专家，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=2048,
            )
            text = resp.choices[0].message.content.strip()
            return self._parse_json_response(text)
        except Exception as e:
            print(f"[LLMClient] SDK 调用失败: {e}")
            return {}

    def _call_requests(self, prompt: str) -> Dict[str, str]:
        """通过纯 requests 调用"""
        import requests
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是影视翻译专家，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 2048,
            }
            proxies = self._parse_proxy()
            resp = requests.post(
                url, headers=headers, json=data,
                timeout=self.timeout,
                proxies=proxies,
                verify=False,
            )
            resp.raise_for_status()
            result = resp.json()
            text = result["choices"][0]["message"]["content"].strip()
            return self._parse_json_response(text)
        except Exception as e:
            print(f"[LLMClient] requests 调用失败: {e}")
            return {}

    def _parse_json_response(self, text: str) -> Dict[str, str]:
        """从 LLM 响应中解析 JSON"""
        # 去掉可能的 markdown 包裹
        text = text.strip()
        if text.startswith("```"):
            # 去掉 ```json 和 ```
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items() if v}
        except json.JSONDecodeError:
            # 尝试提取第一个 JSON 对象
            import re
            match = re.search(r'\{[^{}]*\}', text)
            if match:
                try:
                    data = json.loads(match.group())
                    return {str(k): str(v) for k, v in data.items() if v}
                except json.JSONDecodeError:
                    pass
        print(f"[LLMClient] 无法解析响应: {text[:200]}")
        return {}