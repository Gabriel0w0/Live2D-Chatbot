import os, json, uuid ,httpx 
from config import AUDIO_DIR, VOICEVOX_URL  # 從 config 匯入

class TTS:
    def __init__(self, speaker_id=58):
        self.speaker_id = speaker_id
        self.audio_dir = AUDIO_DIR          # 使用 config 的變數
        os.makedirs(self.audio_dir, exist_ok=True)

    async def synthesize_to_file(self, text):
        # 使用 AsyncClient 進行非同步請求
        async with httpx.AsyncClient() as client:
            # Step 1: audio_query
            try:
                resp = await client.post(
                    f"{VOICEVOX_URL}/audio_query",
                    params={"text": text, "speaker": self.speaker_id},
                    timeout=15.0 # 設定超時避免卡死
                )
                resp.raise_for_status() # 檢查 HTTP 錯誤
                query = resp.json()
            except Exception as e:
                raise RuntimeError(f"audio_query failed: {e}")

            # Step 2: synthesis
            try:
                synth_resp = await client.post(
                    f"{VOICEVOX_URL}/synthesis",
                    params={"speaker": self.speaker_id},
                    headers={"Content-Type": "application/json"},
                    json=query,  # httpx 支援直接傳 json
                    timeout=60.0 # 生成音檔可能比較久
                )
                synth_resp.raise_for_status()
            except Exception as e:
                raise RuntimeError(f"synthesis failed: {e}")

            # Step 3: Save as a wav file
            filename = f"{uuid.uuid4().hex}.wav"
            filepath = os.path.join(self.audio_dir, filename)
            
            with open(filepath, "wb") as f:
                f.write(synth_resp.content)

            return f"/static/audio/{filename}"