# Quick Testing Guide for TOTP 2FA Implementation

## Installation

Before testing, install the new dependencies:

```bash
pip install -r requirements.txt
```

This installs:
- `pyotp` - TOTP (Time-based One-Time Password) library
- `qrcode` - QR code generation

## Test Scenario 1: Register Account WITH 2FA

1. **Start client**:
   ```bash
   python client.py
   ```

2. **Click "Register here"** link on login screen

3. **Fill in account details**:
   - Username: `testuser2fa`
   - Password: `password123`
   - Account Type: Select "Parent"

4. **When prompted for 2FA**:
   - Click "YES" on the dialog asking about 2FA
   - A new window opens showing a QR code
   - **Scan with authenticator app**:
     - Open Google Authenticator, Authy, or similar
     - Scan the QR code (or enter the base32 secret manually if shown)
     - The app will display a 6-digit code that changes every 30 seconds

5. **Confirm setup**:
   - Click "OK, I've Scanned It"
   - Account is created successfully
   - You'll see: "Account created with 2FA enabled!"

## Test Scenario 2: Login WITH 2FA

1. **Start client**:
   ```bash
   python client.py
   ```

2. **Enter credentials**:
   - Username: `testuser2fa` (from scenario 1)
   - Password: `password123`
   - Click LOGIN

3. **When prompted for 2FA code**:
   - A dialog appears asking for the 6-digit code
   - Open your authenticator app
   - Copy the current 6-digit code
   - Paste into the dialog or type it in
   - Click OK

4. **Expected result**:
   - Login succeeds
   - You're taken to Parent or Child dashboard depending on role

## Test Scenario 3: Register Account WITHOUT 2FA

1. **Start client**:
   ```bash
   python client.py
   ```

2. **Click "Register here"**

3. **Fill in account details**:
   - Username: `testuser_no_2fa`
   - Password: `password123`
   - Account Type: Select "Parent"

4. **When prompted for 2FA**:
   - Click "NO"
   - Account is created normally

5. **Later, when logging in**:
   - Enter username and password
   - Direct login (no 2FA code prompt)
   - Immediate access to dashboard

## Test Scenario 4: Failed 2FA Attempts

1. **Login with 2FA-enabled account**

2. **When prompted for code**:
   - Intentionally enter wrong code (e.g., "000000")
   - Click OK

3. **Expected behavior**:
   - Error message: "Invalid 2FA code. Try again."
   - You can try up to 3 times

4. **After 3 failed attempts**:
   - Error: "Too many failed attempts"
   - Must restart and login again

## Server Logs to Watch

When running `python server.py`, watch for these log messages:

**Registration with 2FA**:
```
🔐  2FA enabled for new user 'testuser2fa' (id=1)
📝 Register OK  'testuser2fa'  role=parent  new_id=1  ip=127.0.0.1
```

**Login step 1 (password validation)**:
```
🔐 Login step 1/2 — 'testuser2fa' requires 2FA code
```

**Login step 2 (2FA validation)**:
```
✅ Login OK (2FA verified)  'testuser2fa'  role=parent  id=1
```

**Failed 2FA attempts**:
```
❌ 2FA failed (max attempts) for 'testuser2fa'
```

## Database Verification

You can verify 2FA is stored correctly by checking the database:

```bash
# In MySQL:
SELECT client_id, client_username, client_2fa_enabled, client_2fa_secret 
FROM clients;
```

You should see:
- Accounts with `client_2fa_enabled = 1` and a secret string
- Accounts with `client_2fa_enabled = 0` and NULL secret

## Common Issues

### QR Code Won't Display
- Ensure `qrcode` library is installed: `pip install qrcode[pil]`
- The window should pop up in a new Tkinter window

### "Invalid 2FA Code" Even Though Code is Correct
- Make sure your device time is synchronized
- The code changes every 30 seconds — use the current code
- Try the code from the next time window (wait for it to change)

### 2FA Secret Not Storing
- Check server logs for "Migration: added column client_2fa_enabled"
- Ensure MySQL `clients` table has the new columns
- Try restarting the server to trigger migrations

### Authenticator App Not Recognizing QR
- Try manual entry instead of QR code scan
- The base32 secret is shown in text form below the QR code
- Copy and paste it into your authenticator app's manual entry option

## Key Implementation Details

- **Secret storage**: Base32-encoded random string (24 characters)
- **QR provision URI**: `otpauth://totp/username@Parental%20Control?secret=...`
- **Code validation**: HMAC-SHA1, 6-digit code, 30-second time step
- **Tolerance**: Current time window + 1 previous window (35 seconds max drift)
- **Database columns**:
  - `client_2fa_enabled` (BOOLEAN)
  - `client_2fa_secret` (VARCHAR(255))

## Next Steps (Optional Enhancements)

1. **Account Settings UI**: Allow users to enable/disable 2FA after account creation
2. **Backup Codes**: Generate 10 single-use backup codes for account recovery
3. **2FA Recovery**: Email or SMS-based recovery if user loses authenticator
4. **Audit Log**: Track all 2FA setup and login events
5. **Session Timeout**: Expire waiting_2fa sessions after 5 minutes
6. **Rate Limiting**: Block IP after too many failed 2FA attempts
