import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# Hardcoded Gmail credentials (fallback if not set in admin panel)
HARDCODED_GMAIL = "examify.site@gmail.com"
HARDCODED_PASSWORD = "bptn jjav pjnr infz"


def get_email_settings():
    """Get email settings from DB, falling back to hardcoded credentials."""
    from models import EmailSettings
    settings = EmailSettings.query.first()
    
    # Use hardcoded credentials as fallback if DB settings are empty
    if settings:
        if not settings.gmail_address:
            settings.gmail_address = HARDCODED_GMAIL
        if not settings.gmail_app_password:
            settings.gmail_app_password = HARDCODED_PASSWORD
    
    return settings


def send_email(to_email, subject, html_body, settings=None):
    """Send a styled HTML email via Gmail SMTP."""
    if not settings:
        settings = get_email_settings()
    
    # Use hardcoded as final fallback
    gmail_addr = (settings.gmail_address if settings and settings.gmail_address else HARDCODED_GMAIL)
    gmail_pass = (settings.gmail_app_password if settings and settings.gmail_app_password else HARDCODED_PASSWORD)
    
    if not to_email:
        print("[Email] No recipient email. Skipping.")
        return False

    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"Bill Splitter <{gmail_addr}>"
        msg['To'] = to_email

        msg.attach(MIMEText(html_body, 'html'))

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(gmail_addr, gmail_pass)
            server.sendmail(gmail_addr, to_email, msg.as_string())
        
        print(f"[Email] Sent to {to_email}: {subject}")
        return True

    except Exception as e:
        print(f"[Email] Failed to send to {to_email}: {e}")
        return False



def expense_notification_html(payer_name, expense_description, total_amount, user_amount, all_splits, expense_date):
    """Generate a beautiful styled HTML email for expense notification."""
    splits_rows = ""
    for name, amount in all_splits:
        splits_rows += f"""
        <tr>
            <td style="padding: 10px 16px; border-bottom: 1px solid #f0f0f0; color: #444;">{name}</td>
            <td style="padding: 10px 16px; border-bottom: 1px solid #f0f0f0; text-align: right; font-weight: 600; color: #6a11cb;">PKR {amount:.2f}</td>
        </tr>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#f4f6fb; font-family: 'Segoe UI', Arial, sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fb; padding: 40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:16px; overflow:hidden; box-shadow: 0 4px 24px rgba(106,17,203,0.10);">
        
        <!-- Header -->
        <tr>
          <td style="background: linear-gradient(135deg, #6a11cb 0%, #2575fc 100%); padding: 36px 40px; text-align:center;">
            <h1 style="margin:0; color:#fff; font-size:26px; font-weight:700; letter-spacing:-0.5px;">💸 New Expense Added</h1>
            <p style="margin:8px 0 0; color:rgba(255,255,255,0.85); font-size:14px;">{expense_date}</p>
          </td>
        </tr>
        
        <!-- Greeting -->
        <tr>
          <td style="padding: 32px 40px 0;">
            <p style="margin:0; font-size:16px; color:#333;">Hi there! 👋</p>
            <p style="margin:12px 0 0; font-size:15px; color:#555; line-height:1.6;">
              <strong style="color:#6a11cb;">{payer_name}</strong> added a new expense and you're included in the split.
            </p>
          </td>
        </tr>
        
        <!-- Expense Card -->
        <tr>
          <td style="padding: 24px 40px;">
            <div style="background: linear-gradient(135deg, #f8f0ff, #eef4ff); border-radius:12px; padding: 24px; border-left: 4px solid #6a11cb;">
              <p style="margin:0 0 6px; font-size:13px; color:#888; text-transform:uppercase; letter-spacing:1px;">Expense</p>
              <p style="margin:0 0 16px; font-size:22px; font-weight:700; color:#222;">{expense_description}</p>
              <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:12px;">
                <div>
                  <p style="margin:0; font-size:12px; color:#888;">Total Amount</p>
                  <p style="margin:4px 0 0; font-size:20px; font-weight:700; color:#6a11cb;">PKR {total_amount:.2f}</p>
                </div>
                <div style="text-align:right;">
                  <p style="margin:0; font-size:12px; color:#888;">Your Share</p>
                  <p style="margin:4px 0 0; font-size:20px; font-weight:700; color:#e74c3c;">PKR {user_amount:.2f}</p>
                </div>
              </div>
            </div>
          </td>
        </tr>
        
        <!-- Split Breakdown -->
        <tr>
          <td style="padding: 0 40px 24px;">
            <p style="margin:0 0 12px; font-size:14px; font-weight:600; color:#333;">Split Breakdown</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px; overflow:hidden; border: 1px solid #eee;">
              <tr style="background:#f8f8f8;">
                <th style="padding: 10px 16px; text-align:left; font-size:13px; color:#666; font-weight:600;">Person</th>
                <th style="padding: 10px 16px; text-align:right; font-size:13px; color:#666; font-weight:600;">Amount</th>
              </tr>
              {splits_rows}
            </table>
          </td>
        </tr>
        
        <!-- CTA -->
        <tr>
          <td style="padding: 0 40px 32px; text-align:center;">
            <p style="margin:0 0 16px; font-size:14px; color:#888;">Log in to view details or mark as paid.</p>
            <a href="http://127.0.0.1:5000" style="display:inline-block; background: linear-gradient(135deg, #6a11cb, #2575fc); color:#fff; text-decoration:none; padding: 14px 32px; border-radius:8px; font-weight:600; font-size:15px;">View Dashboard →</a>
          </td>
        </tr>
        
        <!-- Footer -->
        <tr>
          <td style="background:#f8f8f8; padding: 20px 40px; text-align:center; border-top: 1px solid #eee;">
            <p style="margin:0; font-size:12px; color:#aaa;">Bill Splitter App • Sent automatically</p>
          </td>
        </tr>
        
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def reminder_html(username, debts):
    """Generate a styled reminder email for unpaid debts."""
    debt_rows = ""
    total_owed = 0
    for debt in debts:
        debt_rows += f"""
        <tr>
          <td style="padding: 12px 16px; border-bottom: 1px solid #f0f0f0; color:#444;">{debt['expense']}</td>
          <td style="padding: 12px 16px; border-bottom: 1px solid #f0f0f0; color:#666;">{debt['payer']}</td>
          <td style="padding: 12px 16px; border-bottom: 1px solid #f0f0f0; text-align:right; font-weight:600; color:#e74c3c;">PKR {debt['amount']:.2f}</td>
        </tr>"""
        total_owed += debt['amount']

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#f4f6fb; font-family: 'Segoe UI', Arial, sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fb; padding: 40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:16px; overflow:hidden; box-shadow: 0 4px 24px rgba(231,76,60,0.10);">
        
        <!-- Header -->
        <tr>
          <td style="background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%); padding: 36px 40px; text-align:center;">
            <h1 style="margin:0; color:#fff; font-size:26px; font-weight:700;">🔔 Payment Reminder</h1>
            <p style="margin:8px 0 0; color:rgba(255,255,255,0.85); font-size:14px;">You have outstanding balances</p>
          </td>
        </tr>
        
        <!-- Greeting -->
        <tr>
          <td style="padding: 32px 40px 0;">
            <p style="margin:0; font-size:16px; color:#333;">Hi <strong>{username}</strong>! 👋</p>
            <p style="margin:12px 0 0; font-size:15px; color:#555; line-height:1.6;">
              This is a friendly reminder that you have unpaid balances. Please settle them at your earliest convenience.
            </p>
          </td>
        </tr>
        
        <!-- Total -->
        <tr>
          <td style="padding: 24px 40px;">
            <div style="background: linear-gradient(135deg, #fff5f5, #fff); border-radius:12px; padding: 20px; border-left: 4px solid #e74c3c; text-align:center;">
              <p style="margin:0; font-size:13px; color:#888; text-transform:uppercase; letter-spacing:1px;">Total You Owe</p>
              <p style="margin:8px 0 0; font-size:32px; font-weight:700; color:#e74c3c;">PKR {total_owed:.2f}</p>
            </div>
          </td>
        </tr>
        
        <!-- Debt Breakdown -->
        <tr>
          <td style="padding: 0 40px 24px;">
            <p style="margin:0 0 12px; font-size:14px; font-weight:600; color:#333;">Outstanding Balances</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="border-radius:10px; overflow:hidden; border: 1px solid #eee;">
              <tr style="background:#f8f8f8;">
                <th style="padding: 10px 16px; text-align:left; font-size:13px; color:#666; font-weight:600;">Expense</th>
                <th style="padding: 10px 16px; text-align:left; font-size:13px; color:#666; font-weight:600;">Paid By</th>
                <th style="padding: 10px 16px; text-align:right; font-size:13px; color:#666; font-weight:600;">You Owe</th>
              </tr>
              {debt_rows}
            </table>
          </td>
        </tr>
        
        <!-- CTA -->
        <tr>
          <td style="padding: 0 40px 32px; text-align:center;">
            <a href="http://127.0.0.1:5000" style="display:inline-block; background: linear-gradient(135deg, #e74c3c, #c0392b); color:#fff; text-decoration:none; padding: 14px 32px; border-radius:8px; font-weight:600; font-size:15px;">Pay Now →</a>
          </td>
        </tr>
        
        <!-- Footer -->
        <tr>
          <td style="background:#f8f8f8; padding: 20px 40px; text-align:center; border-top: 1px solid #eee;">
            <p style="margin:0; font-size:12px; color:#aaa;">Bill Splitter App • Automated Reminder</p>
          </td>
        </tr>
        
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_expense_notification(expense, settlements):
    """Send expense notification emails to all included users (except payer)."""
    settings = get_email_settings()
    if not settings or not settings.gmail_address:
        return

    payer_name = expense.payer.username
    all_splits = [(s.debtor.username, s.amount_due) for s in settlements]
    expense_date = expense.date.strftime('%B %d, %Y at %I:%M %p')

    for settlement in settlements:
        user = settlement.debtor
        # Skip payer (they already know) and users without email
        if user.id == expense.payer_id or not user.email:
            continue

        html = expense_notification_html(
            payer_name=payer_name,
            expense_description=expense.description,
            total_amount=expense.amount,
            user_amount=settlement.amount_due,
            all_splits=all_splits,
            expense_date=expense_date
        )
        send_email(
            to_email=user.email,
            subject=f"💸 New Expense: {expense.description} — PKR {expense.amount:.2f}",
            html_body=html,
            settings=settings
        )


def payment_received_html(payer_name, payer_username, debtor_name, expense_description, amount_paid, paid_date):
    """Generate a styled HTML email notifying the payer that someone paid them."""
    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0; padding:0; background:#f4f6fb; font-family: 'Segoe UI', Arial, sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f6fb; padding: 40px 0;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff; border-radius:16px; overflow:hidden; box-shadow: 0 4px 24px rgba(46,204,113,0.12);">

        <!-- Header -->
        <tr>
          <td style="background: linear-gradient(135deg, #2ecc71 0%, #27ae60 100%); padding: 36px 40px; text-align:center;">
            <h1 style="margin:0; color:#fff; font-size:26px; font-weight:700;">✅ Payment Received!</h1>
            <p style="margin:8px 0 0; color:rgba(255,255,255,0.85); font-size:14px;">{paid_date}</p>
          </td>
        </tr>

        <!-- Greeting -->
        <tr>
          <td style="padding: 32px 40px 0;">
            <p style="margin:0; font-size:16px; color:#333;">Hi <strong>{payer_name}</strong>! 👋</p>
            <p style="margin:12px 0 0; font-size:15px; color:#555; line-height:1.6;">
              Great news! <strong style="color:#27ae60;">{debtor_name}</strong> has marked their share as paid.
            </p>
          </td>
        </tr>

        <!-- Payment Card -->
        <tr>
          <td style="padding: 24px 40px;">
            <div style="background: linear-gradient(135deg, #f0fff4, #e8f8f5); border-radius:12px; padding: 24px; border-left: 4px solid #2ecc71;">
              <p style="margin:0 0 6px; font-size:13px; color:#888; text-transform:uppercase; letter-spacing:1px;">Expense</p>
              <p style="margin:0 0 16px; font-size:20px; font-weight:700; color:#222;">{expense_description}</p>
              <div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:12px;">
                <div>
                  <p style="margin:0; font-size:12px; color:#888;">Paid By</p>
                  <p style="margin:4px 0 0; font-size:18px; font-weight:700; color:#27ae60;">{debtor_name}</p>
                </div>
                <div style="text-align:right;">
                  <p style="margin:0; font-size:12px; color:#888;">Amount</p>
                  <p style="margin:4px 0 0; font-size:24px; font-weight:700; color:#27ae60;">PKR {amount_paid:.2f}</p>
                </div>
              </div>
            </div>
          </td>
        </tr>

        <!-- CTA -->
        <tr>
          <td style="padding: 0 40px 32px; text-align:center;">
            <p style="margin:0 0 16px; font-size:14px; color:#888;">Log in to view your updated balance.</p>
            <a href="http://127.0.0.1:5000" style="display:inline-block; background: linear-gradient(135deg, #2ecc71, #27ae60); color:#fff; text-decoration:none; padding: 14px 32px; border-radius:8px; font-weight:600; font-size:15px;">View Dashboard →</a>
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#f8f8f8; padding: 20px 40px; text-align:center; border-top: 1px solid #eee;">
            <p style="margin:0; font-size:12px; color:#aaa;">Bill Splitter App • Sent automatically</p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def send_payment_notification(settlement):
    """Notify the expense payer that a user has paid their share."""
    settings = get_email_settings()
    if not settings or not settings.gmail_address:
        return

    payer = settlement.expense.payer
    debtor = settlement.debtor

    if not payer.email:
        print(f"[Email] Payer {payer.username} has no email, skipping payment notification.")
        return

    paid_date = datetime.utcnow().strftime('%B %d, %Y at %I:%M %p')
    html = payment_received_html(
        payer_name=payer.username,
        payer_username=payer.username,
        debtor_name=debtor.username,
        expense_description=settlement.expense.description,
        amount_paid=settlement.amount_due,
        paid_date=paid_date
    )
    send_email(
        to_email=payer.email,
        subject=f"✅ {debtor.username} paid PKR {settlement.amount_due:.2f} for '{settlement.expense.description}'",
        html_body=html,
        settings=settings
    )


def send_bulk_reminders(app):
    """Send reminder emails to all users with unpaid debts."""
    from models import Settlement, EmailSettings
    settings = get_email_settings()
    if not settings or not settings.gmail_address:
        return

    with app.app_context():
        # Get all unpaid settlements grouped by user
        unpaid = Settlement.query.filter_by(is_paid=False).all()
        
        user_debts = {}
        for s in unpaid:
            uid = s.user_id
            if uid not in user_debts:
                user_debts[uid] = []
            user_debts[uid].append({
                'expense': s.expense.description,
                'payer': s.expense.payer.username,
                'amount': s.amount_due
            })
        
        for user_id, debts in user_debts.items():
            user = s.debtor.__class__.query.get(user_id)
            if user and user.email and not user.is_admin:
                html = reminder_html(user.username, debts)
                send_email(
                    to_email=user.email,
                    subject=f"🔔 Payment Reminder — PKR {sum(d['amount'] for d in debts):.2f} outstanding",
                    html_body=html,
                    settings=settings
                )
        
        # Update last reminder sent time
        settings.last_reminder_sent = datetime.utcnow()
        from models import db
        db.session.commit()
