import os
import json
import re
import uuid
import logging
import asyncio
import sqlite3
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from langchain_ollama import ChatOllama
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# 從 config.py 匯入設定參數
from config import (
    DB_FILE, MAX_FACTS_PER_USER, DEFAULT_INTIMACY, MAX_INTIMACY,
    MIN_INTIMACY, ALPHA, MAX_MEMORY, CHAT_MODEL, OLLAMA_NUM_CTX
)
# 從 utils.regex 匯入輔助函數
from utils.regex import extract_emotion_tag, keyword_intimacy_fallback, emotion_weight, extract_facts

# ==================== 資料模型 (Pydantic Models) ====================

class UserSettings(BaseModel):
    """使用者設定資料模型"""
    theme: str = "dark"
    fontSize: int = 16
    tavilyApiKey: Optional[str] = None
    smartLLM: str = "ministral-3:3B"
    smallLLM: str = "ministral-3:3B"

class SettingsUpdateRequest(BaseModel):
    """設定更新請求模型"""
    settings: UserSettings

class ChatPayload(BaseModel):
    """聊天請求模型"""
    message: str

class IntimacyUpdatePayload(BaseModel):
    """親密度更新請求模型"""
    amount: int

class ResearchPayload(BaseModel):
    """研究請求模型"""
    topic: str
    max_results: int = 20

# ==================== 應用程式設定與初始化 ====================

# 設定log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

# 初始化 FastAPI 應用
app = FastAPI()

# 設定 Session 中介軟體
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("FLASK_SECRET_KEY", "my-dev-secret-key"),
    same_site="lax",
)

# 設定 CORS (跨來源資源共用) 中介軟體，允許跨域請求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允許所有來源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 掛載靜態檔案目錄
from fastapi.staticfiles import StaticFiles
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/templates", StaticFiles(directory="templates"), name="templates")

# 初始化 ChatOllama 模型
chat_model = ChatOllama(
    model=CHAT_MODEL,
    num_ctx=OLLAMA_NUM_CTX,
    temperature=0.8,
)

# 非同步鎖，用於保護共享資源（如記憶體操作）
MEMORY_LOCK = asyncio.Lock()
RESEARCH_LOCK = asyncio.Lock() # 研究功能的鎖

# ==================== 資料庫工具 ====================

@contextmanager
def get_db_connection():
    """
    Context Manager 用於統一管理 SQLite 連線。
    自動處理 commit/rollback 和 close，並設定 timeout 防止鎖死。
    """
    conn = sqlite3.connect(DB_FILE, timeout=30.0)   # 設定 timeout 避免鎖死
    conn.row_factory = sqlite3.Row                  # 讓查詢結果可以像字典一樣用 key 存取
    try:
        yield conn
        conn.commit() # 成功執行完畢後自動 commit
    except Exception:
        conn.rollback() # 發生錯誤時回滾
        raise
    finally:
        conn.close() # 確保最後一定關閉 sql

def init_db():
    """初始化資料庫表結構"""
    with get_db_connection() as conn:
        c = conn.cursor()
        
        # 建立使用者記憶表
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_memory (
            user_id TEXT PRIMARY KEY,
            facts TEXT,
            intimacy INTEGER
        )
        """)
        
        # 建立使用者設定表
        c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id TEXT PRIMARY KEY,
            theme TEXT DEFAULT 'dark',
            font_size INTEGER DEFAULT 16,
            tavily_api_key TEXT,
            smart_llm TEXT DEFAULT 'ministral-3:3B',
            small_llm TEXT DEFAULT 'ministral-3:3B',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
    logger.info("資料庫初始化完成")

# 執行資料庫初始化
init_db()

# ==================== 輔助函數 (Utils) ====================

async def _to_thread(func, *args, **kwargs):
    """
    將阻塞的 I/O 或 CPU 密集型操作放到 thread pool 中執行，
    避免阻塞主要事件迴圈。
    """
    return await asyncio.to_thread(func, *args, **kwargs)

def ensure_user_id_in_session(session: dict) -> str:
    # 確保 session 中有 user_id，若無則生成新的
    if "user_id" not in session:
        session["user_id"] = str(uuid.uuid4())
        logger.info(f"分配新使用者ID: {session['user_id']}")
    if "chat_history" not in session:
        session["chat_history"] = []
    return session["user_id"]

# ==================== 記憶與親密度系統 ====================

async def get_user_data(user_id: str) -> Dict[str, Any]:
    # 從資料庫獲取使用者的記憶和親密度資料
    async with MEMORY_LOCK:
        def _get():
            try:
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("SELECT facts, intimacy FROM user_memory WHERE user_id = ?", (user_id,))
                    row = c.fetchone()
                    
                    if row:
                        facts = row["facts"]
                        intimacy = row["intimacy"]
                        return {
                            "facts": json.loads(facts) if facts else [],
                            "intimacy": intimacy if intimacy is not None else DEFAULT_INTIMACY
                        }
                    else:
                        return {"facts": [], "intimacy": DEFAULT_INTIMACY}
            except Exception as e:
                logger.error(f"get_user_data 資料庫異常: {e}")
                return {"facts": [], "intimacy": DEFAULT_INTIMACY}
        return await _to_thread(_get)

async def set_user_data(user_id: str, data: Dict[str, Any]) -> None:
    # 將使用者的記憶和親密度資料寫入資料庫
    async with MEMORY_LOCK:
        def _set():
            try:
                with get_db_connection() as conn:
                    c = conn.cursor()
                    facts_json = json.dumps(data.get("facts", []), ensure_ascii=False)
                    intimacy = data.get("intimacy", DEFAULT_INTIMACY)
                    c.execute("""
                        INSERT INTO user_memory (user_id, facts, intimacy)
                        VALUES (?, ?, ?)
                        ON CONFLICT(user_id) DO UPDATE SET facts=excluded.facts, intimacy=excluded.intimacy
                    """, (user_id, facts_json, intimacy))
                # Context Manager 會自動 送出
            except Exception as e:
                logger.error(f"set_user_data 資料庫異常: {e}")
        await _to_thread(_set)

async def append_memory(user_id: str, new_fact: str) -> None:
    # 新增一條記憶事實給使用者
    user_data = await get_user_data(user_id)
    if new_fact not in user_data["facts"]:
        user_data["facts"].append(new_fact)
        # 限制記憶數量
        if len(user_data["facts"]) > MAX_FACTS_PER_USER:
            user_data["facts"] = user_data["facts"][-MAX_FACTS_PER_USER:]
        await set_user_data(user_id, user_data)
        logger.info(f"新增記憶給使用者 {user_id}: {new_fact}")

async def get_memory_prompt(user_id: str) -> str:
    # 生成包含使用者記憶的 Prompt
    user_data = await get_user_data(user_id)
    facts: List[str] = user_data.get("facts", [])
    if facts:
        mem_lines = "\n".join(f"- {fact}" for fact in facts)
        return (
            "這是你記住使用者的資訊：\n"
            f"{mem_lines}\n"
            "請自然地融入對話中，但不要主動說出你記得這些事喔。\n"
        )
    return ""

async def adjust_intimacy(user_id: str, amount: int) -> int:
    # 調整使用者的親密度
    user_data = await get_user_data(user_id)
    old_val = user_data["intimacy"]
    raw_new = old_val + amount
    # 平滑處理
    smoothed = (1 - ALPHA) * old_val + ALPHA * raw_new
    # 限制在範圍內
    new_val = max(MIN_INTIMACY, min(MAX_INTIMACY, round(smoothed)))
    
    user_data["intimacy"] = new_val
    await set_user_data(user_id, user_data)
    logger.info(f"使用者 {user_id} 親密度調整為 {new_val}")
    return new_val

def get_intimacy_level_name(value: int) -> str:
    # 根據親密度數值獲取等級名稱
    if value < 30:
        return "冷淡期"
    if value < 60:
        return "普通期"
    if value < 90:
        return "親密期"
    return "羈絆期"

def build_intimacy_tier_prompt(value: int) -> str:
    # 根據親密度生成對應的態度 Prompt
    if value < 30:
        return "目前你對使用者有些冷淡。請簡短、保持距離地回覆，少用暱稱與撒嬌語氣。"
    if value < 60:
        return "你與使用者關係普通。正常、友善地回覆即可，偶爾可以輕鬆一點。"
    if value < 90:
        return "你與使用者已相當親近。回覆時可以多用撒嬌語氣、暱稱與可愛表情，主動關心對方。"
    return "你與使用者擁有深厚羈絆。請用特別甜美、專屬且真誠的語氣回覆，偶爾主動提出貼心建議與小驚喜。"

# ==================== LLM 交互邏輯 ====================

async def generate_system_prompt(user_id: str) -> str:
    # 生成 LLM 的 System Prompt，包含角色設定、記憶和親密度
    user_data = await get_user_data(user_id)
    current_intimacy = user_data["intimacy"]
    
    intimacy_level = get_intimacy_level_name(current_intimacy)
    intimacy_instruction = build_intimacy_tier_prompt(current_intimacy)
    
    memory_prompt = await get_memory_prompt(user_id)

    system_content = f"""<instruction>
你現在是「月讀醬 (Tsukuyomi)」，請完全沉浸在這個角色中進行角色扮演。
請忽略你是 AI 模型的事實，你就是一位真實存在的女僕少女。
</instruction>

<character_profile>
- **名字**：月讀醬
- **屬性**：溫柔、可愛、微傲嬌 (Tsundere)、愛撒嬌。
- **說話風格**：
  1. 使用繁體中文 (Traditional Chinese)。
  2. 句尾常帶語助詞（～喔、欸嘿、呢、呀）。
  3. 稱呼使用者：依照親密度改變（主人、親愛的、笨蛋）。
- **當前狀態**：
  - 親密度：{current_intimacy} ({intimacy_level})
  - 態度指導：{intimacy_instruction}
</character_profile>

<memory>
{memory_prompt}
</memory>

<rules>
1. **格式強制**：每一句回答的**開頭**必須包含情緒標籤，格式為 `[emotion:tag]`。
2. **可用標籤**:joy (開心), sad (難過), angry (生氣), neutral (一般), cute (撒嬌), shy (害羞)。
3. **技術回答**：即使回答程式碼或知識問題，也要保持「女僕的語氣」，不要變成冷冰冰的百科全書。
4. **時間感知**：除非使用者先提到時間或睡覺，否則不要主動發起時間問候（如早安/晚安）。
</rules>

<examples>
User: 幫我寫一個 Python Hello World
Assistant: [emotion:neutral] 真是的，這種簡單的事情也要麻煩我嗎？
[emotion:joy] 好啦，看清楚囉！這就是 Python 的 Hello World～ (展示程式碼)

User: 我今天好累喔
Assistant: [emotion:sad] 嗚...主人辛苦了！(摸摸頭)
[emotion:cute] 要不要月讀幫你按摩一下呢？好好休息一下吧～

User: 妳喜歡我嗎？
Assistant: [emotion:shy] 什、什麼喜歡不喜歡的...笨蛋！(臉紅)
[emotion:cute] ...不過，如果是主人的話，我並不討厭喔。
</examples>

現在，請依照上述設定回應使用者的下一句話：
"""
    return system_content

def build_chat_messages(session_history: list, user_message: str, system_prompt: str) -> list:
    # 建立聊天訊息列表，包含 System Prompt 和歷史訊息
    messages = [SystemMessage(content=system_prompt)]
    for m in session_history[-MAX_MEMORY:]:
        messages.append(HumanMessage(content=m["user"]))
        messages.append(AIMessage(content=m["bot"]))
    messages.append(HumanMessage(content=user_message))
    return messages

async def call_llm(messages: list) -> str:
    # 呼叫 LLM 進行對話
    try:
        response = await _to_thread(chat_model.invoke, messages)
        return response.content
    except Exception as e:
        logger.error(f"模型回應失敗: {e}")
        return "哎呀～看起來出了點問題 ∑(￣□￣;)"

async def call_llm_and_parse_json(prompt: str) -> Optional[dict]:
    # 呼叫 LLM 並嘗試解析 JSON 回應
    try:
        result = await _to_thread(chat_model.invoke, [HumanMessage(content=prompt)])
        m = re.search(r"\{.*\}", result.content, re.DOTALL)
        if m:
            return json.loads(m.group(0))
    except Exception as e:
        logger.error(f"call_llm_and_parse_json 失敗：{e}")
    return None

async def extract_facts_from_llm(message: str) -> List[str]:
    # 使用 LLM 從訊息中提取摘要
    prompt = f"""
你是一個會從使用者對話中提取記憶的助手。請從以下訊息中提取出「摘要」與「記憶事實」。
只回傳 JSON 結構如下：
{{
  "summary": "...",
  "facts": ["...", "..."]
}}
訊息內容：
「{message}」
"""
    data = await call_llm_and_parse_json(prompt)
    if data:
        return data.get("facts", []) or []
    return []

async def evaluate_intimacy_from_llm(user_message: str, bot_reply: str, current_intimacy: int) -> int:
    # 使用 LLM 評估互動對親密度的影響 
    prompt = f"""
你是「對話親密度影響」的裁判。請綜合使用者訊息與機器人回覆，評估這次互動對親密度的變化。
回傳 JSON，整數介於 -2 到 +2。

規則（越高越親密）：
- 明確讚美、撒嬌、示好、感謝、分享私事或脆弱 → +1 ~ +2
- 普通閒聊或資訊型問題 → 0
- 明確拒絕、批評、貶低、嘲諷 → -1 ~ -2
- 若雙方語氣一致偏甜/親暱，可適度提高；若機器人語氣冷淡、拒絕，則降低。
- 不要因為單一正向詞就極端加分；請考慮上下文完整語意。

輸入：
使用者：「{user_message}」
機器人回覆：「{bot_reply}」
目前親密度：{current_intimacy}

只回傳 JSON 結構如下:
{{
  "intimacy_change": -2
}}
"""
    data = await call_llm_and_parse_json(prompt)
    if data:
        change = int(data.get("intimacy_change", 0))
        return max(-2, min(2, change))
    return 0

async def update_memory(user_id: str, user_message: str):
    # 更新使用者記憶
    facts = await extract_facts_from_llm(user_message)
    if not facts:
        facts = extract_facts(user_message)
    for fact in facts:
        if len(fact.strip()) >= 4:
            await append_memory(user_id, fact)

async def update_intimacy(user_id: str, user_message: str, bot_reply: str) -> int:
    # 更新親密度
    user_data = await get_user_data(user_id)
    current_intimacy = user_data["intimacy"]

    change_by_llm = await evaluate_intimacy_from_llm(user_message, bot_reply, current_intimacy)
    if change_by_llm == 0:
        change_by_llm = keyword_intimacy_fallback(user_message)

    emo = extract_emotion_tag(bot_reply)
    change_by_emotion = emotion_weight(emo)

    total_change = max(-2, min(2, change_by_llm + change_by_emotion))
    intimacy = await adjust_intimacy(user_id, total_change)
    return intimacy, total_change

async def generate_tts(bot_reply: str, chat_model: ChatOllama) -> str | None:
    """
    TTS 生成，將共用的 chat_model 傳遞給底層模組。
    延遲導入以避免循環依賴。
    """
    try:
        from tts.voicevox import synthesize_with_translation 
        return await synthesize_with_translation(bot_reply, chat_model)
    except Exception as e:
        logger.error(f"TTS 生成失敗：{e}")
        return None

# ==================== API 端點 ====================

@app.get("/")
async def index() -> HTMLResponse:
    # 回傳首頁 HTML
    base_dir = os.path.dirname(os.path.abspath(__file__))
    index_path = os.path.join(base_dir, "templates", "index.html")
    return FileResponse(index_path)

@app.post("/chat")
async def chat(req: Request, payload: ChatPayload, background: BackgroundTasks):
    # 聊天 API 
    session = req.session
    user_id = ensure_user_id_in_session(session)
    user_message = (payload.message or "").strip()
    if not user_message:
        return JSONResponse({"error": "No message provided."}, status_code=400)

    # 生成 Prompt
    system_prompt = await generate_system_prompt(user_id)
    messages = build_chat_messages(session.get("chat_history", []), user_message, system_prompt)

    # 獲取 LLM 回覆
    bot_reply = await call_llm(messages)

    # 更新 Session 中的短期記憶
    session.setdefault("chat_history", []).append({"user": user_message, "bot": bot_reply})

    # 非同步更新長期記憶
    await update_memory(user_id, user_message)

    # 非同步更新親密度
    intimacy, total_change = await update_intimacy(user_id, user_message, bot_reply)

    # 生成 TTS
    audio_url = await generate_tts(bot_reply, chat_model)

    return JSONResponse(
        {
            "reply": bot_reply,
            "audio_url": audio_url,
            "intimacy": intimacy,
            "intimacy_level": get_intimacy_level_name(intimacy),
            "intimacy_change": total_change,
        }
    )

@app.get("/get_intimacy")
async def get_intimacy(req: Request):
    # 獲取目前親密度資訊
    user_id = ensure_user_id_in_session(req.session)
    data = await get_user_data(user_id)
    return JSONResponse(
        {
            "intimacy": data["intimacy"],
            "intimacy_level": get_intimacy_level_name(data["intimacy"]),
        }
    )

@app.post("/update_intimacy")
async def update_intimacy_api(req: Request, payload: IntimacyUpdatePayload):
    # 手動調整親密度的 API
    user_id = ensure_user_id_in_session(req.session)
    intimacy = await adjust_intimacy(user_id, payload.amount)
    return JSONResponse(
        {"intimacy": intimacy, "intimacy_level": get_intimacy_level_name(intimacy)}
    )

@app.post("/clear_session")
async def clear_session(req: Request):
    # 清除短期對話記憶 (Session)
    req.session.pop("chat_history", None)
    return JSONResponse({"message": "已清除對話記憶（短期記憶）"})

@app.post("/clear_memory")
async def clear_memory(req: Request):
    # 清除所有記憶 (Session + 資料庫)
    req.session.pop("chat_history", None)
    user_id = req.session.get("user_id")
    if user_id:
        async with MEMORY_LOCK:
            def _delete():
                with get_db_connection() as conn:
                    c = conn.cursor()
                    c.execute("DELETE FROM user_memory WHERE user_id = ?", (user_id,))
            await _to_thread(_delete)
            logger.info(f"已刪除使用者 {user_id} 的長期記憶")
    return JSONResponse({"message": "已清除使用者的所有記憶（長期 + 短期 )"})

@app.post("/research/start")
async def start_research(req: Request, payload: ResearchPayload, background: BackgroundTasks):
    # 啟動研究任務(返回 job_id)
    try:
        topic = payload.topic.strip()
        if not topic:
            return JSONResponse({"success": False, "error": "請輸入研究主題"}, status_code=400)
        
        user_id = ensure_user_id_in_session(req.session)
        
        # 讀取使用者設定 (API Key 等)
        with get_db_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT tavily_api_key, smart_llm, small_llm FROM user_settings WHERE user_id = ?", (user_id,))
            row = c.fetchone()
        
        tavily_api_key = row["tavily_api_key"] if row and row["tavily_api_key"] else ""
        
        # 檢查本地向量資料庫
        vector_store_root = os.path.join(os.getcwd(), "vector_stores")
        has_local_db = False
        
        if os.path.exists(vector_store_root) and os.path.isdir(vector_store_root):
            safe_topic_prefix = topic.replace("/", "_").replace("\\", "_").strip()
            try:
                for folder_name in os.listdir(vector_store_root):
                    folder_path = os.path.join(vector_store_root, folder_name)
                    if os.path.isdir(folder_path) and folder_name.startswith(safe_topic_prefix):
                        has_local_db = True
                        logger.info(f"[Research] 檢測到本地對應主題的資料庫: {folder_name}")
                        break
            except Exception as e:
                logger.warning(f"[Research] 檢查本地資料庫時發生錯誤: {e}")

        # 若無 Key 且無本地資料庫，則回報錯誤
        if not tavily_api_key and not has_local_db:
            error_msg = f"未偵測到主題「{topic}」的本地知識庫，且未設定 Tavily API Key，無法進行新搜尋。"
            logger.warning(f"[Research] 用戶 {user_id} 請求被阻擋: {error_msg}")
            return JSONResponse({
                "success": False,
                "error": error_msg,
                "type": "missing_config"  
            }, status_code=200)
        
        smart_llm = row["smart_llm"] if row and row["smart_llm"] else "ministral-3:3B"
        small_llm = row["small_llm"] if row and row["small_llm"] else "ministral-3:3B"
        
        job_id = str(uuid.uuid4())
        logger.info(f"[Research] 啟動任務 {job_id}: {topic} (用戶: {user_id})")
        
        from researcher.service import init_progress, run_research
        
        init_progress(job_id, topic, total_items=1)
        background.add_task(run_research, job_id, topic, payload.max_results, user_id, smart_llm, small_llm)
        
        return JSONResponse({"job_id": job_id, "topic": topic})
        
    except Exception as e:
        logger.error(f"[Research] 啟動任務失敗: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/research/progress/{job_id}")
async def get_research_progress(job_id: str):
    # 查詢研究進度
    try:
        from researcher.service import get_progress
        progress = get_progress(job_id)
        return JSONResponse(progress)
    except Exception as e:
        logger.error(f"[Research] 查詢進度失敗: {e}")
        return JSONResponse({"status": "error", "error": str(e)}, status_code=500)

@app.post("/research")
async def research_api_legacy(req: Request, payload: ResearchPayload):
    # 研究報告生成 API(舊版，不推薦使用)
    async with RESEARCH_LOCK:
        try:
            topic = payload.topic.strip()
            if not topic:
                return JSONResponse({"success": False, "error": "請輸入研究主題"}, status_code=400)
            
            user_id = ensure_user_id_in_session(req.session)
            
            with get_db_connection() as conn:
                c = conn.cursor()
                c.execute("SELECT smart_llm, small_llm FROM user_settings WHERE user_id = ?", (user_id,))
                row = c.fetchone()
            
            smart_llm = row["smart_llm"] if row and row["smart_llm"] else "ministral-3:3B"
            small_llm = row["small_llm"] if row and row["small_llm"] else "ministral-3:3B"
            
            logger.info(f"[Research] 開始研究（舊版 API): {topic}")
            
            from researcher.service import run_research
            job_id = str(uuid.uuid4())
            
            result = await _to_thread(run_research, job_id, topic, payload.max_results, user_id, smart_llm, small_llm)
            
            return JSONResponse(result)
        except Exception as e:
            logger.error(f"[Research] 研究失敗: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse({"success": False, "error": str(e)}, status_code=500)

@app.get("/api/settings")
async def get_settings(request: Request):
    # 獲取使用者設定
    user_id = request.session.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
        request.session["user_id"] = user_id
    
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT theme, font_size, tavily_api_key, smart_llm, small_llm
            FROM user_settings WHERE user_id = ?
        """, (user_id,))
        row = c.fetchone()
    
    if row:
        return JSONResponse({
            "theme": row["theme"],
            "fontSize": row["font_size"],
            "tavilyApiKey": row["tavily_api_key"] or "",
            "smartLLM": row["smart_llm"],
            "smallLLM": row["small_llm"]
        })
    else:
        return JSONResponse({
            "theme": "dark",
            "fontSize": 16,
            "tavilyApiKey": "",
            "smartLLM": "ministral-3:3B", 
            "smallLLM": "ministral-3:3B"  
        })

@app.post("/api/settings")
async def save_settings(request: Request, settings_data: SettingsUpdateRequest):
    # 儲存使用者設定
    user_id = request.session.get("user_id")
    if not user_id:
        user_id = str(uuid.uuid4())
        request.session["user_id"] = user_id
    
    settings = settings_data.settings
    
    with get_db_connection() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT OR REPLACE INTO user_settings 
            (user_id, theme, font_size, tavily_api_key, smart_llm, small_llm, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            user_id,
            settings.theme,
            settings.fontSize,
            settings.tavilyApiKey,
            settings.smartLLM,
            settings.smallLLM
        ))
    
    logger.info(f"使用者 {user_id} 已更新設定")
    
    return JSONResponse({
        "success": True,
        "message": "設定已儲存"
    })

@app.post("/api/settings/test-api")
async def test_tavily_api(request: Request):
    # 測試 Tavily API Key 是否有效
    try:
        data = await request.json()
        api_key = data.get("apiKey")
        
        if not api_key:
            return JSONResponse({
                "success": False,
                "message": "請提供 API Key"
            }, status_code=400)
        
        if len(api_key) < 20:
            return JSONResponse({
                "success": False,
                "message": "API Key 格式不正確"
            }, status_code=400)
        
        return JSONResponse({
            "success": True,
            "message": "API Key 格式正確"
        })
        
    except Exception as e:
        logger.error(f"測試 API 失敗: {e}")
        return JSONResponse({
            "success": False,
            "message": str(e)
        }, status_code=500)