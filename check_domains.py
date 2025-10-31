import os
import datetime
import requests
from typing import Tuple, Optional

# 从环境变量获取Telegram配置
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# WHOIS API配置
WHOIS_API_URL = "https://www.guokeyun.com/front/website/whois"

def get_domains_from_file(file_path: str) -> list:
    """从文件读取域名列表"""
    with open(file_path, 'r') as f:
        return [line.strip() for line in f if line.strip()]

def check_domain_status(domain: str) -> Tuple[str, Optional[int], Optional[datetime.datetime]]:
    """
    检查域名状态
    返回: (状态, 距离到期天数, 到期时间)
    """
    try:
        # 调用国科云WHOIS API
        response = requests.get(
            WHOIS_API_URL,
            params={'domainName': domain},
            timeout=10
        )
        response.raise_for_status()
        
        result = response.json()
        
        # 检查API响应状态
        if result.get('status') != 200:
            return "查询失败", None, None
        
        data = result.get('data', {})
        
        # 检查域名状态
        domain_status = data.get('Domain Status', '')
        
        # 如果域名状态为空或包含未注册的标识，认为域名未注册
        if not domain_status or 'available' in domain_status.lower():
            return "未注册", None, None
        
        # 获取到期时间
        expiration_time_str = data.get('Expiration Time', '')
        
        if not expiration_time_str:
            return "已注册(无到期信息)", None, None
        
        # 解析到期时间 (支持多种格式)
        time_formats = [
            '%Y-%m-%dT%H:%M:%SZ',           # 2026-07-19T16:52:20Z
            '%Y-%m-%dT%H:%M:%S.%fZ',        # 2032-05-03T23:59:59.0Z
            '%Y-%m-%d %H:%M:%S',            # 2026-04-02 21:17:57
            '%Y-%m-%dT%H:%M:%S',            # 2026-07-19T16:52:20 (无Z)
        ]
        
        expiry_date = None
        for fmt in time_formats:
            try:
                expiry_date = datetime.datetime.strptime(
                    expiration_time_str.strip(), 
                    fmt
                )
                break
            except ValueError:
                continue
        
        if expiry_date is None:
            print(f"无法解析到期时间 {domain}: {expiration_time_str}")
            return "已注册(到期时间格式错误)", None, None
        
        # 计算距离到期的天数
        today = datetime.datetime.now()
        days_until_expiry = (expiry_date - today).days
        
        return "已注册", days_until_expiry, expiry_date
            
    except requests.exceptions.Timeout:
        print(f"查询超时 {domain}")
        return "查询超时", None, None
    except requests.exceptions.RequestException as e:
        print(f"查询出错 {domain}: {e}")
        return "查询失败", None, None
    except Exception as e:
        print(f"处理出错 {domain}: {e}")
        return "查询失败", None, None

def send_telegram_notification(message: str):
    """发送Telegram通知"""
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
        print("Telegram notification sent successfully.")
    except Exception as e:
        print(f"Failed to send Telegram notification: {e}")

def main():
    """主函数"""
    print("开始检查域名状态...\n")
    
    # 读取域名列表
    try:
        domains = get_domains_from_file('domains.txt')
    except FileNotFoundError:
        print("错误: domains.txt 文件不存在")
        return
    except Exception as e:
        print(f"读取域名文件出错: {e}")
        return
    
    if not domains:
        print("域名列表为空")
        return
    
    print(f"共需检查 {len(domains)} 个域名\n")
    
    expiring_domains = []
    unregistered_domains = []
    failed_domains = []
    
    # 检查每个域名
    for i, domain in enumerate(domains, 1):
        print(f"[{i}/{len(domains)}] 检查 {domain}...", end=' ')
        
        status, days_until_expiry, expiry_date = check_domain_status(domain)
        print(status)
        
        if status == "未注册":
            unregistered_domains.append(domain)
        elif status == "已注册" and days_until_expiry is not None:
            if 0 <= days_until_expiry <= 16:
                expiring_domains.append((domain, days_until_expiry, expiry_date))
        elif "查询失败" in status or "超时" in status:
            failed_domains.append(domain)
    
    # 构建通知消息
    message_parts = []
    
    if unregistered_domains:
        message_parts.append("<b>🔄 未注册域名 🔄</b>\n")
        message_parts.extend([f"• {domain}" for domain in unregistered_domains])
        message_parts.append("")  # 空行分隔
    
    if expiring_domains:
        message_parts.append("<b>⚠️ 即将到期域名（16天内）⚠️</b>\n")
        for domain, days, expiry in expiring_domains:
            message_parts.append(f"• <b>{domain}</b> 将在 <b>{days}</b> 天后到期")
            message_parts.append(f"  到期时间: {expiry.strftime('%Y-%m-%d %H:%M:%S')}")
        message_parts.append("")
    
    if failed_domains:
        message_parts.append("<b>❌ 查询失败的域名 ❌</b>\n")
        message_parts.extend([f"• {domain}" for domain in failed_domains])
    
    # 打印结果摘要
    print("\n" + "="*50)
    print(f"未注册域名: {len(unregistered_domains)} 个")
    print(f"即将到期域名: {len(expiring_domains)} 个")
    print(f"查询失败: {len(failed_domains)} 个")
    print("="*50 + "\n")
    
    # 发送通知
    if message_parts:
        full_message = "\n".join(message_parts)
        send_telegram_notification(full_message)
        print("通知已发送。")
    else:
        print("没有需要报告的域名。")

if __name__ == "__main__":
    main()