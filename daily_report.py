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

# Read lazily so --preview mode works without real credentials.
WINDSOR_API_KEY = os.environ.get("WINDSOR_API_KEY", "")
GMAIL_ADDRESS   = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASS  = os.environ.get("GMAIL_APP_PASSWORD", "").replace(" ", "")
RECIPIENTS      = [e.strip() for e in os.environ.get("REPORT_RECIPIENT", GMAIL_ADDRESS).split(",") if e.strip()]
GA4_ACCOUNT_ID  = "338483850"

WINDSOR_URL = "https://connectors.windsor.ai/googleanalytics4"


def _require_env() -> None:
    """Fail fast with a clear message if any required secret is missing."""
    missing = [k for k, v in {
        "WINDSOR_API_KEY":     WINDSOR_API_KEY,
        "GMAIL_ADDRESS":       GMAIL_ADDRESS,
        "GMAIL_APP_PASSWORD":  GMAIL_APP_PASS,
    }.items() if not v]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")


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


def fetch_top_products(report_date: str, limit: int = 5) -> list:
    """Top N products by revenue for the day. Returns [] on any failure."""
    try:
        rows = _windsor_get(
            report_date,
            "item_name,item_revenue,items_purchased",
        )
    except Exception as e:
        print(f"Could not fetch top products: {e}")
        return []
    rows = [r for r in rows if float(r.get("item_revenue", 0) or 0) > 0]
    rows.sort(key=lambda x: -float(x.get("item_revenue", 0) or 0))
    return rows[:limit]


# =====================================================================
# Email template — light SaaS theme, brand coral accent (#E78592)
# Designed for CEO daily-skim: Revenue + Orders lead, supporting
# metrics, funnel, top products, and channels follow.
# =====================================================================
def build_html(report_date: str, summary: dict, channels: list, products: list = None) -> str:
    products = products or []

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

    # ---- Palette --------------------------------------------------------
    BRAND       = "#E78592"
    BRAND_DARK  = "#C96775"
    BRAND_SOFT  = "#FCE9EC"
    INK         = "#0F172A"
    INK_MUTED   = "#475569"
    INK_FAINT   = "#94A3B8"
    BORDER      = "#E5E7EB"
    SURFACE     = "#FFFFFF"
    CANVAS      = "#F6F7F9"
    TRACK       = "#F1F2F4"
    ROW_TINT    = "#FAFBFC"

    # ---- Channels table -------------------------------------------------
    visible_channels = [
        r for r in channels
        if float(r.get("purchase_revenue", 0) or 0) > 0
        or int(r.get("ecommerce_purchases", 0) or 0) > 0
    ]
    max_ch_rev = max(
        (float(r.get("purchase_revenue", 0) or 0) for r in visible_channels),
        default=1,
    ) or 1

    channel_rows = ""
    for i, row in enumerate(visible_channels):
        rev    = float(row.get("purchase_revenue", 0) or 0)
        orders = int(row.get("ecommerce_purchases", 0) or 0)
        sess   = int(row.get("sessions", 0) or 0)
        bar_pct = max(int(rev / max_ch_rev * 100), 2) if rev else 0
        is_last = (i == len(visible_channels) - 1)
        border  = "" if is_last else f"border-bottom:1px solid {BORDER};"
        channel_rows += f"""
        <tr>
          <td style="padding:13px 20px;font-size:13px;color:{INK};font-weight:500;{border}">
            {row.get('session_default_channel_group', '—')}
          </td>
          <td style="padding:13px 20px;{border}" width="42%">
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td width="130" style="padding-right:12px;">
                  <div style="background:{TRACK};border-radius:3px;height:6px;line-height:6px;font-size:0;">
                    <div style="background:{BRAND};height:6px;line-height:6px;width:{bar_pct}%;border-radius:3px;font-size:0;">&nbsp;</div>
                  </div>
                </td>
                <td style="font-size:13px;font-weight:600;color:{INK};white-space:nowrap;">&#8377;{rev:,.0f}</td>
              </tr>
            </table>
          </td>
          <td style="padding:13px 20px;text-align:right;font-size:13px;color:{INK_MUTED};font-variant-numeric:tabular-nums;{border}">{orders:,}</td>
          <td style="padding:13px 20px;text-align:right;font-size:13px;color:{INK_MUTED};font-variant-numeric:tabular-nums;{border}">{sess:,}</td>
        </tr>"""

    # ---- Products table -------------------------------------------------
    product_rows = ""
    if products:
        max_p_rev = max(
            (float(p.get("item_revenue", 0) or 0) for p in products),
            default=1,
        ) or 1
        for i, p in enumerate(products):
            name  = p.get("item_name", "—") or "—"
            p_rev = float(p.get("item_revenue", 0) or 0)
            qty   = int(p.get("items_purchased", 0) or 0)
            bar_pct = max(int(p_rev / max_p_rev * 100), 2) if p_rev else 0
            is_last = (i == len(products) - 1)
            border  = "" if is_last else f"border-bottom:1px solid {BORDER};"
            display_name = name if len(name) <= 48 else name[:46] + "…"
            product_rows += f"""
            <tr>
              <td width="28" style="padding:13px 0 13px 20px;font-size:12px;color:{INK_FAINT};font-weight:600;font-variant-numeric:tabular-nums;{border}">{i+1}</td>
              <td style="padding:13px 14px 13px 8px;font-size:13px;color:{INK};font-weight:500;{border}">{display_name}</td>
              <td style="padding:13px 20px;{border}" width="38%">
                <table cellpadding="0" cellspacing="0" border="0" width="100%">
                  <tr>
                    <td width="110" style="padding-right:12px;">
                      <div style="background:{TRACK};border-radius:3px;height:6px;line-height:6px;font-size:0;">
                        <div style="background:{BRAND};height:6px;line-height:6px;width:{bar_pct}%;border-radius:3px;font-size:0;">&nbsp;</div>
                      </div>
                    </td>
                    <td style="font-size:13px;font-weight:600;color:{INK};white-space:nowrap;">&#8377;{p_rev:,.0f}</td>
                  </tr>
                </table>
              </td>
              <td style="padding:13px 20px;text-align:right;font-size:13px;color:{INK_MUTED};font-variant-numeric:tabular-nums;{border}">{qty:,}</td>
            </tr>"""

    # ---- Funnel (single-color, stepped opacity) -------------------------
    funnel_steps = [
        ("Sessions",     sessions),
        ("Active Users", users),
        ("Add to Cart",  carts),
        ("Checkouts",    checkouts),
        ("Purchases",    purchases),
    ]
    max_funnel = funnel_steps[0][1] or 1
    opacities  = [1.00, 0.82, 0.64, 0.46, 0.28]
    funnel_html = ""
    for idx, (label, val) in enumerate(funnel_steps):
        pct = max(int(val / max_funnel * 100), 2) if val else 0
        fill_rgba = f"rgba(231,133,146,{opacities[idx]})"
        top_pad = "0" if idx == 0 else "12px"
        conv_from_prev = ""
        if idx > 0:
            prev_val = funnel_steps[idx - 1][1]
            if prev_val:
                drop = (val / prev_val * 100)
                conv_from_prev = f"{drop:.1f}% of prev"
        funnel_html += f"""
        <tr>
          <td style="padding-top:{top_pad};">
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td style="padding-bottom:6px;">
                  <table cellpadding="0" cellspacing="0" border="0" width="100%">
                    <tr>
                      <td style="font-size:12px;color:{INK_MUTED};font-weight:500;">{label}</td>
                      <td align="right" style="font-size:12px;color:{INK};font-weight:600;font-variant-numeric:tabular-nums;">
                        {val:,}{f' <span style="color:{INK_FAINT};font-weight:400;">&middot; {conv_from_prev}</span>' if conv_from_prev else ''}
                      </td>
                    </tr>
                  </table>
                </td>
              </tr>
              <tr>
                <td>
                  <div style="background:{TRACK};border-radius:4px;height:8px;line-height:8px;font-size:0;">
                    <div style="background:{fill_rgba};height:8px;line-height:8px;width:{pct}%;border-radius:4px;font-size:0;">&nbsp;</div>
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    # ---- Helpers --------------------------------------------------------
    def stat_cell(label, value):
        return f"""
        <div style="background:{SURFACE};border:1px solid {BORDER};border-radius:10px;padding:16px 14px 14px;text-align:center;">
          <div style="font-size:19px;font-weight:700;color:{INK};letter-spacing:-0.3px;line-height:1.1;font-variant-numeric:tabular-nums;">{value}</div>
          <div style="font-size:10px;color:{INK_FAINT};margin-top:6px;text-transform:uppercase;letter-spacing:0.7px;font-weight:600;">{label}</div>
        </div>"""

    def rate_bar(label, rate, scale=1.0, last=False):
        width = min(rate * scale, 100)
        margin = "" if last else "margin-bottom:18px;"
        return f"""
        <table cellpadding="0" cellspacing="0" border="0" width="100%" style="{margin}">
          <tr>
            <td style="padding-bottom:6px;">
              <table cellpadding="0" cellspacing="0" border="0" width="100%">
                <tr>
                  <td style="font-size:12px;color:{INK_MUTED};font-weight:500;">{label}</td>
                  <td align="right" style="font-size:13px;color:{INK};font-weight:700;font-variant-numeric:tabular-nums;">{rate:.2f}%</td>
                </tr>
              </table>
            </td>
          </tr>
          <tr>
            <td>
              <div style="background:{TRACK};border-radius:4px;height:8px;line-height:8px;font-size:0;">
                <div style="background:{BRAND};height:8px;line-height:8px;width:{width:.1f}%;border-radius:4px;font-size:0;">&nbsp;</div>
              </div>
            </td>
          </tr>
        </table>"""

    # ---- Products section (only render if data is present) -------------
    products_section = ""
    if product_rows:
        products_section = f"""
  <tr>
    <td style="padding-top:20px;">
      <div style="background:{SURFACE};border:1px solid {BORDER};border-radius:12px;overflow:hidden;">
        <div style="padding:22px 22px 18px;border-bottom:1px solid {BORDER};">
          <div style="font-size:14px;font-weight:700;color:{INK};letter-spacing:-0.2px;">Top Products</div>
          <div style="font-size:12px;color:{INK_FAINT};margin-top:2px;">Best sellers by revenue &middot; top {len(products)}</div>
        </div>
        <table cellpadding="0" cellspacing="0" border="0" width="100%">
          <tr style="background:{ROW_TINT};">
            <th colspan="2" align="left" style="padding:11px 20px;font-size:10px;color:{INK_FAINT};font-weight:700;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid {BORDER};">Product</th>
            <th align="left" style="padding:11px 20px;font-size:10px;color:{INK_FAINT};font-weight:700;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid {BORDER};">Revenue</th>
            <th align="right" style="padding:11px 20px;font-size:10px;color:{INK_FAINT};font-weight:700;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid {BORDER};">Units</th>
          </tr>
          {product_rows}
        </table>
      </div>
    </td>
  </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<meta name="x-apple-disable-message-reformatting">
<meta name="color-scheme" content="light only">
<meta name="supported-color-schemes" content="light only">
<title>Daily Sales Report — Hair Drama Company</title>
<!--[if mso]>
<style type="text/css">
  table {{ border-collapse: collapse; }}
</style>
<![endif]-->
</head>
<body style="margin:0;padding:0;background:{CANVAS};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;-webkit-font-smoothing:antialiased;color:{INK};">

<div style="display:none;max-height:0;overflow:hidden;font-size:1px;line-height:1px;color:{CANVAS};">
  Daily sales for {report_date} — &#8377;{revenue:,.0f} revenue across {purchases:,} orders.
</div>

<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{CANVAS};padding:36px 16px;">
<tr><td align="center">

<table role="presentation" width="680" cellpadding="0" cellspacing="0" border="0" style="max-width:680px;width:100%;">

  <!-- Header -->
  <tr>
    <td style="padding-bottom:24px;">
      <div style="display:inline-block;background:{BRAND_SOFT};color:{BRAND_DARK};font-size:10px;font-weight:700;letter-spacing:1.2px;text-transform:uppercase;padding:5px 10px;border-radius:4px;margin-bottom:10px;">Daily Sales Report</div>
      <div style="font-size:22px;font-weight:700;color:{INK};letter-spacing:-0.5px;">Hair Drama Company</div>
      <div style="font-size:13px;color:{INK_MUTED};margin-top:4px;">Performance summary for {report_date}</div>
    </td>
  </tr>

  <!-- Hero: Revenue + Orders -->
  <tr>
    <td>
      <table cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr valign="top">
          <td width="50%" valign="top" style="padding-right:6px;">
            <div style="background:{SURFACE};border:1px solid {BORDER};border-radius:12px;padding:24px 24px 22px;">
              <div style="font-size:11px;color:{INK_FAINT};font-weight:600;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:14px;">Revenue</div>
              <div style="font-size:36px;font-weight:700;color:{BRAND_DARK};letter-spacing:-1.2px;line-height:1.05;">&#8377;{revenue:,.0f}</div>
              <div style="font-size:12px;color:{INK_MUTED};margin-top:10px;">Gross purchase value &middot; {report_date}</div>
            </div>
          </td>
          <td width="50%" valign="top" style="padding-left:6px;">
            <div style="background:{SURFACE};border:1px solid {BORDER};border-radius:12px;padding:24px 24px 22px;">
              <div style="font-size:11px;color:{INK_FAINT};font-weight:600;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:14px;">Orders</div>
              <div style="font-size:36px;font-weight:700;color:{INK};letter-spacing:-1.2px;line-height:1.05;font-variant-numeric:tabular-nums;">{purchases:,}</div>
              <div style="font-size:12px;color:{INK_MUTED};margin-top:10px;">Avg order value &#8377;{aov:,.0f}</div>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Secondary stats -->
  <tr>
    <td style="padding-top:12px;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr valign="top">
          <td width="20%" style="padding-right:6px;">{stat_cell("Sessions", f"{sessions:,}")}</td>
          <td width="20%" style="padding:0 6px;">{stat_cell("Active Users", f"{users:,}")}</td>
          <td width="20%" style="padding:0 6px;">{stat_cell("Add to Cart", f"{carts:,}")}</td>
          <td width="20%" style="padding:0 6px;">{stat_cell("Cart Rate", f"{cart_rate:.1f}%")}</td>
          <td width="20%" style="padding-left:6px;">{stat_cell("Conversion", f"{conv_rate:.2f}%")}</td>
        </tr>
      </table>
    </td>
  </tr>

  <!-- Funnel + Performance Rates -->
  <tr>
    <td style="padding-top:20px;">
      <table cellpadding="0" cellspacing="0" border="0" width="100%">
        <tr valign="top">
          <td width="50%" style="padding-right:8px;">
            <div style="background:{SURFACE};border:1px solid {BORDER};border-radius:12px;padding:24px;">
              <div style="font-size:14px;font-weight:700;color:{INK};letter-spacing:-0.2px;">Conversion Funnel</div>
              <div style="font-size:12px;color:{INK_FAINT};margin-top:2px;margin-bottom:18px;">Step-by-step user journey</div>
              <table cellpadding="0" cellspacing="0" border="0" width="100%">{funnel_html}</table>
            </div>
          </td>
          <td width="50%" style="padding-left:8px;">
            <div style="background:{SURFACE};border:1px solid {BORDER};border-radius:12px;padding:24px;">
              <div style="font-size:14px;font-weight:700;color:{INK};letter-spacing:-0.2px;">Performance Rates</div>
              <div style="font-size:12px;color:{INK_FAINT};margin-top:2px;margin-bottom:18px;">Conversion efficiency by stage</div>
              {rate_bar("Cart → Purchase", cart_rate)}
              {rate_bar("Checkout → Purchase", checkout_rate)}
              {rate_bar("Session → Purchase", conv_rate, scale=10.0, last=True)}
              <div style="font-size:11px;color:{INK_FAINT};margin-top:14px;line-height:1.5;">Session → Purchase bar is scaled 10&times; for visibility.</div>
            </div>
          </td>
        </tr>
      </table>
    </td>
  </tr>

  {products_section}

  <!-- Channels -->
  <tr>
    <td style="padding-top:20px;">
      <div style="background:{SURFACE};border:1px solid {BORDER};border-radius:12px;overflow:hidden;">
        <div style="padding:22px 22px 18px;border-bottom:1px solid {BORDER};">
          <div style="font-size:14px;font-weight:700;color:{INK};letter-spacing:-0.2px;">Revenue by Channel</div>
          <div style="font-size:12px;color:{INK_FAINT};margin-top:2px;">Traffic source breakdown</div>
        </div>
        <table cellpadding="0" cellspacing="0" border="0" width="100%">
          <tr style="background:{ROW_TINT};">
            <th align="left" style="padding:11px 20px;font-size:10px;color:{INK_FAINT};font-weight:700;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid {BORDER};">Channel</th>
            <th align="left" style="padding:11px 20px;font-size:10px;color:{INK_FAINT};font-weight:700;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid {BORDER};">Revenue</th>
            <th align="right" style="padding:11px 20px;font-size:10px;color:{INK_FAINT};font-weight:700;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid {BORDER};">Orders</th>
            <th align="right" style="padding:11px 20px;font-size:10px;color:{INK_FAINT};font-weight:700;text-transform:uppercase;letter-spacing:0.8px;border-bottom:1px solid {BORDER};">Sessions</th>
          </tr>
          {channel_rows if channel_rows else f'<tr><td colspan="4" style="padding:24px;text-align:center;font-size:13px;color:{INK_FAINT};">No channel revenue recorded for this period.</td></tr>'}
        </table>
      </div>
    </td>
  </tr>

  <!-- Footer -->
  <tr>
    <td style="padding:32px 0 8px;text-align:center;">
      <div style="font-size:12px;color:{INK_MUTED};">Hair Drama Company &nbsp;&middot;&nbsp; Automated daily sales report</div>
      <div style="font-size:11px;color:{INK_FAINT};margin-top:4px;">Data from GA4 via Windsor.ai &nbsp;&middot;&nbsp; {report_date}</div>
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


def _sample_data() -> tuple:
    """Realistic sample data for --preview mode (no network calls needed)."""
    summary = {
        "purchase_revenue": 184750,
        "ecommerce_purchases": 142,
        "sessions": 8420,
        "active_users": 6180,
        "add_to_carts": 612,
        "checkouts": 248,
    }
    channels = [
        {"session_default_channel_group": "Direct",         "purchase_revenue": 68400, "ecommerce_purchases": 52, "sessions": 1840},
        {"session_default_channel_group": "Organic Search", "purchase_revenue": 51200, "ecommerce_purchases": 41, "sessions": 2960},
        {"session_default_channel_group": "Paid Social",    "purchase_revenue": 32100, "ecommerce_purchases": 26, "sessions": 1720},
        {"session_default_channel_group": "Email",          "purchase_revenue": 18450, "ecommerce_purchases": 14, "sessions": 480},
        {"session_default_channel_group": "Referral",       "purchase_revenue":  9600, "ecommerce_purchases":  7, "sessions": 620},
        {"session_default_channel_group": "Organic Social", "purchase_revenue":  5000, "ecommerce_purchases":  2, "sessions": 800},
    ]
    products = [
        {"item_name": "Pearl Embellished Hair Clip Set",      "item_revenue": 28400, "items_purchased": 38},
        {"item_name": "Satin Scrunchie Bundle - Pastels",     "item_revenue": 21600, "items_purchased": 54},
        {"item_name": "Velvet Bow Hair Band - Midnight",      "item_revenue": 16200, "items_purchased": 27},
        {"item_name": "Crystal Hair Pin - Floral Collection", "item_revenue": 12800, "items_purchased": 16},
        {"item_name": "Silk Headband - Rose Garden",          "item_revenue":  9450, "items_purchased": 21},
    ]
    return summary, channels, products


def run_preview(output_path: str = "preview.html") -> None:
    """Render the email template with sample data and save to disk for design review."""
    sample_date = (date.today() - timedelta(days=1)).isoformat()
    summary, channels, products = _sample_data()
    html = build_html(sample_date, summary, channels, products)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Preview written to {output_path} ({len(html):,} chars) — open it in a browser.")


def run_send() -> None:
    """Fetch yesterday's data from Windsor and email it. This is the production path."""
    _require_env()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    print(f"Fetching data for {yesterday}...")
    summary  = fetch_sales(yesterday)
    channels = fetch_channel_breakdown(yesterday)
    products = fetch_top_products(yesterday, limit=5)
    print(f"Summary keys: {list(summary.keys())}")
    print(f"Channels: {len(channels)} rows, Products: {len(products)} rows")
    subject = f"Daily Sales Report — {yesterday} | Hair Drama Company"
    html    = build_html(yesterday, summary, channels, products)
    send_email(subject, html)


def main():
    """CLI entry point. Default behavior is to send the report (cron-friendly).

    Usage:
        python3 daily_sales_report.py                 # Fetch + email (production)
        python3 daily_sales_report.py --preview       # Render preview.html with sample data
        python3 daily_sales_report.py --preview foo.html   # Custom output path
    """
    import sys
    args = sys.argv[1:]
    if args and args[0] in ("--preview", "-p"):
        out = args[1] if len(args) > 1 else "preview.html"
        run_preview(out)
    elif args and args[0] in ("--help", "-h"):
        print(main.__doc__)
    else:
        run_send()


if __name__ == "__main__":
    main()
