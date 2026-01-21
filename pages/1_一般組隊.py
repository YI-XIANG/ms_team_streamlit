import json
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
from typing import Tuple

# Firebase Admin SDK
import firebase_admin
from firebase_admin import credentials, db as firebase_db

MAX_TEAM_SIZE = 6
UNAVAILABLE_KEY = "__UNAVAILABLE__"


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
        service_account_info = dict(st.secrets["gcp_service_account"])  # from secrets.toml / cloud secrets
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


def get_start_of_week(base_date: date) -> date:
    days_since_thu = (base_date.weekday() - 3) % 7
    return base_date - timedelta(days=days_since_thu)


def get_default_schedule_for_week():
    return {
        "proposed_slots": {},
        "availability": {UNAVAILABLE_KEY: []},
    }


def load_data():
    try:
        ref = _get_rtdb_ref()
        data = ref.get() or {"teams": [], "members": {}}
        data.setdefault("teams", [])
        data.setdefault("members", {})
        return data
    except Exception as e:
        st.error(f"❌ 載入資料時發生未預期的錯誤：{e}")
        return {"teams": [], "members": {}}


def save_data(data):
    try:
        ref = _get_rtdb_ref()
        ref.set(data)
    except Exception as e:
        st.error(f"❌ 儲存資料時發生未預期的錯誤：{e}")


def build_team_text(team):
    today = date.today()
    start_of_this_week_str = get_start_of_week(today).strftime('%Y-%m-%d')
    remark = team.get('team_remark', '')
    time_display = remark if remark else "時間待定"
    title = f"【{team['team_name']} 徵人】"
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
    return "\n\n".join(filter(None, [title, time, remark_text, member_text, missing_text])).strip()


def get_week_range(base_date: date) -> str:
    start_of_week = get_start_of_week(base_date)
    end_of_week = start_of_week + timedelta(days=6)
    return f"{start_of_week.strftime('%m/%d')} ~ {end_of_week.strftime('%m/%d')}"


def generate_weekly_schedule_days(start_date: date) -> list[str]:
    start_of_week = get_start_of_week(start_date)
    weekdays_zh = ["一", "二", "三", "四", "五", "六", "日"]
    schedule_days = [
        f"星期{weekdays_zh[(start_of_week + timedelta(days=i)).weekday()]} ({(start_of_week + timedelta(days=i)).strftime('%m-%d')})"
        for i in range(7)
    ]
    return schedule_days


WEEKDAY_PLAIN = ["星期四", "星期五", "星期六", "星期日", "星期一", "星期二", "星期三"]


def get_weekday_label_pairs(start_date: date) -> Tuple[list[str], list[str]]:
    weekday_with_date = [
        f"{label}({(start_date + timedelta(days=i)).strftime('%m/%d')})"
        for i, label in enumerate(WEEKDAY_PLAIN)
    ]
    return WEEKDAY_PLAIN, weekday_with_date


def _get_member_weekly_availability(name: str, members_data: dict, week_key: str) -> tuple[dict, dict]:
    base_info = members_data.get(name, {}) if isinstance(members_data, dict) else {}
    weekly_data = base_info.get("weekly_data", {}) if isinstance(base_info.get("weekly_data", {}), dict) else {}
    if week_key in weekly_data:
        availability = weekly_data.get(week_key, {}).get("availability", {}) or {}
    elif base_info.get("weekly_week_start") == week_key:
        availability = base_info.get("weekly_availability", {}) or {}
    else:
        availability = {}
    return base_info, availability


def _normalize_member_payload(member) -> dict:
    if isinstance(member, dict):
        name = str(member.get("name", "") or "")
        job = str(member.get("job", "") or "")
        level = str(member.get("level", "") or "")
        atk = str(member.get("atk", "") or "")
    elif isinstance(member, (list, tuple)):
        name = str(member[0]) if len(member) >= 1 else ""
        job = str(member[1]) if len(member) >= 2 else ""
        level = str(member[2]) if len(member) >= 3 else ""
        atk = str(member[3]) if len(member) >= 4 else ""
    else:
        name = job = level = atk = ""
    return {"name": name, "job": job, "level": level, "atk": atk}


def _extract_day_label(time_label: str) -> str:
    clean_label = (time_label or "").split("(", 1)[0].strip()
    return clean_label or time_label or ""


def _is_member_available_on_day(name: str, members_data: dict, week_key: str, day_label: str) -> bool:
    if not name or not day_label:
        return False
    _, availability = _get_member_weekly_availability(name, members_data, week_key)
    return bool(availability.get(day_label))


def _build_uploaded_member_rows(normalized_teams: list[dict], members_data: dict, week_key: str) -> tuple[list[dict], list[str]]:
    time_columns: list[str] = []
    for team in normalized_teams:
        label = team.get("time_label", "")
        if label and label not in time_columns:
            time_columns.append(label)

    rows: list[dict] = []
    for team in normalized_teams:
        time_label = team.get("time_label", "")
        day_label = _extract_day_label(time_label)
        for slot_index, member_entry in enumerate(team.get("members", [])):
            name = str(member_entry.get("name", "") or "")
            job = members_data.get(name, {}).get("job") or member_entry.get("job", "")
            row = {
                "team_id": team.get("team_id", 0),
                "slot_index": slot_index,
                "隊伍名稱": team.get("team_name", f"隊伍 {team.get('team_id', slot_index)+1}"),
                "時間": time_label or "時間待定",
                "名稱": name,
                "職業": job,
            }
            for time_col in time_columns:
                row[time_col] = ""
            if time_label and time_label in time_columns:
                row[time_label] = "✅" if _is_member_available_on_day(name, members_data, week_key, day_label) else ""
            rows.append(row)

    return rows, time_columns


def parse_uploaded_team_payload(payload: dict) -> list[dict]:
    raw_team_list = payload.get("隊伍") or payload.get("teams") or []
    normalized = []
    for idx, raw_team in enumerate(raw_team_list):
        if not isinstance(raw_team, dict):
            continue
        time_label = raw_team.get("時間") or raw_team.get("time") or f"第{idx+1}組"
        members = raw_team.get("成員") or raw_team.get("members") or []
        normalized_members = [_normalize_member_payload(m) for m in members if m is not None]
        normalized_members = normalized_members[:MAX_TEAM_SIZE]
        while len(normalized_members) < MAX_TEAM_SIZE:
            normalized_members.append({"name": "", "job": "", "level": "", "atk": ""})
        normalized.append({
            "team_name": f"第{idx+1}組",
            "time_label": time_label,
            "members": normalized_members,
            "team_id": idx
        })
    return normalized

st.set_page_config(layout="wide", page_title="楓之谷組隊系統", page_icon="🍁")
st.title("📋 手動分組")

# 系統說明
st.info("💡 **手動分隊**：建立和管理隊伍，手動安排成員加入，適合精確控制隊伍配置")

data = load_data()
teams = data.get("teams", [])
all_members = data.get("members", {})

today = date.today()
start_of_this_week = get_start_of_week(today)
start_of_this_week_str = start_of_this_week.strftime('%Y-%m-%d')
start_of_next_week_str = (start_of_this_week + timedelta(days=7)).strftime('%Y-%m-%d')

if "uploaded_normalized_teams" not in st.session_state:
    st.session_state.uploaded_normalized_teams = []
if "uploaded_team_data_key" not in st.session_state:
    st.session_state.uploaded_team_data_key = ""

# 搜尋功能
st.subheader("🔍 成員隊伍查詢")
member_names_for_search = [""] + sorted(list(all_members.keys()))
selected_member_for_search = st.selectbox(
    "選擇成員查看其參與的隊伍",
    member_names_for_search,
    key="member_search_manual",
    help="快速查詢特定成員目前參與的所有隊伍"
)

if selected_member_for_search:
    # 查找該成員參與的所有隊伍
    participating_teams = []
    for idx, team in enumerate(teams):
        team_members = [m.get("name", "") for m in team.get("member", [])]
        if selected_member_for_search in team_members:
            # 獲取該成員在隊伍中的詳細資訊
            member_info = next((m for m in team.get("member", []) if m.get("name") == selected_member_for_search), {})
            participating_teams.append({
                "隊伍名稱": team.get("team_name", f"隊伍 {idx+1}"),
                "職業": member_info.get("job", ""),
                "隊伍編號": f"第{idx+1}隊"
            })
    
    if participating_teams:
        df_participating = pd.DataFrame(participating_teams)
        st.dataframe(df_participating, width="stretch", hide_index=True)
        st.success(f"✅ 找到 {len(participating_teams)} 個隊伍包含 {selected_member_for_search}")
    else:
        st.info(f"ℹ️ {selected_member_for_search} 目前沒有參與任何隊伍")

st.markdown("---")

st.subheader("📥 上傳 `teams.json` 並微調組隊順序")
st.write("請上傳符合 `teams.json` 結構的檔案，即可依照原始分組快速產生六人一組的視覺卡片。完成後可在下方表格拖曳重新排序或調整排序數字，快速微調組別呈現位置。")
uploaded_json = st.file_uploader("選擇上傳的 JSON 檔", type="json", key="uploaded_team_json", help="JSON 格式範例請參考 `teams.json`。", label_visibility="visible")

def _display_uploaded_groups(editable_df, normalized_teams, members_data, week_start_date):
    sorted_df = editable_df.sort_values("排序").reset_index(drop=True)
    if sorted_df.empty:
        st.warning("目前沒有有效的組別資料。")
        return
    st.caption("拖曳表格左側把手即可重新排列顯示順序；或手動修改「排序」數字做細部調整。卡片會由上而下顯示。")
    for _, row in sorted_df.iterrows():
        team_id = int(row["team_id"])
        team = normalized_teams[team_id]
        current_members = [m for m in team["members"] if m.get("name")]
        missing_count = MAX_TEAM_SIZE - len(current_members)
        status = "🎉 已滿員" if missing_count == 0 else f"⏳ 尚缺 {missing_count} 人"
        st.markdown(f"**{team['team_name']}｜{team['time_label']}**")
        st.metric("狀態", status)
        member_rows = []
        week_key = week_start_date.strftime("%Y-%m-%d")
        assigned_day = team["time_label"].split("(", 1)[0].strip()
        for member in team["members"]:
            name = (member.get("name") or "").strip()
            display_name = name if name else "尚未填入"
            base_info, availability = _get_member_weekly_availability(name, members_data, week_key) if name else ({}, {})
            job = base_info.get("job", member.get("job", ""))
            assigned_date_display = team["time_label"]
            matches_day = bool(assigned_day and availability.get(assigned_day, False))
            date_text = f"{assigned_date_display} {'✅' if matches_day else ''}".strip()
            member_rows.append({
                "名稱": display_name,
                "職業": job,
                "日期": date_text,
            })
        st.caption("六人一組 · 可再拖曳排序以微調顯示位置；日期欄位會比對資料庫中的可參加日。")
        if member_rows:
            st.dataframe(pd.DataFrame(member_rows), use_container_width=True, hide_index=True)
        else:
            st.info("尚未填入任何成員名單")
        st.divider()


def _save_uploaded_member_changes(edited_df: pd.DataFrame, metadata_rows: list[dict], members_data: dict):
    updated_records = edited_df.to_dict("records")
    if not updated_records or len(updated_records) != len(metadata_rows):
        st.error("資料列數異常，請重新開啟頁面後再試一次。")
        return
    normalized_teams = st.session_state.get("uploaded_normalized_teams", [])
    if not normalized_teams:
        st.error("找不到可調整的隊伍資料，請重新上傳。")
        return

    changes_applied = 0
    for meta, row in zip(metadata_rows, updated_records):
        team_idx = meta.get("team_id", -1)
        slot_idx = meta.get("slot_index", -1)
        if not isinstance(team_idx, int) or not isinstance(slot_idx, int):
            continue
        if team_idx < 0 or team_idx >= len(normalized_teams):
            continue
        team_entry = normalized_teams[team_idx]
        members_list = team_entry.get("members", [])
        if slot_idx < 0 or slot_idx >= len(members_list):
            continue
        name = (row.get("名稱") or "").strip()
        fallback_member = members_list[slot_idx]
        member_info = members_data.get(name, {})
        members_list[slot_idx] = {
            "name": name,
            "job": member_info.get("job", fallback_member.get("job", "")),
            "level": member_info.get("level", fallback_member.get("level", "")),
            "atk": member_info.get("atk", fallback_member.get("atk", "")),
        }
        changes_applied += 1

    if changes_applied:
        st.session_state.uploaded_normalized_teams = normalized_teams
        st.success("名稱變更已套用，職業與可參加時間會由報名資料自動更新。")
    else:
        st.warning("未偵測到有效變更，請確認名稱是否正確。")


def _render_uploaded_member_editor(normalized_teams: list[dict], members_data: dict, week_key: str):
    rows, time_columns = _build_uploaded_member_rows(normalized_teams, members_data, week_key)
    if not rows:
        st.info("目前沒有可供調整的隊伍欄位。")
        return

    display_columns = ["隊伍名稱", "時間", "名稱", "職業", *time_columns]
    df_display = pd.DataFrame(
        [
            {col: row[col] for col in display_columns}
            for row in rows
        ],
        columns=display_columns
    )
    member_options = sorted({"", *members_data.keys(), *{row["名稱"] for row in rows if row["名稱"]}})

    column_config = {
        "隊伍名稱": st.column_config.TextColumn("隊伍名稱", disabled=True),
        "時間": st.column_config.TextColumn("時間", disabled=True),
        "名稱": st.column_config.SelectboxColumn(
            "名稱",
            options=member_options,
            required=False,
            help="僅能變更名稱欄位，職業與可參加時間會自動從報名資料帶入。"
        ),
        "職業": st.column_config.TextColumn("職業", disabled=True),
        **{label: st.column_config.TextColumn(label, disabled=True) for label in time_columns},
    }

    st.caption("編輯名稱即可將成員調到其他組，其餘欄位會即時從系統報名資料更新。")
    with st.form("uploaded_team_member_form", clear_on_submit=False):
        edited_df = st.data_editor(
            df_display,
            key="uploaded_team_member_editor",
            column_config=column_config,
            column_order=("隊伍名稱", "時間", "名稱", "職業", *time_columns),
            num_rows="fixed",
            use_container_width=True,
            hide_index=True,
        )
        if st.form_submit_button("💾 套用名稱變更", type="primary"):
            _save_uploaded_member_changes(edited_df, rows, members_data)

if uploaded_json:
    try:
        parsed_payload = json.load(uploaded_json)
    except json.JSONDecodeError as err:
        st.error(f"❌ 無法解析 JSON：{err}")
    else:
        normalized_from_payload = parse_uploaded_team_payload(parsed_payload)
        if normalized_from_payload:
            file_signature = "-".join([
                getattr(uploaded_json, "name", ""),
                str(getattr(uploaded_json, "size", "")),
                start_of_this_week_str,
            ])
            if st.session_state.uploaded_team_data_key != file_signature:
                st.session_state.uploaded_team_data_key = file_signature
                st.session_state.uploaded_normalized_teams = normalized_from_payload
            normalized_teams = st.session_state.uploaded_normalized_teams or normalized_from_payload

            rows = []
            for team in normalized_teams:
                preview_names = [m["name"] for m in team["members"] if m["name"]]
                preview_text = "、".join(preview_names) if preview_names else "尚未有成員"
                rows.append({
                    "team_id": team["team_id"],
                    "排序": team["team_id"] + 1,
                    "時間": team["time_label"],
                    "成員概覽": preview_text,
                })
            df_preview = pd.DataFrame(rows).set_index("team_id")
            editable = st.data_editor(
                df_preview,
                key="uploaded_team_editor",
                column_config={
                    "排序": st.column_config.NumberColumn("排序", min_value=1, max_value=max(1, len(rows)), help="數字越小的組別會越靠前顯示"),
                    "時間": st.column_config.TextColumn("時間", disabled=True),
                    "成員概覽": st.column_config.TextColumn("成員概覽", disabled=True),
                },
                column_order=("排序", "時間", "成員概覽"),
                num_rows="fixed",
                width="stretch",
                hide_index=True,
            )
            _display_uploaded_groups(editable.reset_index(), normalized_teams, all_members, start_of_this_week)
            _render_uploaded_member_editor(normalized_teams, all_members, start_of_this_week_str)
        else:
            st.warning("找不到可用的隊伍資料，請確認 JSON 結構是否含有 `隊伍` 清單。")
else:
    st.info("尚未上傳任何 JSON 檔案。")

team_view_week = {}

for idx, team in enumerate(teams):
    if "team_view_week" not in st.session_state:
        st.session_state.team_view_week = {}
    if idx not in st.session_state.team_view_week:
        st.session_state.team_view_week[idx] = start_of_this_week_str

    view_week_start_str = st.session_state.team_view_week[idx]
    view_week_start_date = datetime.strptime(view_week_start_str, '%Y-%m-%d').date()

    schedule_to_display = team.get("schedules", {}).get(view_week_start_str, get_default_schedule_for_week())
    team_time_remark = team.get('team_remark', '')

    # 隊伍狀態資訊
    member_count = sum(1 for m in team.get("member", []) if m.get("name"))
    if member_count == 0:
        continue
    status_icon = "🎉" if member_count >= MAX_TEAM_SIZE else "⏳"
    time_info = f"｜⏰ {team_time_remark}" if team_time_remark else "｜⏰ 時間待定"
    
    expander_label = f"{status_icon} **{team['team_name']}** {time_info}"
    with st.expander(expander_label, expanded=False):
        # 隊伍統計
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            progress_value = member_count / MAX_TEAM_SIZE
            st.progress(progress_value, text=f"👥 成員: {member_count}/{MAX_TEAM_SIZE}")
        with col2:
            if member_count < MAX_TEAM_SIZE:
                st.metric("尚缺人數", f"{MAX_TEAM_SIZE - member_count} 人")
            else:
                st.metric("隊伍狀態", "已滿員")
        with col3:
            if team_time_remark:
                st.metric("活動時間", team_time_remark)
            else:
                st.metric("活動時間", "待定")
        
        st.markdown("---")

        tab1, = st.tabs(["**👥 成員名單**"])

        with tab1:
            # 週次切換（本週 / 下週），顯示日期範圍
            this_range = get_week_range(start_of_this_week)
            next_range = get_week_range(start_of_this_week + timedelta(days=7))
            label_this = f"本週({this_range})"
            label_next = f"下週({next_range})"
            view_choice = st.radio("顯示週次", [label_this, label_next], horizontal=True, key=f"member_list_week_{idx}")
            week_start_date = start_of_this_week if view_choice == label_this else (start_of_this_week + timedelta(days=7))
            week_key_str = week_start_date.strftime('%Y-%m-%d')
            weekday_plain, weekday_with_date = get_weekday_label_pairs(week_start_date)
            with st.form(f"team_form_{idx}", clear_on_submit=False):
                c1, c2 = st.columns(2)
                team_name = c1.text_input("隊伍名稱", value=team["team_name"], key=f"name_{idx}")
                team_remark = c2.text_input("隊伍時間", value=team.get("team_remark", ""), key=f"remark_{idx}", help="主要時間請至「時間調查」分頁設定")
                st.write("**編輯隊伍成員 (請由名稱欄位選擇)：**")

                current_members_list = team.get("member", [])
                if len(current_members_list) != MAX_TEAM_SIZE:
                    current_members_list.extend([{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE - len(current_members_list))])
                current_members_list = current_members_list[:MAX_TEAM_SIZE]

                # 合併為單一 DataFrame，並加入上方欄位與可參加日期（依週次切換）
                member_names_for_team_select = [""] + sorted(list(all_members.keys()))
                rows = []
                for m in current_members_list:
                    nm = m.get("name", "")
                    base_info = all_members.get(nm, {}) if nm in all_members else {}
                    job = base_info.get("job", m.get("job", ""))
                    level = base_info.get("level", m.get("level", ""))
                    atk = base_info.get("atk", m.get("atk", ""))
                    # 取所選週次的 availability（優先 weekly_data，其次舊欄位在同週）
                    weekly_data = base_info.get("weekly_data", {}) if isinstance(base_info.get("weekly_data", {}), dict) else {}
                    if week_key_str in weekly_data:
                        wa = weekly_data.get(week_key_str, {}).get("availability", {}) or {}
                    elif base_info.get("weekly_week_start") == week_key_str:
                        wa = base_info.get("weekly_availability", {}) or {}
                    else:
                        wa = {}
                    row = {"名稱": nm, "職業": job, "等級": level, "表攻": atk}
                    for p, w in zip(weekday_plain, weekday_with_date):
                        row[w] = "✅" if wa.get(p, False) else ""
                    rows.append(row)
                if rows:
                    df_combined = pd.DataFrame(rows, columns=["名稱","職業","等級","表攻"] + weekday_with_date)
                else:
                    df_combined = pd.DataFrame(columns=["名稱","職業","等級","表攻"] + weekday_with_date)

                edited_df = st.data_editor(df_combined, key=f"editor_{idx}", num_rows="fixed", width="stretch",
                    column_config={
                        "_index": None,
                        "名稱": st.column_config.SelectboxColumn("名稱", options=member_names_for_team_select, required=False),
                        "職業": st.column_config.TextColumn("職業", disabled=True),
                        "等級": st.column_config.TextColumn("等級", disabled=True),
                        "表攻": st.column_config.TextColumn("表攻", disabled=True),
                        **{label: st.column_config.TextColumn(label, disabled=True) for label in weekday_with_date},
                    },
                    column_order=("名稱", "職業", "等級", "表攻", *weekday_with_date)
                )
                st.markdown("---")

                btn_cols = st.columns([2, 1, 1])
                if btn_cols[0].form_submit_button(f"💾 儲存變更", type="primary", width="stretch"):
                    updated_members = [
                        {"name": row["名稱"], **all_members.get(row["名稱"], {})} if row["名稱"] else {"name": "", "job": "", "level": "", "atk": ""}
                        for _, row in edited_df.iterrows()
                    ]
                    data["teams"][idx].update({
                        "team_name": team_name,
                        "team_remark": team_remark,
                        "member": updated_members
                    })
                    save_data(data)
                    st.success(f"隊伍 '{team_name}' 的資料已更新！")
                    st.rerun()

                if btn_cols[1].form_submit_button(f"🔄 清空成員", width="stretch"):
                    data["teams"][idx]["member"] = [{"name": "", "job": "", "level": "", "atk": ""} for _ in range(MAX_TEAM_SIZE)]
                    save_data(data)
                    st.success(f"隊伍 '{team['team_name']}' 的成員已清空！")
                    st.rerun()

                if btn_cols[2].form_submit_button(f"🗑️ 刪除隊伍", width="stretch"):
                    deleted_name = data["teams"].pop(idx)["team_name"]
                    save_data(data)
                    st.success(f"隊伍 '{deleted_name}' 已被刪除！")
                    st.rerun()


        # 移除「時間調查」頁籤與相關功能

