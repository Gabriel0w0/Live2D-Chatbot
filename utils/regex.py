import re
from typing import List, Optional

# ==============================================================================
# 正則表達式模式定義 (Regex Patterns)
# ==============================================================================

# 正向情緒關鍵字：用於判斷使用者是否表達好感
POSITIVE_PAT = re.compile(
    r"(謝謝|喜歡你|愛你|太棒|好棒|可愛|真貼心|抱抱|想你|最愛|婆|老婆|乖|厲害|good|nice)", 
    re.I  # 忽略大小寫
)

# 負向情緒關鍵字：用於判斷使用者是否表達厭惡或攻擊
NEGATIVE_PAT = re.compile(
    r"(不喜歡你|討厭你|爛|閉嘴|走開|煩|生氣|滾|笨蛋|智障|bad|hate)", 
    re.I
)

# 中性/結束語關鍵字：用於判斷對話是否僅為簡單確認
NEUTRAL_PAT = re.compile(
    r"(嗯|哦|好|OK|好的|是喔|知)[!！。.\s]*$", 
    re.I
)

# ==============================================================================
# 親密度與情緒評分邏輯
# ==============================================================================

def keyword_intimacy_fallback(text: str) -> int:
    """
    [親密度備援機制]
    當 LLM 無法回傳有效的 JSON 或解析失敗時，使用此函數進行粗略評分。
    
    Args:
        text (str): 使用者的輸入訊息。
        
    Returns:
        int: 親密度變化值 (-1, 0, 1)。
    """
    if not text:
        return 0
        
    # 優先順序：正向 -> 負向 -> 中性 -> 無變化
    if POSITIVE_PAT.search(text):
        return 1
    if NEGATIVE_PAT.search(text):
        return -1
    if NEUTRAL_PAT.search(text):
        return 0
        
    return 0

def extract_emotion_tag(text: str) -> Optional[str]:
    """
    [情緒標籤提取]
    從模型的回覆中提取情緒標籤 (格式: [emotion:xxx])。
    
    Args:
        text (str): 模型的原始回覆文字。
        
    Returns:
        Optional[str]: 提取到的情緒字串 (如 'joy', 'sad')，若無則回傳 None。
    """
    if not text:
        return None
        
    # 搜尋格式為 [emotion:單字] 的標籤
    tags = re.findall(r"\[emotion:(\w+)\]", text, flags=re.I)
    
    # 根據 Prompt 規則，情緒標籤通常位於句首
    # 因此先用第一個找到的標籤作為該句的主要情緒
    return tags[0].lower() if tags else None

def emotion_weight(emotion: Optional[str]) -> int:
    """
    [情緒權重轉換]
    將文字情緒標籤轉換為親密度的增減數值。
    
    Args:
        emotion (Optional[str]): 情緒標籤 (如 'joy')。
        
    Returns:
        int: 親密度變化權重。
    """
    if not emotion:
        return 0
        
    # 定義情緒對應的分數表
    table = {
        "joy": 1,      # 讓月讀醬開心 -> 加分
        "cute": 1,     # 讓月讀醬覺得可愛/撒嬌 -> 加分
        "shy": 1,      # 讓月讀醬害羞 (通常是正向調情) -> 加分
        "neutral": 0,  # 平靜 -> 不變
        "sad": -1,     # 讓月讀醬難過 -> 扣分 (視為負面互動)
        "angry": -1    # 讓月讀醬生氣 -> 扣分
    }
    
    # 使用 get(key, default) 避免未定義的情緒導致錯誤
    return table.get(emotion.lower(), 0)

# ==============================================================================
# 事實提取邏輯 (Fact Extraction)
# ==============================================================================

def extract_facts(message: str) -> List[str]:
    """
    [記憶事實提取 - Regex版]
    作為 LLM 提取記憶失敗時的備援方案。
    使用正則表達式嘗試從對話中抓取使用者的基本資料。
    
    Args:
        message (str): 使用者的輸入訊息。
        
    Returns:
        List[str]: 提取到的事實列表 (例如 ["使用者的名字是小明", "使用者喜歡貓"])。
    """
    if not message:
        return []
    
    facts: List[str] = []

    # 1. 提取名字
    # 匹配模式：我叫XXX, 我的名字是XXX, 叫我XXX
    # (?:...) 是非捕獲群組，只用來分組但不佔用結果
    m = re.search(r"(?:我叫|名字是|叫我)\s*([\u4e00-\u9fa5a-zA-Z0-9]+)", message)
    if m:
        facts.append(f"使用者的名字是{m.group(1)}")

    # 2. 提取喜好
    # 匹配模式：我喜歡XXX, 我超愛XXX
    m = re.search(r"我(?:超?喜歡|超?愛)\s*([\u4e00-\u9fa5a-zA-Z0-9]+)", message)
    if m:
        facts.append(f"使用者喜歡{m.group(1)}")

    # 3. 提取討厭的事物
    # 匹配模式：我討厭XXX, 我不喜歡XXX
    m = re.search(r"我(?:討厭|不喜歡)\s*([\u4e00-\u9fa5a-zA-Z0-9]+)", message)
    if m:
        facts.append(f"使用者討厭{m.group(1)}")

    # 4. 提取年齡
    # 匹配模式：我...XX歲
    m = re.search(r"我.*?(\d{1,3})\s*歲", message)
    if m:
        facts.append(f"使用者{m.group(1)}歲")

    # 5. 提取居住地
    # 匹配模式：我住在XXX
    m = re.search(r"我住在\s*([\u4e00-\u9fa5a-zA-Z0-9]+)", message)
    if m:
        facts.append(f"使用者住在{m.group(1)}")

    # 6. 提取職業/身分
    # 匹配模式：我是XXX (排除常見的形容詞誤判)
    exclude_jobs = ["笨蛋", "人", "男生", "女生", "開心", "難過", "累", "生氣"]
    # (?!...) 是負向先行斷言，確保後面不會接 "心情"、"樣子" 等詞
    m = re.search(r"我是\s*([\u4e00-\u9fa5a-zA-Z0-9]+)(?!.*(心情|樣子))", message)
    if m:
        job = m.group(1)
        # 過濾掉太短或在排除列表中的詞彙
        if job not in exclude_jobs and len(job) > 1:
            facts.append(f"使用者的身分/職業是{job}")

    # 7. 提取當下狀態/心情
    # 匹配模式：包含 "我今天" + 心情關鍵字
    if "我今天" in message:
        emotions = ["開心", "難過", "累", "生氣", "放鬆", "忙"]
        for emo in emotions:
            if emo in message:
                facts.append(f"使用者今天覺得{emo}")
                
    return facts