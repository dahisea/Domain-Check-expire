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

def check_domain_status(domain):
    try:
        domain_info = whois(domain)
        
        # 检查域名是否未注册
        if not domain_info.domain_name:
            return "未注册", None, None
            
        expiry_date = domain_info.expiration_date
        
        if isinstance(expiry_date, list):
            expiry_date = expiry_date[0]
            
        if expiry_date:
            today = datetime.datetime.now()
            days_until_expiry = (expiry_date - today).days
            return "已注册", days_until_expiry, expiry_date
            
        return "已注册(无到期信息)", None, None
    except Exception as e:
        # 某些whois查询异常可能表示域名未注册
        if "No match for" in str(e) or "NOT FOUND" in str(e):
            return "未注册", None, None
        print(f"Error checking {domain}: {e}")
        return "查询失败", None, None

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
    unregistered_domains = []
    
    for domain in domains:
        status, days_until_expiry, expiry_date = check_domain_status(domain)
        
        if status == "未注册":
            unregistered_domains.append(domain)
        elif status == "已注册" and days_until_expiry is not None and 0 <= days_until_expiry <= 16:
            expiring_domains.append((domain, days_until_expiry, expiry_date))
    
    message_parts = []
    
    if unregistered_domains:
        message_parts.append("<b>🔄 未注册域名 🔄</b>\n")
        message_parts.extend([f"• {domain}" for domain in unregistered_domains])
        message_parts.append("")  # 空行分隔
    
    if expiring_domains:
        message_parts.append("<b>⚠️ 即将到期域名 ⚠️</b>\n")
        for domain, days, expiry in expiring_domains:
            message_parts.append(f"• <b>{domain}</b> 将在 <b>{days}</b> 天后到期")
            message_parts.append(f"  到期时间: {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
    
    if message_parts:
        full_message = "\n".join(message_parts)
        send_telegram_notification(full_message)
        print("Notification sent.")
    else:
        print("No unregistered or expiring domains to report.")

if __name__ == "__main__":
    main()