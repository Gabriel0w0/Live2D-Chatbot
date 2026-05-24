from typing import TYPE_CHECKING
from langchain_core.messages import HumanMessage

if TYPE_CHECKING:
    from langchain_ollama import ChatOllama

async def translate_to_japanese(
    text: str, 
    role_style: str = "可愛、撒嬌語氣", 
    chat_model: 'ChatOllama' = None 
) -> str:
    if not text.strip():
        return ""
    
    if chat_model is None:
        return text 

    prompt = f"""
請將以下中文翻譯成日文，並保持角色語氣：{role_style}。
中文：
「{text}」
請只輸出日文翻譯，不要加入任何解釋
"""
    
    # 使用 ainvoke (Async Invoke)
    try:
        result = await chat_model.ainvoke([HumanMessage(content=prompt)])
        # 使用 Python 內建的 strip() 取代 regex
        return result.content.strip()
    except Exception as e:
        print(f"[Translation Error] {e}")
        return text # 失敗時回傳原文，避免出錯