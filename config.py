import os

# ==================== 系統路徑與檔案設定 ====================
# SQLite 資料庫檔案路徑，用於儲存使用者記憶、親密度與個人設定
DB_FILE = "memory.db"
# TTS (文字轉語音) 生成的音檔存放目錄
AUDIO_DIR = "static/audio"

# ==================== LLM 模型設定 (Ollama) ====================
# 預設使用的聊天模型名稱 (需確保 Ollama 已下載此模型，如 ollama pull gemma3)
CHAT_MODEL = "gemma3"
# 模型的上下文窗口大小 (Token 數)，越大的值可容納越長的對話與 RAG 參考資料
OLLAMA_NUM_CTX = 8192

# ==================== 記憶系統設定 ====================
# 短期記憶：每次對話傳送給 LLM 的「最近對話輪數」 (避免 Prompt 過長)
MAX_MEMORY = 10
# 長期記憶：每個使用者資料庫中最多儲存的「關於使用者的事實」數量
MAX_FACTS_PER_USER = 20

# ==================== RAG 研究報告設定 ====================
# 研究報告生成時的「最大並行執行緒數」，數值越高生成越快，但對 CPU 的負載也越重
MAX_RAG_CONCURRENCY = 4

# ==================== 親密度系統設定 ====================
# 新使用者的初始親密度 (0-100)
DEFAULT_INTIMACY = 50
# 親密度的最大值與最小值限制
MAX_INTIMACY = 100
MIN_INTIMACY = 0
# 親密度更新的平滑係數 (Alpha)
# 用於指數移動平均，數值越小，親密度變化越平緩；數值越大，變化越劇烈
ALPHA = 0.3

# ==================== 語音合成 (TTS) 設定 ====================
# 是否啟用翻譯功能 (True = 將中文回應翻譯成日文後再送給 Voicevox 合成)
TRANSLATE = True
# Voicevox 引擎的 API 位址
# 優先讀取環境變數 "VOICEVOX_URL"，若未設定則預設為 localhost:50021
VOICEVOX_URL = os.getenv("VOICEVOX_URL", "http://localhost:50021")

# ==================== 系統初始化 ====================
# 啟動時自動建立語音目錄 (如果不存在的話)，避免出錯
os.makedirs(AUDIO_DIR, exist_ok=True)
