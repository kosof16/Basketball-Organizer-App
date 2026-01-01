# 🔐 Admin Setup Guide

## Quick Start - Admin Login

### Default Credentials

```
Username: admin
Password: basketball2024
```

⚠️ **IMPORTANT**: Change the default password before deploying to production!

---

## Changing Admin Password

### Method 1: Update Secrets File

1. Open `.streamlit/secrets.toml`
2. Modify the credentials:
   ```toml
   admin_username = "your-username"
   admin_password = "your-secure-password"
   ```
3. Restart the Streamlit app

### Method 2: Environment Variables (Streamlit Cloud)

When deploying to Streamlit Cloud:

1. Go to your app settings
2. Click "Secrets" in the left menu
3. Add:
   ```toml
   admin_username = "your-username"
   admin_password = "your-secure-password"
   ```
4. Click "Save"

---

## Security Best Practices

### Password Requirements

✅ **Recommended:**
- Minimum 12 characters
- Mix of uppercase and lowercase
- Include numbers and symbols
- Don't reuse passwords from other sites
- Use a password manager

❌ **Avoid:**
- Common words or phrases
- Personal information
- Sequential numbers (123456)
- Default passwords

### Example Strong Password

```
MyB@sketb@ll2024!Org
```

---

## Admin Panel Features

Once logged in, you'll have access to:

### 📅 Schedule Games
- Create new games
- Set date, time, location
- Automated RSVP opening

### 👥 Manage RSVPs
- View all responses
- Manually adjust player statuses
- Move players between confirmed/waitlist
- Delete responses

### 🎮 Gamification Overview
- Total players registered
- Total points awarded
- Average engagement metrics
- Top player statistics

### 📊 Analytics (Future)
- Attendance trends
- Player reliability scores
- Game popularity metrics

---

## Troubleshooting

### "Invalid Credentials" Error

**Check:**
1. Username is correct (default: `admin`)
2. Password matches secrets file exactly
3. No extra spaces in username/password
4. Secrets file is properly formatted

**Debug Steps:**
```bash
# Check secrets file exists
ls -la .streamlit/secrets.toml

# View secrets (be careful - contains passwords!)
cat .streamlit/secrets.toml

# Look for these lines:
# admin_username = "admin"
# admin_password = "your-password"
```

### App Not Reading Secrets

**If using Streamlit Cloud:**
1. Secrets must be added in the web dashboard
2. Format must be valid TOML
3. Check for syntax errors

**If running locally:**
1. Ensure `.streamlit/secrets.toml` exists
2. Check file permissions
3. Restart Streamlit app

---

## Session Management

### Session Timeout

Admin sessions expire after **30 minutes** of inactivity for security.

To change timeout:
1. Open `src/config.py`
2. Modify:
   ```python
   SESSION_TIMEOUT_MINUTES = 30  # Change this value
   ```

### Manual Logout

Always click **"🚪 Logout"** button when done to:
- Clear session state
- Log admin action
- Prevent unauthorized access

---

## Multi-Admin Setup (Future Enhancement)

Currently supports single admin. For multi-admin:

**Option 1: Shared Credentials**
```toml
admin_username = "admin"
admin_password = "shared-password"
```

**Option 2: Database-Backed (Future)**
- Store admin users in database
- Individual credentials per admin
- Role-based permissions
- Audit trail by user

---

## Resetting Admin Password

### If You Forgot Password

1. **Access Server/Deployment:**
   - Update `.streamlit/secrets.toml`
   - Or update Streamlit Cloud secrets

2. **Can't Access Deployment:**
   - Redeploy app with new secrets
   - Or access server terminal

3. **Emergency:**
   - Fork repository
   - Update secrets
   - Deploy new instance

---

## Security Considerations

### ✅ Do:
- Change default password immediately
- Use strong, unique passwords
- Enable 2FA on deployment platform
- Restrict admin access
- Monitor admin logs
- Regular password rotation

### ❌ Don't:
- Share admin credentials
- Commit secrets to git
- Use weak passwords
- Leave sessions open on shared computers
- Disable security features

---

## Production Deployment

### Before Going Live:

1. **Change Credentials**
   ```toml
   admin_password = "super-secure-random-password"
   ```

2. **Enable Logging**
   - Monitor admin actions
   - Track authentication attempts
   - Review regularly

3. **Backup Secrets**
   - Store securely (password manager)
   - Don't commit to repository
   - Document recovery process

4. **Test Access**
   - Verify login works
   - Test session timeout
   - Confirm logout functionality

---

## Contact & Support

- **Issues**: [GitHub Issues](https://github.com/kosof16/Basketball-Organizer-App/issues)
- **Security**: Report vulnerabilities privately

---

## Quick Reference

```bash
# Start app
streamlit run app_enhanced.py

# Login
Username: admin
Password: basketball2024  # CHANGE THIS!

# Admin Panel
Navigate to: ⚙️ Admin (in sidebar)
```

Remember: **Security is everyone's responsibility!** 🔒
