import os
from functools import lru_cache

from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek


load_dotenv()  # 加载 .env 文件中的环境变量


@lru_cache(maxsize=1)
def get_chat_model() ->ChatDeepSeek:
    """
    创建并缓存大模型实例。

    使用缓存可以避免每次请求都重新初始化客户端。
    """
    
    api_key=os.getenv("DEEPSEEK_API_KEY")

    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 环境变量未设置，请在 .env 文件中配置。")
    
    model_name = os.getenv("LLM_MODEL","deepseek-chat")
    temperature = float(os.getenv("LLM_TEMPERATURE", "0.1"))
    timeout = float(os.getenv("LLM_TIMEOUT", "60"))

    return ChatDeepSeek(
        model=model_name,
        temperature=temperature,
        timeout=timeout,
        max_retries=2,
        api_key=api_key,
    )