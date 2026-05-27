"""Session上下文压缩 — 旧chunks -> LLM摘要 -> 摘要chunk"""


def compress_session(session, max_tokens: int = 100000) -> "Session":
    """当session tokens超出限制时压缩历史chunks为摘要"""
    return session  # stub: 待接入LLM摘要
