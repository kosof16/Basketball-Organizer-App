# 🏀 Basketball Organizer

A modern, full-featured web application for organizing recreational basketball games with intelligent RSVP management, player gamification, and automated communications.

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)](https://streamlit.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 📖 Overview

Basketball Organizer transforms the chaos of organizing pickup basketball games into a streamlined, engaging experience. Built with Streamlit and powered by intelligent algorithms, it handles everything from RSVP management to team generation, while keeping players engaged through gamification.

### 🎯 Problem Statement

Organizing recreational basketball games typically involves:
- Manual tracking of RSVPs via group chats
- Last-minute cancellations leaving teams short
- No show tracking or accountability
- Difficulty managing overflow when games are popular
- Lost engagement between games

### ✨ Solution

Basketball Organizer automates the entire process while adding engagement features:
- **Smart RSVP System**: Automatic capacity management with intelligent waitlist
- **Gamification**: Points, achievements, and leaderboards to boost participation
- **Automated Notifications**: Email reminders and confirmations
- **Admin Dashboard**: Easy game scheduling and player management
- **Analytics**: Track attendance trends and player reliability

---

## 🚀 Key Features

### 🏆 Gamification System
- **10 Unlockable Achievements**: From "First Timer" to "Court Legend"
- **Points System**: Earn points for RSVPs, attendance, bringing friends
- **Leaderboards**: Compete on points, games attended, attendance rate, streaks
- **Player Profiles**: Detailed stats, achievements, and progress tracking
- **Streak Rewards**: Bonus points for consecutive game attendance

### 📧 Email Notifications
- **Professional Templates**: 6 beautiful HTML email templates
- **Automated Sending**: Game reminders, RSVP confirmations, waitlist updates
- **Achievement Celebrations**: Email notifications when unlocking badges
- **Weekly Digests**: Activity summaries for engaged players
- **Customizable**: SMTP support for Gmail, SendGrid, or custom servers

### ⏳ Smart Waitlist Management
- **Priority Algorithm**: Based on attendance history and reliability
- **Auto-Promotion**: Automatically fills spots when players cancel
- **Real-time Position**: Players see their waitlist number
- **Group-Aware**: Considers player + guests for promotion
- **Fair System**: Reliable players get priority

### 👥 RSVP & Player Management
- **One-Click RSVP**: Quick and easy confirmation
- **Guest Management**: Bring friends with ease
- **Status Tracking**: Confirmed, Waitlist, Cancelled
- **Capacity Visualization**: Real-time availability display
- **Deadline Management**: Automatic RSVP cutoffs

### 🎮 Team Generation
- **Balanced Teams**: Automatic fair team creation
- **Random Distribution**: Shuffle for variety
- **Flexible Team Sizes**: 2+ teams supported

### 📊 Analytics & Insights
- **Player Statistics**: Games played, attendance rate, reliability scores
- **Attendance Trends**: Track participation over time
- **Top Players**: Most active and reliable players
- **Capacity Utilization**: Optimize game scheduling

### ⚙️ Admin Tools
- **Game Scheduling**: Quick game creation with templates
- **Player Management**: Manage RSVPs and statuses
- **Waitlist Control**: Manual promotion controls
- **Gamification Overview**: Monitor engagement metrics
- **Audit Logs**: Track admin actions

---

## 🛠️ Technology Stack

### Frontend
- **[Streamlit](https://streamlit.io/)** - Interactive web framework for Python
- **[Altair](https://altair-viz.github.io/)** - Declarative statistical visualization
- **Custom CSS** - Enhanced UI styling and animations

### Backend
- **[Python 3.8+](https://www.python.org/)** - Core programming language
- **Modular Architecture** - Clean separation of concerns
- **Service Layer Pattern** - Business logic isolation

### Database
- **[PostgreSQL](https://www.postgresql.org/)** - Primary database (production)
- **[SQLite](https://www.sqlite.org/)** - Fallback database (development)
- **Session State** - In-memory fallback option

### Email
- **SMTP Protocol** - Standard email sending
- **HTML Templates** - Beautiful responsive emails
- **Gmail/SendGrid Support** - Popular email providers

### Development
- **Git** - Version control
- **Modular Design** - 35+ organized modules
- **Type Hints** - Enhanced code quality
- **Logging** - Comprehensive error tracking

---

## 📦 Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)
- Git

### Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/kosof16/Basketball-Organizer-App.git
   cd Basketball-Organizer-App
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the application**
   ```bash
   # Enhanced version with all features
   streamlit run app_enhanced.py

   # OR refactored version with original features
   streamlit run app.py

   # OR original monolithic version
   streamlit run Basketball_organizer_gt.py
   ```

4. **Open your browser**
   ```
   http://localhost:8501
   ```

---

## ⚙️ Configuration

### Basic Setup

The app works out-of-the-box with sensible defaults. All configuration is optional.

### Database Configuration (Optional)

For production use with PostgreSQL, create `.streamlit/secrets.toml`:

```toml
[database]
host = "your-db-host.com"
dbname = "basketball_organizer"
user = "your_username"
password = "your_password"
port = 5432
```

### Email Configuration (Optional)

To enable email notifications:

```toml
[email]
smtp_server = "smtp.gmail.com"
smtp_port = 587
sender_email = "your-email@gmail.com"
sender_password = "your-app-password"
app_url = "https://your-app.streamlit.app"
```

**Gmail Setup:**
1. Enable 2-factor authentication
2. Generate app password: https://myaccount.google.com/apppasswords
3. Use the 16-character password above

### Admin Access

```toml
admin_username = "admin"
admin_password = "your-secure-password"
```

### Game Settings

Configure in `src/config.py`:
```python
CAPACITY = 15  # Maximum players per game
CUTOFF_DAYS = 1  # RSVP deadline (days before game)
SESSION_TIMEOUT_MINUTES = 30  # Admin session timeout
```

---

## 🎮 Usage

### For Players

1. **RSVP for Games**
   - Navigate to "🏀 RSVP" page
   - Enter your name
   - Optionally add guests
   - Submit to earn points!

2. **Track Your Stats**
   - Visit "📊 My Stats" page
   - View points, achievements, rank
   - See progress to next milestone

3. **Compete on Leaderboard**
   - Check "🏆 Leaderboard" page
   - See rankings by various metrics
   - Track your position

### For Organizers/Admins

1. **Login to Admin Panel**
   - Navigate to "⚙️ Admin"
   - Enter admin credentials

2. **Schedule Games**
   - Go to "Schedule Game" tab
   - Set date, time, location
   - Click "Schedule Game"

3. **Manage RSVPs**
   - View all responses
   - Manually adjust statuses
   - Manage waitlist

4. **Monitor Engagement**
   - View gamification stats
   - Track player activity
   - Review analytics

---

## 📂 Project Structure

```
Basketball-Organizer-App/
├── app_enhanced.py              # Main application (enhanced)
├── app.py                       # Refactored application
├── Basketball_organizer_gt.py   # Original monolithic app
├── requirements.txt             # Python dependencies
├── .streamlit/
│   └── secrets.toml            # Configuration (not in repo)
├── src/
│   ├── config.py               # Configuration management
│   ├── constants.py            # Application constants
│   ├── models/
│   │   └── database.py         # Database layer
│   ├── services/
│   │   ├── auth_service.py     # Authentication
│   │   ├── game_service.py     # Game management
│   │   ├── rsvp_service.py     # RSVP management
│   │   ├── calendar_service.py # Calendar events
│   │   ├── team_service.py     # Team generation
│   │   ├── gamification_service.py  # Points & achievements
│   │   ├── notification_service.py  # Email notifications
│   │   └── waitlist_service.py      # Waitlist management
│   ├── components/
│   │   └── gamification_ui.py  # UI components
│   └── utils/
│       ├── helpers.py          # Utility functions
│       └── session.py          # Session management
└── docs/
    ├── FEATURES.md             # Feature documentation
    ├── REFACTORING.md          # Architecture guide
    ├── README_ENHANCEMENTS.md  # Enhancement summary
    └── README_REFACTORING.md   # Refactoring summary
```

---

## 🎨 Screenshots

### RSVP Page
Players can quickly RSVP, see capacity, and earn points instantly.

### Player Stats
Comprehensive profile showing points, achievements, rank, and progress.

### Leaderboard
Compete with friends across multiple metrics with beautiful visualizations.

### Admin Dashboard
Streamlined game scheduling and player management interface.

---

## 🏗️ Architecture

### Design Patterns
- **Service Layer Pattern**: Business logic separated from UI
- **Repository Pattern**: Database abstraction for flexibility
- **Component Pattern**: Reusable UI components
- **Configuration Pattern**: Centralized settings management

### Key Principles
- **Modular Design**: 35+ small, focused modules
- **Separation of Concerns**: Clear layer boundaries
- **DRY (Don't Repeat Yourself)**: Minimal code duplication
- **SOLID Principles**: Maintainable, extensible code
- **Type Hints**: Enhanced code quality and IDE support

---

## 📊 Performance

- **Lightweight**: Fast page loads with efficient caching
- **Scalable**: Handles 100+ players easily
- **Responsive**: Real-time updates and feedback
- **Reliable**: Comprehensive error handling and logging

---

## 🚀 Deployment

### Streamlit Cloud (Recommended)

1. Fork/clone this repository
2. Sign up at [share.streamlit.io](https://share.streamlit.io)
3. Click "New app"
4. Select your repository and branch
5. Set main file to `app_enhanced.py`
6. Add secrets in advanced settings
7. Deploy!

### Other Platforms

- **Heroku**: Use provided `Procfile`
- **Docker**: Create container with Streamlit
- **AWS/GCP/Azure**: Deploy as web service

---

## 🤝 Contributing

Contributions are welcome! Here's how to help:

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make your changes**
4. **Commit with clear messages**
   ```bash
   git commit -m "feat: Add amazing feature"
   ```
5. **Push to your branch**
   ```bash
   git push origin feature/amazing-feature
   ```
6. **Open a Pull Request**

### Development Guidelines
- Follow existing code style
- Add docstrings to functions
- Update documentation
- Test thoroughly before submitting

---

## 📝 Changelog

### Version 2.2 (Current - Enhanced)
- ✨ Added gamification system (10 achievements)
- ✨ Implemented email notifications (6 templates)
- ✨ Created smart waitlist with auto-promotion
- 🎨 Enhanced UI with stats and leaderboard pages
- 📚 Comprehensive documentation

### Version 2.1 (Refactored)
- ♻️ Refactored monolithic code into modular architecture
- 📦 Created service layer for business logic
- 🗄️ Abstracted database layer
- 📖 Added technical documentation

### Version 1.0 (Original)
- 🎉 Initial release
- ✅ Basic RSVP functionality
- 👥 Team generation
- 📅 Game scheduling

---

## 🐛 Known Issues

- Email notifications require SMTP configuration (optional feature)
- First-time database setup may take a moment
- Session state storage doesn't persist between app restarts

See [Issues](https://github.com/kosof16/Basketball-Organizer-App/issues) for full list.

---

## 🗺️ Roadmap

### Short Term
- [ ] Mobile app (React Native)
- [ ] SMS notifications (Twilio)
- [ ] Payment integration (Stripe)
- [ ] Photo sharing
- [ ] Recurring game scheduling

### Long Term
- [ ] Multi-sport support
- [ ] Tournament management
- [ ] Team statistics tracking
- [ ] Social features (chat, comments)
- [ ] API for third-party integrations

---

## 📚 Documentation

- **[FEATURES.md](FEATURES.md)** - Complete feature documentation
- **[REFACTORING.md](REFACTORING.md)** - Architecture guide
- **[README_ENHANCEMENTS.md](README_ENHANCEMENTS.md)** - Enhancement summary
- **Inline Docstrings** - Every function documented

---

## 🙏 Acknowledgments

- **Streamlit** - Amazing web framework
- **Altair** - Beautiful visualizations
- **PostgreSQL** - Robust database
- **Basketball Community** - Inspiration and feedback

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 📧 Contact & Support

- **Issues**: [GitHub Issues](https://github.com/kosof16/Basketball-Organizer-App/issues)
- **Discussions**: [GitHub Discussions](https://github.com/kosof16/Basketball-Organizer-App/discussions)
- **Email**: your-email@example.com

---

## ⭐ Show Your Support

If you find this project useful, please consider:
- ⭐ Starring the repository
- 🐛 Reporting bugs
- 💡 Suggesting features
- 🤝 Contributing code
- 📢 Sharing with others

---

## 🎯 Quick Links

- [Live Demo](https://your-app.streamlit.app) *(if deployed)*
- [Documentation](FEATURES.md)
- [Issue Tracker](https://github.com/kosof16/Basketball-Organizer-App/issues)
- [Release Notes](https://github.com/kosof16/Basketball-Organizer-App/releases)

---

<div align="center">

**Made with ❤️ for basketball communities everywhere**

🏀 **Keep ballin'!** 🏀

</div>
