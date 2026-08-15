"""
llm_client.py - 大模型客户端
v0.9.0 重构版 - 简化代码，统一日志，增强错误处理
"""
import json
import re
import time
import traceback
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.log import logger


class LLMClient:
    """大模型客户端"""

    def __init__(self, base_url: str, api_key: str, model: str,
                 prompt_template: str = "", timeout: int = 60,
                 verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.prompt_template = prompt_template
        self.timeout = timeout
        # v1.2.7: SSL 验证可配置 - 内网环境可关闭
        self.verify_ssl = verify_ssl
        self._client = None
        self._http_client = None  # v1.3.6: 保存 httpx.Client 引用，用于强制关闭连接
        self._use_sdk = False
        self._init_client()

    def _init_client(self):
        """初始化客户端（优先 SDK，失败降级为 requests）"""
        try:
            import openai
            import httpx

            # v1.3.1: 不再污染全局 os.environ
            # 改用 http_client 传代理 - 让 openai SDK 内部的 httpx 使用我们的代理配置
            proxy_url = self._parse_proxy()
            http_client = None
            if proxy_url:
                # 提取字符串形式的代理 URL
                if isinstance(proxy_url, dict):
                    proxy = list(proxy_url.values())[0]
                else:
                    proxy = proxy_url
                # 构建 httpx.Client 显式传 proxy，避免污染全局环境变量
                http_client = httpx.Client(
                    proxy=proxy,
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )
                logger.info(f"[LLMClient] 已配置 httpx 代理: {proxy}")
            else:
                # v1.3.6: 即使没有代理，也创建 httpx.Client 以便后续强制关闭连接
                http_client = httpx.Client(
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                )

            client_kwargs = {
                "base_url": self.base_url,
                "api_key": self.api_key,
                "timeout": self.timeout,
            }
            if http_client is not None:
                client_kwargs["http_client"] = http_client
            self._client = openai.OpenAI(**client_kwargs)
            self._http_client = http_client  # v1.3.6: 保存引用用于强制关闭
            self._use_sdk = True
            logger.info(f"[LLMClient] SDK 模式初始化成功: {self.model}")
        except Exception as e:
            logger.warning(f"[LLMClient] SDK 初始化失败，降级为 requests: {e}")
            self._client = None
            self._http_client = None
            self._use_sdk = False

    def _parse_proxy(self) -> Optional[dict]:
        """解析代理配置"""
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

    def translate_terms(self, title: str, year: Any, terms: List[str]) -> Dict[str, str]:
        """翻译一批词条，返回 {原文: 译文}"""
        if not terms:
            return {}

        prompt = self._build_prompt(title, year, terms)
        terms_count = len(terms)
        # v1.2.9: 翻译耗时统计 - 用于性能监控和日志
        start_ts = time.time()

        try:
            if self._use_sdk and self._client:
                result = self._call_sdk(prompt, terms_count)
            else:
                result = self._call_requests(prompt, terms_count)

            elapsed = round(time.time() - start_ts, 2)
            if result:
                logger.info(f"[LLMClient] 翻译成功: {len(result)} 个词条 "
                            f"(输入{terms_count}条, 耗时{elapsed}s, max_tokens={self._calc_max_tokens(terms_count)})")
            else:
                logger.warning(f"[LLMClient] 翻译返回空结果 (耗时{elapsed}s)")
            return result
        except Exception as e:
            elapsed = round(time.time() - start_ts, 2)
            logger.error(f"[LLMClient] 翻译失败 (耗时{elapsed}s): {e}\n{traceback.format_exc()}")
            return {}

    def _build_prompt(self, title: str, year: Any, terms: List[str]) -> str:
        """构建提示词"""
        template = self.prompt_template or self._get_default_prompt()
        prompt = template
        prompt = prompt.replace("{title_json}", json.dumps(title, ensure_ascii=False))
        prompt = prompt.replace("{year_json}", json.dumps(year, ensure_ascii=False))
        prompt = prompt.replace("{terms_json}", json.dumps(terms, ensure_ascii=False))
        return prompt

    def _get_default_prompt(self) -> str:
        return """你是影视翻译专家。将以下词条翻译成简体中文。
context: {"title": {title_json}, "year": {year_json}}
terms: {terms_json}
输出: JSON 对象，键为原文，值为译文。无法翻译保留原文。只输出 JSON，不要 markdown。"""

    def _calc_max_tokens(self, terms_count: int) -> int:
        """v1.2.8: 根据批量大小动态计算 max_tokens
        - 5 条以内：2048（默认）
        - 5~10 条：3072
        - 10~20 条：4096
        - 20+ 条：6144
        避免大批量翻译时返回截断导致 JSON 解析失败
        """
        if terms_count <= 5:
            return 2048
        if terms_count <= 10:
            return 3072
        if terms_count <= 20:
            return 4096
        return 6144

    def close(self):
        """v1.3.6: 强制关闭底层 HTTP 连接，让卡住的 LLM 调用立即抛异常退出"""
        try:
            if self._http_client is not None:
                self._http_client.close()
                logger.info("[LLMClient] 已强制关闭 HTTP 连接")
        except Exception:
            pass
        try:
            if self._client is not None and hasattr(self._client, 'close'):
                self._client.close()
        except Exception:
            pass
        self._client = None
        self._http_client = None

    def _call_sdk(self, prompt: str, terms_count: int = 5) -> Dict[str, str]:
        """通过 openai SDK 调用
        v1.3.6: 移除 create() 中无效的 timeout 参数（openai SDK 不支持该参数）
        timeout 已在 httpx.Client 构造时设置，由 stop_service 调用 close() 强制中断
        """
        try:
            max_tokens = self._calc_max_tokens(terms_count)
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "你是影视翻译专家，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            text = resp.choices[0].message.content.strip()
            return self._parse_response(text)
        except Exception as e:
            logger.error(f"[LLMClient] SDK 调用失败: {e}")
            return {}

    def _call_requests(self, prompt: str, terms_count: int = 5) -> Dict[str, str]:
        """通过纯 requests 调用"""
        import requests
        try:
            url = f"{self.base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            max_tokens = self._calc_max_tokens(terms_count)
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "你是影视翻译专家，只输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": max_tokens,
            }
            proxies = self._parse_proxy()
            # v1.2.9: 修复 - 之前硬编码 verify=False 导致 SSL 配置失效
            # 现在跟随 self.verify_ssl，与 SDK 模式保持一致
            resp = requests.post(
                url, headers=headers, json=data,
                timeout=self.timeout,
                proxies=proxies,
                verify=self.verify_ssl,
            )
            resp.raise_for_status()
            result = resp.json()
            text = result["choices"][0]["message"]["content"].strip()
            return self._parse_response(text)
        except Exception as e:
            logger.error(f"[LLMClient] requests 调用失败: {e}")
            return {}

    def _parse_response(self, text: str) -> Dict[str, str]:
        """从 LLM 响应中解析 JSON"""
        text = text.strip()
        if text.startswith("```"):
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
            match = re.search(r'\{[^{}]*\}', text)
            if match:
                try:
                    data = json.loads(match.group())
                    return {str(k): str(v) for k, v in data.items() if v}
                except json.JSONDecodeError:
                    pass

        logger.warning(f"[LLMClient] 无法解析响应: {text[:200]}")
        return {}
