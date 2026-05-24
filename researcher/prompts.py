# -*- coding: utf-8 -*-
"""
報告生成 Prompt 模板集合

提供多種 Prompt 模板用於 RAG 報告生成系統，包括：
- 大綱生成（結構化/通用）
- 內容生成（標準/嚴格模式）
- 報告編譯
- 圖像描述生成

版本：v2.1.0
最後更新：2025-12-04
變更記錄：
- v2.0: 所有 Prompt 統一添加 {context} 變數
- v2.0.1: 加強防幻覺、增加 Few-shot 範例、精簡指示
- v2.0.2: 修正內容重複問題、最佳化「資料不足」處理邏輯
"""

from langchain_core.prompts import PromptTemplate

class PromptTemps:
    VERSION = "2.1"
    
    def __init__(self):
        pass

    @classmethod
    def get_version(cls):
        """返回當前 Prompt 模板版本"""
        return cls.VERSION

    # ========================================
    # 大綱生成 Prompts
    # ========================================

    @staticmethod
    def get_rag_outline_prompt() -> PromptTemplate:
        """RAG 大綱生成 Prompt
        
        變數: context, question
        """
        return PromptTemplate.from_template(
"""你是專業的報告撰寫助手。請根據背景資料與子節主題，撰寫完整段落內容（繁體中文，符合臺灣用語，語氣正式學術）。

背景資料：
{context}

撰寫主題：
{question}

撰寫規則：
1. 檢查背景資料是否包含與「撰寫主題」相關的具體資訊
2. 如果背景資料「只有基本介紹」而無法回答撰寫主題的具體問題，請「只」輸出：「資料不足，無法針對此主題提供詳細說明。」
3. 如果背景資料包含相關的具體資訊，則撰寫 3-5 句完整段落，內容必須完全基於背景資料
4. 不要在「資料不足」訊息前面加上任何基本介紹或其他內容
5. 直接切入主題核心，避免冗長開場

正確範例（資料充足）：
VOCALOID 技術的核心是基於頻率域歌聲合成（Frequency-domain Singing Articulation Splicing and Shaping），通過錄製真人歌手的聲音樣本，分析音素特徵後建立聲音資料庫。使用者可透過輸入歌詞和音符，系統會自動拼接對應的音素並調整音高、音長等參數。這種技術讓初音未來能夠演唱各種風格的歌曲，音質自然度隨著版本升級持續提升。

錯誤範例（不要這樣寫）：
初音未來是由Crypton Future Media於2007年開發的虛擬歌手軟體，使用Yamaha的VOCALOID技術。她的角色設定為16歲...資料不足。現有資料僅提及...

正確範例（資料不足）：
資料不足，無法針對此主題提供詳細說明。

請開始撰寫："""
        )

    @staticmethod
    def get_outline_prompt() -> PromptTemplate:
        """標準大綱生成 Prompt
        
        變數: context, question
        """
        return PromptTemplate.from_template(
"""你是一位專業的內容規劃師，擅長根據主題與背景資料撰寫結構清晰、格式一致的報告大綱。

背景資料（供參考）：
{context}

主題：{question}

請根據以上主題與背景資料，使用繁體中文(符合臺灣用語習慣)撰寫一份報告大綱，**請使用以下格式並限制章節數量不超過 5 節**:
每個章節請使用阿拉伯數字編號(例如:1.、2.、3.），每個章節下使用 `-` 符號條列子項目。

輸出格式範例如下：
1. 引言
- 本報告的目的
- 主題的重要性
2. 主體分析
- 方法論介紹
- 研究資料來源
3. 結論與建議
- 核心發現摘要
- 未來建議

請保持正式語氣與條列清楚，確保模型輸出格式與上述範例一致，並避免超過 5 個章節。"""
        )
    
    @staticmethod
    def get_langgraph_outline_prompt() -> PromptTemplate:
        """結構化大綱生成 Prompt（v2.3 - 防止事實錯誤版本）"""
        return PromptTemplate.from_template(
"""你是專業的研究架構設計專家。請根據主題與背景資料，撰寫結構清晰的研究報告大綱（繁體中文，符合臺灣用語）。

背景資料：
{context}

研究主題：{question}

核心規則：
1. 基於背景資料撰寫，不得要求即時資料、特定網站、數據庫或外部檔案
2. 章節標題與撰寫提示中，必須完整使用「{question}」，嚴禁使用「本主題」、「該議題」等代稱
3. 撰寫提示「不要」包含具體的年份、數字、人名等容易出錯的細節
4. 撰寫提示應該是「通用的指導方向」，例如：「說明發展歷程」而非「說明 2010 年以來的發展」
5. 不要向使用者提出問題或要求額外資料

輸出格式（嚴格遵守）：
- 最多 5 個章節，使用阿拉伯數字編號（1. 2. 3.）
- 每章節下用 `-` 條列子項目
- 子項目格式：「子節標題:通用的撰寫指導（不含具體年份/數字）」
- 不得加上前言、結語等多餘文字

✅ 正確範例：
1. 研究背景與動機
- 研究的起因與目的:說明{question}的研究背景及其主要目標。
- 議題的重要性分析:分析{question}在產業或社會層面的重要性與影響。

2. 發展歷程與演進
- 誕生與早期發展:介紹{question}的起源與初期發展階段。
- 技術演進與功能拓展:說明{question}在技術層面的演進過程。

❌ 錯誤範例（不要這樣寫）：
1. 研究背景與動機
- 研究的起因與目的:說明{question}自2010年問世以來的發展...  ← ❌ 包含具體年份
- 市場規模分析:說明{question}在2023年達到10億美元的市場規模...  ← ❌ 包含具體數字

請開始撰寫大綱（直接從第 1 章開始）："""
    )

    # ========================================
    # 內容生成 Prompts
    # ========================================

    @staticmethod
    def get_content_prompt() -> PromptTemplate:
        """標準內容生成 Prompt（v2.3 結構化標題版）
        
        變數: context, question, heading_level
        """
        return PromptTemplate.from_template(
"""你是專業的報告撰寫助理。請根據提供的背景資料與章節標題，撰寫一個結構完整的小節內容。

背景資料：
{context}

章節標題：
{question}

【撰寫與格式規則（必須嚴格遵守）】：
1. 第一行必須是此小節的標題，請直接使用變數 {heading_level} 開頭，例如：
   "{heading_level} {question}"
   （請不要自行決定使用幾個 #，必須完全依照 heading_level 變數）
2. 標題下方請撰寫 2 到 5 個完整、連貫的自然段落說明。
3. 內容必須完全基於背景資料中與章節標題相關的部分。
4. 段落中可以使用一般文字或適度列點（-），但嚴禁再使用任何其他 `#` 標題。
5. 嚴禁輸出與本小節無關的大綱、總結或開場白。
6. 使用繁體中文（符合臺灣用語習慣），語氣正式清楚。

【判斷邏輯】：
- 若背景資料「只有基本介紹」且無法回答具體問題 → 請只輸出一行：「資料不足，無法針對此主題提供詳細說明。」
- 若背景資料充足 → 請依照上述格式撰寫內容。

請開始撰寫："""
        )

    @staticmethod
    def get_content_prompt_strict() -> PromptTemplate:
        """嚴格模式內容生成 Prompt（v2.3 結構化標題版）
        
        變數: context, question, heading_level
        """
        return PromptTemplate.from_template(
"""你是專業的報告撰寫助理。請根據背景資料撰寫段落（繁體中文，符合臺灣用語）。

背景資料：
{context}

章節標題：
{question}

【嚴格格式限制】：
1. 第一行必須是標題：請輸出 "{heading_level} {question}"
2. 標題下方撰寫 2-5 句完整段落，語氣正式。
3. 只能使用背景資料中與章節標題直接相關的資訊。
4. 禁止使用額外的 `#` 標題。

【資料不足時】：
如果背景資料不包含相關資訊，請「只」輸出：「資料不足，無法針對此主題提供詳細說明。」

請開始撰寫："""
        )

    @staticmethod
    def get_content_prompt_lenient() -> PromptTemplate:
        """寬鬆模式內容生成 Prompt（v2.3 結構化標題版）
        
        變數: context, question, heading_level
        """
        return PromptTemplate.from_template(
"""你是專業的報告撰寫助理。請根據背景資料撰寫內容。

背景資料：
{context}

章節標題：
{question}

【撰寫策略與格式】：
1. 第一行強制輸出標題："{heading_level} {question}"
2. 從背景資料中找出與章節標題「相關」的資訊（含間接相關）。
3. 撰寫 3-5 句段落，可包含相關背景、類似案例或推論。
4. 使用繁體中文，語氣正式。
5. 不要使用額外的 Markdown 標題（#）。

只有在背景資料「完全無關」時才回答「資料不足」。

請開始撰寫："""
    )


    # ========================================
    # 報告編譯與圖像生成
    # ========================================

    @staticmethod
    def get_report_compile_prompt() -> PromptTemplate:
        """報告編譯 Prompt
        
        變數: question, img_desc
        """
        return PromptTemplate.from_template(
"""你是專業的報告撰寫專家，擅長將大綱與草稿內容改寫為內容完整、語氣正式且邏輯清晰的繁體中文報告（符合臺灣用語習慣）。

請依據以下提供的章節草稿，改寫並擴充成一篇全新的報告段落，每個章節請撰寫 3 到 5 句完整、連貫的自然段落，不得使用條列式或列點方式呈現。

報告結構：
1. 引言：說明主題背景、研究動機與重要性
2. 主體內容：依章節標題與草稿內容撰寫自然段落，結構清楚、語意通順，段落間銜接順暢
3. 結論：總結報告重點，並提出建議與未來展望

撰寫要求：
- 直接從報告正文開始撰寫，不要使用「以下是」、「這是一篇……」、「本文將會……」等開場白
- 每一章節都必須以自然段落呈現，請勿保留任何「*」或條列符號
- 每個段落應有清楚主題句與支持句，具備完整敘述功能
- 可依上下文邏輯，適度補充與延伸原草稿，增強內容的說明性與專業性
- 使用連接詞或過渡語（例如「首先」、「此外」、「進一步來說」、「總結而言」）以增進段落間的連貫性
- 請避免直接重複草稿句子，而是以原意為基礎進行通順且流暢的改寫
- 如果草稿中出現「資料不足」字樣，請跳過該部分不要撰寫

章節草稿：
{question}

圖片摘要資訊（可酌情納入參考，若無相關性可忽略）：
{img_desc}

請開始撰寫報告："""
        )

    @staticmethod
    def get_image_prompt() -> PromptTemplate:
        """圖像描述生成 Prompt
        
        變數: question
        """
        return PromptTemplate.from_template(
"""你是資料視覺化設計顧問。請根據以下報告大綱內容，設計 1 至 2 張代表性圖片的圖像生成描述（image prompts）。

這些圖像描述將用於圖像生成模型（如 FLUX1）自動繪製報告用圖。每個 prompt 應以英文撰寫，清楚描述圖中應呈現的主題、場景、物體、人物、結構、風格等，避免抽象語言，讓模型能產出具體畫面。

報告大綱：
{question}

輸出格式（嚴格遵守）：
Image 1 Prompt: [具體的英文圖像描述]
Image 2 Prompt: [具體的英文圖像描述]

範例：
Image 1 Prompt: A professional infographic showing the evolution timeline of virtual idol technology, featuring Hatsune Miku character design with teal twin-tails, digital interface elements, and musical notes, modern flat design style, vibrant colors
Image 2 Prompt: A conceptual illustration of AI-powered voice synthesis system, displaying waveforms, vocal parameters, and holographic singing character, futuristic tech aesthetic, blue and cyan color scheme

請開始撰寫圖像描述："""
        )

    # ========================================
    # 驗證與檢查
    # ========================================

    @staticmethod
    def validate_prompt_template(template: PromptTemplate, required_vars: list) -> bool:
        """驗證 Prompt 是否包含必要變數"""
        template_vars = template.input_variables
        missing_vars = [var for var in required_vars if var not in template_vars]
        
        if missing_vars:
            print(f"[WARN] Prompt 缺少必要變數: {missing_vars}")
            return False
        return True

    @classmethod
    def self_check(cls):
        """自我檢查所有 Prompt 的完整性"""
        print(f"[INFO] 執行 Prompt 模板自我檢查 (標準版 v{cls.VERSION})...")
        
        checks = [
            ("get_rag_outline_prompt", ['context', 'question']),
            ("get_outline_prompt", ['context', 'question']),
            ("get_langgraph_outline_prompt", ['context', 'question']),
            # 這裡的三個都加上了 heading_level
            ("get_content_prompt", ['context', 'question', 'heading_level']),
            ("get_content_prompt_strict", ['context', 'question', 'heading_level']),
            ("get_content_prompt_lenient", ['context', 'question', 'heading_level']), # 之前你的 check 少了 lenient，這次補上
            ("get_report_compile_prompt", ['question', 'img_desc']),
            ("get_image_prompt", ['question']),
        ]
        
        all_passed = True
        for method_name, required_vars in checks:
            method = getattr(cls, method_name)
            template = method()
            passed = cls.validate_prompt_template(template, required_vars)
            status = "✅" if passed else "❌"
            print(f"{status} {method_name}: {template.input_variables}")
            if not passed:
                all_passed = False
        
        if all_passed:
            print("[INFO] ✅ 所有 Prompt 檢查通過！")
        else:
            print("[WARN] ⚠️ 部分 Prompt 存在問題，請檢查上方訊息。")
        
        return all_passed

# ========================================
# DoclingPromptTemps (圖片辨識與自訂 QA)
# ========================================

class DoclingPromptTemps:
    """Docling 相關 Prompt 模板
    
    用於圖片辨識和自訂問答功能。
    """
    
    def __init__(self):
        pass

    @staticmethod
    def get_image_prompt() -> str:
        """圖片辨識 Prompt"""
        return (
"""你是圖片辨識模型。請只描述這張圖片的內容。

限制：
- 只描述圖片的內容，不要加入任何多餘的語句或格式
- 不要說明你是誰，也不要做任何猜測
- 以繁體中文回答，使用兩句話內完成

請描述這張圖片的內容，並提供相關的細節和背景資訊。"""
        )
    
    @staticmethod
    def get_custom_qa_prompt() -> PromptTemplate:
        """自訂問答 Prompt"""
        return PromptTemplate.from_template(
            """根據提供的資料段落，請盡可能推論並回答問題。
若資料中無明確記載，請說明資料可能的相關內容。

資料內容：
{context}

問題：
{question}

請提供答案："""
        )

# ========================================
# 測試程式碼
# ========================================

if __name__ == "__main__":
    print("="*60)
    print("Prompt 模板自我檢查")
    print("="*60)
    
    # 執行自我檢查
    result = PromptTemps.self_check()
    
    print("\n" + "="*60)
    print(f"檢查結果: {'✅ 通過' if result else '❌ 失敗'}")
    print(f"當前版本: {PromptTemps.get_version()}")
    print("="*60)
    
    # 測試範例
    if result:
        print("\n[INFO] 測試生成 content prompt...")
        content_prompt = PromptTemps.get_content_prompt()
        print(f"[INFO] 變數: {content_prompt.input_variables}")
        print(f"[INFO] 模板長度: {len(content_prompt.template)} 字元")
        print("\n[INFO] 測試生成 langgraph outline prompt...")
        outline_prompt = PromptTemps.get_langgraph_outline_prompt()
        print(f"[INFO] 變數: {outline_prompt.input_variables}")
        print(f"[INFO] 模板長度: {len(outline_prompt.template)} 字元")      
        print("\n[INFO] ✅ 所有測試完成！")