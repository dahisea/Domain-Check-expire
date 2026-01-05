import os
import time
import datetime
import requests
from typing import Tuple, Optional, List

# 从环境变量获取Telegram配置
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# WHOIS API配置
WHOIS_API_URL = "https://www.guokeyun.com/front/website/whois"

# 配置项
CONFIG = {
    'max_retries': 3,           # 最大重试次数
    'retry_delay': 2,           # 重试延迟（秒）
    'request_delay': 1,         # 请求间延迟（秒）
    'timeout': 15,              # 请求超时时间（秒）
    'expiry_alert_days': 16,    # 到期提醒天数
}

def get_domains_from_file(file_path: str) -> List[str]:
    """从文件读取域名列表"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            domains = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        return domains
    except FileNotFoundError:
        raise FileNotFoundError(f"域名列表文件 {file_path} 不存在")
    except Exception as e:
        raise Exception(f"读取域名文件失败: {e}")

def check_domain_status(domain: str, retry_count: int = 0) -> Tuple[str, Optional[int], Optional[datetime.datetime], str]:
    """
    检查域名状态（带重试机制）
    返回: (状态, 距离到期天数, 到期时间, 详细信息)
    """
    try:
        # 调用国科云WHOIS API
        response = requests.get(
            WHOIS_API_URL,
            params={'domainName': domain},
            timeout=CONFIG['timeout']
        )
        response.raise_for_status()
        
        result = response.json()
        
        # 检查API响应状态
        if result.get('status') != 200:
            error_msg = result.get('message', '未知错误')
            raise Exception(f"API返回错误: {error_msg}")
        
        data = result.get('data', {})
        
        # 检查域名状态
        domain_status = data.get('Domain Status', '').lower()
        
        # 如果域名状态为空或包含未注册的标识
        if not domain_status or 'available' in domain_status or 'not found' in domain_status:
            return "未注册", None, None, "域名可注册"
        
        # 检查特殊状态
        special_statuses = {
            'redemptionperiod': '赎回期',
            'redemption': '赎回期',
            'pendingdelete': '删除期',
            'pending delete': '删除期',
            'autorenewperiod': '自动续费期',
            'renewperiod': '续费期',
            'clienthold': '暂停解析',
            'serverhold': '注册局锁定',
        }
        
        status_info = []
        for status_key, status_name in special_statuses.items():
            if status_key in domain_status.replace(' ', ''):
                status_info.append(status_name)
        
        special_status = f"已注册({', '.join(status_info)})" if status_info else "已注册"
        
        # 获取到期时间
        expiration_time_str = data.get('Expiration Time', '')
        
        if not expiration_time_str:
            return special_status, None, None, "无到期时间信息"
        
        # 解析到期时间
        time_formats = [
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d',
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
            return special_status, None, None, f"到期时间格式无法解析: {expiration_time_str}"
        
        # 计算距离到期的天数
        today = datetime.datetime.now()
        days_until_expiry = (expiry_date - today).days
        
        detail = f"到期: {expiry_date.strftime('%Y-%m-%d')}, 剩余 {days_until_expiry} 天"
        return special_status, days_until_expiry, expiry_date, detail
            
    except requests.exceptions.Timeout:
        if retry_count < CONFIG['max_retries']:
            print(f"超时，{CONFIG['retry_delay']}秒后重试 ({retry_count + 1}/{CONFIG['max_retries']})...", end=' ')
            time.sleep(CONFIG['retry_delay'])
            return check_domain_status(domain, retry_count + 1)
        return "查询超时", None, None, f"请求超时 (已重试{CONFIG['max_retries']}次)"
        
    except requests.exceptions.RequestException as e:
        if retry_count < CONFIG['max_retries']:
            print(f"出错，{CONFIG['retry_delay']}秒后重试 ({retry_count + 1}/{CONFIG['max_retries']})...", end=' ')
            time.sleep(CONFIG['retry_delay'])
            return check_domain_status(domain, retry_count + 1)
        return "查询失败", None, None, f"网络错误: {str(e)}"
        
    except Exception as e:
        if retry_count < CONFIG['max_retries'] and "API返回错误" in str(e):
            print(f"API错误，{CONFIG['retry_delay']}秒后重试 ({retry_count + 1}/{CONFIG['max_retries']})...", end=' ')
            time.sleep(CONFIG['retry_delay'])
            return check_domain_status(domain, retry_count + 1)
        return "查询失败", None, None, str(e)

def send_telegram_notification(message: str) -> bool:
    """发送Telegram通知"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️  未配置Telegram凭据，跳过通知发送")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        return True
    except Exception as e:
        print(f"❌ Telegram通知发送失败: {e}")
        return False

def format_duration(seconds: float) -> str:
    """格式化时间长度"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        return f"{seconds/60:.1f}分钟"
    else:
        return f"{seconds/3600:.1f}小时"

def main():
    """主函数"""
    start_time = time.time()
    
    print("=" * 60)
    print("🔍 域名状态监控系统")
    print("=" * 60)
    print(f"⏰ 开始时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"⚙️  配置: 最多重试{CONFIG['max_retries']}次, 请求间隔{CONFIG['request_delay']}秒")
    print("=" * 60)
    print()
    
    # 读取域名列表
    try:
        domains = get_domains_from_file('domains.txt')
    except Exception as e:
        print(f"❌ {e}")
        return
    
    if not domains:
        print("⚠️  域名列表为空")
        return
    
    print(f"📋 共需检查 {len(domains)} 个域名\n")
    
    # 结果统计
    results = {
        'unregistered': [],
        'expiring': [],
        'normal': [],
        'special': [],
        'failed': []
    }
    
    # 检查每个域名
    for i, domain in enumerate(domains, 1):
        print(f"[{i:3d}/{len(domains)}] {domain:30s} ", end='')
        
        status, days_until_expiry, expiry_date, detail = check_domain_status(domain)
        
        # 根据状态分类
        if status == "未注册":
            print(f"✨ {status}")
            results['unregistered'].append((domain, detail))
            
        elif "查询失败" in status or "超时" in status:
            print(f"❌ {status}")
            results['failed'].append((domain, detail))
            
        elif status.startswith("已注册(") and status != "已注册":
            print(f"⚠️  {status}")
            results['special'].append((domain, status, detail))
            
        elif status == "已注册" and days_until_expiry is not None:
            if 0 <= days_until_expiry <= CONFIG['expiry_alert_days']:
                print(f"🔔 即将到期 (剩余{days_until_expiry}天)")
                results['expiring'].append((domain, days_until_expiry, expiry_date))
            else:
                print(f"✅ 正常 (剩余{days_until_expiry}天)")
                results['normal'].append((domain, days_until_expiry, expiry_date))
        else:
            print(f"ℹ️  {status}")
            results['normal'].append((domain, 0, None))
        
        # 请求间延迟（最后一个域名不需要延迟）
        if i < len(domains):
            time.sleep(CONFIG['request_delay'])
    
    # 计算执行时间
    elapsed_time = time.time() - start_time
    
    # 打印结果摘要
    print("\n" + "=" * 60)
    print("📊 检查结果汇总")
    print("=" * 60)
    print(f"✨ 未注册域名: {len(results['unregistered'])} 个")
    print(f"🔔 即将到期域名: {len(results['expiring'])} 个 (≤{CONFIG['expiry_alert_days']}天)")
    print(f"⚠️  特殊状态域名: {len(results['special'])} 个")
    print(f"✅ 正常域名: {len(results['normal'])} 个")
    print(f"❌ 查询失败: {len(results['failed'])} 个")
    print(f"⏱️  总耗时: {format_duration(elapsed_time)}")
    print("=" * 60)
    print()
    
    # 构建详细的通知消息
    message_parts = []
    message_parts.append(f"<b>🔍 域名监控报告</b>")
    message_parts.append(f"检查时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    message_parts.append(f"共检查: {len(domains)} 个域名\n")
    
    if results['unregistered']:
        message_parts.append(f"<b>✨ 未注册域名 ({len(results['unregistered'])})</b>")
        for domain, _ in results['unregistered']:
            message_parts.append(f"• {domain}")
        message_parts.append("")
    
    if results['expiring']:
        message_parts.append(f"<b>🔔 即将到期域名 ({len(results['expiring'])})</b>")
        # 按剩余天数排序
        sorted_expiring = sorted(results['expiring'], key=lambda x: x[1])
        for domain, days, expiry in sorted_expiring:
            urgency = "🔴" if days <= 7 else "🟡" if days <= 14 else "🟢"
            message_parts.append(f"{urgency} <b>{domain}</b>")
            message_parts.append(f"   剩余 <b>{days}</b> 天 | 到期: {expiry.strftime('%Y-%m-%d')}")
        message_parts.append("")
    
    if results['special']:
        message_parts.append(f"<b>⚠️ 特殊状态域名 ({len(results['special'])})</b>")
        for domain, status, _ in results['special']:
            message_parts.append(f"• {domain}: {status}")
        message_parts.append("")
    
    if results['failed']:
        message_parts.append(f"<b>❌ 查询失败 ({len(results['failed'])})</b>")
        for domain, detail in results['failed']:
            message_parts.append(f"• {domain}")
            message_parts.append(f"   {detail}")
        message_parts.append("")
    
    message_parts.append(f"⏱️ 耗时: {format_duration(elapsed_time)}")
    
    # 发送通知（仅当有重要信息时）
    should_notify = (results['unregistered'] or 
                    results['expiring'] or 
                    results['special'] or 
                    results['failed'])
    
    if should_notify:
        full_message = "\n".join(message_parts)
        if send_telegram_notification(full_message):
            print("✅ Telegram通知已发送")
        else:
            print("⚠️  通知发送失败或未配置")
    else:
        print("ℹ️  所有域名状态正常，无需发送通知")
    
    print("\n✨ 检查完成！\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断执行")
    except Exception as e:
        print(f"\n\n❌ 程序异常: {e}")
        raise