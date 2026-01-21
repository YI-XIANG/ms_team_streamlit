import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import re
import json
import io
from typing import Tuple
import streamlit.components.v1 as components
from prompt import system_prompt

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, db as firebase_db

# --- 基礎設定 ---
st.set_page_config(layout="wide", page_title="楓之谷組隊系統", page_icon="🍁")

# --- 常數與設定 ---
MAX_TEAM_SIZE = 6
JOB_OPTIONS = {
    "🛡 劍士": ["龍騎士", "十字軍", "騎士"],
    "🏹 弓箭手": ["狙擊手", "遊俠"],
    "🗡 盜賊": ["暗殺者", "神偷"],
    "🏴‍☠️ 海盜": ["格鬥家", "槍神"],
    "🧙‍♂️ 法師": ["火毒", "冰雷", "祭司"]
}
JOB_SELECT_LIST = [job for sublist in JOB_OPTIONS.values() for job in sublist]
UNAVAILABLE_KEY = "__UNAVAILABLE__"
DUNGEON_OPTIONS = ["拉圖斯", "殘暴炎魔"]
DEFAULT_DUNGEON = DUNGEON_OPTIONS[0]


def normalize_dungeon(dungeon: str) -> str:
    """將輸入的副本名稱修正為合法值，預設為 DEFAULT_DUNGEON。"""
    if isinstance(dungeon, str) and dungeon in DUNGEON_OPTIONS:
        return dungeon
    return DEFAULT_DUNGEON

# --- 核心函式 ---

def _parse_firebase_url(full_url: str) -> Tuple[str, str]:
    """將 secrets 中的完整 RTDB URL 拆成 databaseURL 與 reference path。
    例如: https://example-default-rtdb.firebaseio.com/team_info ->
      (https://example-default-rtdb.firebaseio.com, /team_info)
    """
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
    """使用 Service Account 初始化 Firebase Admin（僅初始化一次）。"""
    if not firebase_admin._apps:
        service_account_info = dict(st.secrets["gcp_service_account"])  # from secrets.toml / cloud secrets
        database_url_full = st.secrets["firebase"]["url"]
        database_url_base, _ = _parse_firebase_url(database_url_full)
        cred = credentials.Certificate(service_account_info)
        firebase_admin.initialize_app(cred, {
            "databaseURL": database_url_base
        })

def _get_rtdb_ref():
    """回傳專案資料的 RTDB 參照。"""
    _init_firebase_admin_if_needed()
    database_url_full = st.secrets["firebase"]["url"]
    _, ref_path = _parse_firebase_url(database_url_full)
    return firebase_db.reference(ref_path)

def get_start_of_week(base_date: date) -> date:
    """計算給定日期所在週的星期四是哪一天。
    週期為星期四至星期三，不做額外跳週調整。
    """
    days_since_thu = (base_date.weekday() - 3) % 7
    start = base_date - timedelta(days=days_since_thu)
    return start

def get_default_schedule_for_week():
    """回傳一週行程的預設資料結構"""
    return {
        "proposed_slots": {},
        "availability": {UNAVAILABLE_KEY: []},
        "final_time": "",
    }


def _upgrade_dungeon_schema(data: dict):
    """資料升級：為隊伍與每週報名增加副本欄位，預設為 DEFAULT_DUNGEON。"""
    if not isinstance(data, dict):
        return {"teams": [], "members": {}}

    # 隊伍副本欄位
    for team in data.get("teams", []):
        team["dungeon"] = normalize_dungeon(team.get("dungeon", DEFAULT_DUNGEON))

    # 成員每週資料副本欄位（支援多副本）
    members = data.get("members", {})
    for _, info in members.items():
        fallback_dungeon = normalize_dungeon(info.get("weekly_dungeon", info.get("dungeon", DEFAULT_DUNGEON)))
        info["weekly_dungeon"] = fallback_dungeon
        weekly_data = info.get("weekly_data", {})
        if not isinstance(weekly_data, dict):
            info["weekly_data"] = {}
            continue
        for week_key, week_obj in list(weekly_data.items()):
            # 若不是 dict，直接重置
            if not isinstance(week_obj, dict):
                weekly_data[week_key] = {}
                continue

            # 若已是「多副本」結構（key 為副本名稱，value 為 dict）
            if any(isinstance(v, dict) and k in DUNGEON_OPTIONS for k, v in week_obj.items()):
                for dungeon_name, dungeon_obj in week_obj.items():
                    if not isinstance(dungeon_obj, dict):
                        week_obj[dungeon_name] = {}
                        dungeon_obj = week_obj[dungeon_name]
                    # 確保子物件內部結構存在
                    dungeon_obj.setdefault("availability", {})
                    dungeon_obj.setdefault("participation_count", "")
                    dungeon_obj.setdefault("last_updated", "")
                continue

            # 舊結構：單一物件，含 availability/participation_count/dungeon 等欄位
            dungeon_name = normalize_dungeon(week_obj.get("dungeon", fallback_dungeon))
            new_entry = {
                dungeon_name: {
                    "availability": week_obj.get("availability", {}),
                    "participation_count": week_obj.get("participation_count", ""),
                    "last_updated": week_obj.get("last_updated", ""),
                }
            }
            weekly_data[week_key] = new_entry

    return data


def load_data():
    """從 Firebase 載入、遷移並驗證資料結構（使用 Admin SDK）。"""
    try:
        ref = _get_rtdb_ref()
        data = ref.get()

        if data is None:
            return {"teams": [], "members": {}}

        data.setdefault("teams", [])
        data.setdefault("members", {})

        today = date.today()
        start_of_this_week = get_start_of_week(today)
        start_of_this_week_str = start_of_this_week.strftime('%Y-%m-%d')
        start_of_next_week_str = (start_of_this_week + timedelta(days=7)).strftime('%Y-%m-%d')
        valid_week_keys = {start_of_this_week_str, start_of_next_week_str}

        for team in data["teams"]:
            # 資料結構遷移：舊的 schedule -> 新的 schedules
            if "schedule" in team and "schedules" not in team:
                old_schedule = team.pop("schedule")
                start_date_key = old_schedule.pop("schedule_start_date", start_of_this_week_str)
                team["schedules"] = {start_date_key: old_schedule}

            team.setdefault("schedules", {})

            # 清理過期的週次資料
            current_schedules = team.get("schedules", {})
            managed_schedules = {key: value for key, value in current_schedules.items() if key in valid_week_keys}

            # ### 【健壯性優化】 ###
            # 確保本週與下週的行程資料存在且結構完整
            for week_key in valid_week_keys:
                if week_key not in managed_schedules:
                    managed_schedules[week_key] = get_default_schedule_for_week()
                else:
                    # 確保即使週次存在，其內部結構也是完整的
                    managed_schedules[week_key].setdefault("proposed_slots", {})
                    managed_schedules[week_key].setdefault("availability", {UNAVAILABLE_KEY: []})
                    managed_schedules[week_key].setdefault("final_time", "")

            team["schedules"] = managed_schedules

            # 資料結構遷移：舊的 boss_times -> 新的 team_remark
            if "boss_times" in team and "team_remark" not in team:
                team["team_remark"] = team.pop("boss_times")
            else:
                team.setdefault("team_remark", "")

        # 升級資料結構：加入副本欄位
        return _upgrade_dungeon_schema(data)

    except Exception as e:
        st.error(f"❌ 載入資料時發生未預期的錯誤：{e}, {e.__traceback__.tb_lineno}")

    return {"teams": [], "members": {}}

def save_data(data):
    """將資料儲存到 Firebase（使用 Admin SDK）。"""
    try:
        ref = _get_rtdb_ref()
        # 直接 set Python 物件，Admin SDK 會處理序列化
        ref.set(data)
    except Exception as e:
        st.error(f"❌ 儲存資料時發生未預期的錯誤：{e}")

def build_team_text(team):
    """產生用於複製到 Discord 的隊伍資訊文字"""
    today = date.today()
    start_of_this_week_str = get_start_of_week(today).strftime('%Y-%m-%d')
    this_week_schedule = team.get('schedules', {}).get(start_of_this_week_str, {})
    final_time = this_week_schedule.get('final_time', '')
    time_display = final_time if final_time else "時間待定"
    dungeon = normalize_dungeon(team.get("dungeon", DEFAULT_DUNGEON))
    remark = team.get('team_remark', '')

    title = f"【{team['team_name']} 徵人】"
    dungeon_line = f"副本：{dungeon}"
    time = f"時間：{time_display}"
    remark_text = f"備註：{remark}" if remark else ""

    current_members = [m for m in team.get("member", []) if m.get("name")]
    members_lines = [
        f"{i}. {member.get('level','')} {member.get('job','')} {member.get('name')}".strip()
        for i, member in enumerate(current_members, 1)
    ]
    member_text = "✅ 目前成員：\n" + "\n".join(members_lines) if members_lines else ""

    missing_count = MAX_TEAM_SIZE - len(current_members)
    missing_text = f"📋 尚缺 {missing_count} 人，歡迎私訊！" if missing_count > 0 else "🎉 隊伍已滿，可先排後補！"

    return "\n\n".join(filter(None, [title, dungeon_line, time, remark_text, member_text, missing_text])).strip()

def render_global_weekly_availability():
    """Render 本週與下週可參加名單（唯讀）。"""
    st.markdown("---")
    st.subheader("全局：本週與下週可參加名單（唯讀）")
    today = date.today()
    start_this = get_start_of_week(today)
    this_range = f"{start_this.strftime('%m/%d')} ~ {(start_this + timedelta(days=6)).strftime('%m/%d')}"
    next_start = start_this + timedelta(days=7)
    next_range = f"{next_start.strftime('%m/%d')} ~ {(next_start + timedelta(days=6)).strftime('%m/%d')}"
    label_this = f"本週({this_range})"
    label_next = f"下週({next_range})"
    week_view = st.radio("檢視週次", [label_this, label_next], horizontal=True)
    week_start = start_this if week_view == label_this else start_this + timedelta(days=7)
    week_days = generate_weekly_schedule_days(week_start)

    rows = []
    for name, info in st.session_state.data.get("members", {}).items():
        wa = info.get("weekly_availability", {})
        # 只顯示在該週內有填寫的成員資訊
        if not any(wa.get(d, False) for d in week_days):
            continue
        row = {"名稱": name, "職業": info.get("job", ""), "等級": info.get("level", "")}
        mapping = {
            week_days[0]: "星期四",
            week_days[1]: "星期五",
            week_days[2]: "星期六",
            week_days[3]: "星期日",
            week_days[4]: "星期一",
            week_days[5]: "星期二",
            week_days[6]: "星期三",
        }
        for label in week_days:
            wk = mapping[label]
            row[label] = "✅" if wa.get(wk, False) else ""
        rows.append(row)
    df_week = pd.DataFrame(rows, columns=["名稱","職業","等級"] + week_days)
    if not df_week.empty:
        st.dataframe(df_week, width="stretch")
    else:
        st.info("本週尚無成員勾選可參加日期。")
    return

def get_week_range(base_date: date) -> str:
    """產生週次的日期範圍字串，例如 '08/14 ~ 08/20'"""
    start_of_week = get_start_of_week(base_date)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%m/%d')} ~ {end_of_week.strftime('%m/%d')}"

def generate_weekly_schedule_days(start_date: date) -> list[str]:
    """根據開始日期產生一週七天的字串列表"""
    start_of_week = get_start_of_week(start_date)
    weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
    schedule_days = [
        f"星期{weekdays_zh[(start_of_week + timedelta(days=i)).weekday()]} ({(start_of_week + timedelta(days=i)).strftime('%m-%d')})"
        for i in range(7)
    ]
    return schedule_days

def dataframe_to_markdown(df: pd.DataFrame) -> str:
    """將 DataFrame 轉成 Markdown 表格字串，供 prompt 使用。"""
    if df.empty:
        return ""
    columns = df.columns.tolist()
    header = "| " + " | ".join(columns) + " |"
    separator = "| " + " | ".join("---" for _ in columns) + " |"
    rows = []
    for row in df.itertuples(index=False):
        cells = [
            "" if pd.isna(value) else str(value)
            for value in row
        ]
        rows.append("| " + " | ".join(cells) + " |")
    return "\n".join([header, separator] + rows)

def build_prompt_from_table(df: pd.DataFrame) -> str:
    """套入 Markdown 內容並回傳最終 prompt 文案。"""
    markdown_table = dataframe_to_markdown(df)
    if not markdown_table:
        markdown_table = "目前無顯示成員資料。"
    return system_prompt.format(markdown=markdown_table)

@st.dialog("下載人員手冊")
def download_members_csv():
    """彈跳視窗：輸入密碼下載人員手冊"""
    st.write("請輸入管理員密碼以下載完整人員手冊：")
    
    password = st.text_input("密碼", type="password", key="download_password")
    
    col1, col2 = st.columns(2)
    
    if col1.button("下載", type="primary", width="stretch"):
        # 這裡可以自訂密碼，建議從 secrets 讀取
        correct_password = st.secrets.get("download_password", st.secrets["setting"]["pwd"])
        
        if password == correct_password:
            # 準備 CSV 資料
            all_members = st.session_state.data.get("members", {})
            if all_members:
                members_data = []
                for name, info in all_members.items():
                    members_data.append({
                        "遊戲ID": name,
                        "職業": info.get("job", ""),
                        "等級": info.get("level", ""),
                        "表攻": info.get("atk", ""),
                        "公會成員": "是" if info.get("is_guild_member", True) else "否"
                    })
                
                df = pd.DataFrame(members_data)
                
                # 轉換為 CSV
                csv_buffer = io.StringIO()
                df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
                csv_data = csv_buffer.getvalue()
                
                # 產生檔案名稱
                current_date = datetime.now().strftime("%Y%m%d")
                filename = f"楓之谷公會成員名冊_{current_date}.csv"
                
                st.download_button(
                    label="📥 下載 CSV 檔案",
                    data=csv_data,
                    file_name=filename,
                    mime="text/csv",
                    width="stretch"
                )
                st.success("密碼正確！請點擊上方按鈕下載檔案。")
            else:
                st.warning("目前沒有成員資料可供下載。")
        else:
            st.error("密碼錯誤，請重新輸入。")
    
    if col2.button("取消", width="stretch"):
        st.rerun()


# --- 初始化 Session State & 同步函式 ---
if "data" not in st.session_state:
    st.session_state.data = load_data()

if "team_view_week" not in st.session_state:
    st.session_state.team_view_week = {}

def sync_data_and_save():
    """將 session state 中的資料儲存到 Firebase"""
    save_data(st.session_state.data)

# --- UI 介面 ---
st.title("🍁 Monarchs 公會組隊系統")


# 快速導航
st.subheader(f"🚀本週區間：{get_week_range(date.today())} ")
col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **👤 註冊角色**  
    建立你的遊戲角色資料，包含職業、等級、表攻等資訊
    """)

with col2:
    st.markdown("""
    **📋 手動分隊**  
    建立和管理隊伍，手動安排成員加入
    """)

st.markdown("---")

# ------ 註冊功能 ------
st.header("👤 公會成員表")
if "profile_expander_open" not in st.session_state:
    st.session_state.profile_expander_open = False
with st.expander("點此註冊或更新你的個人資料", expanded=st.session_state.profile_expander_open):
    all_members = st.session_state.data.get("members", {})

    # 選單選擇既有ID後自動帶入到輸入框（放在表單外，避免 on_change 限制）
    def _on_pick_existing_member():
        picked = st.session_state.get("member_id_select_existing", "")
        if picked and picked != "<創建成員>":
            st.session_state["member_id_input_main"] = picked
        else:
            # 進入新建模式：清空欄位
            st.session_state["member_id_input_main"] = ""
        st.session_state.profile_expander_open = True

    member_options = sorted(list(all_members.keys()))
    st.selectbox(
        "從名單選擇（將自動帶入下方輸入框）",
        options=["<創建成員>"] + member_options,
        key="member_id_select_existing",
        on_change=_on_pick_existing_member,
    )

    with st.form("member_form", clear_on_submit=False):
        c1, c2, c3, c4, c5 = st.columns([2, 2, 1, 1, 1])
        # 遊戲ID：選到既有成員時不可編輯；創建模式可輸入
        member_id_input = c1.text_input("遊戲ID", key="member_id_input_main", disabled=st.session_state.get("member_id_input_main", "") in all_members)
        selected_member_name = member_id_input if member_id_input in all_members else ""
        default_info = all_members.get(selected_member_name, {"job": "", "level": "", "atk": "", "is_guild_member": True})
        job_index = JOB_SELECT_LIST.index(default_info.get("job", "")) if default_info.get("job") in JOB_SELECT_LIST else 0
        job_input = c2.selectbox("職業", options=JOB_SELECT_LIST, index=job_index, disabled=False)
        level_input = c3.text_input("等級", value=default_info.get("level", ""))
        atk_input = c4.text_input("表攻 (乾表)", value=default_info.get("atk", ""))
        is_guild_member = c5.checkbox("公會成員", value=default_info.get("is_guild_member", True), help="勾選表示為公會正式成員")

        st.markdown("---")
        btn_cols = st.columns([3, 1])
        if btn_cols[0].form_submit_button("💾 儲存角色資料", width="stretch"):
            final_name = (member_id_input or "").strip()
            if not final_name:
                st.warning("請務必填寫遊戲ID！")
            else:
                member_dict = st.session_state.data.setdefault("members", {}).get(final_name, {})
                # 僅儲存基本資料（不動每週報名資料）
                member_dict.update({
                    "job": job_input,
                    "level": level_input,
                    "atk": atk_input,
                    "is_guild_member": is_guild_member,
                })
                st.session_state.data["members"][final_name] = member_dict
                sync_data_and_save()
                st.success(f"角色 '{final_name}' 的資料已儲存！")
                st.session_state.profile_expander_open = True
                st.rerun()

        if selected_member_name and btn_cols[1].form_submit_button("🗑️ 刪除此角色", width="stretch"):
            del st.session_state.data["members"][selected_member_name]
            # 同步刪除隊伍中的成員
            for team_idx in range(len(st.session_state.data['teams'])):
                st.session_state.data['teams'][team_idx]['member'] = [
                    m for m in st.session_state.data['teams'][team_idx].get('member', []) if m.get('name') != selected_member_name
                ]
            sync_data_and_save()
            st.success(f"角色 '{selected_member_name}' 已從名冊中刪除！")
            st.session_state.profile_expander_open = True
            st.rerun()

    # 下載功能放在表單外面
    st.markdown("---")
    if st.button("📥 下載人員手冊", type="secondary", help="需要管理員密碼"):
        download_members_csv()

st.markdown("---")

# ------ 每週報名（快速） ------
st.header("📅 每週報名")
signup_cols = st.columns([1, 1, 1, 1])
all_members = st.session_state.data.get("members", {})

# 快速選擇ID（搜尋 + 記住上次選擇）
default_member_idx = 0
member_keys_sorted = sorted(list(all_members.keys()))
if "last_signup_member" in st.session_state and st.session_state["last_signup_member"] in member_keys_sorted:
    default_member_idx = member_keys_sorted.index(st.session_state["last_signup_member"]) + 1

selected_member_for_signup = signup_cols[0].selectbox(
    "選擇你的遊戲ID（若無請先於上方註冊）",
    options=[""] + member_keys_sorted,
    index=default_member_idx,
    key="weekly_signup_member_select",
    help="此處只需選擇ID並勾選可參加的時間與次數"
)

this_range_q = f"{get_start_of_week(date.today()).strftime('%m/%d')} ~ {(get_start_of_week(date.today()) + timedelta(days=6)).strftime('%m/%d')}"
next_start_q = get_start_of_week(date.today()) + timedelta(days=7)
next_range_q = f"{next_start_q.strftime('%m/%d')} ~ {(next_start_q + timedelta(days=6)).strftime('%m/%d')}"
label_this_q = f"本週({this_range_q})"
label_next_q = f"下週({next_range_q})"
week_choice_quick = signup_cols[1].radio("週次", [label_this_q, label_next_q], horizontal=True, key="weekly_signup_week_choice")

start_thu_quick = get_start_of_week(date.today()) if week_choice_quick == label_this_q else (get_start_of_week(date.today()) + timedelta(days=7))
week_key_quick = start_thu_quick.strftime('%Y-%m-%d')

def _get_member_default_dungeon(info_dict, week_key):
    """取得成員在該週的預設副本選擇。"""
    if not isinstance(info_dict, dict):
        return DEFAULT_DUNGEON
    weekly_data = info_dict.get("weekly_data", {}) if isinstance(info_dict.get("weekly_data", {}), dict) else {}
    week_entry = weekly_data.get(week_key)
    # 新結構：week_entry 為 { dungeon_name: {...} }
    if isinstance(week_entry, dict) and any(k in DUNGEON_OPTIONS for k in week_entry.keys()):
        # 若只有一個副本，就用它；多個則優先使用 DEFAULT_DUNGEON，否則任一
        dungeon_keys = list(week_entry.keys())
        if len(dungeon_keys) == 1:
            return normalize_dungeon(dungeon_keys[0])
        if DEFAULT_DUNGEON in dungeon_keys:
            return DEFAULT_DUNGEON
        return normalize_dungeon(dungeon_keys[0])
    # 舊結構：單一物件含 dungeon 欄位
    if isinstance(week_entry, dict) and "dungeon" in week_entry:
        return normalize_dungeon(week_entry.get("dungeon", DEFAULT_DUNGEON))
    if "weekly_dungeon" in info_dict:
        return normalize_dungeon(info_dict.get("weekly_dungeon"))
    return DEFAULT_DUNGEON

dungeon_default_selection = DEFAULT_DUNGEON

dungeon_default_selection = DEFAULT_DUNGEON

if selected_member_for_signup:
    st.session_state["last_signup_member"] = selected_member_for_signup

    # 預設參與次數
    info_q = all_members.get(selected_member_for_signup, {})
    dungeon_default_selection = _get_member_default_dungeon(info_q, week_key_quick)
    dungeon_choice_idx = DUNGEON_OPTIONS.index(dungeon_default_selection) if dungeon_default_selection in DUNGEON_OPTIONS else 0
    dungeon_choice = signup_cols[2].selectbox(
        "副本",
        options=DUNGEON_OPTIONS,
        index=dungeon_choice_idx,
        key=f"weekly_signup_dungeon_{selected_member_for_signup}",  # 切換週次時保留當前使用者選擇
    )
    _wdata_q = info_q.get("weekly_data", {}) if isinstance(info_q.get("weekly_data", {}), dict) else {}
    week_entry_q = _wdata_q.get(week_key_quick, {}) if isinstance(_wdata_q.get(week_key_quick, {}), dict) else {}
    dungeon_entry_q = week_entry_q.get(dungeon_choice, {}) if isinstance(week_entry_q, dict) else {}
    if str(dungeon_entry_q.get("participation_count", "")).isdigit():
        participation_default_q = int(dungeon_entry_q.get("participation_count", 1))
    elif str(info_q.get("weekly_participation_count", "")).isdigit():
        participation_default_q = int(info_q.get("weekly_participation_count", 1))
    else:
        participation_default_q = 1

    participation_count_q = signup_cols[3].selectbox(
        "參與次數",
        options=[1, 2],
        index=[1, 2].index(participation_default_q),
        key=f"weekly_signup_participation_{selected_member_for_signup}_{week_key_quick}_{dungeon_choice}",
    )

    # 日期勾選（快速）
    day_names_q = ["星期四", "星期五", "星期六", "星期日", "星期一", "星期二", "星期三"]
    days_q = [(start_thu_quick + timedelta(days=i), day_names_q[i]) for i in range(7)]

    # 預設值（依該成員該週資料）
    weekly_default_q = {}
    if isinstance(week_entry_q, dict) and dungeon_choice in week_entry_q:
        weekly_default_q = week_entry_q.get(dungeon_choice, {}).get("availability", {}) or {}

    cols_q = st.columns(7)
    weekly_availability_q = {}
    for i, (d, label) in enumerate(days_q):
        weekly_availability_q[label] = cols_q[i].checkbox(
            f"{label}\n{d.strftime('%m/%d')}",
            value=bool(weekly_default_q.get(label, False)),
            key=f"weekly_q_{selected_member_for_signup}_{week_key_quick}_{dungeon_choice}_{label}",
        )

    if st.button("📨 送出本次報名", type="primary", width="stretch"):
        now_iso_q = datetime.now().isoformat(timespec="seconds")
        member_dict_q = st.session_state.data.setdefault("members", {}).get(selected_member_for_signup, {})
        weekly_data_q = member_dict_q.setdefault("weekly_data", {})
        week_entry_save = weekly_data_q.setdefault(week_key_quick, {})
        # 驗證：本週所有副本的次數總和不可超過 2
        if isinstance(week_entry_save, dict):
            old_pc_current = week_entry_save.get(dungeon_choice, {}).get("participation_count", 0) or 0
            other_total = 0
            for d_name, d_obj in week_entry_save.items():
                if d_name == dungeon_choice or not isinstance(d_obj, dict):
                    continue
                val = d_obj.get("participation_count", 0) or 0
                try:
                    other_total += int(val)
                except Exception:
                    continue
            try:
                new_pc_int = int(participation_count_q)
            except Exception:
                new_pc_int = 0
            # 先扣掉舊的，再加上新的
            total_after = other_total + new_pc_int
            if total_after > 2:
                st.error("本週所有副本的報名次數總和不可超過 2，請調整後再送出。")
                st.stop()

        # 寫入目前副本資料
        week_entry_save[dungeon_choice] = {
            "availability": weekly_availability_q,
            "participation_count": participation_count_q,
            "last_updated": now_iso_q,
        }
        # 舊欄位同步（相容）
        member_dict_q.update({
            "weekly_availability": weekly_availability_q,
            "weekly_last_updated": now_iso_q,
            "weekly_week_start": week_key_quick,
            "weekly_participation_count": participation_count_q,
            "weekly_dungeon": dungeon_choice,
        })
        st.session_state.data["members"][selected_member_for_signup] = member_dict_q
        sync_data_and_save()
        st.success("✅ 已送出報名！")
        st.rerun()


st.markdown("---")

st.subheader("🙋已報名成員")
today = date.today()
start_this = get_start_of_week(today)
this_range_l = f"{start_this.strftime('%m/%d')} ~ {(start_this + timedelta(days=6)).strftime('%m/%d')}"
next_start_l = start_this + timedelta(days=7)
next_range_l = f"{next_start_l.strftime('%m/%d')} ~ {(next_start_l + timedelta(days=6)).strftime('%m/%d')}"
label_this_l = f"本週({this_range_l})"
label_next_l = f"下週({next_range_l})"
list_cols = st.columns([2, 1])
list_week_choice = list_cols[0].radio("顯示週次", [label_this_l, label_next_l], horizontal=True, key="list_week_choice")
dungeon_filter = list_cols[1].selectbox("副本", options=["全部"] + DUNGEON_OPTIONS, key="list_dungeon_filter")
week_start = start_this if list_week_choice == label_this_l else start_this + timedelta(days=7)
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

rows = []
show_week = week_start.strftime('%Y-%m-%d')
for name, info in st.session_state.data.get("members", {}).items():
    # 優先從 weekly_data 讀取該週資料
    weekly_data = info.get("weekly_data", {}) if isinstance(info.get("weekly_data", {}), dict) else {}
    week_obj = weekly_data.get(show_week)

    # 沒有週資料時，嘗試使用舊欄位（僅支援單副本舊資料）
    if not isinstance(week_obj, dict) or not week_obj:
        if info.get("weekly_week_start") != show_week:
            continue
        wa = info.get("weekly_availability", {}) or {}
        pc = info.get("weekly_participation_count", "")
        dungeon_val = normalize_dungeon(info.get("weekly_dungeon", DEFAULT_DUNGEON))
        if dungeon_filter != "全部" and dungeon_val != dungeon_filter:
            continue
        if not any(bool(wa.get(p, False)) for p in weekday_plain):
            continue
        participation_count_str = "" if pc in (None, "") else str(pc)
        row = {
            "名稱": name,
            "職業": str(info.get("job", "")),
            "等級": str(info.get("level", "")),
            "副本": dungeon_val,
            "次數": participation_count_str
        }
        for plain, label in zip(weekday_plain, weekday_labels):
            row[label] = "✅" if wa.get(plain, False) else ""
        rows.append(row)
        continue

    # 新結構：同一週可有多個副本
    for dungeon_key, dungeon_obj in week_obj.items():
        if not isinstance(dungeon_obj, dict):
            continue
        dungeon_val = normalize_dungeon(dungeon_key or dungeon_obj.get("dungeon", DEFAULT_DUNGEON))
        if dungeon_filter != "全部" and dungeon_val != dungeon_filter:
            continue
        wa = dungeon_obj.get("availability", {}) or {}
        pc = dungeon_obj.get("participation_count", "")
        if not any(bool(wa.get(p, False)) for p in weekday_plain):
            continue
        participation_count_str = "" if pc in (None, "") else str(pc)
        row = {
            "名稱": name,
            "職業": str(info.get("job", "")),
            "等級": str(info.get("level", "")),
            "副本": dungeon_val,
            "次數": participation_count_str
        }
        for plain, label in zip(weekday_plain, weekday_labels):
            row[label] = "✅" if wa.get(plain, False) else ""
        rows.append(row)

df_members = pd.DataFrame(rows, columns=["名稱","職業","等級","副本","次數"] + weekday_labels)
st.dataframe(df_members, width="stretch", hide_index=True)

st.markdown("---")
ai_prompt_text = build_prompt_from_table(df_members)
st.subheader("🤖 AI 分隊提示詞")
st.caption("可複製下方文字並貼到分隊協作提示中，內容已包含目前本週顯示的成員資訊。")
if "latus_prompt_triggered" not in st.session_state:
    st.session_state.latus_prompt_triggered = False

def _get_latus_prompt(df: pd.DataFrame) -> Tuple[str, pd.DataFrame]:
    """只保留拉圖斯資料並產生對應 Prompt。"""
    if df.empty:
        return "", df
    latus_df = df[df["副本"] == "拉圖斯"]
    prompt_text = build_prompt_from_table(latus_df)
    return prompt_text, latus_df

with st.container():
    prompt_btn_cols = st.columns([3, 2])
    if prompt_btn_cols[0].button("產生拉圖斯分隊", width="stretch"):
        prompt_text, _ = _get_latus_prompt(df_members)
        st.session_state.latus_prompt = prompt_text
        st.session_state.latus_prompt_triggered = True

    if st.session_state.get("latus_prompt_triggered") and st.session_state.get("latus_prompt"):
        prompt_to_copy = st.session_state.latus_prompt
        safe_prompt = json.dumps(prompt_to_copy)
        components.html(
            f"""
            <div style="display:flex;align-items:center;gap:0.5rem;">
              <button id="copyPrompt" style="padding:0.35rem 1rem;border:none;border-radius:4px;background:#0b6cf3;color:#fff;font-weight:600;cursor:pointer;">
                複製拉圖斯分隊 Prompt
              </button>
              <span id="copyStatus" style="font-size:0.85rem;color:#008000;"></span>
            </div>
            <script>
            const textToCopy = {safe_prompt};
            const btn = document.getElementById("copyPrompt");
            const statusEl = document.getElementById("copyStatus");
            btn.addEventListener("click", () => {{
                navigator.clipboard.writeText(textToCopy).then(() => {{
                    statusEl.textContent = "已複製，可貼到 prompt 內。";
                }}).catch(() => {{
                    statusEl.textContent = "瀏覽器無法自動複製，請手動 Ctrl+C。";
                }});
            }});
            </script>
            """,
            height=70,
        )
