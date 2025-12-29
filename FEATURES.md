# 🎮 Basketball Organizer - New Features Documentation

## Overview

This document details the three major feature enhancements added to the Basketball Organizer App:
1. **Gamification System** - Player engagement through points, achievements, and leaderboards
2. **Email Notifications** - Automated email communications for game updates
3. **Enhanced Waitlist** - Smart waitlist management with auto-promotion

---

## 🏆 1. Gamification System

### Features

#### **Points System**
Players earn points for various activities:
- **+10 points**: RSVP confirmation
- **+5 points**: Early RSVP (>24h in advance)
- **+20 points**: Game attendance
- **+5 points/guest**: Bringing guests
- **+5 points/game**: Streak bonus (consecutive games)
- **-5 points**: Late cancellation
- **-10 points**: No-show

#### **Achievements** (10 Total)
| Achievement | Icon | Description | Points | Requirement |
|------------|------|-------------|--------|-------------|
| First Timer | 🏀 | Attended first game | 10 | 1+ games |
| Court Regular | ⭐ | Regular player | 50 | 10+ games |
| Court Veteran | 👑 | Experienced player | 150 | 25+ games |
| Court Legend | 🏆 | Elite player | 300 | 50+ games |
| Reliable Player | 💎 | Consistent attendance | 75 | 90%+ attendance (5+ games) |
| Perfect Record | ✨ | Never missed a game | 200 | 100% attendance (10+ games) |
| Hot Streak | 🔥 | Consecutive games | 40 | 5+ consecutive games |
| Early Bird | 🌅 | Early RSVPs | 30 | 10+ early RSVPs |
| Team Player | 🤝 | Brings friends | 25 | 5+ guests brought |
| Season MVP | 🌟 | Top performer | 100 | Highest attendance this month |

#### **Player Statistics**
Each player tracks:
- Total points earned
- Games attended
- Attendance rate (%)
- Current streak
- Longest streak
- Early RSVPs
- Guests brought
- Cancellations
- No-shows
- Global rank

#### **Leaderboards**
Rank players by:
- Total Points
- Games Attended
- Attendance Rate
- Current Streak

### Usage

#### Track Player Activity
```python
from src.services.gamification_service import update_player_stats

# When player RSVPs
update_player_stats(
    player_name="John Doe",
    action="rsvp_confirmed",
    details={
        "is_early": True,  # RSVP >24h in advance
        "guests_count": 2  # Bringing 2 guests
    }
)

# When player attends
update_player_stats(
    player_name="John Doe",
    action="attendance_confirmed",
    details={"game_date": date.today()}
)
```

#### Check Achievements
```python
from src.services.gamification_service import check_achievements

# Returns list of newly earned achievement IDs
new_achievements = check_achievements("John Doe")
```

#### Get Player Profile
```python
from src.services.gamification_service import get_player_stats

stats = get_player_stats("John Doe")
print(f"Points: {stats['total_points']}")
print(f"Games: {stats['games_attended']}")
print(f"Streak: {stats['current_streak']}")
```

#### Display Leaderboard
```python
from src.services.gamification_service import get_leaderboard

# Get top 10 by points
leaderboard = get_leaderboard("points", limit=10)
for rank, (name, points) in enumerate(leaderboard, 1):
    print(f"{rank}. {name}: {points} points")
```

---

## 📧 2. Email Notifications

### Features

#### **Email Templates**
Six pre-designed professional email templates:

1. **Game Scheduled** - New game announcement
2. **RSVP Confirmation** - Confirmation with game details
3. **Game Reminder** - 24h before game reminder
4. **Waitlist Promoted** - Notification when promoted from waitlist
5. **Achievement Unlocked** - Celebration email for achievements
6. **Weekly Digest** - Weekly recap of activity

#### **Notification Types**
- Game scheduled notifications
- RSVP confirmations with points earned
- Game day reminders
- Waitlist promotion alerts
- Achievement celebrations
- Weekly activity digests

### Configuration

Add to `.streamlit/secrets.toml`:

```toml
[email]
smtp_server = "smtp.gmail.com"
smtp_port = 587
sender_email = "your-email@gmail.com"
sender_password = "your-app-password"
app_url = "https://your-basketball-app.com"
```

**Gmail Setup:**
1. Enable 2-factor authentication
2. Generate app password: https://myaccount.google.com/apppasswords
3. Use app password in `sender_password`

### Usage

#### Send RSVP Confirmation
```python
from src.services.notification_service import email_service

email_service.send_rsvp_confirmation(
    to_email="player@example.com",
    player_name="John Doe",
    game_details={
        "game_date": date(2024, 12, 25),
        "start_time": "7:00 PM",
        "location": "Main Gym"
    },
    guests=["Jane", "Bob"],
    points_earned=25
)
```

#### Send Game Reminder
```python
email_service.send_game_reminder(
    to_email="player@example.com",
    player_name="John Doe",
    game_details={
        "start_time": "7:00 PM",
        "end_time": "9:00 PM",
        "location": "Main Gym",
        "confirmed_count": 12
    }
)
```

#### Send Achievement Notification
```python
from src.services.gamification_service import ACHIEVEMENTS

achievement = ACHIEVEMENTS["court_regular"]
email_service.send_achievement_notification(
    to_email="player@example.com",
    player_name="John Doe",
    achievement=achievement,
    player_stats={
        "total_points": 500,
        "games_attended": 10,
        "rank": 5
    }
)
```

### Email Features

- **HTML Emails**: Beautiful, responsive HTML templates
- **Gradient Designs**: Professional gradient backgrounds
- **Game Details**: Clear formatting of game information
- **Points Display**: Show points earned
- **Call-to-Action**: Direct links to app
- **Personalization**: Player name and stats included

---

## ⏳ 3. Enhanced Waitlist System

### Features

#### **Smart Priority System**
Waitlist position determined by:
- **Games attended** (+10 points per game)
- **Attendance rate** (+50 for 90%+, +25 for 75%+)
- **Current streak** (+5 per consecutive game)
- **Cancellations** (-5 per cancellation)
- **No-shows** (-15 per no-show)

#### **Auto-Promotion**
Automatically promotes players from waitlist when:
- A confirmed player cancels
- Game capacity increases
- Admin manually adjusts

#### **Waitlist Features**
- Real-time position tracking
- Automatic notifications
- Priority-based ordering
- Group consideration (player + guests)
- Capacity-aware promotion

### Usage

#### Get Waitlist Stats
```python
from src.services.waitlist_service import get_waitlist_stats

stats = get_waitlist_stats(game_id=1)
print(f"Waitlist: {stats['waitlist_count']} players")
print(f"Confirmed: {stats['confirmed_count']}")
print(f"Available: {stats['available_spots']} spots")
print(f"Next up: {stats['next_to_promote']}")
```

#### Handle Cancellation
```python
from src.services.waitlist_service import handle_cancellation_promotion

# When a player cancels
promoted = handle_cancellation_promotion(
    game_id=1,
    game_details={
        "game_date": date(2024, 12, 25),
        "start_time": "7:00 PM",
        "end_time": "9:00 PM",
        "location": "Main Gym"
    }
)

print(f"Promoted: {promoted}")  # ['Jane Doe', 'Bob Smith']
```

#### Check Waitlist Position
```python
from src.services.waitlist_service import get_waitlist_position

position = get_waitlist_position(game_id=1, player_name="John Doe")
if position:
    print(f"You're #{position} on the waitlist")
```

#### Manual Promotion
```python
from src.services.waitlist_service import promote_from_waitlist

promoted = promote_from_waitlist(
    game_id=1,
    game_details={...},
    notify=True  # Send email notifications
)
```

### Waitlist Logic

1. **Player RSVPs**: If game is full, added to waitlist with priority score
2. **Position Calculated**: Based on attendance history and reliability
3. **Cancellation Occurs**: Auto-promotion triggered
4. **Best Candidate Selected**: Highest priority who fits in available spots
5. **Status Updated**: Player moved from waitlist to confirmed
6. **Notification Sent**: Email notification (if configured)
7. **Gamification Updated**: Points awarded, stats updated

---

## 🎨 UI Components

### Player Profile Display
```python
from src.components.gamification_ui import display_player_profile

display_player_profile("John Doe")
```

Shows:
- Total points, games, attendance rate, rank
- Progress bars for streaks and milestones
- Unlocked achievements with icons
- Locked achievements preview
- Activity history table

### Leaderboard Display
```python
from src.components.gamification_ui import display_leaderboard

display_leaderboard(metric="points", title="🏆 Top Players")
```

Features:
- Metric selector (points, games, attendance, streak)
- Top 20 ranked list
- Medals for top 3 (🥇🥈🥉)
- Interactive chart visualization

### Achievement Notification
```python
from src.components.gamification_ui import display_achievement_notification

display_achievement_notification("court_regular")
```

Shows:
- Balloons celebration 🎈
- Large achievement icon
- Achievement name and description
- Points earned
- Gradient background

### Points Badge
```python
from src.components.gamification_ui import display_points_badge

display_points_badge(points=500)
```

Displays:
- Compact points display
- Gradient background
- Trophy icon

---

## 📱 Running the Enhanced App

### Standard App (with refactoring only)
```bash
streamlit run app.py
```

### Enhanced App (with all new features)
```bash
streamlit run app_enhanced.py
```

### Original App (preserved for reference)
```bash
streamlit run Basketball_organizer_gt.py
```

---

## 🔧 Configuration

### Email Setup (Optional)

`.streamlit/secrets.toml`:
```toml
[email]
smtp_server = "smtp.gmail.com"
smtp_port = 587
sender_email = "basketball-app@gmail.com"
sender_password = "your-app-password"
app_url = "https://your-app.streamlit.app"
```

### Game Settings

`src/config.py`:
```python
class Config:
    CAPACITY = 15  # Max players per game
    CUTOFF_DAYS = 1  # RSVP deadline (days before)
    SESSION_TIMEOUT_MINUTES = 30
```

---

## 📊 Data Storage

### Session State Storage
- Player stats (games_attended, points, etc.)
- Achievements earned
- Points transactions
- Waitlist queue

### Database Storage (if configured)
- Games
- RSVPs
- Player responses

### Future: Persistent Storage
For production use, consider:
- PostgreSQL for player stats
- Redis for leaderboards
- Cloud storage for achievement history

---

## 🎯 Best Practices

### Gamification
1. **Award points immediately** after actions
2. **Check achievements** after updating stats
3. **Display notifications** for new achievements
4. **Update leaderboards** in real-time

### Email Notifications
1. **Always check** `email_service.enabled` before sending
2. **Use try-except** for email operations
3. **Log all email attempts** for debugging
4. **Provide fallback** for users without email

### Waitlist Management
1. **Update statuses** after every RSVP change
2. **Promote immediately** after cancellations
3. **Notify players** of their waitlist position
4. **Consider group sizes** when promoting

---

## 🚀 Future Enhancements

### Gamification
- [ ] Season-based competitions
- [ ] Custom achievement editor
- [ ] Team achievements
- [ ] Power-ups and bonuses
- [ ] Profile customization

### Notifications
- [ ] SMS notifications (Twilio)
- [ ] Push notifications (PWA)
- [ ] Slack/Discord integration
- [ ] Calendar invites (iCal)
- [ ] Reminder scheduling

### Waitlist
- [ ] Waitlist time limits
- [ ] Priority passes
- [ ] Waitlist analytics
- [ ] Automatic expiry
- [ ] Smart capacity prediction

---

## 📚 Additional Resources

- **Gamification Guide**: See examples in `src/services/gamification_service.py`
- **Email Templates**: Customize in `src/services/notification_service.py`
- **Waitlist Algorithm**: Details in `src/services/waitlist_service.py`
- **UI Components**: Reusable components in `src/components/gamification_ui.py`

---

## 🤝 Support

For questions or issues:
1. Check this documentation
2. Review service module docstrings
3. Examine example usage in `app_enhanced.py`
4. Create an issue in the repository

---

**Version**: 2.2 (Enhanced)
**Last Updated**: December 2024
**Author**: Basketball Organizer Team
