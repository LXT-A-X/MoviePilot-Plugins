"""
llm_client.py - 大模型客户端
重构版 - 简化代码，统一日志，增强错误处理
"""
import json
import random
import re
import threading
import time
import traceback
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.sdk.config import settings
from app.sdk.logging import logger



class LLMError(Exception):
    """LLM 调用错误基类。"""
    kind = "error"


class RateLimited(LLMError):
    """真限流（HTTP 429 / rate_limit / tpm-rpm 超限）——应熔断退避，不丢词条。"""
    kind = "rate_limited"

    def __init__(self, message: str = "", retry_after: Optional[float] = None):
        super().__init__(message)
        self.retry_after = retry_after


class QuotaExceeded(LLMError):
    """余额/配额不足 —— 立即失败，绝不当限流重试。"""
    kind = "quota_exceeded"


class AuthenticationError(LLMError):
    """认证失败（401/403/api key 无效）——立即失败，不重试。"""
    kind = "authentication_failed"


class ContextLengthExceeded(LLMError):
    """上下文超长 —— 应缩小批次重试。"""
    kind = "context_length_exceeded"


class LLMServerError(LLMError):
    """服务端问题（500/502/503/504）——短退避重试，不算限流。"""
    kind = "server_error"


class NetworkError(LLMError):
    """网络异常（连接失败/超时/DNS/代理）——短退避重试，不算限流。
    统一错误枚举新增 network_error（此前网络异常落到 unknown）。"""
    kind = "network_error"


class EmptyResponseError(LLMError):
    """200 但模型没吐内容（如思考型模型）——有限重试。"""
    kind = "empty_response"


class LLMClient:
    """大模型客户端"""

    def __init__(self, base_url: str, api_key: str, model: str,
                 prompt_template: str = "", timeout: int = 60,
                 verify_ssl: bool = True, use_proxy: bool = True,
                 min_interval: float = 1.2, max_rpm: int = 0,
                 thinking_off: bool = True, thinking_params: str = "",
                 tpm_budget: int = 0):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.prompt_template = prompt_template
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.use_proxy = bool(use_proxy)
        self.min_interval = max(0.0, float(min_interval or 0))
        self.max_rpm = max(0, int(max_rpm or 0))
        self._gate_lock = threading.Lock()
        self._last_call_ts = 0.0
        self._call_history = deque()
        self.last_error = ""
        self.last_error_kind = ""
        # v4.6.60（P1-3）：真实请求计数 —— 「词条数」不等于「AI 请求次数」，分开统计便于看日志排限流
        self.stat_requests = 0        # 实际发出的请求次数（含重试）
        self.stat_success = 0         # 有有效结果的请求次数
        self.stat_failed = 0          # 返回空/失败的请求次数
        self.stat_rate_limited = 0    # 429 / 限流次数
        self.stat_quota = 0           # 真·配额/余额不足次数
        # v4.6.61（P2-2）：令牌与延迟统计 —— 供应商返回 usage 时记实际值，否则记估算
        self.stat_tokens_in = 0
        self.stat_tokens_out = 0
        self.stat_latency_ms = 0
        self.stat_last_latency_ms = 0
        # v4.6.64（P1-5/P1-6）：每次 HTTP attempt 留痕（含 429/5xx/401）—— 供 Job 批次历史完整回答
        # 「到底发了几次请求、哪些 429、哪些成功、哪批失败」。
        self.attempts: List[dict] = []
        self.last_http_status = 0
        self._last_usage: Optional[tuple] = None
        # v4.6.61（P2-3）：TPM 令牌预算门（0 = 不启用）—— 近 60 秒估算令牌 + 本次 ≤ 预算才发请求
        self.tpm_budget = max(0, int(tpm_budget or 0))
        self._token_history: deque = deque()
        self._last_est_tokens = 0
        self.rate_limited_until = 0.0
        self.last_failed_batch: List[str] = []
        self.thinking_off = bool(thinking_off)
        self._custom_thinking = self._parse_custom_thinking(thinking_params)
        if self.thinking_off:
            self._thinking_variants = ([self._custom_thinking] if self._custom_thinking
                                       else [dict(_v) for _v in self._THINKING_VARIANTS])
        else:
            self._thinking_variants = []
        self._thinking_idx = 0        # 当前用到第几种写法；>=len 表示不再发参数
        self._rc_retry_done = False   # 本次调用是否已因「只吐思考不吐正文/被截断」换写法重试过
        self._client = None
        self._http_client = None
        self._use_sdk = False
        self._init_client()

    def _init_client(self):
        """初始化客户端（优先 SDK，失败降级为 requests）"""
        try:
            import openai
            import httpx

            proxy_url = self._parse_proxy()
            _trust_env = bool(self.use_proxy) and not self._is_private_target(self.base_url)
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
                    trust_env=_trust_env,
                    verify=self.verify_ssl,
                )
                logger.info(f"[LLM] 已配置 httpx 代理: {proxy}")
            else:
                http_client = httpx.Client(
                    timeout=self.timeout,
                    verify=self.verify_ssl,
                    trust_env=_trust_env,
                )

            client_kwargs = {
                "base_url": self.base_url,
                "api_key": self.api_key,
                "timeout": self.timeout,
            }
            if http_client is not None:
                client_kwargs["http_client"] = http_client
            self._client = openai.OpenAI(**client_kwargs)
            self._http_client = http_client
            self._use_sdk = True
            logger.info(f"[LLM] SDK 客户端初始化成功（仅预热 LLM 通道，不拉取人物）: {self.model}")
        except Exception as e:
            logger.warning(f"[LLM] SDK 初始化失败，降级为 requests: {e}")
            self._client = None
            self._http_client = None
            self._use_sdk = False

    def _parse_proxy(self) -> Optional[dict]:
        """解析代理配置；v3.7.4: 目标是本机/内网地址（ollama/litellm/lmstudio 等）时豁免代理，
        否则 MP 配置了全局代理时本地 AI 请求会被转发到代理导致全部失败。
        R5: 插件「使用代理」关闭时直接不走代理（原实现该开关对 LLM 完全无效，
        设置页文案误导）。"""
        try:
            if not getattr(self, "use_proxy", True):
                return None
            raw = getattr(settings, 'PROXY', None)
            if not raw:
                return None
            # 本机/内网目标 → 不走代理
            if self._is_private_target(self.base_url):
                return None
            if isinstance(raw, dict):
                http = str(raw.get("http") or raw.get("https") or "").strip()
                https = str(raw.get("https") or raw.get("http") or "").strip()
                if http or https:
                    _px = http or https
                    self._check_socks_dep(_px)
                    return {"http://": http or https, "https://": https or http}
            elif isinstance(raw, (list, tuple)):
                for item in raw:
                    s = str(item or "").strip()
                    if s.startswith(("http://", "https://", "socks5://")):
                        self._check_socks_dep(s)
                        return {"http://": s, "https://": s}
            else:
                s = str(raw).strip()
                if s.startswith(("http://", "https://", "socks5://")):
                    self._check_socks_dep(s)
                    return {"http://": s, "https://": s}
        except Exception:
            pass
        return None

    def _check_socks_dep(self, proxy_url: str) -> None:
        """socks5 代理依赖自检 —— 未安装对应依赖时显式提示（只提示一次），
        避免用户只看到晦涩的 httpx/requests 异常。依赖：httpx[socks]（socksio）/ PySocks（requests）。"""
        try:
            if "socks" not in str(proxy_url or "").lower():
                return
            if getattr(self, "_socks_warned", False):
                return
            _ok = False
            try:
                import socksio  # noqa: F401  （httpx[socks] 提供，SDK 模式用）
                _ok = True
            except Exception:
                pass
            if not _ok:
                try:
                    import socks  # noqa: F401  （PySocks 提供，requests 降级模式用）
                    _ok = True
                except Exception:
                    pass
            self._socks_warned = True
            if not _ok:
                logger.warning("[LLM] 检测到 socks5 代理，但缺少依赖（httpx[socks] / PySocks）—— "
                               "socks5 代理将不可用；请安装依赖（pip install \"httpx[socks]\" PySocks）"
                               "或改用 http(s) 代理")
        except Exception:
            pass

    @staticmethod
    def _is_private_target(url: str) -> bool:
        """目标地址是否本机/内网（无需代理）。"""
        try:
            from urllib.parse import urlparse
            host = (urlparse(str(url or "")).hostname or "").lower()
            if not host:
                return False
            if host in ("127.0.0.1", "localhost", "::1"):
                return True
            if host.startswith(("10.", "192.168.", "127.")):
                return True
            if host.startswith("172."):
                try:
                    seg = int(host.split(".")[1])
                    if 16 <= seg <= 31:
                        return True
                except Exception:
                    pass
            return False
        except Exception:
            return False

    def _requests_session(self):
        """专用 requests.Session —— trust_env 跟随「使用代理」开关。
        requests 默认 trust_env=True，会读取 HTTP_PROXY / HTTPS_PROXY / ALL_PROXY，
        导致 use_proxy=False 时本地/内网 LLM 仍被宿主环境代理接管。"""
        _s = getattr(self, "_req_session", None)
        if _s is None:
            import requests as _rq
            _s = _rq.Session()
            self._req_session = _s
        _s.trust_env = bool(getattr(self, "use_proxy", False)) and not self._is_private_target(self.base_url)
        return _s


    # 内置写法阶梯（按「有效性 + 通用性」排序；全部实测于 api.deepseek.com 可通过：
    #   1) thinking.type=disabled —— DeepSeek 官方文档（OpenAI 格式）的思考开关，GLM/豆包同款；实测直接出正文、0 推理 token；
    #   2) reasoning_effort=none —— 实测同样完全关闭（Anthropic 格式口径 none=关；多数兼容端点通用）；
    #   3) reasoning_effort=minimal —— DeepSeek 官方映射表最低档（minimal→low）：拿不到前两种时至少把思考压到最低；
    #      官方：思考默认开、默认 effort=high；映射 minimal/low→low，medium/high/xhigh→high，max/ultra→max；
    #   4) chat_template_kwargs.enable_thinking=false —— vLLM/SGLang/部分网关（Qwen3 等）。
    _THINKING_VARIANTS = (
        {"thinking": {"type": "disabled"}},
        {"reasoning_effort": "none"},
        {"reasoning_effort": "minimal"},
        {"chat_template_kwargs": {"enable_thinking": False, "thinking": False},
         "enable_thinking": False},
    )

    @staticmethod
    def _parse_custom_thinking(raw: str) -> dict:
        """解析设置页「自定义关闭思考参数」（JSON 对象）。非法/空 → 返回 {}（改用内置阶梯）。"""
        _s = str(raw or "").strip()
        if not _s:
            return {}
        try:
            _d = json.loads(_s)
        except Exception as e:
            logger.warning(f"[LLM] 自定义关闭思考参数不是合法 JSON，已忽略（用内置默认）: {e}")
            return {}
        if isinstance(_d, dict) and _d:
            return _d
        logger.warning("[LLM] 自定义关闭思考参数必须是 JSON 对象（如 {\"reasoning_effort\": \"none\"}），已忽略")
        return {}

    def _reasoning_params(self) -> dict:
        """当前要发的「关闭思考」参数（空 dict = 不发）。具体写法由阶梯下标决定。"""
        _vs = getattr(self, "_thinking_variants", []) or []
        _i = int(getattr(self, "_thinking_idx", 0) or 0)
        if _i >= len(_vs):
            return {}
        return dict(_vs[_i])

    def _downgrade_reasoning(self, msg: str = "", status: Optional[int] = None) -> bool:
        """换到下一种「关闭思考」写法。
        两种触发：①端点拒绝参数（带 msg/status，检查 400/unknown parameter 等关键词）；
        ②实测模型仍只吐思考/被截断（不带参数，无条件换下一种）。
        :return: True=已换到新写法（调用方应更新请求参数后重试）；False=没有更多写法
        """
        _vs = getattr(self, "_thinking_variants", []) or []
        _i = int(getattr(self, "_thinking_idx", 0) or 0)
        if _i >= len(_vs):
            return False
        if msg or status is not None:
            _m = str(msg or "").lower()
            _reject = (int(status or 0) == 400) or any(_k in _m for _k in (
                "unrecognized", "unknown parameter", "unknown field", "extra field", "extra inputs",
                "unexpected keyword", "not supported", "unsupported", "invalid_request_error",
                "invalid request", "invalid parameter", "error code: 400", "status_code: 400",
                "400 bad request", "client error: 400",
            ))
            if not _reject:
                return False
        self._thinking_idx = _i + 1
        return True

    def _fix_base_v1(self) -> bool:
        """base_url 缺 /v1 导致 SDK 路径 404 时，自动补 /v1 并重建客户端（一次）。
        requests 路径早有同款自愈，SDK 路径此前没有 —— 日志里「SDK 调用失败: 404 page not found」
        就是这么来的（只能靠 fallback 到 requests 或改配置）。
        :return: True=已修正（调用方可原样重试）
        """
        if getattr(self, "_v1_fixed", False):
            return False
        _b = str(self.base_url or "").rstrip("/")
        if "/v1" in _b.split("/")[-2:]:
            return False
        self._v1_fixed = True
        self.base_url = _b + "/v1"
        try:
            self._init_client()
        except Exception as e:
            logger.warning(f"[LLM] 补 /v1 后重建客户端失败: {e}")
            return False
        logger.warning(f"[LLM] SDK 404：地址缺 /v1，自动改用 {self.base_url} 重建客户端重试")
        return True


    # ── 错误分类证据表（v4.6.60 重写）──
    # 「明确账单/余额」证据：只有这些才判 quota_exceeded 并进入 30 分钟配额暂停
    _QUOTA_HARD_PAT = ("insufficient_balance", "insufficient balance", "billing_hard_limit_reached",
                       "billing hard limit", "exceeded your current quota",
                       "billing", "credit", "balance", "余额", "欠费", "欠款", "充值")
    # 「歧义配额」token：OpenAI 在**限流**响应里也会带 insufficient_quota ——
    # 故它不能单独作为判决依据（必须先看有没有限流证据），这是「TPM/RPM 被误判成余额不足」的根因
    _QUOTA_SOFT_PAT = ("insufficient_quota", "insufficient quota", "quota exceeded", "quota")
    # 「限流」证据：出现任一即视为限流，优先级高于歧义配额 token
    _RATE_EV_PAT = ("rate_limit_error", "rate_limit", "rate limit", "too many requests",
                    "tpm", "rpm", "限流")
    _QUOTA_CODE_PAT = _QUOTA_SOFT_PAT   # 兼容旧引用
    _QUOTA_PAT = _QUOTA_HARD_PAT
    _AUTH_PAT = ("401", "403", "incorrect api key", "invalid api key", "api key invalid",
                 "api key not", "no api key", "missing api key", "unauthorized",
                 "authentication", "forbidden", "权限")
    _CTX_PAT = ("context_length_exceeded", "context length", "maximum context", "reduce the length",
                "too many tokens", "max_tokens")
    _RATE_PAT = _RATE_EV_PAT
    _SERVER_PAT = ("500", "502", "503", "504", "internal server error", "bad gateway",
                   "service unavailable", "overloaded", "server error")
    _NET_PAT = ("connection", "connect", "timeout", "timed out", "dns", "name resolution",
                "network", "unreachable", "connection reset", "proxy", "ssl", "certificate")

    @classmethod
    def classify_error(cls, text: str, status: Optional[int] = None) -> str:
        """错误分类（v4.6.60 重写顺序）。
        优先级 ——
          ① 证据判定：**限流证据**（rate_limit_error / tpm / rpm / too many requests）
             优先于「歧义配额 token」insufficient_quota；
             只有「明确账单证据」（billing / credit / balance / 欠费 / 余额）才判 quota_exceeded
          ② HTTP status / 结构化状态码（401/403 认证、**429 一律限流**、5xx 服务端）
          ③ 受控关键词（最后兜底）
        旧实现把 insufficient_quota 放在最前 —— 上游返回
        `429 + rate_limit_error + message: inference exceeds tpm/rpm limit + code: insufficient_quota`
        时会被误判为 quota_exceeded，进而被硬停 30 分钟（真实原因只是限流）。
        统一错误枚举：rate_limited / quota_exceeded / authentication_failed /
        context_length_exceeded / server_error / network_error / unknown
        """
        t = str(text or "").lower()
        try:
            _st = int(status) if status is not None else None
        except Exception:
            _st = None

        # ① 证据判定（先于一切）—— 限流证据压过歧义配额 token
        _rate_ev = any(k in t for k in cls._RATE_EV_PAT)
        _bill_ev = any(k in t for k in cls._QUOTA_HARD_PAT)
        if _bill_ev and not _rate_ev:
            return "quota_exceeded"

        # ② HTTP status：认证 / 限流 / 服务端（优先于任何关键词）
        if _st in (401, 403):
            return "authentication_failed"
        if _st == 429:
            # 429 一律限流（真·余额不足已被 ① 拦下）→ 走短退避，绝不进 30 分钟配额暂停
            return "rate_limited"
        if _st is not None and 500 <= _st <= 599:
            return "server_error"

        # ③ 受控关键词兜底（status 缺失或为其它码时）
        if _rate_ev:
            return "rate_limited"
        if any(k in t for k in cls._QUOTA_SOFT_PAT):
            return "quota_exceeded"
        if any(k in t for k in cls._CTX_PAT):
            return "context_length_exceeded"
        if any(k in t for k in cls._AUTH_PAT):
            return "authentication_failed"
        if any(k in t for k in cls._SERVER_PAT):
            return "server_error"
        if any(k in t for k in cls._NET_PAT):
            return "network_error"
        return "unknown"

    @staticmethod
    def _typed_of(kind: str, message: str, retry_after: Optional[float] = None) -> LLMError:
        if kind == "rate_limited":
            return RateLimited(message, retry_after=retry_after)
        return {"quota_exceeded": QuotaExceeded, "authentication_failed": AuthenticationError,
                "context_length_exceeded": ContextLengthExceeded, "server_error": LLMServerError,
                "network_error": NetworkError,
                "empty_response": EmptyResponseError}.get(kind, LLMError)(message)

    @staticmethod
    def _retry_after_of(resp) -> Optional[float]:
        """从响应头解析 Retry-After（秒）。"""
        try:
            h = getattr(resp, "headers", None) or {}
            v = h.get("Retry-After") or h.get("retry-after")
            if v is None:
                return None
            return max(0.0, float(str(v).strip()))
        except Exception:
            return None

    def _acquire_slot(self, stop_check: Optional[Any] = None, est_tokens: int = 0) -> None:
        """LLM 单通道入口 —— 实例级串行锁 + 最小请求间隔。所有线程都要过这里。
        追加 RPM 窗口限制 —— max_rpm>0 时，最近 60 秒请求数必须 < max_rpm。
        追加统一熔断门 —— 熔断窗口（rate_limited_until）内，任何 LLM 请求
        （含测试连接/手动翻译/People Pool/Webhook/失败重试）一律禁止发出。
        v4.6.61（P2-3）追加 TPM 预算门 —— tpm_budget>0 时，近 60 秒估算令牌 + 本次估算
        不得超过预算，超出先等待（减少「429 → 重试 → 再 429 → 熔断」循环）。"""
        _until = float(getattr(self, "rate_limited_until", 0) or 0)
        if _until > time.time():
            _left = max(0.0, _until - time.time())
            raise RateLimited(f"LLM 限流熔断中，剩 {int(_left)}s", retry_after=_left)
        while True:
            if stop_check is not None and stop_check():
                raise InterruptedError("已请求停止翻译")
            if self._gate_lock.acquire(timeout=0.5):
                break
        try:
            self.stat_requests += 1   # v4.6.60：通过闸门 = 即将真实发出一次请求
            self._last_est_tokens = max(0, int(est_tokens or 0))
            _gap = float(self.min_interval or 0)
            _end = self._last_call_ts + _gap
            while time.time() < _end:
                if stop_check is not None and stop_check():
                    raise InterruptedError("已请求停止翻译")
                time.sleep(min(0.2, max(0.05, _end - time.time())))
            if self.max_rpm > 0:
                while True:
                    if stop_check is not None and stop_check():
                        raise InterruptedError("已请求停止翻译")
                    _now = time.time()
                    _win = [t for t in self._call_history if _now - t < 60.0]
                    self._call_history = deque(_win)
                    if len(_win) < self.max_rpm:
                        break
                    _wait = 60.0 - (_now - _win[0]) + 0.05
                    time.sleep(min(0.5, max(0.05, _wait)))
            # v4.6.61（P2-3）：TPM 令牌预算门（估算令牌走 60 秒滑动窗口）
            if self.tpm_budget > 0 and self._last_est_tokens > 0:
                while True:
                    if stop_check is not None and stop_check():
                        raise InterruptedError("已请求停止翻译")
                    _now = time.time()
                    _win = [(t, n) for t, n in self._token_history if _now - t < 60.0]
                    self._token_history = deque(_win)
                    _sum = sum(n for _, n in _win)
                    if _sum + self._last_est_tokens <= self.tpm_budget:
                        break
                    _old = _win[0][0] if _win else _now
                    _wait = max(0.2, 60.0 - (_now - _old) + 0.05)
                    logger.info(f"[LLM] TPM 预算门：近 1 分钟 ≈{_sum} + 本次 ≈{self._last_est_tokens} "
                                f"> 预算 {self.tpm_budget}，等待约 {min(_wait, 60.0):.0f}s")
                    time.sleep(min(0.5, _wait))
        except BaseException:
            try:
                self._gate_lock.release()
            except Exception:
                pass
            raise

    def _release_slot(self) -> None:
        _now = time.time()
        self._last_call_ts = _now
        try:
            self._call_history.append(_now)
            while self._call_history and _now - self._call_history[0] >= 60.0:
                self._call_history.popleft()
        except Exception:
            pass
        try:
            # v4.6.61（P2-3）：把本次估算令牌计入 TPM 窗口（无论成败，上游都按请求计费）
            _est = int(getattr(self, "_last_est_tokens", 0) or 0)
            if self.tpm_budget > 0 and _est > 0:
                self._token_history.append((_now, _est))
                while self._token_history and _now - self._token_history[0][0] >= 60.0:
                    self._token_history.popleft()
        except Exception:
            pass
        try:
            self._gate_lock.release()
        except Exception:
            pass

    def drain_attempts(self) -> List[dict]:
        """取出并清空 HTTP attempt 留痕（v4.6.64）—— 供插件层写入 Job 批次历史。"""
        _a = list(getattr(self, "attempts", []) or [])
        self.attempts = []
        return _a

    def translate_terms(self, title: str, year: Any, terms: List[str],
                        stop_check: Optional[Any] = None,
                        raise_typed: bool = False,
                        job_id: str = "", batch_no: int = 0,
                        batch_total: int = 0) -> Dict[str, str]:
        """统一入口 —— 先过单通道限速门（串行锁 + 最小间隔 + 可选 TPM 预算门），再走原翻译逻辑。
        raise_typed=True 时：429/配额/认证/超长/服务错误抛类型化异常（供翻译 worker 熔断/缩批），
        不再在底层 sleep 重试（单层策略）；默认 False 保持旧行为（内部重试，失败返回 {}）。
        v4.6.61（P2-1/P2-3）：job_id/batch_no 用于日志溯源；tpm_budget>0 时按估算令牌预约请求。
        v4.6.62（第 17 节）：跨作品聚合改用 translate_items（结构化输入 + 按 id 返回）。"""
        if not terms:
            return {}
        _est = 0
        if self.tpm_budget > 0:
            try:
                _est = (max(1, len(self._build_prompt(title, year, terms)) // 2)
                        + self._calc_max_tokens(len(terms)))
            except Exception:
                _est = max(1, len(terms) * 60)
        self._acquire_slot(stop_check, est_tokens=_est)
        try:
            return self._translate_terms_locked(title, year, terms, stop_check, raise_typed,
                                                job_id=job_id, batch_no=batch_no,
                                                batch_total=batch_total)
        finally:
            self._release_slot()

    def translate_items(self, items: List[dict], stop_check: Optional[Any] = None,
                        raise_typed: bool = False,
                        job_id: str = "", batch_no: int = 0,
                        batch_total: int = 0) -> Dict[str, str]:
        """结构化翻译（v4.6.62 · 第 17 节）—— items: [{"id","text","kind","title","year","item_id"}]，
        返回 {id: translation}。用于「跨作品聚合（global）」：每条词条携带自己的作品上下文，
        不同作品出现相同原文也不会串译（不再只依赖 {原文:译文}）。"""
        if not items:
            return {}
        _est = 0
        if self.tpm_budget > 0:
            try:
                _est = (max(1, len(self._build_prompt_structured(items)) // 2)
                        + self._calc_max_tokens(len(items)))
            except Exception:
                _est = max(1, len(items) * 60)
        self._acquire_slot(stop_check, est_tokens=_est)
        try:
            return self._translate_terms_locked("", "", [], stop_check, raise_typed,
                                                job_id=job_id, batch_no=batch_no,
                                                batch_total=batch_total, items=items)
        finally:
            self._release_slot()

    def _translate_terms_locked(self, title: str, year: Any, terms: List[str],
                                stop_check: Optional[Any] = None,
                                raise_typed: bool = False,
                                job_id: str = "", batch_no: int = 0,
                                batch_total: int = 0,
                                items: Optional[List[dict]] = None) -> Dict[str, str]:
        """翻译一批词条，返回 {原文: 译文}
        缺陷 J —— 批级重试：返回为空且 last_error 非空时（超时/网络/解析失败，
        非"限流重试 4 次"场景）再重试 2 次，间隔 3s/6s；连续失败把本批词条记到
        last_failed_batch，供插件层收集进失败清单（仪表盘可见、可重试、不毒化断点）。
        stop_check 可调用对象 —— 重试循环每轮/sleep 前调用，返回 True 立即抛
        InterruptedError 终止（停止后不再等 3 次重试，UI 立即恢复）。
        """
        if not terms and not items:
            return {}

        if items is not None:
            prompt = self._build_prompt_structured(items)
            terms_count = len(items)
            _texts = [str((x or {}).get("text") or "") for x in items]
        else:
            prompt = self._build_prompt(title, year, terms)
            terms_count = len(terms)
            _texts = list(terms)
        start_ts = time.time()
        self.last_error_kind = ""
        # v4.6.61（P2-1/P2-2）：请求号 + usage 复位（本次请求的令牌/延迟入统计）
        _req_no = int(self.stat_requests or 0)
        self._last_usage = None

        try:
            result = {}
            last_err = ""
            for _attempt in range(3):
                if stop_check is not None and stop_check():
                    raise InterruptedError("已请求停止翻译")
                # v4.6.64：每次真实 HTTP attempt 先记一条（结束/异常时更新）—— 429/5xx/401 也留痕
                _att = {"job_id": str(job_id or ""), "batch_no": int(batch_no or 0),
                        "term_count": terms_count, "request_no": int(self.stat_requests or 0),
                        "attempt": _attempt + 1,
                        "started_at": datetime.now().isoformat(timespec="seconds"),
                        "finished_at": "", "http_status": 0, "error_kind": "", "ok": False}
                self.attempts.append(_att)
                try:
                    if self._use_sdk and self._client:
                        result = self._call_sdk(prompt, terms_count, stop_check=stop_check,
                                                raise_typed=raise_typed)
                    else:
                        result = self._call_requests(prompt, terms_count, stop_check=stop_check,
                                                     raise_typed=raise_typed)
                    _att["http_status"] = int(getattr(self, "last_http_status", 0) or 0)
                    _att["ok"] = bool(result)
                    if not result:
                        _att["error_kind"] = str(getattr(self, "last_error_kind", "") or "unknown")
                except LLMError as _le:
                    _att["http_status"] = int(getattr(self, "last_http_status", 0) or 0)
                    _att["error_kind"] = str(getattr(_le, "kind", "") or "error")
                    raise
                finally:
                    _att["finished_at"] = datetime.now().isoformat(timespec="seconds")
                if result:
                    break
                last_err = self.last_error or "翻译返回空结果"
                _ferr_l = str(last_err).lower()
                _kind_now = str(getattr(self, "last_error_kind", "") or "")
                _hard = _kind_now in ("authentication_failed", "quota_exceeded", "context_length_exceeded")
                if not _hard and _kind_now in ("", "unknown"):
                    _hard = _ferr_l.startswith(("401", "403")) or any(
                        _k in _ferr_l for _k in ("incorrect api key", "invalid api key",
                                                 "unauthorized", "权限", "截断"))
                if _hard:
                    logger.warning(f"[LLM] 不可重试错误{('(' + _kind_now + ')') if _kind_now else ''}，"
                                   f"立即失败: {last_err[:120]}")
                    break
                if _attempt < 2:
                    _wait = 3 if _attempt == 0 else 6
                    logger.warning(f"[LLM] 批次翻译为空，{_wait}s 后重试 ({_attempt + 1}/2) | 原因: {last_err}")
                    if stop_check is not None and stop_check():
                        raise InterruptedError("已请求停止翻译")
                    time.sleep(_wait)

            # 失败留痕：本批词条（供插件层收集，不毒化断点）
            if not result:
                self.last_failed_batch = list(_texts)
            else:
                self.last_failed_batch = []

            elapsed = round(time.time() - start_ts, 2)
            # v4.6.61（P2-2）：令牌与延迟统计（供应商返回 usage → 实际值；否则估算）
            _us = getattr(self, "_last_usage", None)
            if _us and len(_us) >= 2 and (int(_us[0]) or int(_us[1])):
                _in_t, _out_t = int(_us[0]), int(_us[1])
            else:
                _in_t = max(1, len(prompt) // 2)
                _out_t = max(1, int(sum(len(str(v)) for v in (result or {}).values())) // 2)
            try:
                self.stat_tokens_in += int(_in_t)
                self.stat_tokens_out += int(_out_t)
                self.stat_latency_ms += int(elapsed * 1000)
                self.stat_last_latency_ms = int(elapsed * 1000)
            except Exception:
                pass
            if result:
                self.stat_success += 1   # v4.6.60：本请求有有效返回
                self.last_error = ""
                if len(result) < terms_count:
                    self.last_error = f"解析到 {len(result)} 条 / 期望 {terms_count} 条（部分词条可能丢失）"
                    logger.warning(f"[LLM] job={job_id} batch={batch_no}/{batch_total} request={_req_no} "
                                   f"仅翻译 {len(result)}/{terms_count} 条，部分词条丢失（缺失项保留待重试）")
                logger.info(f"[LLM] job={job_id} batch={batch_no}/{batch_total} request={_req_no} OK "
                            f"returned={len(result)}/{terms_count} latency={elapsed}s "
                            f"tokens~={_in_t}/{_out_t} max_tokens={self._calc_max_tokens(terms_count)}")
            else:
                self.stat_failed += 1   # v4.6.60：本请求为空/失败
                self.last_error = last_err or "翻译返回空结果"
                if not self.last_error_kind:
                    self.last_error_kind = self.classify_error(self.last_error)
                logger.warning(f"[LLM] job={job_id} batch={batch_no}/{batch_total} request={_req_no} "
                               f"翻译批失败已重试 3 次仍为空 (耗时{elapsed}s) | 原因: {self.last_error}")
            return result
        except LLMError:
            elapsed = round(time.time() - start_ts, 2)
            try:
                self.stat_latency_ms += int(elapsed * 1000)
            except Exception:
                pass
            _k = str(getattr(self, "last_error_kind", "") or "")
            if _k == "rate_limited":
                self.stat_rate_limited += 1
            elif _k == "quota_exceeded":
                self.stat_quota += 1
            else:
                self.stat_failed += 1
            logger.warning(f"[LLM] job={job_id} batch={batch_no}/{batch_total} request={_req_no} "
                           f"类型化失败({_k}) (耗时{elapsed}s): {self.last_error[:160]}")
            raise
        except InterruptedError as _ie:
            self.last_error = str(_ie)
            self.last_failed_batch = []
            elapsed = round(time.time() - start_ts, 2)
            logger.info(f"[LLM] 已按停止请求中断翻译 (耗时{elapsed}s)")
            return {}
        except Exception as e:
            self.last_error = str(e)[:200]
            self.last_failed_batch = list(_texts)
            elapsed = round(time.time() - start_ts, 2)
            logger.error(f"[LLM] 翻译失败 (耗时{elapsed}s): {e}\n{traceback.format_exc()}")
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

    # 结构化输入内置提示词（v4.6.62 · 第 17 节）—— 跨作品聚合时每条词条自带 title/year/kind 上下文，
    # 按 id 一一对应返回，避免不同作品出现相同原文时串译。
    STRUCTURED_PROMPT = """你是影视翻译专家。下面 items 是待翻译条目，每项含：
id（唯一标识，必须原样回填）、text（待翻译原文）、kind（person=人物姓名 / role=角色名）、
title（所属作品名）、year（年份）、item_id（作品 ID）。
请结合 title/year/kind 与作品背景，把每项 text 翻译成**简体中文**；若 text 已是简体中文或无需翻译，
translation 原样返回原文。不同 item 即使 text 相同，也各自按其作品上下文翻译。
items: {items_json}
输出: JSON 数组，每项为 {"id": "与输入一致的 id", "translation": "译文"}；
id 必须与输入一一对应、不得增删或改序。只输出 JSON，不要 markdown、不要额外说明。"""

    def _build_prompt_structured(self, items: List[dict]) -> str:
        """结构化提示词 —— 用户自定义模板若含 {items_json} 占位符则用其模板，否则用内置结构化模板。"""
        _tpl = self.prompt_template or ""
        if "{items_json}" not in _tpl:
            _tpl = self.STRUCTURED_PROMPT
        _payload = []
        for x in (items or []):
            _x = x or {}
            _payload.append({
                "id": str(_x.get("id") or ""),
                "text": str(_x.get("text") or ""),
                "kind": str(_x.get("kind") or ""),
                "title": str(_x.get("title") or ""),
                "year": str(_x.get("year") or ""),
                "item_id": str(_x.get("item_id") or ""),
            })
        return _tpl.replace("{items_json}", json.dumps(_payload, ensure_ascii=False))

    def _calc_max_tokens(self, terms_count: int) -> int:
        """根据批量大小动态计算 max_tokens
        - 5 条以内：2048（默认）
        - 5~10 条：3072
        - 10~20 条：4096
        - 20+ 条：8192（v3.7.6: T7 —— 30 条/批 + 长译名时 6144 易截断，提到 8192）
        避免大批量翻译时返回截断导致 JSON 解析失败
        """
        if terms_count <= 5:
            return 2048
        if terms_count <= 10:
            return 3072
        if terms_count <= 20:
            return 4096
        return 8192

    def close(self):
        """强制关闭底层 HTTP 连接，让卡住的 LLM 调用立即抛异常退出"""
        try:
            if self._http_client is not None:
                self._http_client.close()
                logger.info("[LLM] 已强制关闭 HTTP 连接")
        except Exception:
            pass
        try:
            if self._client is not None and hasattr(self._client, 'close'):
                self._client.close()
        except Exception:
            pass
        self._client = None
        self._http_client = None

    def _call_sdk(self, prompt: str, terms_count: int = 5,
                  stop_check: Optional[Any] = None,
                  raise_typed: bool = False) -> Dict[str, str]:
        """通过 openai SDK 调用
        移除 create() 中无效的 timeout 参数（openai SDK 不支持该参数）
        timeout 已在 httpx.Client 构造时设置，由 stop_service 调用 close() 强制中断
        429 限流（tpm/rpm 超限）自动重试，间隔递增
        T4 —— stop_check 透传：429 sleep 前检查，停止后立即中断不再空等 5+10+20s
        raise_typed=True 时不再内部 sleep 重试，429/配额/认证/超长/5xx 抛类型化异常；
            错误分类走 classify_error（余额不足不再被当成 429 白等）
        """
        max_tokens = self._calc_max_tokens(terms_count)
        self._rc_retry_done = False
        kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": "你是影视翻译专家，只输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=max_tokens,
        )
        _rp = self._reasoning_params()
        if _rp:
            kwargs["extra_body"] = dict(_rp)
        wait = 5
        for attempt in range(4):
            try:
                resp = self._client.chat.completions.create(**kwargs)
                self.last_http_status = 200   # v4.6.64：HTTP attempt 留痕用
                # v4.6.61（P2-2）：记录供应商返回的 usage（如有）
                try:
                    _u = getattr(resp, "usage", None)
                    if _u is not None:
                        self._last_usage = (int(getattr(_u, "prompt_tokens", 0) or 0),
                                            int(getattr(_u, "completion_tokens", 0) or 0))
                except Exception:
                    pass
                choice = resp.choices[0]
                _fr = getattr(choice, "finish_reason", None) or ""
                if str(_fr).lower() == "length":
                    _think = bool(getattr(choice.message, "reasoning_content", None))
                    if _think and not self._rc_retry_done and self._downgrade_reasoning():
                        _rp4 = self._reasoning_params()
                        if _rp4:
                            self._rc_retry_done = True
                            kwargs.pop("extra_body", None)
                            kwargs["extra_body"] = dict(_rp4)
                            logger.warning(f"[LLM] 模型仍在深度思考导致截断 → 换下一种关闭思考写法重试"
                                           f"（{json.dumps(_rp4, ensure_ascii=False)}）")
                            continue
                    self.last_error = ("输出被 max_tokens 截断（finish_reason=length）"
                                       + ("；检测到模型仍在深度思考（reasoning_content），"
                                          "请换非思考模型，或在设置页填写该服务商的「自定义关闭思考参数」"
                                          if _think else "，请调大 max_tokens 或减小单批条数"))
                    self.last_error_kind = "context_length_exceeded"
                    logger.warning(f"[LLM] {self.last_error}")
                    if raise_typed:
                        raise ContextLengthExceeded(self.last_error)
                    return {}
                text = (choice.message.content or "").strip()
                if not text and getattr(choice.message, "reasoning_content", None):
                    if not self._rc_retry_done and self._downgrade_reasoning():
                        _rp2 = self._reasoning_params()
                        if _rp2:
                            self._rc_retry_done = True
                            kwargs.pop("extra_body", None)
                            kwargs["extra_body"] = dict(_rp2)
                            logger.warning(f"[LLM] 检测到思考型模型 content 为空，换下一种关闭思考写法重试"
                                           f"（{json.dumps(_rp2, ensure_ascii=False)}）")
                            continue
                    self.last_error = ("模型只返回了思考内容（reasoning_content），未产出正式答案。"
                                       "已尝试关闭思考仍失败，请换非思考模型或在设置页填写"
                                       "该服务商的「自定义关闭思考参数」")
                    self.last_error_kind = "empty_response"
                    logger.warning(f"[LLM] {self.last_error}")
                    if raise_typed:
                        raise EmptyResponseError(self.last_error)
                    return {}
                if not text:
                    self.last_error = "模型返回空内容"
                    self.last_error_kind = "empty_response"
                    if raise_typed:
                        raise EmptyResponseError(self.last_error)
                return self._parse_response(text)
            except LLMError:
                raise
            except Exception as e:
                msg = str(e)
                if "404" in msg and self._fix_base_v1():
                    continue
                if self._downgrade_reasoning(msg, getattr(getattr(e, "response", None), "status_code", None)):
                    _rp3 = self._reasoning_params()
                    logger.warning(f"[LLM] 关闭思考参数被端点拒绝，换下一种写法重试"
                                   f"（{'不发参数' if not _rp3 else json.dumps(_rp3, ensure_ascii=False)}）: {msg[:140]}")
                    kwargs.pop("extra_body", None)
                    if _rp3:
                        kwargs["extra_body"] = dict(_rp3)
                    continue
                _resp_sdk = getattr(e, "response", None)
                self.last_http_status = int(getattr(_resp_sdk, "status_code", 0) or 0)   # v4.6.64
                _kind = self.classify_error(msg, getattr(_resp_sdk, "status_code", None))
                _ra = self._retry_after_of(_resp_sdk)
                if _kind == "rate_limited":
                    self.last_error_kind = "rate_limited"
                    self.last_error = msg[:200]
                    if raise_typed:
                        self.rate_limited_until = time.time() + (_ra or 60.0)
                        raise RateLimited(msg[:200], retry_after=_ra) from e
                    if attempt < 3:
                        _wait = float(_ra) if _ra else float(wait)
                        _wait = max(0.5, _wait * (0.8 + 0.4 * random.random()))
                        self.rate_limited_until = time.time() + _wait
                        logger.warning(f"[LLM] 触发限流(429)，{_wait:.1f}s 后重试 ({attempt + 1}/4)")
                        if stop_check is not None and stop_check():
                            raise InterruptedError("已请求停止翻译")
                        time.sleep(_wait)
                        wait *= 2
                        continue
                elif _kind in ("quota_exceeded", "authentication_failed", "context_length_exceeded"):
                    self.last_error_kind = _kind
                    self.last_error = msg[:200]
                    logger.warning(f"[LLM] {_kind}：立即失败不重试: {msg[:160]}")
                    if raise_typed:
                        raise self._typed_of(_kind, msg[:200]) from e
                    return {}
                elif _kind == "server_error":
                    self.last_error_kind = "server_error"
                    self.last_error = msg[:200]
                    logger.warning(f"[LLM] 服务端错误(5xx)，不当作限流: {msg[:160]}")
                    if raise_typed:
                        raise LLMServerError(msg[:200]) from e
                    return {}
                elif _kind == "network_error":
                    self.last_error_kind = "network_error"
                    self.last_error = msg[:200]
                    logger.warning(f"[LLM] 网络异常，不当作限流: {msg[:160]}")
                    if raise_typed:
                        raise NetworkError(msg[:200]) from e
                    return {}
                self.last_error = msg[:200]
                logger.error(f"[LLM] SDK 调用失败: {msg}")
                return {}
        self.last_error = "限流重试 4 次仍失败"
        self.last_error_kind = "rate_limited"
        if raise_typed:
            raise RateLimited(self.last_error)
        return {}

    def _call_requests(self, prompt: str, terms_count: int = 5,
                       stop_check: Optional[Any] = None,
                       raise_typed: bool = False) -> Dict[str, str]:
        """通过纯 requests 调用
        429 限流（tpm/rpm 超限）自动重试，间隔递增
        T4 —— stop_check 透传：429 sleep 前检查，停止后立即中断不再空等
        错误分类（配额/认证/超长/5xx 不再混入 429）；raise_typed=True 时抛类型化异常不重试
        """
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        max_tokens = self._calc_max_tokens(terms_count)
        self._rc_retry_done = False
        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是影视翻译专家，只输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "max_tokens": max_tokens,
        }
        _rp = self._reasoning_params()
        data.update(_rp)
        _rt_keys = set(_rp.keys())   # 已发过的「关闭思考」参数键（换写法时按此摘除，兼容自定义参数）
        proxies = self._parse_proxy()
        wait = 5
        tried_v1 = False
        for attempt in range(4):
            try:
                resp = self._requests_session().post(
                    url, headers=headers, json=data,
                    timeout=self.timeout,
                    proxies=proxies,
                    verify=self.verify_ssl,
                )
                self.last_http_status = int(getattr(resp, "status_code", 0) or 0)   # v4.6.64
                if resp.status_code == 404 and "/v1" not in (self.base_url or "").rstrip("/").split("/")[-2:] \
                        and not tried_v1:
                    tried_v1 = True
                    base = (self.base_url or "").rstrip("/")
                    url = base + "/v1/chat/completions"
                    logger.warning(f"[LLM] 404：地址缺 /v1，自动改用 {url} 重试一次")
                    continue
                # 429/限流：sensenova 429003 tpm/rpm limit，等几秒再试
                if resp.status_code == 429:
                    _body_txt = ""
                    try:
                        _body_txt = str(resp.text or "")[:300]
                    except Exception:
                        pass
                    _kind = self.classify_error(_body_txt or "429", 429)
                    _ra = self._retry_after_of(resp)
                    if _kind in ("quota_exceeded", "authentication_failed", "context_length_exceeded"):
                        self.last_error_kind = _kind
                        self.last_error = _body_txt[:200]
                        logger.warning(f"[LLM] {_kind}（HTTP 429 但非限流）：立即失败: {_body_txt[:160]}")
                        if raise_typed:
                            raise self._typed_of(_kind, _body_txt[:200])
                        return {}
                    self.last_error_kind = "rate_limited"
                    if raise_typed:
                        self.rate_limited_until = time.time() + (_ra or 60.0)
                        raise RateLimited(_body_txt[:200] or "429", retry_after=_ra)
                    if attempt < 3:
                        _wait = float(_ra) if _ra else float(wait)
                        _wait = max(0.5, _wait * (0.8 + 0.4 * random.random()))
                        self.rate_limited_until = time.time() + _wait
                        logger.warning(f"[LLM] 触发限流(429)，{_wait:.1f}s 后重试 ({attempt + 1}/4)")
                        if stop_check is not None and stop_check():
                            raise InterruptedError("已请求停止翻译")
                        time.sleep(_wait)
                        wait *= 2
                        continue
                resp.raise_for_status()
                result = resp.json()
                # v4.6.61（P2-2）：记录供应商返回的 usage（如有）
                try:
                    _u = (result or {}).get("usage") or {}
                    if _u:
                        self._last_usage = (int(_u.get("prompt_tokens") or 0),
                                            int(_u.get("completion_tokens") or 0))
                except Exception:
                    pass
                _choice0 = (result.get("choices") or [{}])[0] or {}
                _msg0 = (_choice0.get("message") or {}) or {}
                if str(_choice0.get("finish_reason") or "").lower() == "length":
                    _think = bool(_msg0.get("reasoning_content"))
                    if _think and not self._rc_retry_done and self._downgrade_reasoning():
                        _rp4 = self._reasoning_params()
                        if _rp4:
                            self._rc_retry_done = True
                            for _k in _rt_keys:
                                data.pop(_k, None)
                            data.update(_rp4)
                            _rt_keys = set(_rp4.keys())
                            logger.warning(f"[LLM] 模型仍在深度思考导致截断 → 换下一种关闭思考写法重试"
                                           f"（{json.dumps(_rp4, ensure_ascii=False)}）")
                            continue
                    self.last_error = ("输出被 max_tokens 截断（finish_reason=length）"
                                       + ("；检测到模型仍在深度思考（reasoning_content），"
                                          "请换非思考模型，或在设置页填写该服务商的「自定义关闭思考参数」"
                                          if _think else "，请调大 max_tokens 或减小单批条数"))
                    self.last_error_kind = "context_length_exceeded"
                    logger.warning(f"[LLM] {self.last_error}")
                    if raise_typed:
                        raise ContextLengthExceeded(self.last_error)
                    return {}
                text = str(_msg0.get("content") or "").strip()
                if not text and isinstance(result, dict):
                    _rc = _msg0.get("reasoning_content")
                    if _rc and not self._rc_retry_done and self._downgrade_reasoning():
                        _rp2 = self._reasoning_params()
                        if _rp2:
                            self._rc_retry_done = True
                            for _k in _rt_keys:
                                data.pop(_k, None)
                            data.update(_rp2)
                            _rt_keys = set(_rp2.keys())
                            logger.warning(f"[LLM] 检测到思考型模型 content 为空，换下一种关闭思考写法重试"
                                           f"（{json.dumps(_rp2, ensure_ascii=False)}）")
                            continue
                    if _rc:
                        self.last_error = ("模型只返回了思考内容（reasoning_content）没有正文，"
                                           "请换非思考模型或在设置页填写该服务商的「自定义关闭思考参数」")
                        self.last_error_kind = "empty_response"
                        logger.warning(f"[LLM] {self.last_error}")
                        if raise_typed:
                            raise EmptyResponseError(self.last_error)
                        return {}
                if not text:
                    self.last_error = "模型返回空内容"
                    self.last_error_kind = "empty_response"
                    logger.warning(f"[LLM] 模型返回空内容: {result}")
                    if raise_typed:
                        raise EmptyResponseError(self.last_error)
                    return {}
                return self._parse_response(text)
            except LLMError:
                raise
            except Exception as e:
                msg = str(e)
                if self._downgrade_reasoning(msg, getattr(getattr(e, "response", None), "status_code", None)):
                    _rp3 = self._reasoning_params()
                    logger.warning(f"[LLM] 关闭思考参数被端点拒绝，换下一种写法重试"
                                   f"（{'不发参数' if not _rp3 else json.dumps(_rp3, ensure_ascii=False)}）: {msg[:140]}")
                    for _k in _rt_keys:
                        data.pop(_k, None)
                    data.update(_rp3)
                    _rt_keys = set(_rp3.keys())
                    continue
                _resp = getattr(e, "response", None)
                self.last_http_status = int(getattr(_resp, "status_code", 0) or 0)   # v4.6.64
                _kind = self.classify_error(msg, getattr(_resp, "status_code", None))
                if _kind == "rate_limited":
                    self.last_error_kind = "rate_limited"
                    self.last_error = msg[:200]
                    if raise_typed:
                        raise RateLimited(msg[:200], retry_after=self._retry_after_of(_resp)) from e
                    if attempt < 3:
                        _wait = max(0.5, float(wait) * (0.8 + 0.4 * random.random()))
                        self.rate_limited_until = time.time() + _wait
                        logger.warning(f"[LLM] 触发限流(429)，{_wait:.1f}s 后重试 ({attempt + 1}/4)")
                        if stop_check is not None and stop_check():
                            raise InterruptedError("已请求停止翻译")
                        time.sleep(_wait)
                        wait *= 2
                        continue
                elif _kind in ("quota_exceeded", "authentication_failed", "context_length_exceeded"):
                    self.last_error_kind = _kind
                    self.last_error = msg[:200]
                    logger.warning(f"[LLM] {_kind}：立即失败不重试: {msg[:160]}")
                    if raise_typed:
                        raise self._typed_of(_kind, msg[:200]) from e
                    return {}
                elif _kind == "server_error":
                    self.last_error_kind = "server_error"
                    self.last_error = msg[:200]
                    logger.warning(f"[LLM] 服务端错误(5xx)，不当作限流: {msg[:160]}")
                    if raise_typed:
                        raise LLMServerError(msg[:200]) from e
                    return {}
                elif _kind == "network_error":
                    self.last_error_kind = "network_error"
                    self.last_error = msg[:200]
                    logger.warning(f"[LLM] 网络异常，不当作限流: {msg[:160]}")
                    if raise_typed:
                        raise NetworkError(msg[:200]) from e
                    return {}
                self.last_error = msg[:200]
                logger.error(f"[LLM] requests 调用失败: {msg}")
                return {}
        self.last_error = "限流重试 4 次仍失败"
        self.last_error_kind = "rate_limited"
        if raise_typed:
            raise RateLimited(self.last_error)
        return {}

    _XML_ILLEGAL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")

    @classmethod
    def _scalar_map(cls, data: dict):
        """LLM JSON 只接受 scalar（str/int/float/bool）→ 去空白后的 str。
        出现 dict/list/嵌套对象 → 返回 (None, True)，调用方据此整批判失败 ——
        杜绝把 Python dict/list 的 repr 当译文写进库（文档 §十：垃圾 LLM JSON 不进库）。
        :return: (映射 dict 或 None, 是否含非 scalar 垃圾)
        """
        if not isinstance(data, dict):
            return None, True
        _out: Dict[str, str] = {}
        for _k, _v in data.items():
            if isinstance(_v, (str, int, float, bool)):
                _s = cls._XML_ILLEGAL_RE.sub("", str(_v)).strip()
                if _s:
                    _out[str(_k)] = _s
            elif _v is None:
                continue
            else:
                return None, True
        return _out, False

    def _parse_response(self, text: str) -> Dict[str, str]:
        """从 LLM 响应中解析 JSON。
        - 对象 {原文: 译文}（legacy）：只接受标量值，dict/list/嵌套 → 整批拒绝（v4.6.21）。
        - 数组 [{"id":..,"translation":..}]（v4.6.62 · 结构化输入）：按 id → 译文返回。"""
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        _parsed = None
        try:
            _parsed = json.loads(text)
        except json.JSONDecodeError:
            _arr = self._extract_json_array(text)
            if _arr:
                try:
                    _parsed = json.loads(_arr)
                except json.JSONDecodeError:
                    _parsed = None
            if _parsed is None:
                match = self._extract_json_object(text)
                if match:
                    try:
                        _parsed = json.loads(match)
                    except json.JSONDecodeError:
                        _parsed = None
        # 结构化输入：JSON 数组（按 id 一一对应）
        if isinstance(_parsed, list):
            _out: Dict[str, str] = {}
            for _it in _parsed:
                if not isinstance(_it, dict):
                    continue
                _id = str(_it.get("id") or "").strip()
                _tr = _it.get("translation")
                if _id and isinstance(_tr, (str, int, float)) and str(_tr).strip():
                    _out[_id] = str(_tr).strip()
            if _out:
                return _out
            self.last_error = f"结构化响应无有效项: {text[:80]}"
            logger.warning(f"[LLM] 结构化响应无法解析出 id/translation: {text[:200]}")
            return {}
        if isinstance(_parsed, dict):
            _out, _bad = self._scalar_map(_parsed)
            if _bad:
                # 文档 §十：出现 dict/list/nested object → 整批失败，不得把 dict 字符串入库
                self.last_error = f"JSON 含非标量值（dict/list），整批拒绝入库: {text[:80]}"
                logger.warning(f"[LLM] 响应含非标量（dict/list）值，整批拒绝入库: {text[:200]}")
                return {}
            return _out or {}

        self.last_error = f"JSON 解析失败: {text[:80]}"
        logger.warning(f"[LLM] 无法解析响应: {text[:200]}")
        return {}

    @staticmethod
    def _extract_json_array(text: str) -> str:
        """平衡方括号扫描，提取最外层完整 JSON 数组（字符串内括号不计数）。找不到返回空串。"""
        try:
            start = text.find("[")
            if start < 0:
                return ""
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "[":
                    depth += 1
                elif ch == "]":
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
            return ""
        except Exception:
            return ""

    @staticmethod
    def _extract_json_object(text: str) -> str:
        """平衡括号扫描，从文本中提取最外层完整 JSON 对象
        （字符串内的括号不参与计数，支持嵌套对象）。找不到返回空串。"""
        try:
            start = text.find("{")
            if start < 0:
                return ""
            depth = 0
            in_str = False
            esc = False
            for i in range(start, len(text)):
                ch = text[i]
                if in_str:
                    if esc:
                        esc = False
                    elif ch == "\\":
                        esc = True
                    elif ch == '"':
                        in_str = False
                    continue
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[start:i + 1]
            return ""
        except Exception:
            return ""
