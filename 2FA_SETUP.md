# Two-Factor Authentication (2FA) Setup Guide

## Overview
The system now uses **TOTP-based Two-Factor Authentication** at the login stage. This is a time-based authentication method that works with authenticator apps like Google Authenticator, Authy, Microsoft Authenticator, etc.

## How It Works

### Registration with 2FA
1. User starts registration and is asked: *"Would you like to enable Two-Factor Authentication (2FA)?"*
2. If **YES**:
   - A TOTP secret is generated (a random base32 string)
   - A QR code is displayed for the user to scan with their authenticator app
   - The secret is also shown in text form for manual entry
   - User clicks "OK, I've Scanned It" to confirm
   - The secret is stored in the database with `client_2fa_enabled = TRUE`

3. If **NO**:
   - Account is created normally without 2FA
   - User can log in with just username and password

### Login with 2FA
1. User enters username and password
2. Server validates credentials
3. If **2FA is enabled** for that account:
   - Server responds with `LOGIN_2FA_REQUIRED`
   - Client prompts: *"Enter the 6-digit code from your authenticator"*
   - User enters the code
   - Client sends `2FA_CODE|<code>` to server
   - Server validates the code using TOTP algorithm (allows current window + 1 previous window for tolerance)
   - If valid → `LOGIN_OK` (user is logged in)
   - If invalid → `LOGIN_FAIL|2FA_INVALID_CODE` (user can retry, max 3 attempts)

4. If **2FA is NOT enabled**:
   - Server responds with `LOGIN_OK` immediately
   - User logs in directly

## Database Schema

The `clients` table now includes:
- `client_2fa_enabled` (BOOLEAN, DEFAULT FALSE) - whether 2FA is enabled for this account
- `client_2fa_secret` (VARCHAR(255)) - the TOTP secret key

## Files Modified

### Server-Side (`server.py`)
- **Added**: `pyotp` import for TOTP validation
- **Removed**: Pending registrations dictionary (parent-approval flow)
- **Updated**: `REGISTER` handler to accept and store 2FA secret
- **Updated**: `LOGIN` handler to check 2FA status and request code if needed
- **Added**: `2FA_CODE` handler to validate TOTP codes

### Client-Side (`client.py`)
- **Added**: `pyotp` and `qrcode` imports
- **Updated**: `register()` method to:
  - Ask user if they want 2FA
  - Generate TOTP secret
  - Display QR code for scanning
  - Include secret in registration message
- **Updated**: `login()` method to:
  - Handle `LOGIN_2FA_REQUIRED` response
  - Prompt for 6-digit code
  - Send code to server for validation
  - Handle 2FA errors (invalid code, max attempts)
- **Removed**: `2FA_CHALLENGE` handler (parent approval flow)

### Dependencies (`requirements.txt`)
- **Added**: `pyotp==2.9.0` (TOTP library)
- **Added**: `qrcode==7.4.2` (QR code generation)

## Testing 2FA

### Test Case 1: Register with 2FA
```bash
python client.py
# 1. Click "Register here"
# 2. Enter username and password
# 3. Select "Parent" role
# 4. When asked about 2FA, click "Yes"
# 5. A window will show a QR code
# 6. Use your authenticator app (Google Authenticator, Authy, etc.) to scan
# 7. Click "OK, I've Scanned It"
# 8. Account is created with 2FA enabled
```

### Test Case 2: Login with 2FA
```bash
python client.py
# 1. Enter username and password from account created with 2FA
# 2. Server asks for 2FA code
# 3. Open your authenticator app and enter the 6-digit code
# 4. Click OK
# 5. Login succeeds
```

### Test Case 3: Login WITHOUT 2FA
```bash
python client.py
# 1. Enter username and password from account created WITHOUT 2FA
# 2. Direct login → no 2FA prompt
# 3. Login succeeds immediately
```

## TOTP Details

- **Algorithm**: HMAC-SHA1
- **Time Step**: 30 seconds
- **Code Length**: 6 digits
- **Tolerance**: Current window + 1 previous window (allows users up to 35 seconds drift)
- **Max Attempts**: 3 failed attempts before lockout

## Security Considerations

✅ **Implemented**:
- TOTP-based 2FA (industry standard)
- QR code provisioning for easy setup
- Time-based rotating codes (changes every 30 seconds)
- Code validation with tolerance window
- Attempt limiting (max 3 tries)

⚠️ **Still TODO/Future Hardening**:
- Backup codes for account recovery
- 2FA reconfiguration after setup
- Rate limiting on failed 2FA attempts
- Session timeout for waiting_2fa entries
- Backup 2FA method (SMS, email)
- 2FA enforcement policy (require 2FA for all users)

## Troubleshooting

### QR Code Won't Scan
- Use the manual entry code displayed below the QR code
- Make sure your authenticator app supports TOTP

### "Invalid 2FA Code" Error
- Check that your device time is synchronized (most authenticator apps handle this)
- Make sure you're entering the current 6-digit code (it changes every 30 seconds)
- Try the code from the next time window

### "Too Many Failed Attempts"
- Wait a moment and try logging in again (the waiting_2fa session will timeout)
- Or restart the application

## Migration Notes

Old accounts created before 2FA implementation:
- `client_2fa_enabled` = FALSE (default)
- `client_2fa_secret` = NULL
- These accounts can still log in normally without 2FA
- Users can optionally set up 2FA through a future "Account Settings" feature (not yet implemented)
