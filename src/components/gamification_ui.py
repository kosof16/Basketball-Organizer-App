"""UI components for gamification features"""
import streamlit as st
import pandas as pd
import altair as alt
from typing import Optional
from src.services.gamification_service import (
    get_player_stats, get_player_achievements, get_leaderboard,
    get_player_rank, ACHIEVEMENTS
)


def display_player_profile(player_name: str):
    """Display comprehensive player profile with stats and achievements"""

    st.markdown(f"### 👤 {player_name}'s Profile")

    # Get player data
    stats = get_player_stats(player_name)
    achievements = get_player_achievements(player_name)
    rank = get_player_rank(player_name, "points")

    # Stats overview
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("🎯 Total Points", stats["total_points"])

    with col2:
        st.metric("🏀 Games Attended", stats["games_attended"])

    with col3:
        st.metric("📊 Attendance Rate", f"{stats['attendance_rate']:.0f}%")

    with col4:
        st.metric("🏆 Rank", f"#{rank}" if rank > 0 else "N/A")

    # Progress bars
    st.markdown("#### 📈 Your Progress")

    col1, col2 = st.columns(2)

    with col1:
        # Streak progress
        st.markdown("**🔥 Current Streak**")
        streak_progress = min(stats["current_streak"] / 10, 1.0)
        st.progress(streak_progress)
        st.caption(f"{stats['current_streak']} games (Best: {stats['longest_streak']})")

    with col2:
        # Games to next milestone
        st.markdown("**🎯 Next Milestone**")
        games_attended = stats["games_attended"]
        next_milestone = 10 if games_attended < 10 else \
                        25 if games_attended < 25 else \
                        50 if games_attended < 50 else 100

        milestone_progress = games_attended / next_milestone
        st.progress(min(milestone_progress, 1.0))
        st.caption(f"{games_attended}/{next_milestone} games to next milestone")

    # Achievements
    st.markdown("#### 🏆 Achievements")

    if achievements:
        # Display achievements in a grid
        cols = st.columns(4)
        for idx, achievement in enumerate(achievements):
            with cols[idx % 4]:
                st.markdown(f"""
                <div style="
                    background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%);
                    color: white;
                    padding: 15px;
                    border-radius: 10px;
                    text-align: center;
                    margin: 5px;
                ">
                    <div style="font-size: 32px;">{achievement['icon']}</div>
                    <div style="font-size: 12px; font-weight: bold; margin-top: 5px;">{achievement['name']}</div>
                </div>
                """, unsafe_allow_html=True)

        st.caption(f"Unlocked {len(achievements)}/{len(ACHIEVEMENTS)} achievements")
    else:
        st.info("🎯 No achievements yet. Keep playing to unlock them!")

    # Locked achievements (preview)
    locked = [a for aid, a in ACHIEVEMENTS.items() if aid not in [ach['id'] for ach in achievements]]

    if locked:
        with st.expander("🔒 Locked Achievements", expanded=False):
            for achievement in locked[:5]:  # Show first 5 locked
                col1, col2, col3 = st.columns([1, 4, 2])
                with col1:
                    st.markdown(f"<div style='font-size: 24px;'>{achievement['icon']}</div>",
                              unsafe_allow_html=True)
                with col2:
                    st.markdown(f"**{achievement['name']}**")
                    st.caption(achievement['description'])
                with col3:
                    st.caption(f"+{achievement['points']} pts")

    # Activity history
    with st.expander("📊 Activity History", expanded=False):
        history_data = {
            "Metric": ["Total RSVPs", "Attended", "Cancelled", "Early RSVPs", "Guests Brought"],
            "Count": [
                stats["games_rsvp"],
                stats["games_attended"],
                stats["games_cancelled"],
                stats["early_rsvps"],
                stats["guests_brought"]
            ]
        }
        st.dataframe(pd.DataFrame(history_data), use_container_width=True, hide_index=True)


def display_leaderboard(metric: str = "points", title: str = "🏆 Leaderboard"):
    """Display leaderboard for specified metric"""

    st.markdown(f"### {title}")

    # Metric selector
    metric_options = {
        "Points": "points",
        "Games Attended": "games_attended",
        "Attendance Rate": "attendance_rate",
        "Current Streak": "current_streak"
    }

    selected_metric_name = st.selectbox(
        "Rank by:",
        options=list(metric_options.keys()),
        index=0,
        key=f"leaderboard_metric_{metric}"
    )

    selected_metric = metric_options[selected_metric_name]

    # Get leaderboard
    leaderboard = get_leaderboard(selected_metric, limit=20)

    if not leaderboard:
        st.info("No players yet. Be the first!")
        return

    # Create dataframe
    df = pd.DataFrame(leaderboard, columns=["Player", "Value"])
    df.insert(0, "Rank", range(1, len(df) + 1))

    # Format value column based on metric
    if selected_metric == "attendance_rate":
        df["Value"] = df["Value"].apply(lambda x: f"{x:.0f}%")
    elif selected_metric == "points":
        df["Value"] = df["Value"].apply(lambda x: f"{int(x):,}")
    else:
        df["Value"] = df["Value"].apply(lambda x: int(x))

    # Add medals for top 3
    def add_medal(row):
        if row["Rank"] == 1:
            return f"🥇 {row['Player']}"
        elif row["Rank"] == 2:
            return f"🥈 {row['Player']}"
        elif row["Rank"] == 3:
            return f"🥉 {row['Player']}"
        return row["Player"]

    df["Player"] = df.apply(add_medal, axis=1)

    # Display table
    st.dataframe(df, use_container_width=True, hide_index=True)

    # Visualization
    if len(leaderboard) > 0:
        # Convert back for chart
        chart_df = pd.DataFrame(leaderboard[:10], columns=["Player", "Score"])

        chart = alt.Chart(chart_df).mark_bar().encode(
            x=alt.X('Score:Q', title=selected_metric_name),
            y=alt.Y('Player:N', sort='-x', title=''),
            color=alt.Color(
                'Score:Q',
                scale=alt.Scale(scheme='goldorange'),
                legend=None
            ),
            tooltip=['Player', 'Score']
        ).properties(
            height=300,
            title=f"Top 10 by {selected_metric_name}"
        )

        st.altair_chart(chart, use_container_width=True)


def display_achievement_notification(achievement_id: str):
    """Display a celebratory notification for new achievement"""

    achievement = ACHIEVEMENTS.get(achievement_id)
    if not achievement:
        return

    st.balloons()

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%);
        color: white;
        padding: 30px;
        border-radius: 15px;
        text-align: center;
        margin: 20px 0;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    ">
        <h1 style="margin: 0;">🏆 Achievement Unlocked! 🏆</h1>
        <div style="font-size: 80px; margin: 20px 0;">{achievement['icon']}</div>
        <h2 style="margin: 10px 0;">{achievement['name']}</h2>
        <p style="font-size: 18px; margin: 10px 0;">{achievement['description']}</p>
        <p style="font-size: 28px; font-weight: bold; margin-top: 20px;">+{achievement['points']} Points!</p>
    </div>
    """, unsafe_allow_html=True)


def display_points_badge(points: int):
    """Display points badge in sidebar or header"""

    st.markdown(f"""
    <div style="
        background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%);
        color: white;
        padding: 10px 20px;
        border-radius: 20px;
        text-align: center;
        display: inline-block;
    ">
        <span style="font-size: 20px; font-weight: bold;">🎯 {points:,}</span>
        <span style="font-size: 12px; opacity: 0.9;"> points</span>
    </div>
    """, unsafe_allow_html=True)
