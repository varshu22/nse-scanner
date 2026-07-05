"""Send strategy results to Telegram. Reads BOT token + chat id from env."""
import os
import requests

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')


def send(text):
    if not BOT_TOKEN or not CHAT_ID:
        print("[telegram] missing TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID -- printing instead:\n" + text)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # Telegram cap 4096 chars/msg -> chunk
    for i in range(0, len(text), 3800):
        chunk = text[i:i + 3800]
        r = requests.post(url, data={'chat_id': CHAT_ID, 'text': chunk,
                                     'parse_mode': 'HTML', 'disable_web_page_preview': True})
        if not r.ok:
            print("[telegram] error:", r.status_code, r.text[:200])


def format_results(results_by_strategy, ts):
    lines = [f"<b>NSE Scanner</b>  {ts}"]
    any_hit = False
    for name, df in results_by_strategy.items():
        lines.append(f"\n<b>{name}</b>")
        if df is None or df.empty:
            lines.append("  no matches")
            continue
        any_hit = True
        for _, r in df.head(30).iterrows():
            sym = r['Symbol'].replace('.NS', '')
            lines.append(f"  {sym}  {r['LTP']}  — {r['Signal']}")
        if len(df) > 30:
            lines.append(f"  …+{len(df)-30} more")
    if not any_hit:
        lines.append("\n(no signals this run)")
    return "\n".join(lines)
