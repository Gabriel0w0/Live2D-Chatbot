import os
import logging
from config import AUDIO_DIR

# 取得應用程式共用的 Logger
logger = logging.getLogger("app")  

def clean_old_audio_files(max_files: int = 20) -> None:
    """
    清理舊的語音快取檔案，只保留最新的 N 個檔案。
    
    Args:
        max_files (int): 要保留的最新檔案數量 (預設 20)。
    """
    
    try:
        # 1. 檢查語音目錄是否存在，若不存在則不需清理
        if not os.path.exists(AUDIO_DIR):
            return

        # 2. 獲取目錄下所有 .wav 檔案
        wav_files = [f for f in os.listdir(AUDIO_DIR) if f.endswith(".wav")]
        
        # 3. 依照「修改時間」進行排序 (由舊到新)
        sorted_files = sorted(
            wav_files,
            key=lambda x: os.path.getmtime(os.path.join(AUDIO_DIR, x))
        )

        # 4. 識別需要刪除的舊檔案
        # 切片 [:-max_files] 表示取「從頭開始」直到「倒數第 max_files 個」之前的所有元素
        # 全部檔案 - 最新的 N 個 = 要刪除的舊檔案
        files_to_delete = sorted_files[:-max_files]

        # 5. 執行刪除
        for f in files_to_delete:
            file_path = os.path.join(AUDIO_DIR, f)
            os.remove(file_path)
            
        # 只有在真的有刪除檔案時才記錄 Log
        if files_to_delete:
            logger.info(f"[Cleanup] 已清理 {len(files_to_delete)} 個舊語音檔，保留最新 {max_files} 個")
            
    except Exception as e:
        logger.error(f"[Cleanup] 清理語音快取失敗：{e}")