import os
import datetime
from whois import whois
import requests

# 从环境变量获取Telegram配置
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

def get_domains_from_file(file_path):
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def check_domain_expiry(domain):
    try:
        domain_info = whois(domain)
        expiry_date = domain_info.expiration_date
        
        if isinstance(expiry_date, list):
            expiry_date = expiry_date[0]
            
        if expiry_date:
            today = datetime.datetime.now()
            days_until_expiry = (expiry_date - today).days
            return days_until_expiry, expiry_date
    except Exception as e:
        print(f"Error checking {domain}: {e}")
    return None, None

def send_telegram_notification(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram credentials not set. Skipping notification.")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")

def main():
    domains = get_domains_from_file('domains.txt')
    expiring_domains = []
    
    for domain in domains:
        days_until_expiry, expiry_date = check_domain_expiry(domain)
        if days_until_expiry is not None and 0 <= days_until_expiry <= 16:
            expiring_domains.append((domain, days_until_expiry, expiry_date))
    
    if expiring_domains:
        message = "<b>⚠️ 域名即将到期通知 ⚠️</b>\n\n"
        for domain, days, expiry in expiring_domains:
            message += f"<b>{domain}</b> 将在 <b>{days}</b> 天后到期\n"
            message += f"到期时间: {expiry.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        send_telegram_notification(message)
        print("Notification sent for expiring domains.")
    else:
        print("No domains expiring in the next 16 days.")

if __name__ == "__main__":
    main()
