import streamlit as st
import pandas as pd
import os
from datetime import datetime, date, time, timedelta
import random
import altair as alt
import io

# --- Constants ---
CAPACITY = 15
DEFAULT_LOCATION = "Main Court"
ADMIN_PASSWORD = st.secrets["ADMIN_PASSWORD"]
CUTOFF_DAYS = 1  # RSVP closes 1 day before event

# --- Page Config ---
st.set_page_config(page_title="🏀 Basketball Organiser", layout="wide")

if "admin_authenticated" not in st.session_state:
    st.session_state.admin_authenticated = False

st.sidebar.markdown("# 📜 Menu")
section = st.sidebar.selectbox("Navigate to", ["🏀 RSVP", "⚙️ Admin"])

# --- File Paths ---
def _paths():
    return ('game.csv', 'responses.csv')

def load_game():
    game_path, _ = _paths()
    if os.path.exists(game_path):
        return pd.read_csv(game_path)
    return pd.DataFrame()

def save_game(date_str, start_str, end_str, location):
    df = pd.DataFrame([{'date': date_str, 'start': start_str, 'end': end_str, 'location': location}])
    game_path, _ = _paths()
    df.to_csv(game_path, index=False)

def load_responses():
    _, resp_path = _paths()
    if os.path.exists(resp_path):
        return pd.read_csv(resp_path)
    return pd.DataFrame(columns=['name', 'others', 'timestamp', 'status'])

def save_responses(df):
    _, resp_path = _paths()
    df.to_csv(resp_path, index=False)

# --- Utilities ---
def format_time_str(t_str):
    try:
        t = datetime.fromisoformat(t_str).time()
    except:
        parts = t_str.split(':')
        t = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
    h, m = t.hour, t.minute
    ampm = 'am' if h < 12 else 'pm'
    hr = h % 12 or 12
    if h == 12 and m == 0:
        return '12 noon'
    if m == 0:
        return f"{hr} {ampm}"
    return f"{hr}:{m:02d} {ampm}"

def add_response(name, others, attend):
    df = load_responses()
    df = df[df['name'] != name]
    status = '❌ Cancelled' if not attend else ''
    entry = {'name': name, 'others': others, 'timestamp': datetime.utcnow().isoformat(), 'status': status}
    df = pd.concat([df, pd.DataFrame([entry])], ignore_index=True)
    save_responses(df)

def update_statuses():
    df = load_responses().sort_values('timestamp')
    cum = 0
    statuses = []
    for _, r in df.iterrows():
        current_status = r['status']
        if current_status in ['❌ Cancelled', '✅ Confirmed', '⏳ Waitlist']:
            statuses.append(current_status)  # preserve manual
        else:
            others = str(r.get('others', '') or '')
            extras = len([o.strip() for o in others.split(',') if o.strip()])
            parts = 1 + extras
            if cum + parts <= CAPACITY:
                statuses.append('✅ Confirmed')
                cum += parts
            else:
                statuses.append('⏳ Waitlist')
    df['status'] = statuses
    save_responses(df)

def generate_teams(num_teams=None):
    update_statuses()
    df = load_responses()
    confirmed = df[df['status'] == '✅ Confirmed']
    players = []
    for _, r in confirmed.iterrows():
        players.append(r['name'])
        others = str(r.get('others', '') or '')
        for o in others.split(','):
            if o.strip(): players.append(o.strip())
    if len(players) < 2:
        return None
    if not num_teams:
        num_teams = 2 if len(players) <= 10 else (len(players) + 2) // 3
    num_teams = max(2, min(num_teams, len(players)))
    random.shuffle(players)
    teams = [[] for _ in range(num_teams)]
    for i, p in enumerate(players):
        teams[i % num_teams].append(p)
    return teams

def show_metrics_and_chart(df):
    conf = len(df[df['status'] == '✅ Confirmed'])
    wait = len(df[df['status'] == '⏳ Waitlist'])
    canc = len(df[df['status'] == '❌ Cancelled'])
    col1, col2, col3 = st.columns(3)
    col1.metric("✅ Confirmed", conf)
    col2.metric("⏳ Waitlist", wait)
    col3.metric("❌ Cancelled", canc)
    st.progress(min(conf / CAPACITY, 1.0), text=f"{conf}/{CAPACITY} confirmed")
    chart_data = pd.DataFrame({'Status': ['Confirmed', 'Waitlist', 'Cancelled'],
                               'Count': [conf, wait, canc]})
    color_map = {'Confirmed': '#4CAF50', 'Waitlist': '#FFC107', 'Cancelled': '#F44336'}
    chart = alt.Chart(chart_data).mark_bar().encode(
        y=alt.Y('Status:N', sort='-x', title=''),
        x=alt.X('Count:Q', title='Players'),
        color=alt.Color('Status:N', scale=alt.Scale(domain=list(color_map.keys()), range=list(color_map.values()))),
        tooltip=['Status:N', 'Count:Q']
    ).properties(width=500, height=200)
    st.altair_chart(chart, use_container_width=True)

def show_admin_tab(df, status_filter):
    filtered = df[df['status'] == status_filter][['name', 'others']].reset_index(drop=True)
    st.table(filtered)
    selected = st.multiselect(f"Select from {status_filter}", filtered['name'].tolist(), key=status_filter)
    col1, col2, col3, col4 = st.columns(4)
    if col1.button(f"Move ➡️ Confirmed ({status_filter})", key=f"{status_filter}_c"):
        df.loc[df['name'].isin(selected), 'status'] = '✅ Confirmed'
        if status_filter == '❌ Cancelled':
            update_statuses()
        save_responses(df)
        st.toast("Moved to Confirmed.")
        st.rerun()
    if col2.button(f"Move ➡️ Waitlist ({status_filter})", key=f"{status_filter}_w"):
        df.loc[df['name'].isin(selected), 'status'] = '⏳ Waitlist'
        save_responses(df)
        st.toast("Moved to Waitlist.")
        st.rerun()
    if col3.button(f"Move ➡️ Cancelled ({status_filter})", key=f"{status_filter}_x"):
        df.loc[df['name'].isin(selected), 'status'] = '❌ Cancelled'
        save_responses(df)
        st.toast("Moved to Cancelled.")
        st.rerun()
    if col4.button(f"🗑️ Remove ({status_filter})", key=f"{status_filter}_rm"):
        df.drop(df[df['name'].isin(selected)].index, inplace=True)
        save_responses(df)
        st.toast(f"Removed from {status_filter}.")
        st.rerun()

# --- ADMIN PAGE ---
if section == '⚙️ Admin':
    st.title(":gear: Admin Dashboard")
    if not st.session_state.admin_authenticated:
        st.sidebar.markdown("## Admin Login 🔒")
        pwd = st.sidebar.text_input("Password", type="password")
        if st.sidebar.button("Login"):
            if pwd == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.rerun()
            else:
                st.sidebar.error("Incorrect password")
    else:
        game_df = load_game()
        st.subheader(":calendar: Schedule Game")
        with st.form("schedule_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                gd = st.date_input("Game Date", date.today() + timedelta(days=1))
                start = st.time_input("Start Time", value=time(10))
            with col2:
                end = st.time_input("End Time", value=time(12))
                loc = st.text_input("Location", DEFAULT_LOCATION)
            if st.form_submit_button("Save Schedule"):
                save_game(gd.isoformat(), start.isoformat(), end.isoformat(), loc)
                st.success("Schedule saved!")

        if not game_df.empty:
            game = game_df.iloc[0].to_dict()
            st.markdown(f"**Date:** {game['date']} — **{format_time_str(game['start'])} to {format_time_str(game['end'])}** @ **{game['location']}**")

        df = load_responses()
        st.subheader(":clipboard: RSVP Overview")
        show_metrics_and_chart(df)

        with st.expander("📝 Manage Players"):
            tabs = st.tabs(["✅ Confirmed", "⏳ Waitlist", "❌ Cancelled"])
            for i, status in enumerate(['✅ Confirmed', '⏳ Waitlist', '❌ Cancelled']):
                with tabs[i]:
                    show_admin_tab(df, status)

        st.subheader("📥 Download RSVP")
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button("Download All CSV", csv, "responses.csv", "text/csv")

        confirmed_df = df[df['status'] == '✅ Confirmed']
        conf_count = len(confirmed_df)
        if conf_count >= 2:
            st.subheader("👥 Generate Teams")
            suggested_teams = min(2 if conf_count <= 10 else (conf_count + 2)//3, conf_count)
            num_teams_input = st.number_input("Number of teams", min_value=2, max_value=conf_count, value=suggested_teams)
            if st.button("Generate Teams"):
                teams = generate_teams(num_teams_input)
                if teams:
                    for i, team in enumerate(teams, 1):
                        st.markdown(f"**Team {i}:** {', '.join(team)}")
                    st.toast("Teams ready!")
                    st.balloons()
                else:
                    st.warning("Not enough players.")
        else:
            st.warning("Not enough confirmed players to generate teams.")

# --- RSVP PAGE ---
else:
    st.title(":basketball: RSVP & Basketball Game Details")
    game_df = load_game()
    if game_df.empty:
        st.warning("No game scheduled.")
    else:
        game = game_df.iloc[0].to_dict()
        date_str = game['date']
        deadline = datetime.fromisoformat(date_str).date() - timedelta(days=CUTOFF_DAYS)
        today = date.today()
        st.markdown(f"### Next Game: **{date_str}** from **{format_time_str(game['start'])}** to **{format_time_str(game['end'])}** @ **{game['location']}**")
        df = load_responses()
        show_metrics_and_chart(df)
        if today < deadline:
            st.info(f"RSVP open until **{deadline}** 🕒")
            with st.form("rsvp_form"):
                name = st.text_input("Your First Name")
                attend = st.select_slider("Will you attend?", ["No ❌", "Yes ✅"], value="Yes ✅")
                others = st.text_input("Additional Players (comma-separated)")
                if st.form_submit_button("Submit RSVP 🎫"):
                    if not name.strip():
                        st.error("Name is required.")
                    else:
                        add_response(name.strip(), others.strip(), attend == "Yes ✅")
                        update_statuses()
                        st.success("RSVP recorded!")
                        st.rerun()
        else:
            st.error(f"RSVP closed on {deadline}. See you next time!")
