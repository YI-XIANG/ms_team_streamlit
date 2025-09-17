import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import random
 
import json
from typing import List, Dict, Tuple
from google import genai
from google.genai import types
from prompt import system_prompt

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, db as firebase_db


# --- 常數 ---
MAX_TEAM_SIZE = 6
UNAVAILABLE_KEY = "__UNAVAILABLE__"


# --- Firebase Admin 初始化與 RTDB 參照 ---
def _parse_firebase_url(full_url: str) -> Tuple[str, str]:
    if not full_url:
        raise ValueError("firebase.url is empty in secrets")
    url = full_url.strip()
    if url.endswith(".json"):
        url = url[:-5]
    url = url.rstrip("/")
    marker = ".com"
    idx = url.find(marker)
    if idx == -1:
        raise ValueError("Invalid Firebase RTDB URL: missing '.com'")
    base = url[: idx + len(marker)]
    path = url[idx + len(marker) :]
    path = path if path else "/"
    if not path.startswith("/"):
        path = "/" + path
    return base, path


def _init_firebase_admin_if_needed():
    if not firebase_admin._apps:
        service_account_info = dict(st.secrets["gcp_service_account"])  # from secrets
        database_url_full = st.secrets["firebase"]["url"]
        database_url_base, _ = _parse_firebase_url(database_url_full)
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            "databaseURL": database_url_base
        })


def _get_rtdb_ref():
    _init_firebase_admin_if_needed()
    database_url_full = st.secrets["firebase"]["url"]
    _, ref_path = _parse_firebase_url(database_url_full)
    return firebase_db.reference(ref_path)


def load_data() -> Dict:
    try:
        ref = _get_rtdb_ref()
        data = ref.get()
        if data is None:
            return {"teams": [], "members": {}}
        data.setdefault("teams", [])
        data.setdefault("members", {})
        return data
    except Exception as e:
        st.error(f"❌ 載入資料失敗：{e}")
        return {"teams": [], "members": {}}


def save_data(data: Dict):
    try:
        ref = _get_rtdb_ref()
        ref.set(data)
    except Exception as e:
        st.error(f"❌ 儲存資料失敗：{e}")


# --- AI Teams 專用存取（與手動分隊分離） ---
def load_ai_teams() -> Dict:
    try:
        ref = _get_rtdb_ref()
        ai = ref.child("ai_teams").get()
        if ai is None:
            return {}
        return ai
    except Exception as e:
        st.error(f"❌ 載入 AI 分隊失敗：{e}")
        return {}


def save_ai_teams(ai_data: Dict):
    try:
        ref = _get_rtdb_ref()
        ref.child("ai_teams").set(ai_data)
    except Exception as e:
        st.error(f"❌ 儲存 AI 分隊失敗：{e}")


def get_start_of_week(base_date: date) -> date:
    days_since_thu = (base_date.weekday() - 3) % 7
    return base_date - timedelta(days=days_since_thu)


def get_default_schedule_for_week():
    return {
        "proposed_slots": {},
        "availability": {UNAVAILABLE_KEY: []},
        "final_time": "",
    }


def generate_weekly_schedule_days(start_date: date) -> List[str]:
    start_of_week = get_start_of_week(start_date)
    weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
    return [
        f"星期{weekdays_zh[(start_of_week + timedelta(days=i)).weekday()]} ({(start_of_week + timedelta(days=i)).strftime('%m-%d')})"
        for i in range(7)
    ]


def create_empty_team(name: str, start_of_this_week_str: str, start_of_next_week_str: str) -> Dict:
    new_schedules = {
        start_of_this_week_str: get_default_schedule_for_week(),
        start_of_next_week_str: get_default_schedule_for_week()
    }
    # 預設給空 proposed_slots，讓隊長可直接填寫
    start_of_this_week_date = datetime.strptime(start_of_this_week_str, '%Y-%m-%d').date()
    start_of_next_week_date = datetime.strptime(start_of_next_week_str, '%Y-%m-%d').date()
    new_schedules[start_of_this_week_str]['proposed_slots'] = {day: "" for day in generate_weekly_schedule_days(start_of_this_week_date)}
    new_schedules[start_of_next_week_str]['proposed_slots'] = {day: "" for day in generate_weekly_schedule_days(start_of_next_week_date)}

    return {
        "team_name": name,
        "team_remark": "",
        "member": [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)],
        "schedules": new_schedules
    }


def auto_assign_members(members: Dict[str, Dict], team_count: int, shuffle_seed: int | None, only_guild: bool) -> List[Dict]:
    # 過濾成員
    filtered = []
    for name, info in members.items():
        if only_guild and not info.get("is_guild_member", True):
            continue
        filtered.append({
            "name": name,
            "job": info.get("job", ""),
            "level": info.get("level", ""),
            "atk": info.get("atk", ""),
        })

    if shuffle_seed is not None:
        random.Random(shuffle_seed).shuffle(filtered)
    else:
        random.shuffle(filtered)

    # 先以職業分桶，嘗試讓每隊職業多樣
    job_to_members: Dict[str, List[Dict]] = {}
    for m in filtered:
        job_to_members.setdefault(m.get("job", ""), []).append(m)

    teams: List[List[Dict]] = [[] for _ in range(team_count)]
    # 輪詢分配各職業桶
    t = 0
    for _, bucket in job_to_members.items():
        for member in bucket:
            # 找到下一個有空位的隊伍
            for _ in range(team_count):
                if len(teams[t]) < MAX_TEAM_SIZE:
                    teams[t].append(member)
                    t = (t + 1) % team_count
                    break
                t = (t + 1) % team_count

    # 轉為資料結構（固定 MAX_TEAM_SIZE，空位填空白）
    normalized = []
    for idx, team_members in enumerate(teams, start=1):
        fixed = team_members[:MAX_TEAM_SIZE]
        if len(fixed) < MAX_TEAM_SIZE:
            fixed += [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE - len(fixed))]
        normalized.append({"team_name": f"AI自動分隊 {idx}", "member": fixed})
    return normalized


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    # 將 DataFrame 轉為簡單的 Markdown 表格，避免依賴外部套件
    if df.empty:
        return ""
    headers = list(df.columns)
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(v) for v in row.tolist()) + " |")
    return "\n".join(lines)


def call_gemini(prompt_template: str) -> dict:
    # 對接 Gemini（若未配置，回傳虛擬資料以示範）
    client = genai.Client(api_key=st.secrets.get("AI_KEY", {}).get("GEMINI_API_KEY"))
    try:
        resp = client.models.generate_content(
            model='gemini-2.5-pro',
            contents=prompt_template,
            config=types.GenerateContentConfig(
                temperature=0.1
            )
        )
        # 目前簡化：若模型回傳非 JSON 或無法解析，回傳示例格式
        try:
            text = resp.text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception:
            return {
                "隊伍": [
                    [["示例成員1", "職業A", "Lv.1"], ["示例成員2", "職業B", "Lv.1"]],
                    [["示例成員3", "職業C", "Lv.2"]]
                ]
            }
    except Exception as e:
        st.error(f"✖ Gemini 呼叫失敗：{e}")
        return {"隊伍": []}


# --- 初始化 Session State 與 UI ---
if "data" not in st.session_state:
    st.session_state.data = load_data()

st.title("🍁 AI 分組")

# 系統說明
st.info("💡 **AI智能分隊**：選擇要分隊的成員，AI會根據職業、等級、時間自動分配最優隊伍配置")

# 初始化 session state
if "ai_selected_members" not in st.session_state:
    st.session_state.ai_selected_members = []

st.subheader("📝 選擇分隊成員")

col1, col2 = st.columns(2)
with col1:
    # 顯示本週/下週並附上日期區間
    today = date.today()
    start_this = get_start_of_week(today)
    this_range = f"{start_this.strftime('%m/%d')} ~ {(start_this + timedelta(days=6)).strftime('%m/%d')}"
    next_start = start_this + timedelta(days=7)
    next_range = f"{next_start.strftime('%m/%d')} ~ {(next_start + timedelta(days=6)).strftime('%m/%d')}"
    label_this = f"本週({this_range})"
    label_next = f"下週({next_range})"
    list_week_choice = st.radio("顯示週次", [label_this, label_next], horizontal=True, key="list_week_choice")
with col2:
    week_start = start_this if list_week_choice == label_this else start_this + timedelta(days=7)
    weekday_labels = [
        f"星期四({(week_start + timedelta(days=0)).strftime('%m/%d')})",
        f"星期五({(week_start + timedelta(days=1)).strftime('%m/%d')})",
        f"星期六({(week_start + timedelta(days=2)).strftime('%m/%d')})",
        f"星期日({(week_start + timedelta(days=3)).strftime('%m/%d')})",
        f"星期一({(week_start + timedelta(days=4)).strftime('%m/%d')})",
        f"星期二({(week_start + timedelta(days=5)).strftime('%m/%d')})",
        f"星期三({(week_start + timedelta(days=6)).strftime('%m/%d')})",
    ]
    weekday_plain = ["星期四","星期五","星期六","星期日","星期一","星期二","星期三"]

    # 獲取所有成員資料
    all_members = st.session_state.data.get("members", {})
    show_week = week_start.strftime('%Y-%m-%d')

    # 獲取有報名的成員資料
    available_members = []
    for name, info in all_members.items():
        # 優先從 weekly_data 讀取該週資料
        weekly_data = info.get("weekly_data", {}) if isinstance(info.get("weekly_data", {}), dict) else {}
        week_obj = weekly_data.get(show_week)
        if not week_obj:
            # 回退舊欄位（只在同週次時顯示）
            if info.get("weekly_week_start") != show_week:
                continue
            wa = info.get("weekly_availability", {}) or {}
            pc = info.get("weekly_participation_count", "")
        else:
            wa = week_obj.get("availability", {}) or {}
            pc = week_obj.get("participation_count", "")

        # 僅顯示有報名（有任一勾選）的人
        if any(bool(wa.get(p, False)) for p in weekday_plain):
            participation_count_str = "" if pc in (None, "") else str(pc)
            available_members.append({
                "name": name,
                "job": str(info.get("job", "")),
                "level": str(info.get("level", "")),
                "participation_count": participation_count_str,
                "availability": wa
            })
    if st.button("📥 匯入全部", key="ai_import_all", help="一次匯入所有報名成員"):
        st.session_state.ai_selected_members = available_members.copy()
        st.success(f"✅ 已匯入 {len(available_members)} 位報名成員")
        st.rerun()

# 當週次切換時，清空已選擇的成員
if "last_week_choice" not in st.session_state:
    st.session_state.last_week_choice = list_week_choice
elif st.session_state.last_week_choice != list_week_choice:
    st.session_state.ai_selected_members = []
    st.session_state.last_week_choice = list_week_choice
    st.rerun()

# 成員選擇界面
st.markdown("**步驟1：選擇要分隊的成員**")

# 下拉選擇成員
member_options = [""] + [m["name"] for m in available_members]
selected_member = st.selectbox("從報名成員中選擇", member_options, key="ai_member_selector", help="選擇要加入AI分隊的成員")

if selected_member and st.button("➕ 加入分隊", key="ai_add_member", type="primary"):
    if selected_member not in [m["name"] for m in st.session_state.ai_selected_members]:
        # 找到選中成員的完整資料
        member_data = next((m for m in available_members if m["name"] == selected_member), None)
        if member_data:
            st.session_state.ai_selected_members.append(member_data)
            st.success(f"✅ 已將 {selected_member} 加入分隊名單")
            st.rerun()
    else:
        st.warning(f"⚠️ {selected_member} 已經在分隊名單中")    

st.markdown("**步驟2：【確認名單】**")

# 顯示已選擇的成員
if st.session_state.ai_selected_members:    
    # 統計資訊
    col1, col2 = st.columns(2)
    with col1:
        st.metric("已選擇成員", f"{len(st.session_state.ai_selected_members)} 人")
    with col2:
        levels = [int(m["level"]) for m in st.session_state.ai_selected_members if m["level"].isdigit()]
        if levels:
            avg_level = sum(levels) / len(levels)
            st.metric("平均等級", f"{avg_level:.0f}")
        else:
            st.metric("平均等級", "N/A")
    
    # 建立 DataFrame
    rows = []
    for member in st.session_state.ai_selected_members:
        row = {
            "名稱": member["name"],
            "職業": member["job"],
            "等級": member["level"],
            "次數": member["participation_count"]
        }
        for plain, label in zip(weekday_plain, weekday_labels):
            row[label] = "✅" if member["availability"].get(plain, False) else ""
        rows.append(row)
    
    df_selected = pd.DataFrame(rows, columns=["名稱","職業","等級","次數"] + weekday_labels)
    
    # 使用 data_editor 讓用戶可以刪除成員（固定行數，不能新增）
    edited_df = st.data_editor(
        df_selected,
        key="ai_selected_members_editor",
        use_container_width=True,
        hide_index=True,
        num_rows="fixed",
        column_config={
            "名稱": st.column_config.TextColumn("名稱", disabled=True),
            "職業": st.column_config.TextColumn("職業", disabled=True),
            "等級": st.column_config.TextColumn("等級", disabled=True),
            "次數": st.column_config.TextColumn("次數", disabled=True),
            **{label: st.column_config.TextColumn(label, disabled=True) for label in weekday_labels}
        }
    )
    
    # 檢查是否有成員被刪除
    if len(edited_df) < len(st.session_state.ai_selected_members):
        # 找出被刪除的成員
        current_names = set(edited_df["名稱"].tolist())
        original_names = set(member["name"] for member in st.session_state.ai_selected_members)
        removed_names = original_names - current_names
        
        # 更新 session state
        st.session_state.ai_selected_members = [
            member for member in st.session_state.ai_selected_members 
            if member["name"] in current_names
        ]
        
        if removed_names:
            st.success(f"✅ 已移除成員：{', '.join(removed_names)}")
            st.rerun()
    
    # 操作按鈕
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("🗑️ 清空所有選擇", key="ai_clear_all", help="移除所有已選擇的成員"):
            st.session_state.ai_selected_members = []
            st.success("✅ 已清空所有選擇的成員")
            st.rerun()
    
    st.markdown("---")
        
else:
    st.info("💡 尚未選擇任何成員。請使用上方下拉選單選擇成員，或點擊「匯入全部」按鈕。")

# AI 分隊生成功能
st.markdown("**步驟3：【AI分組】**")
with st.expander("🔐 管理員功能", expanded=False):
    st.markdown("**需要管理員權限才能使用AI分隊功能**")
    pwd_input = st.text_input("管理員密碼", type="password", key="autoai_pwd", help="輸入管理員密碼以啟用AI功能")
    ctrl1, ctrl2 = st.columns(2)

def get_member_info_by_name(name: str) -> Dict:
    info = st.session_state.data.get("members", {}).get(name, {})
    return {
        "name": name,
        "job": info.get("job", ""),
        "level": info.get("level", ""),
    }

def normalize_ai_result(result: dict) -> List[Dict]:
    teams = []
    for ti, team_data in enumerate(result.get("隊伍", []), start=1):
        # 處理新格式：{"時間": "...", "成員": [...]}
        if isinstance(team_data, dict) and "成員" in team_data:
            members = []
            for m in team_data.get("成員", []):
                if isinstance(m, list) and len(m) >= 3:
                    members.append({
                        "name": str(m[0]), 
                        "job": str(m[1]) if len(m) > 1 else "", 
                        "level": str(m[2]) if len(m) > 2 else ""
                    })
            team_name = f"AI自動分隊 {ti}"
            if "時間" in team_data:
                team_name += f" ({team_data['時間']})"
            teams.append({"team_name": team_name, "member": members})
        # 處理舊格式：直接是成員陣列
        elif isinstance(team_data, list):
            members = []
            for m in team_data:
                if isinstance(m, list) and len(m) >= 3:
                    members.append({
                        "name": str(m[0]), 
                        "job": str(m[1]) if len(m) > 1 else "", 
                        "level": str(m[2]) if len(m) > 2 else ""
                    })
            teams.append({"team_name": f"AI自動分隊 {ti}", "member": members})
    return teams

def _get_member_week_availability(name: str, week_key: str) -> Dict[str, bool]:
    info = st.session_state.data.get("members", {}).get(name, {})
    weekly_data = info.get("weekly_data", {}) if isinstance(info.get("weekly_data", {}), dict) else {}
    week_obj = weekly_data.get(week_key)
    if week_obj:
        return week_obj.get("availability", {}) or {}
    # 回退舊欄位（僅當其週次相符時）
    if info.get("weekly_week_start") == week_key:
        return info.get("weekly_availability", {}) or {}
    return {}

def _parse_team_time_label(team_name: str) -> str:
    # 從隊伍名稱中提取括號內時間字串，如：AI自動分隊 1 (星期六(09/20))
    if not team_name:
        return ""
    if "(" in team_name and ")" in team_name:
        return team_name.split("(")[-1].rstrip(")")
    return ""

def _normalize_time_label_with_weekday(time_label: str, week_start: date) -> str:
    """正規化 AI 傳回的時間標籤，輸出：星期X(mm/dd)。
    支援以下輸入：
    - mm/dd，例如 09/12
    - mm/dd(週字)，例如 09/24(三)
    - 已為 星期X(mm/dd) 則原樣回傳
    """
    if not time_label:
        return ""
    s = time_label.strip().replace("-", "/")
    # 已是標準格式
    if s.startswith("星期") and "(" in s and ")" in s:
        return s
    weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
    # 嘗試解析 mm/dd(週字)
    import re as _re
    m = _re.match(r"^(\d{2}/\d{2})\(([一二三四五六日])\)$", s)
    if m:
        mmdd = m.group(1)
        # 以日期為準反推星期
        for i in range(7):
            d = week_start + timedelta(days=i)
            if d.strftime('%m/%d') == mmdd:
                return f"星期{weekdays_zh[d.weekday()]}({mmdd})"
        return f"星期{m.group(2)}({mmdd})"  # 找不到對應週次時，保留原週字
    # 僅 mm/dd
    if _re.match(r"^\d{2}/\d{2}$", s):
        mmdd = s
        for i in range(7):
            d = week_start + timedelta(days=i)
            if d.strftime('%m/%d') == mmdd:
                return f"星期{weekdays_zh[d.weekday()]}({mmdd})"
        return s
    return s


with ctrl1:
    if st.button("✨ AI 分組", key="autoai_btn", type="primary", help="使用AI智能分析生成最優隊伍配置"):
        correct_pwd = st.secrets.get("setting", {}).get("pwd")
        if correct_pwd is None or pwd_input != correct_pwd:
            st.error("❌ 密碼錯誤，無法執行 AI 分組功能")
            st.stop()
        
        # 使用手動選擇的成員資料
        if not st.session_state.ai_selected_members:
            st.error("❌ 請先選擇要分組的成員！")
            st.stop()
        
        # 建立成員資料的 DataFrame
        ai_rows = []
        for member in st.session_state.ai_selected_members:
            row = {
                "名稱": member["name"],
                "職業": member["job"],
                "等級": member["level"],
                "次數": member["participation_count"]
            }
            for plain, label in zip(weekday_plain, weekday_labels):
                row[label] = "✅" if member["availability"].get(plain, False) else ""
            ai_rows.append(row)
        
        markdown_table = dataframe_to_markdown(pd.DataFrame(ai_rows)) if ai_rows else ""
        prompt_template = system_prompt.format(markdown=markdown_table)
        result = call_gemini(prompt_template)
        week_key = show_week
        ai_data = load_ai_teams()
        ai_data[week_key] = normalize_ai_result(result)
        save_ai_teams(ai_data)
        st.success("✅ AI 分隊生成完成！結果已儲存至分隊資料表")

with ctrl2:
    if st.button("🗑️ 清空所有隊伍", key="ai_delete_all", help="刪除本週所有AI分隊"):
        week_key = show_week
        ai_data = load_ai_teams()
        ai_data[week_key] = []
        save_ai_teams(ai_data)
        st.success("✅ 已清空本週所有 AI 分隊")

st.markdown("---")
st.subheader("AI 分隊編輯")
ai_data = load_ai_teams()
week_teams = ai_data.get(show_week, [])

if not week_teams:
    st.info("此週尚無 AI 分隊資料。")
else:
    all_member_names = [""] + sorted(list(st.session_state.data.get("members", {}).keys()))
    for idx, team in enumerate(week_teams):
        # 生成 expander 標題：idx+1隊 + 日期時間 + 名單 + 【狀態】
        team_name = team.get('team_name', f'AI自動分隊 {idx+1}')
        time_label_raw = _parse_team_time_label(team_name)
        time_label = _normalize_time_label_with_weekday(time_label_raw, week_start)
        members = team.get("member", [])
        member_names = [m.get("name", "") for m in members if m.get("name")]
        member_count = len(member_names)
        member_list_str = ", ".join(member_names) if member_names else "無成員"
        status = "滿員" if member_count >= MAX_TEAM_SIZE else f"{member_count}人"
        expander_title = (
            f"🏅 第{idx+1}隊 | 📅 {time_label}\t"
            f"📌 狀態：【{status}】\t"
            f"👥 成員：{member_list_str}\t"
        )

        with st.expander(expander_title, expanded=False):
            # 轉為可編輯表格；若隊伍名稱帶有時間，新增以該時間為欄名之可參加勾選狀態
            rows_team = []
            added_col_name = time_label if time_label else None
            day_plain = time_label.split("(")[0] if time_label else None
            for m in team.get("member", []):
                row = {
                    "名稱": m.get("name", ""),
                    "職業": m.get("job", ""),
                    "等級": m.get("level", "")
                }
                if added_col_name and row["名稱"]:
                    # 與上方「已報名成員」使用相同的 plain 名稱鍵值
                    wa = _get_member_week_availability(row["名稱"], show_week)
                    row[added_col_name] = "✅" if wa.get(day_plain, False) else ""
                elif added_col_name:
                    row[added_col_name] = ""
                rows_team.append(row)

            base_cols = ["名稱","職業","等級"]
            columns = base_cols + ([added_col_name] if added_col_name else [])
            df_team = pd.DataFrame(rows_team, columns=columns)
            col_cfg = {
                "名稱": st.column_config.SelectboxColumn("名稱", options=all_member_names, required=False),
                "職業": st.column_config.TextColumn("職業", disabled=True),
                "等級": st.column_config.TextColumn("等級", disabled=True),
            }
            if added_col_name:
                col_cfg[added_col_name] = st.column_config.TextColumn(added_col_name, disabled=True)

            edited = st.data_editor(
                df_team,
                key=f"ai_team_editor_{show_week}_{idx}",
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                column_config=col_cfg,
                column_order=columns
            )

            # 即時帶出職業/等級與可參加（當列名稱變更時）
            if added_col_name and not edited.empty:
                wa_cache = {}
                def _get_wa_cached(nm: str) -> Dict[str, bool]:
                    if nm not in wa_cache:
                        wa_cache[nm] = _get_member_week_availability(nm, show_week)
                    return wa_cache[nm]
                for i_row in range(len(edited)):
                    nm = edited.at[i_row, "名稱"] if "名稱" in edited.columns else ""
                    if nm:
                        info = get_member_info_by_name(nm)
                        # 自動填職業/等級（僅當目前欄位為空再帶入，避免覆寫手動編輯）
                        if "職業" in edited.columns and not str(edited.at[i_row, "職業"]).strip():
                            edited.at[i_row, "職業"] = info.get("job", "")
                        if "等級" in edited.columns and not str(edited.at[i_row, "等級"]).strip():
                            edited.at[i_row, "等級"] = info.get("level", "")
                        wa = _get_wa_cached(nm)
                        if added_col_name in edited.columns:
                            edited.at[i_row, added_col_name] = "✅" if wa.get(day_plain, False) else ""

            c1, c2 = st.columns([1,1])
            if c1.button("💾 儲存此隊伍", key=f"ai_save_team_{show_week}_{idx}"):
                # 將名稱映射為 job/level，再寫回資料庫
                updated_members = []
                for _, r in edited.iterrows():
                    name = r.get("名稱")
                    if name:
                        info = get_member_info_by_name(name)
                        updated_members.append({
                            "name": info["name"],
                            "job": info["job"],
                            "level": info["level"],
                        })
                ai_data = load_ai_teams()
                safe_week = ai_data.get(show_week, [])
                # 確保索引存在
                while len(safe_week) <= idx:
                    safe_week.append({"team_name": f"AI自動分隊 {len(safe_week)+1}", "member": []})
                safe_week[idx]["team_name"] = team.get("team_name", f"AI自動分隊 {idx+1}")
                safe_week[idx]["member"] = updated_members
                ai_data[show_week] = safe_week
                save_ai_teams(ai_data)
                st.success("此隊伍已儲存至 AI 分隊資料表！")

            if c2.button("🗑️ 刪除此隊伍", key=f"ai_delete_team_{show_week}_{idx}"):
                ai_data = load_ai_teams()
                cur = ai_data.get(show_week, [])
                if idx < len(cur):
                    cur.pop(idx)
                    ai_data[show_week] = cur
                    save_ai_teams(ai_data)
                    st.success("此隊伍已刪除。")

    # --- 成員搜尋（僅當有 week_teams 時顯示）---
    st.markdown("---")
    st.subheader("查詢成員參加的隊伍")
    member_option = st.selectbox(
        "選擇成員名稱以查詢其所屬隊伍",
        options=all_member_names,
        index=0,
        key=f"member_search_{show_week}",
    )
    if member_option:
        joined = []
        for i, team in enumerate(week_teams, start=1):
            members = team.get("member", [])
            if any((m.get("name") or "") == member_option for m in members):
                team_name = team.get("team_name", f"AI自動分隊 {i}")
                time_label_raw = _parse_team_time_label(team_name)
                time_label_norm = _normalize_time_label_with_weekday(time_label_raw, week_start)
                display = time_label_norm if time_label_norm else team_name
                joined.append({"隊伍": f"第{i}隊", "時間/名稱": display})
        if joined:
            df_joined = pd.DataFrame(joined, columns=["隊伍", "時間/名稱"])
            st.dataframe(df_joined, use_container_width=True, hide_index=True)
        else:
            st.info("此成員尚未加入任何隊伍。")