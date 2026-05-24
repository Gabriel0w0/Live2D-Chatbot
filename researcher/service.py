# -*- coding: utf-8 -*-
import sys, os, re, logging, threading, sqlite3, html
from datetime import datetime
from typing import Dict, Any, Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
researcher_dir = os.path.join(current_dir, 'researcher')
if researcher_dir not in sys.path:
    sys.path.insert(0, researcher_dir)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

logger = logging.getLogger("research_service")

# ==================== 設定管理 ====================

from config import DB_FILE, CHAT_MODEL, MAX_RAG_CONCURRENCY  # 匯入 CHAT_MODEL 和 MAX_RAG_CONCURRENCY

def get_user_settings(user_id: str = "default") -> Dict[str, Any]:
    """從資料庫讀取用戶設定 (同步模式)"""
    try:
        # 設定 timeout 避免資料庫鎖死
        conn = sqlite3.connect(DB_FILE, timeout=10.0)
        c = conn.cursor()
        c.execute("""
            SELECT tavily_api_key, smart_llm, small_llm
            FROM user_settings 
            WHERE user_id = ?
        """, (user_id,))
        row = c.fetchone()
        conn.close()
        
        default_llm = CHAT_MODEL or "gemma3:4b"

        if row:
            return {
                "tavilyApiKey": row[0] or "",
                "smartLLM": row[1] or default_llm,
                "smallLLM": row[2] or default_llm
            }
        else:
            logger.warning(f"[Settings] 用戶 {user_id} 無設定，使用預設值")
            return {
                "tavilyApiKey": "",
                "smartLLM": default_llm,
                "smallLLM": default_llm
            }
    except Exception as e:
        logger.error(f"[Settings] 讀取設定失敗: {e}")
        # 在異常情況下，提供一個安全的預設值
        safe_default = CHAT_MODEL or "gemma3:4b"
        return {
            "tavilyApiKey": "",
            "smartLLM": safe_default,
            "smallLLM": safe_default
        }

# ==================== 進度追蹤系統 ====================

PROGRESS: Dict[str, Dict[str, Any]] = {}
PROGRESS_LOCK = threading.Lock() # 定義用於多線程的鎖

def init_progress(job_id: str, topic: str, total_items: int = 1):
    """初始化進度追蹤"""
    with PROGRESS_LOCK:
        PROGRESS[job_id] = {
            "topic": topic,
            "status": "running",
            "current": 0,
            "total": max(total_items, 1),
            "phase": "初始化",
            "message": "開始建立研究大綱...",
            "result_html": None,
            "error": None,
            "started_at": datetime.now().isoformat(),
        }
    logger.info(f"[Progress] 初始化任務 {job_id}: {topic}")

def update_progress(job_id: str, **kwargs):
    """更新進度（支援任意欄位）"""
    with PROGRESS_LOCK:
        if job_id in PROGRESS:
            PROGRESS[job_id].update(kwargs)
            # 記錄關鍵更新
            if "current" in kwargs or "phase" in kwargs:
                current = PROGRESS[job_id].get("current", 0)
                total = PROGRESS[job_id].get("total", 1)
                phase = PROGRESS[job_id].get("phase", "")
                logger.debug(f"[Progress] {job_id}: {current}/{total} - {phase}")

def get_progress(job_id: str) -> Dict[str, Any]:
    """查詢進度"""
    with PROGRESS_LOCK:
        return PROGRESS.get(job_id, {"status": "not_found"}).copy()

def cleanup_progress(job_id: str, delay_seconds: int = 300):
    """延遲清理進度"""
    def _cleanup():
        import time
        time.sleep(delay_seconds)
        with PROGRESS_LOCK:
            if job_id in PROGRESS:
                del PROGRESS[job_id]
                logger.info(f"[Progress] 已清理任務 {job_id}")
    
    import threading
    threading.Thread(target=_cleanup, daemon=True).start()

# ==================== 主要研究函數 ====================

def run_research(
    job_id: str, 
    topic: str, 
    max_results: int = 20,
    user_id: str = "default",
    smart_llm: str = None,  
    small_llm: str = None,   
    max_concurrency: int = None 
) -> Dict[str, Any]:
    """執行研究並返回結果"""
    try:
        # 讀取 Tavily API Key 和 LLM 預設值
        settings = get_user_settings(user_id)
        
        tavily_api_key = settings.get("tavilyApiKey", "")
        
        # 優先使用 app.py 傳入的參數 (已讀取最新的使用者設定)
        default_llm_fallback = CHAT_MODEL or "gemma3:4b" 
        smart_llm = smart_llm or settings.get("smartLLM", default_llm_fallback)
        small_llm = small_llm or settings.get("smallLLM", default_llm_fallback)
        
        # 設置並行數
        max_concurrency = max_concurrency or MAX_RAG_CONCURRENCY
        
        logger.info(f"[Research] 使用設定: Smart LLM={smart_llm}, Small LLM={small_llm}, Concurrency={max_concurrency}")
        
        if not tavily_api_key:
             logger.warning("[Research] ⚠️ 未設定 Tavily API Key，將嘗試僅使用本地向量資料庫")
        # 從 researcher 子目錄匯入
        from researcher.rag_pipeline import RAGPipeline
        from researcher import parsers
        from researcher.research import (
            generate_content_concurrently, 
            get_content_llm,
            OUTLINE_TEMPERATURE,
            CONTENT_TEMPERATURE,
            normalize_markdown_headings 
        )
        
        # ========== 1. 初始化 RAG 管道 ==========

        update_progress(job_id, phase="初始化", message="正在連接向量資料庫...")
        logger.info(f"[Research] 初始化 RAG 管道...")
        
        # 嘗試使用現有資料庫
        pipeline = RAGPipeline(
            query=topic,
            model=smart_llm,  
            temperature=OUTLINE_TEMPERATURE,
            max_results=max_results,
            num_predict=-1,
            use_existing_db=True, # 先嘗試讀取本地
            tavily_api_key=tavily_api_key
        )
        
        retriever = pipeline.execute()
        
        # 如果本地資料庫無法使用 (retriever is None)
        if retriever is None:
            # 如果這時也沒有 API Key，那就真的無法進行了
            if not tavily_api_key:
                msg = "無法建立研究報告：未設定 Tavily API Key 且無可用的本地資料庫。"
                logger.error(f"[Research] ❌ {msg}")
                update_progress(
                    job_id, status="failed", phase="錯誤",
                    message=msg,
                    error="尚未設定 Tavily API Key 且 無可用的本地向量資料庫"
                )
                return {"success": False, "error": msg}

            # 如果有 Key，才嘗試聯網重建資料庫
            logger.info(f"[Research] 本地資料庫不存在，嘗試聯網建立...")
            update_progress(job_id, message="資料庫不存在，正在聯網建立...")
            
            pipeline = RAGPipeline(
                query=topic,
                model=smart_llm, 
                temperature=OUTLINE_TEMPERATURE,
                max_results=max_results,
                num_predict=-1,
                use_existing_db=False, # 強制重建
                tavily_api_key=tavily_api_key
            )
            
            retriever = pipeline.execute()
            
            if retriever is None:
                update_progress(
                    job_id, status="failed", phase="錯誤",
                    message="無法建立向量資料庫 (搜尋失敗或 API 錯誤)", error="RAG Init Failed"
                )
                return {"success": False, "error": "無法建立向量資料庫"}
        
        # ========== 2. 生成大綱 ==========

        update_progress(job_id, phase="生成大綱", message="正在規劃報告結構...")
        logger.info(f"[Research] 開始生成大綱...")
        
        output = pipeline.generate_structured_outline(retriever, topic)['result']
        outline = parsers.extract(response_output=output)
        
        if not outline:
            update_progress(
                job_id, status="failed", phase="錯誤",
                message="大綱生成失敗：LLM 輸出格式無法解析", error="大綱生成失敗"
            )
            return {"success": False, "error": "大綱生成失敗"}
        
        logger.info(f"[Research] ✅ 大綱解析成功，共 {len(outline)} 個章節")
        
        # ========== 3. 計算總項目數 (保持不變) ==========

        total_items = sum(
            len(section['subpoints']) +
            sum(len(sub.get('subpoints', [])) if isinstance(sub, dict) else 0
                for sub in section['subpoints'])
            for section in outline
        )
        
        update_progress(
            job_id, total=total_items, phase="生成內容",
            message=f"共 {total_items} 個小節，開始並行生成 (Concurrency={max_concurrency})..."
        )
        
        # ========== 4. 生成內容 ==========
        
        # 使用並行生成函數替換原有的循序迴圈，並傳遞 PROGRESS_LOCK
        results = generate_content_concurrently(
            pipeline=pipeline, 
            retriever=retriever, 
            outline=outline, 
            topic=topic,
            small_llm_name=small_llm, 
            max_concurrency=max_concurrency,
            progress_callback=lambda current_count, phase, message: update_progress(
                job_id, current=current_count, phase=phase, message=message
            ),
            progress_lock=PROGRESS_LOCK # 傳遞線程鎖
        )
        
        # 接收並行生成後的結果
        html_content = results['html_content']
        processed_items = results['processed_items']
        failed_items = results['failed_items']
        total_items = results['total_items'] 

        # ========== 5. 完成 ==========

        success_items = total_items - failed_items
        success_rate = (success_items / total_items * 100) if total_items > 0 else 0

        logger.info(f"[Research] ✅ 研究完成！成功率: {success_rate:.1f}%")

        update_progress(
            job_id,
            status="completed",
            current=total_items,
            phase="完成",
            message=f"✅ 已完成 {success_items}/{total_items} 個小節",
            result_html=html_content,
            stats={
                "successRate": f"{success_rate:.1f}%",
                "successItems": success_items,
                "totalItems": total_items,
                "wordCount": len(html_content)
            }
        )

        return {"success": True, "html": html_content}
        
    except Exception as e:
        logger.error(f"[Research] ❌ 研究過程發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        
        update_progress(
            job_id, status="failed", phase="錯誤",
            message=f"研究過程發生錯誤: {str(e)}", error=str(e)
        )
        return {"success": False, "error": str(e)}