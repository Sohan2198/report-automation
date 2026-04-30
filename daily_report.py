#!/usr/bin/env python3
"""Daily sales report script — fetches GA4 data from Windsor.ai and emails it."""

import os
import smtplib
import requests
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

WINDSOR_API_KEY = os.environ["WINDSOR_API_KEY"]
GMAIL_ADDRESS   = os.environ["GMAIL_ADDRESS"]
GMAIL_APP_PASS  = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
RECIPIENTS      = [e.strip() for e in os.environ.get("REPORT_RECIPIENT", GMAIL_ADDRESS).split(",") if e.strip()]
GA4_ACCOUNT_ID  = "338483850"

WINDSOR_URL = "https://connectors.windsor.ai/googleanalytics4"


def _windsor_get(report_date: str, fields: str) -> list:
    params = {
        "api_key":    WINDSOR_API_KEY,
        "date_from":  report_date,
        "date_to":    report_date,
        "account_id": GA4_ACCOUNT_ID,
        "fields":     fields,
    }
    r = requests.get(WINDSOR_URL, params=params, timeout=30)
    print(f"Windsor response [{r.status_code}]: {r.text[:300]}")
    print("testing")
    r.raise_for_status()
    data = r.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("data", [])
    return []


def fetch_sales(report_date: str) -> dict:
    rows = _windsor_get(report_date, ",".join([
        "date", "purchase_revenue", "ecommerce_purchases",
        "sessions", "active_users", "add_to_carts",
        "checkouts", "gross_purchase_revenue",
    ]))
    return rows[0] if rows else {}


def fetch_channel_breakdown(report_date: str) -> list:
    rows = _windsor_get(
        report_date,
        "session_default_channel_group,purchase_revenue,ecommerce_purchases,sessions",
    )
    return sorted(rows, key=lambda x: -float(x.get("purchase_revenue", 0) or 0))


def build_html(report_date: str, summary: dict, channels: list) -> str:
    revenue       = float(summary.get("purchase_revenue", 0) or 0)
    purchases     = int(summary.get("ecommerce_purchases", 0) or 0)
    aov           = revenue / purchases if purchases else 0
    sessions      = int(summary.get("sessions", 0) or 0)
    users         = int(summary.get("active_users", 0) or 0)
    carts         = int(summary.get("add_to_carts", 0) or 0)
    checkouts     = int(summary.get("checkouts", 0) or 0)
    cart_rate     = (purchases / carts * 100) if carts else 0
    checkout_rate = (purchases / checkouts * 100) if checkouts else 0
    conv_rate     = (purchases / sessions * 100) if sessions else 0

    max_rev = max((float(r.get("purchase_revenue", 0) or 0) for r in channels), default=1) or 1
    channel_rows = ""
    for i, row in enumerate(channels):
        rev    = float(row.get("purchase_revenue", 0) or 0)
        orders = int(row.get("ecommerce_purchases", 0) or 0)
        sess   = int(row.get("sessions", 0) or 0)
        if rev == 0 and orders == 0:
            continue
        bar_pct = int(rev / max_rev * 100)
        bg = "#f8f9fc" if i % 2 == 0 else "#ffffff"
        channel_rows += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 14px;font-size:13px;color:#2d3748;border-bottom:1px solid #edf2f7;">
            {row.get('session_default_channel_group', '—')}
          </td>
          <td style="padding:10px 14px;border-bottom:1px solid #edf2f7;">
            <div style="display:flex;align-items:center;gap:8px;">
              <div style="background:#e8f0fe;border-radius:4px;height:8px;width:120px;overflow:hidden;">
                <div style="background:linear-gradient(90deg,#1a73e8,#4285f4);height:8px;width:{bar_pct}%;border-radius:4px;"></div>
              </div>
              <span style="font-size:13px;font-weight:600;color:#1a202c;">&#8377;{rev:,.0f}</span>
            </div>
          </td>
          <td style="padding:10px 14px;text-align:center;font-size:13px;color:#2d3748;border-bottom:1px solid #edf2f7;">{orders}</td>
          <td style="padding:10px 14px;text-align:center;font-size:13px;color:#2d3748;border-bottom:1px solid #edf2f7;">{sess:,}</td>
        </tr>"""

    funnel_steps = [
        ("Sessions",    sessions,   "#4285f4"),
        ("Users",       users,      "#1a73e8"),
        ("Add to Cart", carts,      "#fbbc04"),
        ("Checkouts",   checkouts,  "#fa7b17"),
        ("Purchases",   purchases,  "#34a853"),
    ]
    max_funnel = funnel_steps[0][1] or 1
    funnel_html = ""
    for label, val, color in funnel_steps:
        pct = int(val / max_funnel * 100)
        funnel_html += f"""
        <tr>
          <td style="padding:7px 14px;font-size:12px;color:#4a5568;white-space:nowrap;width:90px;">{label}</td>
          <td style="padding:7px 14px;width:100%;">
            <div style="background:#edf2f7;border-radius:6px;height:18px;overflow:hidden;">
              <div style="background:{color};height:18px;width:{pct}%;border-radius:6px;"></div>
            </div>
          </td>
          <td style="padding:7px 14px;font-size:12px;font-weight:700;color:#1a202c;white-space:nowrap;text-align:right;">{val:,}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Sales Dashboard</title>
</head>
<body style="margin:0;padding:0;background:#f0f4f8;font-family:'Segoe UI',Arial,sans-serif;">

<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0f4f8;padding:24px 0;">
<tr><td align="center">
<table width="660" cellpadding="0" cellspacing="0" style="max-width:660px;width:100%;">

  <tr>
    <td style="background:linear-gradient(135deg,#1a1f36 0%,#2d3561 100%);border-radius:12px 12px 0 0;padding:28px 32px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td>
            <div style="font-size:11px;color:#a0aec0;letter-spacing:2px;text-transform:uppercase;margin-bottom:6px;">Daily Analytics Report</div>
            <div style="font-size:22px;font-weight:700;color:#ffffff;">Hair Drama Company</div>
          </td>
          <td align="right" valign="middle">
            <div style="background:rgba(255,255,255,0.1);border-radius:8px;padding:10px 18px;text-align:center;">
              <div style="font-size:11px;color:#a0aec0;margin-bottom:2px;">Report Date</div>
              <div style="font-size:14px;font-weight:600;color:#fff;">{report_date}</div>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <tr>
    <td style="background:#1e2340;padding:0 32px 20px;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td width="25%" style="padding:16px 8px 0 0;">
            <div style="background:linear-gradient(135deg,#1a73e8,#4285f4);border-radius:10px;padding:18px 16px;">
              <div style="font-size:10px;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Total Revenue</div>
              <div style="font-size:22px;font-weight:700;color:#fff;">&#8377;{revenue:,.0f}</div>
              <div style="margin-top:8px;font-size:10px;color:rgba(255,255,255,0.6);">Gross Purchase</div>
            </div>
          </td>
          <td width="25%" style="padding:16px 8px 0;">
            <div style="background:linear-gradient(135deg,#34a853,#0f9d58);border-radius:10px;padding:18px 16px;">
              <div style="font-size:10px;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Orders</div>
              <div style="font-size:22px;font-weight:700;color:#fff;">{purchases:,}</div>
              <div style="margin-top:8px;font-size:10px;color:rgba(255,255,255,0.6);">Completed Purchases</div>
            </div>
          </td>
          <td width="25%" style="padding:16px 8px 0;">
            <div style="background:linear-gradient(135deg,#fa7b17,#f4511e);border-radius:10px;padding:18px 16px;">
              <div style="font-size:10px;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Avg Order Value</div>
              <div style="font-size:22px;font-weight:700;color:#fff;">&#8377;{aov:,.0f}</div>
              <div style="margin-top:8px;font-size:10px;color:rgba(255,255,255,0.6);">Per Transaction</div>
            </div>
          </td>
          <td width="25%" style="padding:16px 0 0 8px;">
            <div style="background:linear-gradient(135deg,#9334e6,#7627bb);border-radius:10px;padding:18px 16px;">
              <div style="font-size:10px;color:rgba(255,255,255,0.75);text-transform:uppercase;letter-spacing:1px;margin-bottom:8px;">Conv. Rate</div>
              <div style="font-size:22px;font-weight:700;color:#fff;">{conv_rate:.2f}%</div>
              <div style="margin-top:8px;font-size:10px;color:rgba(255,255,255,0.6);">Sessions → Purchase</div>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <tr><td style="background:#1e2340;padding:0 32px 24px;">
    <div style="height:1px;background:rgba(255,255,255,0.08);"></div>
  </td></tr>

  <tr>
    <td style="background:#1e2340;padding:0 32px 28px;border-radius:0 0 0 0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr>
          <td style="text-align:center;padding:0 8px;">
            <div style="background:rgba(255,255,255,0.06);border-radius:8px;padding:14px;">
              <div style="font-size:18px;font-weight:700;color:#fff;">{sessions:,}</div>
              <div style="font-size:10px;color:#a0aec0;margin-top:4px;text-transform:uppercase;letter-spacing:1px;">Sessions</div>
            </div>
          </td>
          <td style="text-align:center;padding:0 8px;">
            <div style="background:rgba(255,255,255,0.06);border-radius:8px;padding:14px;">
              <div style="font-size:18px;font-weight:700;color:#fff;">{users:,}</div>
              <div style="font-size:10px;color:#a0aec0;margin-top:4px;text-transform:uppercase;letter-spacing:1px;">Active Users</div>
            </div>
          </td>
          <td style="text-align:center;padding:0 8px;">
            <div style="background:rgba(255,255,255,0.06);border-radius:8px;padding:14px;">
              <div style="font-size:18px;font-weight:700;color:#fff;">{carts:,}</div>
              <div style="font-size:10px;color:#a0aec0;margin-top:4px;text-transform:uppercase;letter-spacing:1px;">Add to Cart</div>
            </div>
          </td>
          <td style="text-align:center;padding:0 8px;">
            <div style="background:rgba(255,255,255,0.06);border-radius:8px;padding:14px;">
              <div style="font-size:18px;font-weight:700;color:#fbbc04;">{cart_rate:.1f}%</div>
              <div style="font-size:10px;color:#a0aec0;margin-top:4px;text-transform:uppercase;letter-spacing:1px;">Cart Rate</div>
            </div>
          </td>
          <td style="text-align:center;padding:0 8px;">
            <div style="background:rgba(255,255,255,0.06);border-radius:8px;padding:14px;">
              <div style="font-size:18px;font-weight:700;color:#34d399;">{checkout_rate:.1f}%</div>
              <div style="font-size:10px;color:#a0aec0;margin-top:4px;text-transform:uppercase;letter-spacing:1px;">Checkout Rate</div>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <tr>
    <td style="padding:0;">
      <table width="100%" cellpadding="0" cellspacing="0">
        <tr valign="top">

          <td width="45%" style="padding:0 8px 0 0;">
            <div style="background:#ffffff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.08);margin-top:16px;">
              <div style="font-size:13px;font-weight:700;color:#1a202c;margin-bottom:4px;">Conversion Funnel</div>
              <div style="font-size:11px;color:#a0aec0;margin-bottom:16px;">User journey overview</div>
              <table width="100%" cellpadding="0" cellspacing="0">
                {funnel_html}
              </table>
            </div>
          </td>

          <td width="55%" style="padding:0 0 0 8px;">
            <div style="background:#ffffff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.08);margin-top:16px;">
              <div style="font-size:13px;font-weight:700;color:#1a202c;margin-bottom:4px;">Performance Rates</div>
              <div style="font-size:11px;color:#a0aec0;margin-bottom:20px;">Conversion efficiency</div>

              <div style="margin-bottom:18px;">
                <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                  <span style="font-size:12px;color:#4a5568;">Cart &#8594; Purchase</span>
                  <span style="font-size:12px;font-weight:700;color:#f59e0b;">{cart_rate:.1f}%</span>
                </div>
                <div style="background:#fef3c7;border-radius:6px;height:10px;overflow:hidden;">
                  <div style="background:linear-gradient(90deg,#f59e0b,#fbbf24);height:10px;width:{min(cart_rate,100):.0f}%;border-radius:6px;"></div>
                </div>
              </div>

              <div style="margin-bottom:18px;">
                <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                  <span style="font-size:12px;color:#4a5568;">Checkout &#8594; Purchase</span>
                  <span style="font-size:12px;font-weight:700;color:#10b981;">{checkout_rate:.1f}%</span>
                </div>
                <div style="background:#d1fae5;border-radius:6px;height:10px;overflow:hidden;">
                  <div style="background:linear-gradient(90deg,#10b981,#34d399);height:10px;width:{min(checkout_rate,100):.0f}%;border-radius:6px;"></div>
                </div>
              </div>

              <div>
                <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
                  <span style="font-size:12px;color:#4a5568;">Session &#8594; Purchase</span>
                  <span style="font-size:12px;font-weight:700;color:#8b5cf6;">{conv_rate:.2f}%</span>
                </div>
                <div style="background:#ede9fe;border-radius:6px;height:10px;overflow:hidden;">
                  <div style="background:linear-gradient(90deg,#8b5cf6,#a78bfa);height:10px;width:{min(conv_rate*10,100):.0f}%;border-radius:6px;"></div>
                </div>
              </div>
            </div>
          </td>

        </tr>
      </table>
    </td>
  </tr>

  <tr>
    <td style="padding-top:16px;">
      <div style="background:#ffffff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,0.08);overflow:hidden;">
        <div style="padding:20px 20px 12px;border-bottom:1px solid #edf2f7;">
          <div style="font-size:13px;font-weight:700;color:#1a202c;">Revenue by Channel</div>
          <div style="font-size:11px;color:#a0aec0;margin-top:2px;">Traffic source breakdown</div>
        </div>
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr style="background:#f7fafc;">
            <th style="padding:10px 14px;font-size:11px;color:#718096;font-weight:600;text-align:left;text-transform:uppercase;letter-spacing:0.5px;">Channel</th>
            <th style="padding:10px 14px;font-size:11px;color:#718096;font-weight:600;text-align:left;text-transform:uppercase;letter-spacing:0.5px;">Revenue</th>
            <th style="padding:10px 14px;font-size:11px;color:#718096;font-weight:600;text-align:center;text-transform:uppercase;letter-spacing:0.5px;">Orders</th>
            <th style="padding:10px 14px;font-size:11px;color:#718096;font-weight:600;text-align:center;text-transform:uppercase;letter-spacing:0.5px;">Sessions</th>
          </tr>
          {channel_rows}
        </table>
      </div>
    </td>
  </tr>

  <tr>
    <td style="padding:20px 0 8px;text-align:center;">
      <div style="font-size:11px;color:#a0aec0;">Automated report generated for Hair Drama Company &nbsp;&#183;&nbsp; {report_date}</div>
      <div style="font-size:10px;color:#cbd5e0;margin-top:4px;">Powered by GA4 via Windsor.ai</div>
    </td>
  </tr>

</table>
</td></tr>
</table>

</body></html>"""


def send_email(subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_ADDRESS
    msg["To"]      = ", ".join(RECIPIENTS)
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
        server.sendmail(GMAIL_ADDRESS, RECIPIENTS, msg.as_string())
    print(f"Report sent to {', '.join(RECIPIENTS)}")


def main():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    print(f"Fetching data for {yesterday}...")
    summary  = fetch_sales(yesterday)
    channels = fetch_channel_breakdown(yesterday)
    print(f"Summary keys: {list(summary.keys())}")
    print(f"Channels: {len(channels)} rows")
    subject = f"Sales Report — {yesterday} | Hair Drama Company"
    html    = build_html(yesterday, summary, channels)
    send_email(subject, html)


if __name__ == "__main__":
    main()
