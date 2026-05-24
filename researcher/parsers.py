import re
from typing import List, Dict, Optional

def extract(response_output: str, debug: bool = False) -> List[Dict]:
    """提取 LLM 輸出的大綱結構"""
    lines = response_output.strip().splitlines()
    outline = []
    current_section = None
    current_subgroup = None
    
    if debug:
        print(f"\n{'='*70}")
        print(f"[DEBUG] 開始解析，總行數: {len(lines)}")
        print(f"{'='*70}\n")

    for line_idx, line in enumerate(lines):
        original_line = line
        stripped = line.strip()
        
        # ========== 跳過無效行 ==========
        if not stripped:
            continue
        
        # 跳過 LLM 元數據
        skip_patterns = [
            r'^Thought:', r'^AI:', r'^Assistant:', r'^Human:', r'^System:',
            r'^User:', r'^Bot:', r'^Claude:', r'^ChatGPT:', r'^GPT:',
            r'^以下是', r'^以下為', r'^以下將', r'^現在', r'^接下來',
            r'^好的[，,、]', r'^我將', r'^讓我', r'^首先', r'^其次',
            r'^根據您的', r'^根據', r'^基於', r'^參考',
            r'^此大綱', r'^該大綱', r'^本大綱', r'^上述',
            r'^如需', r'^若需', r'^可隨時', r'^請隨時',
            r'^符合您的', r'^符合', r'^滿足', r'^遵循',
            r'^注意[:：]', r'^說明[:：]', r'^提示[:：]',
            r'^Here is', r'^Here are', r'^This is', r'^The following',
            r'^Below is', r'^As requested', r'^Based on',
            r'^Note:', r'^Warning:', r'^Tip:',
        ]
        
        should_skip = False
        for pattern in skip_patterns:
            if re.match(pattern, stripped, re.IGNORECASE):
                if debug:
                    print(f"[{line_idx:3d}] ⏭️  跳過元數據")
                should_skip = True
                break
        if should_skip:
            continue
        
        # 字串閉合
        if re.match(r'^[-=*_~`´¯]{3,}$', stripped) or \
                stripped in ('---', '===', '***', '___', '~~~', '```'):
                    if debug:
                        print(f"[{line_idx:3d}] ⏭️  跳過分隔線")
                    continue

        if re.match(r'^#{1,6}\s*$', stripped):
            continue
        
        # ========== 標準化處理 ==========
        line = re.sub(r'[．。·]', '.', line)
        line = re.sub(r'[、，](?=\s*$)', '', line)
        line = re.sub(r'[（\(]', '(', line)
        line = re.sub(r'[）\)]', ')', line)
        line = re.sub(r'：', ':', line)
        line = re.sub(r'\s+', ' ', line)
        line = line.rstrip()
        
        indent_level = len(original_line) - len(original_line.lstrip())
        line = line.strip()
        
        if debug and line:
            print(f"[{line_idx:3d}] 縮排={indent_level:2d} | {line[:60]}")

        # ========== 主標題偵測 ==========
        if indent_level == 0:
            clean_line = line.lstrip('#').strip()
            clean_line = clean_line.strip('*_~`').strip()
            
            if debug:
                print(f"       🔍 清理後: {clean_line[:50]}")
            
            # 中文標點包裹的標題
            chinese_bracket_match = re.match(r'^[【《「『\[〔]+(.+?)[】》」』\]〕]+(.*)$', clean_line)
            if chinese_bracket_match:
                bracket_content = chinese_bracket_match.group(1).strip()
                after_bracket = chinese_bracket_match.group(2).strip()

                # 強制清洗括號內的標題
                bracket_content = bracket_content.replace('*', '').replace('_', '').replace('`', '').strip()
                
                chapter_patterns = [
                    r'^第([一二三四五六七八九十百千\d]+)[章節部分段]',
                    r'^Part\s+(\d+)',
                    r'^Chapter\s+(\d+)',
                    r'^Section\s+(\d+)',
                ]
                
                is_chapter = any(re.match(p, bracket_content, re.IGNORECASE) for p in chapter_patterns)
                
                if is_chapter or len(bracket_content) <= 20:
                    full_title = f"{bracket_content} {after_bracket}" if after_bracket else bracket_content
                    
                    if current_section:
                        outline.append(current_section)
                    
                    current_section = {
                        "title": full_title,
                        "subpoints": []
                    }
                    current_subgroup = None
                    
                    if debug:
                        print(f"       ✅ 中文標題: {full_title}")
                    continue
            
            # 各種主標題格式
            section_patterns = [
                (r'^(\d+)([\.\-、:）)\]—])\s*(.+)', lambda m: (m.group(1), m.group(2), m.group(3))),
                (r'^\[(\d+)\]\s*(.+)', lambda m: (m.group(1), '.', m.group(2))),
                (r'^〔(\d+)〕\s*(.+)', lambda m: (m.group(1), '.', m.group(2))),
                (r'^[(（](\d+)[)）]\s*(.+)', lambda m: (m.group(1), '.', m.group(2))),
                (r'^[(（]?([一二三四五六七八九十百千]+)[)）、.\s]+(.+)', lambda m: (m.group(1), '、', m.group(2))),
                (r'^([壹貳參肆伍陸柒捌玖拾佰仟]+)[、.\s]+(.+)', lambda m: (m.group(1), '、', m.group(2))),
                (r'^([IVXLCDMivxlcdm]+)\.\s*(.+)', lambda m: (m.group(1), '.', m.group(2))),
                (r'^[(（]([IVXLCDMivxlcdm]+)[)）]\s*(.+)', lambda m: (m.group(1), '.', m.group(2))),
                (r'^([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳])\s*(.+)', lambda m: (m.group(1), '', m.group(2))),
                (r'^([❶❷❸❹❺❻❼❽❾❿])\s*(.+)', lambda m: (m.group(1), '', m.group(2))),
                (r'^([⓵⓶⓷⓸⓹⓺⓻⓼⓽⓾])\s*(.+)', lambda m: (m.group(1), '', m.group(2))),
                (r'^([1️⃣2️⃣3️⃣4️⃣5️⃣6️⃣7️⃣8️⃣9️⃣🔟])\s*(.+)', lambda m: (m.group(1), '', m.group(2))),
                (r'^([A-Z])\.\s*(.+)', lambda m: (m.group(1), '.', m.group(2))),
                (r'^[(（]([A-Z])[)）]\s*(.+)', lambda m: (m.group(1), '.', m.group(2))),
                (r'^(Part|Chapter|Section)\s+(\d+)[:\s]+(.+)', lambda m: (f"{m.group(1)} {m.group(2)}", ':', m.group(3))),
            ]
            
            matched = False
            for pattern, extractor in section_patterns:
                match = re.match(pattern, clean_line, re.IGNORECASE)
                if match:
                    try:
                        result = extractor(match)
                        if len(result) == 3:
                            number, sep, title_text = result
                        else:
                            continue
                        
                        if len(str(number)) <= 10:
                            if current_section:
                                outline.append(current_section)
                            
                            # 強制清洗主標題文字
                            title_text = title_text.strip('*_~`').replace('*', '').replace('_', '').replace('`', '').strip()
                            full_title = f"{number}{sep} {title_text}" if sep else f"{number} {title_text}"
                            
                            current_section = {
                                "title": full_title,
                                "subpoints": []
                            }
                            current_subgroup = None
                            matched = True
                            
                            if debug:
                                print(f"       ✅ 主標題: {full_title}")
                            break
                    except Exception as e:
                        if debug:
                            print(f"       ❌ 解析錯誤: {e}")
                        continue
            
            if matched:
                continue

        # ========== 子項偵測 ==========
        if current_section:
            bullet_chars = [
                '-', '- ', '‣', '⁃', '*', '+', '×', '✕',
                '→', '➔', '➜', '➤', '➡', '⇒', '⟹',
                '►', '▶', '▸', '▹', '▻', '▷', '⊳',
                '←', '↑', '↓', '↔', '⇄', '⇌',
                '✓', '✔', '√', '☑', '✅',
                '✗', '✘', '☒', '❌',
                '○', '●', '◯', '◉', '◎', '⊙', '⊚', '⊛',
                '□', '■', '▢', '▣', '◻', '◼',
                '▪', '▫', '▬', '▭',
                '◇', '◆', '◊', '⬥', '💠',
                '△', '▲', '▽', '▼', '◁', '▷',
                '✦', '✧', '★', '☆', '✪', '⭐',
                '◈', '🔸', '🔹', '🔶', '🔷', '💎',
                '⚫', '⚪', '🔴', '🔵', '🟢', '🟡', '🟠', '🟣',
                '❖', '❘', '❙', '❚',
                '⊕', '⊗',
            ]
            
            starts_with_bullet = any(line.startswith(char) for char in bullet_chars)
            
            if starts_with_bullet:
                for char in bullet_chars:
                    if line.startswith(char):
                        content = line[len(char):].strip()
                        break
                
                content = re.sub(r'^\*{1,3}', '', content)
                content = re.sub(r'\*{1,3}$', '', content)
                content = content.strip()
                
                colon_pos = content.find(':')
                
                if colon_pos > 0:
                    sub_title = content[:colon_pos].strip()
                    description = content[colon_pos+1:].strip()
                    
                    # 強制清洗子標題
                    sub_title = sub_title.replace('*', '').replace('_', '').replace('`', '').strip()
                    
                    if not description or len(description) < 5:
                        current_subgroup = {
                            "title": sub_title,
                            "subpoints": []
                        }
                        current_section["subpoints"].append(current_subgroup)
                        
                        if debug:
                            print(f"       ▶ 子組: {sub_title}")
                    else:
                        full_content = f"{sub_title}: {description}"
                        if current_subgroup:
                            current_subgroup["subpoints"].append(full_content)
                        else:
                            current_section["subpoints"].append(full_content)
                        
                        if debug:
                            print(f"       ✔️  子項")
                else:
                    # 即使沒有冒號，也要清洗
                    content = content.replace('*', '').replace('_', '').replace('`', '').strip()
                    if current_subgroup:
                        current_subgroup["subpoints"].append(content)
                    else:
                        current_section["subpoints"].append(content)
                    
                    if debug:
                        print(f"       ✔️  子項")
                
                continue

            # 子編號偵測
            subnumber_patterns = [
                (r'^([a-zA-Z])[.\)]\s*(.+)', lambda m: m.group(2)),
                (r'^[(（]([a-zA-Z])[)）]\s*(.+)', lambda m: m.group(2)),
                (r'^(\d+\.)+\d+\s+(.+)', lambda m: m.group(2)),
                (r'^[(（](\d+)[)）]\s*(.+)', lambda m: m.group(2)),
                (r'^(\d+)\)\s*(.+)', lambda m: m.group(2)),
                (r'^([ivxlcdm]+)\.\s*(.+)', lambda m: m.group(2)),
                (r'^[(（]([ivxlcdm]+)[)）]\s*(.+)', lambda m: m.group(2)),
                (r'^([αβγδεζηθικλμνξοπρστυφχψω])[.\)]\s*(.+)', lambda m: m.group(2)),
            ]
            
            for pattern, extractor in subnumber_patterns:
                match = re.match(pattern, line, re.IGNORECASE)
                if match:
                    try:
                        content = extractor(match)
                        content = content.strip('*_~`').strip()
                        # 強制清洗編號子項
                        content = content.replace('*', '').replace('_', '').replace('`', '').strip()
                        
                        if current_subgroup:
                            current_subgroup["subpoints"].append(content)
                        else:
                            current_section["subpoints"].append(content)
                        
                        if debug:
                            print(f"       ✔️  編號子項")
                        break
                    except:
                        continue

            # 縮排子項偵測
            if indent_level > 0:
                content = line
                for char in bullet_chars:
                    if content.startswith(char):
                        content = content[len(char):].strip()
                        break
                
                content = re.sub(r'^\*{1,3}', '', content)
                content = re.sub(r'\*{1,3}$', '', content)
                content = content.strip()
                
                colon_pos = content.find(':')
                if colon_pos > 0:
                    sub_title = content[:colon_pos].strip()
                    description = content[colon_pos+1:].strip()
                    
                    # 清洗縮排項
                    sub_title = sub_title.replace('*', '').replace('_', '').replace('`', '').strip()
                    
                    full_content = f"{sub_title}: {description}" if description else sub_title
                else:
                    content = content.replace('*', '').replace('_', '').replace('`', '').strip()
                    full_content = content
                
                if current_subgroup:
                    current_subgroup["subpoints"].append(full_content)
                else:
                    current_section["subpoints"].append(full_content)
                
                if debug:
                    print(f"       ↪️  縮排項")
                continue

    if current_section:
        outline.append(current_section)
    
    if debug:
        print(f"\n{'='*70}")
        print(f"✅ 解析完成: {len(outline)} 個主節")
        print(f"{'='*70}\n")

    return outline


# ===== 測試程式碼 =====
if __name__ == "__main__":
    test_cases = {
        "實際 LLM 輸出": """以下是基於**初音未來**的研究報告大綱：

### **1. 研究背景與動機**
- **初音未來的研究動機:說明為何研究**
- **核心特質分析:系統特性**

### **2. 發展歷程**
- **誕生背景:開發歷史**""",

        "中文編號": """一、研究背景
   - 背景說明
二、研究方法
   - 方法論""",

        "多種符號": """1. 主標題
   ► 箭頭項
   ✓ 勾選項
   ★ 星號項
   🔸 菱形項""",
    }
    
    for name, test_output in test_cases.items():
        print("=" * 70)
        print(f"測試：{name}")
        print("=" * 70)
        
        outline = extract(test_output, debug=False)
        
        if outline:
            for section in outline:
                print(f"\n【{section['title']}】")
                for sub in section['subpoints']:
                    if isinstance(sub, str):
                        display = sub[:60] + "..." if len(sub) > 60 else sub
                        print(f"  -  {display}")
                    elif isinstance(sub, dict):
                        print(f"  ▶ {sub['title']}")
                        for sub_sub in sub['subpoints']:
                            display = sub_sub[:55] + "..." if len(sub_sub) > 55 else sub_sub
                            print(f"    - {display}")
            
            total = sum(len(s['subpoints']) for s in outline)
            print(f"\n✅ 成功: {len(outline)} 個主節，{total} 個子項")
        else:
            print("❌ 解析失敗") 
        print()
    
    print("=" * 70)
    print("✅ 所有測試完成！")
    print("=" * 70)