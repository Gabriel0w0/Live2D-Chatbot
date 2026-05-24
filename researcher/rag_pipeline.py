# -*- coding: utf-8 -*-
from filelock import FileLock
from deep_translator import GoogleTranslator
from researcher.prompts import PromptTemps
from langchain_chroma import Chroma
from langchain_tavily import TavilySearch
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.documents import Document
from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
import os
import re
import hashlib
import jieba  

class RAGPipeline:
    """RAG (Retrieval-Augmented Generation) 管道
    版本: 2.1.0
    新增: 
    - 結構化標題支援 (heading_level)
    - 混合搜尋 (Hybrid Search): Vector Search + BM25
    - 中文分詞支援 (jieba)
    """
    
    def __init__(self, query, model: str, temperature: float,
                 embed_model="embeddinggemma", max_results=5,
                 base_directory="vector_stores", num_predict=-1,
                 use_existing_db=False,
                 tavily_api_key=None,
                 enable_hybrid_search=True):
        """初始化 RAG Pipeline"""
        self.query = query
        self.llm = ChatOllama(
            model=model,
            temperature=temperature,
            num_predict=num_predict
        )
        self.embedder = OllamaEmbeddings(model=embed_model)
        self.max_results = max_results
        self.use_existing_db = use_existing_db
        self.enable_hybrid_search = enable_hybrid_search
        
        # 動態設定 Tavily API Key
        self.tavily_api_key = tavily_api_key
        if self.tavily_api_key:
            os.environ["TAVILY_API_KEY"] = self.tavily_api_key
            print(f"[INFO] 🔑 使用自訂 Tavily API Key")
        elif "TAVILY_API_KEY" not in os.environ:
            print(f"[WARN] ⚠️ 未設定 Tavily API Key，搜尋功能可能無法使用")
            
        # 根據 query 生成專屬資料夾名稱
        self.persist_directory = self._generate_db_path(query, base_directory)
        print(f"[INFO] 📁 向量資料庫路徑: {self.persist_directory}")
        
        self.search_targets = [
            ("tw", "zh-TW"), ("us", "en"), ("uk", "en"),
            ("ca", "en"), ("jp", "ja"), ("kr", "ko")
        ]

    def _generate_db_path(self, query: str, base_dir: str) -> str:
            """根據研究主題生成資料庫路徑 (新增：模糊比對邏輯)"""
            # 1. 清洗檔名 
            clean_query = re.sub(r'[^\w\s\u4e00-\u9fff]', '', query, flags=re.UNICODE)
            clean_query = re.sub(r'\s+', '_', clean_query.strip())
            if len(clean_query) > 50:
                clean_query = clean_query[:50]
                
            # 2. 計算標準 Hash 
            query_hash = hashlib.md5(query.encode('utf-8')).hexdigest()[:8]
            expected_db_name = f"{clean_query}_{query_hash}"
            full_path = os.path.join(base_dir, expected_db_name)

            # 如果是「使用現有資料庫」模式，且「標準路徑不存在」，嘗試找「同名但 Hash 不同」的資料夾
            if self.use_existing_db and not os.path.exists(full_path) and os.path.exists(base_dir):
                # 遍歷目錄找「開頭名稱符合」的資料夾
                candidates = []
                safe_prefix = clean_query + "_" # 例如 "初音未來_"
                
                for folder_name in os.listdir(base_dir):
                    if folder_name.startswith(safe_prefix):
                        candidates.append(folder_name)
                
                # 如果找到候選者，直接使用第一個找到的 
                if candidates:
                    fuzzy_path = os.path.join(base_dir, candidates[0])
                    print(f"[INFO] 模糊比對成功！轉向使用現有資料庫: {candidates[0]}")
                    return fuzzy_path
                
            return full_path

    def load_existing_vectorstore(self):  
        """載入現存的向量資料庫"""
        sqlite_path = os.path.join(self.persist_directory, "chroma.sqlite3")
        
        if not os.path.exists(sqlite_path):
            print(f"[WARN] 向量資料庫不存在: {self.persist_directory}")
            print(f"[HINT] 將建立新的資料庫")
            return None
        
        if os.path.getsize(sqlite_path) < 1024:
            print(f"[ERROR] 資料庫檔案損壞或為空")
            return None
        
        try:
            print(f"[INFO] 載入現存向量資料庫: {self.persist_directory}")
            vectorstore = Chroma(
                persist_directory=self.persist_directory, 
                embedding_function=self.embedder
            )
            
            try:
                existing_docs = vectorstore.get()['documents']
                doc_count = len(existing_docs)
                
                if doc_count == 0:
                    print(f"[WARN] 資料庫為空，建議重新搜尋")
                    return None
                
                print(f"[INFO] ✅ 成功載入 {doc_count} 筆文檔")
                return vectorstore
                
            except Exception as e:
                print(f"[WARN] 無法驗證資料庫內容: {e}")
                return vectorstore
                
        except Exception as e:
            print(f"[ERROR] 載入失敗: {e}")
            return None

    def retrieve_context(self):
        """使用 Tavily 搜尋多國資料"""
        print("[INFO] 使用 Tavily 搜尋多國資料中...")
        all_results = []
        lang_map = {"zh-TW": "zh", "en": "en", "ja": "ja", "ko": "ko"}
        
        for country, lang in self.search_targets:
            lang_code = lang_map.get(lang, "en")
            print(f"[INFO] - 搜尋 {country.upper()} (語言: {lang_code}) ...")
            items = self.tavily_search(self.query, max_results=self.max_results, language=lang_code)
            print(f"[INFO]   -> {country.upper()} 搜尋結果數: {len(items)}")
            all_results.extend(items)
        
        if not all_results:
            print("[WARN] 各國皆無結果，嘗試翻譯 query 為英文再搜尋...")
            try:
                query_en = GoogleTranslator(source='auto', target='en').translate(self.query)
            except Exception:
                query_en = self.query
            all_results = self.tavily_search(query_en, max_results=self.max_results, language="en")
            print(f"[INFO] 翻譯後搜尋結果數: {len(all_results)}")
        
        print(f"[INFO] 共獲得 {len(all_results)} 筆搜尋結果。")
        
        if len(all_results) < 5:
            print(f"[WARN] 搜尋結果較少（{len(all_results)} 筆），可能影響生成品質")
        
        return "\n\n".join([str(item) for item in all_results])

    def tavily_search(self, query, max_results=5, language="en"):
        """執行 Tavily 搜尋"""
        try:
            search = TavilySearch(max_results=max_results, language=language)
            result = search.run(query)
            
            if isinstance(result, dict) and "results" in result:
                return result["results"]
            elif isinstance(result, list):
                return result
            else:
                return [result] if result else []
        except Exception as e:
            print(f"[ERROR] Tavily 搜尋失敗: {e}")
            return []

    def split_chunks(self, text, chunk_size=500, chunk_overlap=50):
        """將長文本切割成小區塊"""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap
        )
        return splitter.split_text(text)

    def build_vectorstore(self, chunks):
        """建立或更新向量資料庫"""
        def hash_text(text):
            return hashlib.md5(text.encode('utf-8')).hexdigest()
        
        lock_path = os.path.join(self.persist_directory, "chroma.lock")
        os.makedirs(self.persist_directory, exist_ok=True)
        
        with FileLock(lock_path, timeout=10):
            parquet_path = os.path.join(self.persist_directory, "chroma-collections.parquet")
            
            if os.path.exists(parquet_path):
                print("[INFO] 向量資料庫已存在，執行內容追加與去重比對...")
                vectorstore = Chroma(
                    persist_directory=self.persist_directory,
                    embedding_function=self.embedder
                )
                
                try:
                    existing_docs = vectorstore.get()['documents']
                    existing_hashes = set(hash_text(doc) for doc in existing_docs)
                    
                    new_chunks = [chunk for chunk in chunks if hash_text(chunk) not in existing_hashes]
                    print(f"[INFO] 篩選後將新增 {len(new_chunks)} 筆內容")
                    
                    if new_chunks:
                        vectorstore.add_texts(new_chunks)
                    else:
                        print("[INFO] 無新內容需要追加")
                except Exception as e:
                    print(f"[WARN] 讀取現有資料庫失敗，重新建立: {e}")
                    vectorstore = Chroma.from_texts(
                        texts=chunks,
                        embedding=self.embedder,
                        persist_directory=self.persist_directory
                    )
            else:
                print("[INFO] 建立新的向量資料庫")
                vectorstore = Chroma.from_texts(
                    texts=chunks,
                    embedding=self.embedder,
                    persist_directory=self.persist_directory
                )
        
        return vectorstore

    def _chinese_tokenizer(self, text: str):
        """中文分詞器（用於 BM25）"""
        return list(jieba.cut(text))

    def _build_hybrid_retriever(self, vectorstore):
        """建立混合檢索器 (Vector + BM25)"""
        try:
            print("[INFO] ⚡ 初始化混合搜尋 (Hybrid Search: Vector + BM25)...")
            
            # 1. 建立向量檢索器
            vector_retriever = vectorstore.as_retriever(
                search_kwargs={"k": self.max_results}
            )
            
            # 2. 從向量資料庫提取所有文檔來建立 BM25 索引
            all_docs_content = vectorstore.get()['documents']
            
            if not all_docs_content or len(all_docs_content) == 0:
                print("[WARN] 資料庫為空，無法建立 BM25，降級為純向量搜尋")
                return vector_retriever
            
            # 轉換為 Document 物件列表
            doc_objects = [Document(page_content=txt) for txt in all_docs_content]
            print(f"[INFO] BM25 索引文檔數: {len(doc_objects)}")
            
            # 3. 建立 BM25 檢索器（使用中文分詞）
            bm25_retriever = BM25Retriever.from_documents(
                doc_objects,
                preprocess_func=self._chinese_tokenizer  # 中文分詞
            )
            bm25_retriever.k = self.max_results
            
            # 4. 組合成 Ensemble Retriever
            # weights: [BM25權重, Vector權重]
            ensemble_retriever = EnsembleRetriever(
                retrievers=[bm25_retriever, vector_retriever],
                weights=[0.4, 0.6]  # 可調整：BM25=40%, Vector=60%
            )
            
            print("[INFO] ✅ 混合檢索器準備完成 (BM25: 40% | Vector: 60%)")
            return ensemble_retriever
            
        except Exception as e:
            print(f"[ERROR] 建立混合檢索器失敗，降級為純向量搜尋: {e}")
            import traceback
            traceback.print_exc()
            return vectorstore.as_retriever(search_kwargs={"k": self.max_results})

    def _docs_to_context(self, docs):
        """將 retriever 返回的文檔轉換為上下文字串"""
        return "\n\n".join([
            doc.page_content if hasattr(doc, 'page_content') else str(doc)
            for doc in docs
        ])

    def _create_rag_chain(self, retriever, custom_prompt=None):
        """建立標準 RAG 鏈"""
        default_prompt = ChatPromptTemplate.from_template(
            "根據以下上下文回答問題。如果無法從上下文判斷，請說明「資訊不足」\n\n"
            "上下文:\n{context}\n\n問題: {question}\n回答:"
        )
        prompt = custom_prompt or default_prompt
        chain = prompt | self.llm | StrOutputParser()
        return chain

    def run_qa(self, retriever, question):
        """單次問答"""
        chain = self._create_rag_chain(retriever)
        docs = retriever.invoke(question)
        context = self._docs_to_context(docs)
        return chain.invoke({"context": context, "question": question})

    def generate_outline_with_sources(self, retriever, topic_prompt):
        """生成大綱並保留來源"""
        chain = self._create_rag_chain(retriever)
        docs = retriever.invoke(topic_prompt)
        context = self._docs_to_context(docs)
        return chain.invoke({"context": context, "question": topic_prompt})

    def generate_structured_outline(self, retriever, topic: str):
        """生成結構化大綱"""
        try:
            prompt_obj = PromptTemps.get_langgraph_outline_prompt()
            outline_prompt = ChatPromptTemplate.from_messages([
                ("system", "你是專業的內容規劃師。"),
                ("user", prompt_obj.template)
            ])
        except Exception as e:
            print(f"[WARN] 無法載入自訂 prompt，使用預設模板: {e}")
            outline_prompt = ChatPromptTemplate.from_template(
                "請為以下主題生成結構化大綱，使用 markdown 格式，包含主要章節和小節：\n"
                "背景資料:\n{context}\n\n主題: {question}\n\n請提供詳細的目錄結構："
            )
        
        chain = outline_prompt | self.llm | StrOutputParser()
        docs = retriever.invoke(topic)
        context = self._docs_to_context(docs)
        
        return {"result": chain.invoke({"context": context, "question": topic})}

    def execute(self):
        """完整 RAG 管道執行（支援混合搜尋）"""
        vectorstore = None
        
        # ========== 階段 1: 載入或建立向量資料庫 ==========
        if self.use_existing_db:
            print("[INFO] 🚀 使用現存資料庫模式（略過搜尋）")
            vectorstore = self.load_existing_vectorstore()
            if vectorstore is None:
                print("[WARN] ⚠️ 無法載入現存資料庫，將執行完整搜尋")
                self.use_existing_db = False
        
        if vectorstore is None:
            print("[INFO] 🔍 完整搜尋模式")
            context = self.retrieve_context()
            chunks = self.split_chunks(context)
            print(f"[INFO] 分段數量: {len(chunks)}")
            
            if len(chunks) == 0:
                print("[ERROR] ❌ 無有效文本可建立資料庫")
                return None
            
            vectorstore = self.build_vectorstore(chunks)
        
        # ========== 階段 2: 建立檢索器（混合 or 純向量）==========
        if self.enable_hybrid_search:
            retriever = self._build_hybrid_retriever(vectorstore)
        else:
            print("[INFO] 使用純向量搜尋模式")
            retriever = vectorstore.as_retriever(
                search_kwargs={"k": self.max_results}
            )
        
        print("[INFO] ✅ 檢索器準備完成，可用於問答或大綱生成。")
        return retriever

    def run_content_generation(self, retriever, question: str, llm_override=None, use_strict_mode=False, heading_level="###"):
        """內容生成（報告段落） - 支援結構化標題"""
        try:
            if use_strict_mode:
                prompt_obj = PromptTemps.get_content_prompt_strict()
                print("[DEBUG] 使用嚴格模式 Prompt（避免幻覺）")
            else:
                prompt_obj = PromptTemps.get_content_prompt()
            
            content_prompt = ChatPromptTemplate.from_messages([
                ("system", "你是專業的報告撰寫助手。"),
                ("user", prompt_obj.template)
            ])
        except Exception as e:
            print(f"[WARN] 無法載入內容生成 prompt: {e}")
            content_prompt = ChatPromptTemplate.from_template(
                "請根據上下文撰寫 3 到 5 句完整、連貫的段落說明。\n"
                "背景資料:\n{context}\n\n章節標題: {question}\n\n"
                "請直接輸出純段落內容，不要加上任何標題或格式："
            )
        
        qa_chain = content_prompt | (llm_override or self.llm) | StrOutputParser()
        docs = retriever.invoke(question)
        context = self._docs_to_context(docs)
        
        # 傳入 heading_level 變數
        return qa_chain.invoke({
            "context": context,
            "question": question,
            "heading_level": heading_level
        })

    def run_content_generation_lenient(self, retriever, question: str, llm_override=None, heading_level="###"):
        """寬鬆模式內容生成（當標準模式失敗時使用） - 支援結構化標題"""
        try:
            from researcher.prompts import PromptTemps
            prompt_obj = PromptTemps.get_content_prompt_lenient()
            
            content_prompt = ChatPromptTemplate.from_messages([
                ("system", "你是專業的報告撰寫助理。"),
                ("user", prompt_obj.template)
            ])
            
            qa_chain = content_prompt | (llm_override or self.llm) | StrOutputParser()
            docs = retriever.invoke(question)
            context = self._docs_to_context(docs)
            
            # 傳入 heading_level 變數
            return qa_chain.invoke({
                "context": context,
                "question": question,
                "heading_level": heading_level
            })
            
        except Exception as e:
            print(f"[ERROR] 寬鬆模式生成失敗: {e}")
            return None

if __name__ == "__main__":
    # 測試範例
    topics = [
        "初音未來",
        "AI & Machine Learning 2024",
        "台灣半導體產業的未來發展？"
    ]
    
    smart_llm = "ministral-3:3b"
    
    for topic in topics:
        print(f"\n{'='*60}")
        print(f"測試主題: {topic}")
        print(f"{'='*60}")
        
        pipeline = RAGPipeline(
            query=topic,
            model=smart_llm,
            temperature=0.15,
            num_predict=-1,
            enable_hybrid_search=True
        )
        
        # 查看生成的資料庫路徑
        print(f"資料庫路徑: {pipeline.persist_directory}")