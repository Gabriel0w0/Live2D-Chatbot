# -*- coding: utf-8 -*-
"""
研究報告生成主程式
功能：
1. 使用 RAG 管道檢索資料
2. 生成報告大綱
3. 為每個子節**並行**生成內容 (ThreadPoolExecutor)
4. 輸出完整報告

版本：v2.1.0
最後更新：2025-12-13
變更：
- 核心：新增 generate_content_concurrently 實現多線程並行內容生成。
- 修正：將所有輔助函數（包括 check_retriever_quality）移到文件頂部，解決 Pylance 警告。
- 修正：main() 函數中硬編碼的模型名稱，改為 ministral-3:3B 以配合專案設定。
- 修復：_process_content_item 和 generate_content_concurrently 引入 threading.Lock 解決並行時的進度更新問題。
"""

from rag_pipeline import RAGPipeline
from langchain_ollama import ChatOllama
import researcher.parsers as parsers
from datetime import datetime
import re
import concurrent.futures 
import html
import threading # [確保] 引入 threading 庫
from typing import Any, List, Tuple, Optional, Callable, Dict, Union

# ========================================
# 參數 
# ========================================

# 模型溫度
OUTLINE_TEMPERATURE = 0.15 
CONTENT_TEMPERATURE = 0.3   

# 內容生成長度
CONTENT_LENGTH_NORMAL = 2048
CONTENT_LENGTH_NESTED = 1024

# 重複檢測閾值
DUPLICATE_CHECK_LENGTH = 100       
DUPLICATE_THRESHOLD = 2            
DUPLICATE_RECENT_WINDOW = 5000     

# 資料充足性閾值
MIN_CONTEXT_LENGTH = 30            
FORCE_GENERATION_THRESHOLD = 500   

# Tavily 搜尋結果數量
MAX_RESULTS = 20

# ========================================
# 預編譯正則 / 共用設定 
# ========================================

# enhance_search_query 用的常見引導詞 / 冗餘文字
REMOVE_PATTERNS = [
    re.compile(r'本章將.*?介紹'),
    re.compile(r'將詳細介紹'),
    re.compile(r'本研究旨在'),
    re.compile(r'以期.*'),
    re.compile(r'包括.*'),
    re.compile(r'涉及.*'),
    re.compile(r'等$'),
]

# ========================================
# 工具函數區塊 
# ========================================

def enhance_search_query(subsection: str, main_topic: str) -> str:
    """改進版查詢增強 - 處理包含冒號和長說明文字的子節標題"""
    if ":" in subsection or "：" in subsection:
        title_part = re.split('[：:]', subsection)[0].strip()
    else:
        title_part = subsection.strip()
    
    # 步驟 2: 移除常見的引導詞和冗餘文字
    for pattern in REMOVE_PATTERNS:
        title_part = pattern.sub('', title_part)
    
    # 移除常見詞彙
    remove_words = [
        "分析", "討論", "評估", "預測", "說明", "介紹",
        "概述", "研究", "探討", "闡述"
    ]
    
    for word in remove_words:
        if title_part.endswith(word):
            title_part = title_part[:-len(word)]
    
    # 步驟 3: 清理空白字元
    title_part = re.sub(r'\s+', ' ', title_part).strip()
    
    # 步驟 4: 限制長度
    words = title_part.split()
    if len(words) > 5:
        core_keywords = " ".join(words[:5])
    else:
        core_keywords = title_part
    
    if len(core_keywords) > 20:
        core_keywords = core_keywords[:20]
    
    # 步驟 5: 組合主題和關鍵字
    enhanced_query = f"{main_topic} {core_keywords}".strip()
    
    # 步驟 6: 添加領域關鍵字
    domain_keywords = {
        "技術": ["技術", "原理"],
        "發展": ["發展", "歷史"],
        "演進": ["演進", "過程"],
        "歷程": ["歷程", "階段"],
        "創新": ["創新", "突破"],
        "影響": ["影響", "作用"],
        "應用": ["應用", "使用"],
        "商業": ["商業", "市場"],
        "文化": ["文化", "現象"],
        "社會": ["社會", "效應"],
        "未來": ["未來", "趨勢"],
        "問題": ["問題", "挑戰"],
    }
    
    for keyword, additions in domain_keywords.items():
        if keyword in core_keywords:
            enhanced_query += f" {additions[0]}"
            break
    
    # 步驟 7: 最終長度限制
    if len(enhanced_query) > 50:
        enhanced_query = enhanced_query[:50].strip()
    
    return enhanced_query

def is_duplicate_content(new_content: str, existing_content: str, 
                        check_length: int = DUPLICATE_CHECK_LENGTH,
                        threshold: int = DUPLICATE_THRESHOLD) -> bool:
    """檢查內容是否重複"""
    new_clean = new_content.strip()[:check_length]
    if len(new_clean) < 20:
        return False
    recent_content = existing_content[-DUPLICATE_RECENT_WINDOW:]
    count = recent_content.count(new_clean)
    if count >= threshold:
        print(f"[WARN] 檢測到重複內容（出現 {count} 次）: {new_clean[:30]}...")
        return True
    return False

def is_content_sufficient(content: str, min_length: int = MIN_CONTEXT_LENGTH) -> bool:
    """檢查內容是否充足"""
    if not content or len(content.strip()) < min_length:
        return False
    
    insufficient_keywords = [
        "資料不足，無法針對此主題提供詳細說明",
        "資料不足，無法提供內容",
        "資料中沒有提到",
        "無法取得內容"
    ]
    
    for keyword in insufficient_keywords:
        if content.strip() == keyword or content.strip() == f"[{keyword}]":
            return False
    return True

def safe_retriever_invoke(retriever: Any, query: str):
    """安全呼叫 retriever.invoke"""
    try:
        return retriever.invoke(query)
    except Exception as e:
        print(f"[ERROR] 檢索失敗（query={query[:50]}...）: {e}")
        return []

def get_content_llm(model_name: str, is_nested: bool = False, 
                   temperature: float = CONTENT_TEMPERATURE,
                   timeout: int = 300) -> ChatOllama:
    """根據巢狀層級返回不同配置的 LLM"""
    num_predict = CONTENT_LENGTH_NESTED if is_nested else CONTENT_LENGTH_NORMAL
    return ChatOllama(
        model=model_name,
        temperature=temperature,
        num_predict=num_predict,
        timeout=timeout,
        num_ctx=8192
    )

def print_section_header(title: str):
    """打印區塊標題"""
    print("\n" + "="*60)
    print(f"  {title}")
    print("="*60)

def normalize_markdown_headings(text: str, expected_level: str = "") -> str:
    """
    清洗內容：移除所有 Markdown 標題 (#)，只保留內文。
    """
    lines = text.splitlines()
    fixed = []
    
    for line in lines:
        stripped = line.lstrip()
        # 如果是標題行 (# 開頭)，直接忽略，只保留純文字內容
        if stripped.startswith("#"):
            continue 
        else:
            fixed.append(line)

    return "\n".join(fixed).strip()

def save_report(topic: str, content: str, outline: list, 
                success_items: int, total_items: int) -> Optional[str]:
    """儲存報告到檔案"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        output_filename = f"report_{topic}_{timestamp}.txt"
        success_rate = (success_items / total_items * 100) if total_items > 0 else 0
        
        with open(output_filename, "w", encoding="utf-8") as f:
            f.write(f"主題：{topic}\n")
            f.write("=" * 60 + "\n")
            f.write(f"生成時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"成功率：{success_rate:.1f}% ({success_items}/{total_items})\n")
            f.write(f"總字數：{len(content)} 字元\n")
            f.write("=" * 60 + "\n\n")
            
            f.write("【報告大綱】\n\n")
            for section in outline:
                f.write(f"{section['title']}\n")
                for sub in section['subpoints']:
                    if isinstance(sub, str):
                        f.write(f"  - {sub}\n")
                    elif isinstance(sub, dict):
                        f.write(f"  • {sub['title']}\n")
                        for sub_sub in sub['subpoints']:
                            f.write(f"    - {sub_sub}\n")
            
            f.write("\n" + "=" * 60 + "\n\n")
            f.write("【報告內容】\n\n")
            f.write(content)
        
        print(f"\n[INFO] ✅ 報告已成功儲存至 {output_filename}")
        print(f"[INFO] 總字數: {len(content)} 字元")
        print(f"[INFO] 成功率: {success_rate:.1f}%")
        return output_filename
        
    except Exception as e:
        print(f"[ERROR] ❌ 儲存檔案失敗: {e}")
        return None


def check_retriever_quality(retriever: Any, topic: str):
    """檢查檢索器品質"""
    print_section_header("檢查搜尋結果品質")
    
    test_queries = [
        topic,
        f"{topic} 技術",
        f"{topic} 歷史",
        f"{topic} 影響",
        f"{topic} 應用"
    ]
    
    total_docs = 0
    total_length = 0
    
    for query in test_queries:
        try:
            docs = safe_retriever_invoke(retriever, query)
            query_length = sum(len(doc.page_content) for doc in docs)
            total_docs += len(docs)
            total_length += query_length
            
            print(f"\n測試查詢: {query}")
            print(f"  找到文檔數: {len(docs)}")
            
            if docs and len(docs) > 0:
                preview = docs[0].page_content[:100].replace('\n', ' ')
                print(f"  第一筆摘要: {preview}...")
        
        except Exception as e:
            print(f"  ❌ 查詢失敗: {e}")
    
    print(f"\n統計資訊:")
    print(f"  總文檔數: {total_docs}")
    
    if total_docs < 10:
        print(f"\n[WARN] ⚠️ 搜尋結果過少")
    else:
        print(f"\n[INFO] ✅ 搜尋結果充足")

# ========================================
# 內容生成函數
# ========================================

def generate_content_with_fallback(pipeline: RAGPipeline, retriever: Any, 
                                   question: str, topic: str, 
                                   llm: ChatOllama,
                                   is_nested: bool = False,
                                   existing_content: str = "") -> Tuple[str, bool]:
    """
    內容生成函數
    """
    
    # 決定標題層級變數 (Prompt 用)
    heading_level = "####" if is_nested else "###"
    
    try:
        # ========================================
        # 階段 1: 多重檢索策略
        # ========================================
        enhanced_query = enhance_search_query(question, topic)
        
        docs = safe_retriever_invoke(retriever, enhanced_query)
        strategy_used = "增強查詢"
        
        if not docs or len(docs) == 0:
            if ":" in question or "：" in question:
                clean_question = re.split('[：:]', question)[0].strip()
            else:
                clean_question = question.strip()
            docs = safe_retriever_invoke(retriever, clean_question)
            strategy_used = "原始查詢"
        
        if not docs or len(docs) == 0:
            domain_keywords_map = {
                "技術": ["技術", "原理", "方法"],
                "發展": ["發展", "歷史", "演進"],
                "歷程": ["歷程", "過程", "階段"],
                "影響": ["影響", "作用", "效果"],
                "應用": ["應用", "使用", "實例"],
                "商業": ["商業", "市場", "模式"],
                "文化": ["文化", "現象", "意義"],
                "社會": ["社會", "效應", "影響"],
                "未來": ["未來", "趨勢", "展望"],
                "問題": ["問題", "挑戰", "困難"],
            }
            found = False
            for domain, keywords in domain_keywords_map.items():
                if domain in question:
                    for keyword in keywords:
                        fallback_query = f"{topic} {keyword}"
                        docs = safe_retriever_invoke(retriever, fallback_query)
                        if docs and len(docs) > 0:
                            strategy_used = f"領域關鍵字({keyword})"
                            found = True
                            break
                    if found:
                        break
        
        if not docs or len(docs) == 0:
            docs = safe_retriever_invoke(retriever, topic)
            strategy_used = "主題查詢"
        
        # ========================================
        # 階段 2: 檢查檢索結果
        # ========================================
        if not docs or len(docs) == 0:
            return "[資料不足，無法提供內容]", False
        
        context_text = pipeline._docs_to_context(docs)
        context_length = len(context_text)
        
        if context_length < MIN_CONTEXT_LENGTH:
            return "[資料不足，無法提供內容]", False
        
        # ========================================
        # 階段 3: 第一次生成（標準模式）
        # ========================================
        content_result = pipeline.run_content_generation(
            retriever=retriever,
            question=question,
            llm_override=llm,
            heading_level=heading_level 
        )
        
        if not content_result:
            return "[生成失敗]", False

        # 強力清洗邏輯：移除可能殘留的標題行
        lines = content_result.strip().split('\n')
        if lines:
            first_line = lines[0].strip()
            # 如果第一行是 # 開頭，或是包含了問題關鍵字，就移除它
            if first_line.startswith('#') or (len(first_line) < 50 and question in first_line):
                content_result = '\n'.join(lines[1:]).strip()
        
        # ========================================
        # 階段 4: 檢查內容充足性並啟動強制生成
        # ========================================
        if not is_content_sufficient(content_result):
            if context_length > FORCE_GENERATION_THRESHOLD:
                try:
                    content_result = pipeline.run_content_generation_lenient(
                        retriever=retriever,
                        question=question,
                        llm_override=llm,
                        heading_level=heading_level 
                    )
                    
                    if not content_result:
                        return "[資料不足，無法提供詳細說明]", False
                    
                    if not is_content_sufficient(content_result):
                        return "[資料不足，無法提供詳細說明]", False
                    
                except Exception as e:
                    return "[資料不足，無法提供詳細說明]", False
            else:
                return "[資料不足，無法提供詳細說明]", False
        
        # ========================================
        # 階段 5: 內容驗證
        # ========================================
        if is_duplicate_content(content_result, existing_content):
            return "[內容重複，已省略]", False
        
        if not content_result.rstrip().endswith(('。', '！', '？', '」', ')', '）', '.')):
            pass 
        
        return content_result, True
        
    except Exception as e:
        print(f"[ERROR] 生成內容時發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return f"[生成失敗: {e}]", False

# ========================================
# 並行內容生成函數 (核心功能)
# ========================================

def _process_content_item(
    item_tuple: Tuple[RAGPipeline, Any, str, str, str, bool, str, Callable, threading.Lock], 
    processed_count: List[int], 
    total_items: int
) -> Tuple[str, bool, str]:
    """單個內容項目處理函數 (在線程中運行)"""
    
    # 從元組中解包出鎖物件
    pipeline, retriever, question, topic, small_llm_name, is_nested, existing_content, progress_callback, progress_lock = item_tuple
    
    # 1. 執行內容生成 (這是最耗時的部分)
    llm_instance = get_content_llm(small_llm_name, is_nested)
    content_result, success = generate_content_with_fallback(
        pipeline=pipeline,
        retriever=retriever,
        question=question,
        topic=topic,
        llm=llm_instance,
        is_nested=is_nested,
        existing_content=existing_content
    )
    
    # 2. 清洗內容
    content_result = normalize_markdown_headings(content_result)
    
    # 3. 更新進度 (線程安全地更新計數器)
    with progress_lock: 
        processed_count[0] += 1
        current_count = processed_count[0]

    # 4. 回調進度
    progress_callback(
        current_count, 
        "生成內容", 
        f"並行處理 {current_count}/{total_items} 個小節：{question[:30]}..."
    )
    
    # 5. 返回結果 (內容, 成功狀態, 佔位符)
    return content_result, success, "" 

def generate_content_concurrently(
    pipeline: RAGPipeline, 
    retriever: Any, 
    outline: List[Dict], 
    topic: str,
    small_llm_name: str,
    max_concurrency: int,
    progress_callback: Callable[[int, str, str], None],
    progress_lock: threading.Lock # [新增] 接收鎖物件
) -> Dict[str, Any]:
    """
    使用 ThreadPoolExecutor 並行處理所有內容生成任務，並以循序方式組裝結果。
    """
    total_items = sum(
        len(section['subpoints']) +
        sum(len(sub.get('subpoints', [])) if isinstance(sub, dict) else 0
            for sub in section['subpoints'])
        for section in outline
    )
    
    # 1. 準備任務列表
    processed_count = [0]
    cumulative_content = "" 
    full_html_content = ""
    failed_items = 0
    
    # 2. 創建 ThreadPoolExecutor
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        
        for section_idx, section in enumerate(outline, 1):
            section_title = section.get('title', f'章節 {section_idx}')
            
            # 寫入章節標題 HTML (循序執行)
            full_html_content += f'''
<div class="report-section">
    <h2 class="section-title">
        <span class="section-number">{section_idx}.</span> {html.escape(section_title)}
    </h2>
'''
            sub_futures = []
            
            # 任務提交：將所有子項目提交到執行緒池
            for sub in section['subpoints']:
                
                if isinstance(sub, str):
                    question = sub
                    is_nested = False
                    task_args = (pipeline, retriever, question, topic, small_llm_name, is_nested, cumulative_content, progress_callback, progress_lock)
                    future = executor.submit(_process_content_item, task_args, processed_count, total_items)
                    sub_futures.append({"type": "standard", "question": question, "future": future})
                    
                elif isinstance(sub, dict) and "title" in sub and "subpoints" in sub:
                    
                    for nested in sub["subpoints"]:
                        question = nested
                        is_nested = True
                        task_args = (pipeline, retriever, question, topic, small_llm_name, is_nested, cumulative_content, progress_callback, progress_lock)
                        future = executor.submit(_process_content_item, task_args, processed_count, total_items)
                        sub_futures.append({"type": "nested", "question": question, "future": future, "group_title": sub["title"]})

            # 4. 等待並處理所有子節點的結果 (循序組裝，確保結構順序正確)
            
            is_nested_group_started = False
            for sub_future_item in sub_futures:
                question = sub_future_item["question"]
                future = sub_future_item["future"]
                item_type = sub_future_item["type"]

                try:
                    # 獲取線程執行結果: content_result, success, _ (content_html 為空)
                    content_result, success, _ = future.result() 
                    
                    # 更新 cumulative_content (用於重複檢查)
                    cumulative_content += content_result

                    # 格式化內容
                    cleaned_content = html.escape(content_result).replace('\n', '<br>')
                    
                    if not success:
                        failed_items += 1
                        display_content = '[資料不足，無法生成]'
                    else:
                        display_content = cleaned_content
                        
                    # 5. 組合 HTML (確保順序)
                    
                    if item_type == "standard":
                        full_html_content += f'''
<div class="subsection">
    <h3>{html.escape(question)}</h3>
    <div class="subsection-content"><p>{display_content}</p></div>
</div>
'''
                    elif item_type == "nested":
                        
                        # 處理巢狀群組標題 (只在第一個巢狀項目出現時寫入)
                        if not is_nested_group_started:
                             group_title = sub_future_item["group_title"]
                             full_html_content += f'<div class="nested-section"><h3 class="nested-title">{html.escape(group_title)}</h3>'
                             is_nested_group_started = True
                             
                        full_html_content += f'''
<div class="nested-item">
    <h4>{html.escape(question)}</h4>
    <p>{display_content}</p>
</div>
'''

                except Exception as e:
                    print(f"[ERROR] 並行任務失敗: {e} (問題: {question[:50]}...)")
                    failed_items += 1
                    
                    error_content = '[生成服務失敗]'
                    
                    if item_type == "standard":
                        full_html_content += f'<div class="subsection"><h3>{html.escape(question)}</h3><div class="subsection-content"><p>{error_content}</p></div></div>'
                    elif item_type == "nested":
                        full_html_content += f'<div class="nested-item"><h4>{html.escape(question)}</h4><p>{error_content}</p></div>'

            # 確保巢狀群組閉合
            if is_nested_group_started:
                 full_html_content += '</div>' # 閉合 nested-section
            
            full_html_content += '</div>' # 閉合 report-section

    # 6. 添加頁尾聲明
    # (這個會在 research_service.py 內添加，為避免重複，這裡省略)
    
    return {
        'html_content': full_html_content,
        'processed_items': processed_count[0],
        'failed_items': failed_items,
        'total_items': total_items,
    }

# ========================================
# 主程式 (僅用於本地測試，保持原始的循序生成邏輯)
# ========================================

def main():
    """主程式流程"""
    
    # 1. 配置參數
    topic = "初音未來"
    smart_llm = "ministral-3:3B" 
    small_llm = "ministral-3:3B"
    
    print_section_header("研究報告生成系統 v2.6.2 (本地循序測試)")
    print(f"主題: {topic}")
    
    # 2. 初始化 RAG 管道
    print_section_header("初始化 RAG 管道")
    pipeline = RAGPipeline(
        query=topic,
        model=smart_llm,
        temperature=OUTLINE_TEMPERATURE,
        max_results=12,
        num_predict=-1,
        use_existing_db=True
    )
    
    retriever = pipeline.execute()
    
    if retriever is None:
        print("\n[INFO] 切換到完整搜尋模式...")
        pipeline = RAGPipeline(
            query=topic,
            model=smart_llm,
            temperature=OUTLINE_TEMPERATURE,
            max_results=MAX_RESULTS,  
            num_predict=-1,
            use_existing_db=False
        )
        retriever = pipeline.execute()
        if retriever is None:
            print("[ERROR] ❌ 無法建立向量資料庫")
            exit(1)
    
    check_retriever_quality(retriever, topic)
    
    # 3. 生成報告大綱
    print_section_header("生成報告大綱")
    output = pipeline.generate_structured_outline(retriever, topic)['result']
    outline = parsers.extract(response_output=output)
    
    if not outline:
        print("[ERROR] ❌ 大綱生成失敗")
        exit(1)
    
    print("\n[INFO] ✅ 大綱生成成功")
    
    # 4. 統計項目數量
    total_items = sum(
        len(section['subpoints']) +
        sum(len(sub.get('subpoints', [])) if isinstance(sub, dict) else 0
            for sub in section['subpoints'])
        for section in outline
    )
    print(f"\n[INFO] 共需生成 {total_items} 個項目的內容")
    
    # 5. 生成報告內容 (循序執行)
    print_section_header("生成報告內容")
    
    content = f"# {topic}\n\n"
    current_item = 0
    failed_items = 0
    
    for section_idx, section in enumerate(outline, 1):
        print(f"\n[INFO] 處理第 {section_idx}/{len(outline)} 章: {section['title']}")
        
        # 由 Python 寫入章節標題 (H2)
        section_title = f"## {section['title']}"
        content += f"{section_title}\n\n"
        
        for sub in section['subpoints']:
            if isinstance(sub, str):
                # ========== 標準項目 (Level 3) ==========
                current_item += 1
                print(f"\n[INFO] [{current_item}/{total_items}] 生成標準項目: {sub[:30]}...")
                
                # 先寫入標題 (H3)
                content += f"### {sub}\n\n"
                
                content_result, success = generate_content_with_fallback(
                    pipeline=pipeline,
                    retriever=retriever,
                    question=sub,
                    topic=topic,
                    llm=get_content_llm(small_llm, is_nested=False),
                    is_nested=False,
                    existing_content=content
                )
                
                if success:
                    # 僅清洗內容（移除 LLM 可能重複輸出的標題）
                    content_result = normalize_markdown_headings(content_result)
                    content += f"{content_result}\n\n"
                else:
                    content += f"[資料不足，無法生成內容]\n\n"
                    failed_items += 1
                    
            elif isinstance(sub, dict) and "title" in sub and "subpoints" in sub:
                # ========== 巢狀項目 (Level 4) ==========
                # 先寫入群組標題 (H3)
                content += f"### {sub['title']}\n\n"
                
                for nested in sub["subpoints"]:
                    current_item += 1
                    print(f"\n[INFO] [{current_item}/{total_items}] 生成巢狀項目: {nested[:30]}...")
                    
                    # 先寫入子項目標題 (H4)
                    content += f"#### {nested}\n\n"
                    
                    content_result, success = generate_content_with_fallback(
                        pipeline=pipeline,
                        retriever=retriever,
                        question=nested,
                        topic=topic,
                        llm=get_content_llm(small_llm, is_nested=True),
                        is_nested=True,
                        existing_content=content
                    )
                    
                    if success:
                        # 僅清洗內容
                        content_result = normalize_markdown_headings(content_result)
                        content += f"{content_result}\n\n"
                    else:
                        content += f"[資料不足，無法生成內容]\n\n"
                        failed_items += 1

    # 頁尾聲明
    content += "\n\n本報告由 月讀醬的研究室 自動生成，可能會有錯誤，請查證內容"    
    
    # 6. 顯示結果
    print_section_header("報告內容預覽")
    print(content[:500] + "...\n(下略)")
    
    # 7. 統計與儲存
    print_section_header("生成統計")
    success_items = total_items - failed_items
    success_rate = (success_items / total_items * 100) if total_items > 0 else 0
    
    print(f"總項目數: {total_items}")
    print(f"成功項目: {success_items}")
    print(f"失敗項目: {failed_items}")
    print(f"成功率: {success_rate:.1f}%")
    print(f"總字數: {len(content)} 字元")
    
    output_file = save_report(topic, content, outline, success_items, total_items)
    if output_file:
        print_section_header("完成")
        print(f"✅ 報告已成功生成: {output_file}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] 使用者中斷程式執行")
        exit(0)
    except Exception as e:
        print(f"\n[ERROR] ❌ 程式執行發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        exit(1)