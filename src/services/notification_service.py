"""Email notification service for player communications"""
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, date, timedelta
from typing import List, Optional, Dict
import streamlit as st

logger = logging.getLogger(__name__)

# Email templates
EMAIL_TEMPLATES = {
    "game_scheduled": {
        "subject": "🏀 New Basketball Game Scheduled - {game_date}",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4CAF50;">🏀 New Game Scheduled!</h2>
                <p>Hi there!</p>
                <p>A new basketball game has been scheduled. Don't miss out!</p>

                <div style="background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%); color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">Game Details</h3>
                    <p><strong>📅 Date:</strong> {game_date}</p>
                    <p><strong>🕐 Time:</strong> {start_time} - {end_time}</p>
                    <p><strong>📍 Location:</strong> {location}</p>
                    <p><strong>⏰ RSVP Deadline:</strong> {deadline}</p>
                </div>

                <p><a href="{app_url}" style="background-color: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0;">RSVP Now</a></p>

                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    Don't wait! Spots fill up fast.<br>
                    See you on the court! 🏀
                </p>
            </div>
        </body>
        </html>
        """
    },

    "rsvp_confirmation": {
        "subject": "✅ RSVP Confirmed - {game_date}",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4CAF50;">✅ You're In!</h2>
                <p>Hey {player_name}!</p>
                <p>Your RSVP has been confirmed. We're excited to see you on the court!</p>

                <div style="background: #f5f5f5; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0;">
                    <p style="margin: 5px 0;"><strong>📅 Date:</strong> {game_date}</p>
                    <p style="margin: 5px 0;"><strong>🕐 Time:</strong> {start_time}</p>
                    <p style="margin: 5px 0;"><strong>📍 Location:</strong> {location}</p>
                    {guests_info}
                </div>

                {points_earned}

                <p>Need to cancel? <a href="{app_url}">Update your RSVP</a></p>

                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    See you soon! 🏀
                </p>
            </div>
        </body>
        </html>
        """
    },

    "game_reminder": {
        "subject": "🏀 Game Tomorrow - Don't Forget!",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #FF9800;">🏀 Game Reminder</h2>
                <p>Hey {player_name}!</p>
                <p><strong>The game is tomorrow!</strong> Just a friendly reminder about your confirmed RSVP.</p>

                <div style="background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%); color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">📅 Tomorrow's Game</h3>
                    <p><strong>🕐 Time:</strong> {start_time} - {end_time}</p>
                    <p><strong>📍 Location:</strong> {location}</p>
                    <p><strong>👥 Players:</strong> {confirmed_count} confirmed</p>
                </div>

                <p>What to bring:</p>
                <ul>
                    <li>🏀 Basketball shoes</li>
                    <li>💧 Water bottle</li>
                    <li>👕 Extra shirt</li>
                    <li>🎉 Good vibes!</li>
                </ul>

                <p>Can't make it? <a href="{app_url}">Cancel your RSVP</a> to free up your spot.</p>

                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    See you tomorrow! 🏀
                </p>
            </div>
        </body>
        </html>
        """
    },

    "waitlist_promoted": {
        "subject": "🎉 You're Off the Waitlist!",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4CAF50;">🎉 Great News!</h2>
                <p>Hey {player_name}!</p>
                <p><strong>A spot just opened up and you've been promoted from the waitlist!</strong></p>

                <div style="background: linear-gradient(135deg, #4CAF50 0%, #45a049 100%); color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">✅ You're Confirmed!</h3>
                    <p><strong>📅 Date:</strong> {game_date}</p>
                    <p><strong>🕐 Time:</strong> {start_time} - {end_time}</p>
                    <p><strong>📍 Location:</strong> {location}</p>
                </div>

                <p style="background: #FFF3E0; padding: 15px; border-left: 4px solid #FF9800; margin: 20px 0;">
                    <strong>⏰ Please confirm you can still make it!</strong><br>
                    If you can no longer attend, please cancel so we can offer your spot to someone else.
                </p>

                <p><a href="{app_url}" style="background-color: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0;">Confirm Attendance</a></p>

                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    See you on the court! 🏀
                </p>
            </div>
        </body>
        </html>
        """
    },

    "achievement_unlocked": {
        "subject": "🏆 Achievement Unlocked: {achievement_name}",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #FF9800;">🏆 Achievement Unlocked!</h2>
                <p>Congratulations {player_name}!</p>

                <div style="background: linear-gradient(135deg, #FF9800 0%, #F57C00 100%); color: white; padding: 30px; border-radius: 10px; margin: 20px 0; text-align: center;">
                    <div style="font-size: 64px; margin-bottom: 10px;">{achievement_icon}</div>
                    <h2 style="margin: 10px 0;">{achievement_name}</h2>
                    <p style="font-size: 18px; margin: 10px 0;">{achievement_description}</p>
                    <p style="font-size: 24px; font-weight: bold; margin-top: 20px;">+{points} Points</p>
                </div>

                <p>Your current stats:</p>
                <ul>
                    <li>🎯 Total Points: {total_points}</li>
                    <li>🏀 Games Attended: {games_attended}</li>
                    <li>🏆 Achievements: {total_achievements}</li>
                    <li>📊 Rank: #{rank}</li>
                </ul>

                <p><a href="{app_url}" style="background-color: #FF9800; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0;">View Profile</a></p>

                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    Keep up the great work! 🏀
                </p>
            </div>
        </body>
        </html>
        """
    },

    "weekly_digest": {
        "subject": "📊 Your Weekly Basketball Recap",
        "body": """
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #4CAF50;">📊 Your Weekly Recap</h2>
                <p>Hey {player_name}!</p>
                <p>Here's your basketball activity for the past week:</p>

                <div style="background: #f5f5f5; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3>This Week</h3>
                    <p>🏀 Games Attended: {games_this_week}</p>
                    <p>🎯 Points Earned: +{points_this_week}</p>
                    <p>🔥 Current Streak: {current_streak} games</p>
                    {new_achievements}
                </div>

                <div style="background: linear-gradient(135deg, #2196F3 0%, #1976D2 100%); color: white; padding: 20px; border-radius: 10px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">📅 Upcoming Games</h3>
                    {upcoming_games}
                </div>

                <div style="background: #FFF3E0; padding: 15px; border-left: 4px solid #FF9800; margin: 20px 0;">
                    <h4 style="margin-top: 0;">🏆 Leaderboard Position</h4>
                    <p>You're ranked <strong>#{rank}</strong> overall!</p>
                    <p>{leaderboard_message}</p>
                </div>

                <p><a href="{app_url}" style="background-color: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 0;">View Full Stats</a></p>

                <p style="color: #666; font-size: 14px; margin-top: 30px;">
                    See you on the court! 🏀
                </p>
            </div>
        </body>
        </html>
        """
    }
}


class EmailService:
    """Email notification service"""

    def __init__(self):
        """Initialize email service with configuration"""
        self.enabled = self._check_email_config()
        self.smtp_server = None
        self.smtp_port = None
        self.sender_email = None
        self.sender_password = None
        self.app_url = "https://your-basketball-app.com"  # Update with actual URL

        if self.enabled:
            self._load_config()

    def _check_email_config(self) -> bool:
        """Check if email configuration is available"""
        return "email" in st.secrets

    def _load_config(self):
        """Load email configuration from secrets"""
        try:
            email_config = st.secrets["email"]
            self.smtp_server = email_config.get("smtp_server", "smtp.gmail.com")
            self.smtp_port = email_config.get("smtp_port", 587)
            self.sender_email = email_config.get("sender_email")
            self.sender_password = email_config.get("sender_password")
            self.app_url = email_config.get("app_url", self.app_url)
        except Exception as e:
            logger.error(f"Error loading email config: {e}")
            self.enabled = False

    def send_email(self, to_email: str, subject: str, html_body: str) -> bool:
        """
        Send an email

        Args:
            to_email: Recipient email address
            subject: Email subject
            html_body: HTML email body

        Returns:
            True if sent successfully, False otherwise
        """
        if not self.enabled:
            logger.warning("Email service not configured. Email not sent.")
            return False

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.sender_email
            msg['To'] = to_email

            # Add HTML content
            html_part = MIMEText(html_body, 'html')
            msg.attach(html_part)

            # Send email
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            logger.info(f"Email sent successfully to {to_email}: {subject}")
            return True

        except Exception as e:
            logger.error(f"Error sending email to {to_email}: {e}")
            return False

    def send_game_scheduled_notification(self, to_email: str, game_details: Dict) -> bool:
        """Send notification when a new game is scheduled"""
        template = EMAIL_TEMPLATES["game_scheduled"]

        subject = template["subject"].format(
            game_date=game_details["game_date"].strftime("%A, %B %d")
        )

        body = template["body"].format(
            game_date=game_details["game_date"].strftime("%A, %B %d, %Y"),
            start_time=game_details["start_time"],
            end_time=game_details["end_time"],
            location=game_details["location"],
            deadline=game_details["deadline"].strftime("%B %d"),
            app_url=self.app_url
        )

        return self.send_email(to_email, subject, body)

    def send_rsvp_confirmation(self, to_email: str, player_name: str, game_details: Dict,
                               guests: List[str] = None, points_earned: int = 0) -> bool:
        """Send RSVP confirmation email"""
        template = EMAIL_TEMPLATES["rsvp_confirmation"]

        subject = template["subject"].format(
            game_date=game_details["game_date"].strftime("%A, %B %d")
        )

        guests_info = ""
        if guests:
            guests_info = f"<p style='margin: 5px 0;'><strong>👥 Guests:</strong> {', '.join(guests)}</p>"

        points_info = ""
        if points_earned > 0:
            points_info = f"""
            <div style="background: #E8F5E9; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p style="margin: 0; color: #4CAF50;"><strong>🎯 Points Earned: +{points_earned}</strong></p>
            </div>
            """

        body = template["body"].format(
            player_name=player_name,
            game_date=game_details["game_date"].strftime("%A, %B %d"),
            start_time=game_details["start_time"],
            location=game_details["location"],
            guests_info=guests_info,
            points_earned=points_info,
            app_url=self.app_url
        )

        return self.send_email(to_email, subject, body)

    def send_game_reminder(self, to_email: str, player_name: str, game_details: Dict) -> bool:
        """Send game reminder email (24h before game)"""
        template = EMAIL_TEMPLATES["game_reminder"]

        subject = template["subject"]

        body = template["body"].format(
            player_name=player_name,
            start_time=game_details["start_time"],
            end_time=game_details["end_time"],
            location=game_details["location"],
            confirmed_count=game_details.get("confirmed_count", 0),
            app_url=self.app_url
        )

        return self.send_email(to_email, subject, body)

    def send_waitlist_promotion(self, to_email: str, player_name: str, game_details: Dict) -> bool:
        """Send notification when promoted from waitlist"""
        template = EMAIL_TEMPLATES["waitlist_promoted"]

        subject = template["subject"]

        body = template["body"].format(
            player_name=player_name,
            game_date=game_details["game_date"].strftime("%A, %B %d"),
            start_time=game_details["start_time"],
            end_time=game_details["end_time"],
            location=game_details["location"],
            app_url=self.app_url
        )

        return self.send_email(to_email, subject, body)

    def send_achievement_notification(self, to_email: str, player_name: str,
                                     achievement: Dict, player_stats: Dict) -> bool:
        """Send achievement unlocked notification"""
        template = EMAIL_TEMPLATES["achievement_unlocked"]

        subject = template["subject"].format(
            achievement_name=achievement["name"]
        )

        body = template["body"].format(
            player_name=player_name,
            achievement_icon=achievement["icon"],
            achievement_name=achievement["name"],
            achievement_description=achievement["description"],
            points=achievement["points"],
            total_points=player_stats.get("total_points", 0),
            games_attended=player_stats.get("games_attended", 0),
            total_achievements=len(player_stats.get("achievements", [])),
            rank=player_stats.get("rank", "N/A"),
            app_url=self.app_url
        )

        return self.send_email(to_email, subject, body)


# Global email service instance
email_service = EmailService()
