# Author:Sakura
# -*- coding: utf-8 -*-
"""
小米钱包自动任务脚本
- 功能：
    1. 完成“浏览组浏览任务”
    2. 领取奖励
    3. 统计今日观看次数
    4. 查询总天数
    5. 可选尝试兑换会员
- 注意：
    执行前请填入 accounts 中的 passToken / userId，或按需添加 phone 用于兑换
"""

import requests
import time
import random
from datetime import datetime, timedelta
import urllib3

# 关闭 https 的警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 创建SimpleRequest类，里面有GET和POST两种请求方法。
class SimpleRequest:
    # cookies: str 表示cookie应该传入字符串类型
    def __init__(self, cookies: str):
        self.session = requests.Session()
        self.base_headers = {
            'Host': 'm.jr.airstarfinance.net',
            'User-Agent': 'Mozilla/5.0 (Linux; U; Android 14; zh-CN; M2012K11AC Build/UKQ1.230804.001; '
                          'AppBundle/com.mipay.wallet; AppVersionName/6.89.1.5275.2323; '
                          'AppVersionCode/20577595; MiuiVersion/stable-V816.0.13.0.UMNCNXM; '
                          'DeviceId/alioth; NetworkType/WIFI; mix_version; WebViewVersion/118.0.0.0) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Mobile Safari/537.36 XiaoMi/MiuiBrowser/4.3',
            'Cookie': cookies
        }
    # 模拟进行GET登录，获取相应的数据
    def get(self, url: str):
        try:
            resp = self.session.get(url, headers=self.base_headers, verify=False, timeout=10)
            return resp.json()
        except Exception as e:
            print("GET 请求失败，原因为:", e)
            return None

    # 模拟进行POST登录，获取相应的数据
    def post(self, url: str, data: dict):
        try:
            resp = self.session.post(url, headers=self.base_headers, data=data, verify=False, timeout=10)
            return resp.json()
        except Exception as e:
            print("POST 请求失败，原因为:", e)
            return None


# 创建XiaomiTask类，里面有诸多方法。
class XiaomiTask:
    def __init__(self, cookies: str, user_id: str = ""):
        # 通过此调用SimpleRequest里面的方法
        self.req = SimpleRequest(cookies)
        self.user_id = user_id
        # 状态为固定值
        self.activity_code = '2211-videoWelfare'
        self.total_days = 0.0
        self.today_records = []
        self.error_info = ""
        # 用于统计每一次脚本的观看视频次数
        self.watch_count = 0
        # 以前是否有兑换记录
        self.has_exchanged_before = False
        # 今天是否有兑换
        self.exchanged_in_7days = False

    def get_task_list(self):
        url = "https://m.jr.airstarfinance.net/mp/api/generalActivity/getTaskList"
        data = {'activityCode': self.activity_code}
        # 获取相应的任务内容
        resp = self.req.post(url, data)
        if not resp or resp.get("code") != 0:
            self.error_info = f"获取任务列表失败: {resp}"
            print(self.error_info)
            return None

        tasks = []
        for task in resp["value"].get("taskInfoList", []):
            if "浏览组浏览任务" in task.get("taskName", ""):
                tasks.append(task)
        return tasks

    def get_task_info(self, task_code):
        # 提取相应的任务信息
        url = "https://m.jr.airstarfinance.net/mp/api/generalActivity/getTask"
        data = {
            "activityCode": self.activity_code,
            "taskCode": task_code,
            "jrairstar_ph": "98lj8puDf9Tu/WwcyMpVyQ=="
        }
        resp = self.req.post(url, data)
        if not resp or resp.get("code") != 0:
            self.error_info = f"任务信息获取失败: {resp}"
            print(self.error_info)
            return None
        else:
            return resp["value"]["taskInfo"].get("userTaskId")

    def complete_task(self, task_id, t_id, brows_click_url_id):
        # 执行相应的任务
        url = (f"https://m.jr.airstarfinance.net/mp/api/generalActivity/completeTask"
               f"?activityCode={self.activity_code}&app=com.mipay.wallet&isNfcPhone=true"
               f"&channel=mipay_indexicon_TVcard&deviceType=2&system=1&visitEnvironment=2"
               f"&taskId={task_id}&browsTaskId={t_id}&browsClickUrlId={brows_click_url_id}")
        resp = self.req.get(url)
        if not resp or resp.get("code") != 0:
            self.error_info = f"任务完成失败: {resp}"
            print(self.error_info)
            return None
        else:
            return resp.get("value")

    def receive_award(self, user_task_id):
        url = (f"https://m.jr.airstarfinance.net/mp/api/generalActivity/luckDraw"
               f"?activityCode={self.activity_code}&userTaskId={user_task_id}"
               f"&app=com.mipay.wallet&isNfcPhone=true&channel=mipay_indexicon_TVcard")
        resp = self.req.get(url)
        if not resp:
            self.error_info = "领取奖励接口未返回数据"
            print(self.error_info)
        else:
            return False, 0

        if resp.get("code") != 0:
            self.error_info = f"领取奖励失败: {resp}"
            print(self.error_info)
        else:
            return False, 0

        try:
            val = resp.get("value", {}).get("value", 0)
            val_int = int(val) if val is not None else 0
        except Exception:
            val_int = 0
        return True, val_int

    def check_exchange_history(self):
        # 是否有兑换历史
        try:
            url = f'https://m.jr.airstarfinance.net/mp/api/generalActivity/queryUserExchangeList?activityCode={self.activity_code}&pageNum=1&pageSize=20'
            resp = self.req.get(url)
            if not resp or resp.get("code") != 0:
                return False
            data = resp.get("value", {}).get("data", [])
            self.has_exchanged_before = len(data) > 0
            # 判断近7天是否有相应的兑换记录
            seven_days_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            self.exchanged_in_7days = any([i.get("createTime", "").startswith(seven_days_ago) for i in data])
            return True
        except Exception as e:
            print("查询兑换历史失败:", e)
            return False

    def query_user_info(self):
        url_days = (f"https://m.jr.airstarfinance.net/mp/api/generalActivity/queryUserGoldRichSum"
                    f"?activityCode={self.activity_code}&app=com.mipay.wallet&deviceType=2")
        resp = self.req.get(url_days)
        if not resp or resp.get("code") != 0:
            self.error_info = f"获取视频天数失败: {resp}"
            print(self.error_info)
            return False

        try:
            # 格式化日期
            self.total_days = int(resp.get("value", 0)) / 100.0
        except Exception:
            self.total_days = 0.0

        url_record = (f"https://m.jr.airstarfinance.net/mp/api/generalActivity/queryUserJoinList"
                      f"?activityCode={self.activity_code}&pageNum=1&pageSize=50")
        resp2 = self.req.get(url_record)
        if not resp2 or resp2.get("code") != 0:
            self.error_info = f"查询任务记录失败: {resp2}"
            print(self.error_info)
            return False

        today = datetime.now().strftime("%Y-%m-%d")
        self.today_records = []
        for i in resp2.get("value", {}).get("data", []):
            if i.get("createTime", "").startswith(today):
                self.today_records.append({
                    "createTime": i.get("createTime"),
                    "value": i.get("value")
                })

        self.check_exchange_history()
        return True

    def exchange_member(self, phone: str, exchange_type: str = "iqiyi"):
        if not phone:
            print("兑换失败，原因为：未提供手机号")
            return None
        url = (f"https://m.jr.airstarfinance.net/mp/api/generalActivity/exchange"
               f"?activityCode={self.activity_code}&exchangeCode={exchange_type}&phone={phone}"
               f"&app=com.mipay.wallet&deviceType=2&system=1&visitEnvironment=2&userExtra=%7B%22platformType%22:1%7D")
        resp = self.req.get(url)
        if not resp:
            print("兑换失败,原因为接口未返回数据")
            return None
        print("=== 兑换接口返回 ===")
        print("code:", resp.get("code"))
        print("message:", resp.get("message"))
        print("value:", resp.get("value"))
        print("===================")
        if resp.get("code") == 0:
            print("兑换成功！")
        return resp

    def run_py(self):
        ok = self.query_user_info()
        if not ok:
            return False

        tasks = self.get_task_list()
        if not tasks:
            return False

        for task in tasks:
            task_id = task.get("taskId")
            task_code = task.get("taskCode")
            t_id = task.get("generalActivityUrlInfo", {}).get("id")
            brows_click_url_id = task.get("generalActivityUrlInfo", {}).get("browsClickUrlId")

            print(f"开始执行任务 {task_code} ...")
            # 模拟进行视频浏览
            time.sleep(random.randint(12, 18))

            user_task = self.complete_task(task_id, t_id, brows_click_url_id)
            if not user_task:
                user_task_id = self.get_task_info(task_code)
            else:
                user_task_id = user_task
            time.sleep(2)

            if user_task_id:
                success, award_val = self.receive_award(user_task_id)
                if success and award_val > 0:
                    self.watch_count += 1
                    print(f"成功领取奖励: {award_val} (后台单位，/100后为天)")
                elif success:
                    print("领取成功，但奖励为0")
                else:
                    print("领取失败或接口返回非预期格式")
            time.sleep(2)

        self.query_user_info()
        return True

# 获取小米cookie
def get_xiaomi_cookie(pass_token, user_id):
    # 创建Session接口，方便使用cookie
    session = requests.Session()
    login_url = (
        "https://account.xiaomi.com/pass/serviceLogin?callback=https%3A%2F%2Fapi.jr.airstarfinance.net%2Fsts%3Fsign%3D1dbHuyAmee0NAZ2xsRw5vhdVQQ8%253D%26followup%3D"
        "https%253A%252F%252Fm.jr.airstarfinance.net%252Fmp%252Fapi%252Flogin%253Ffrom%253Dmipay_indexicon_TVcard"
        "%2526deepLinkEnable%253Dfalse%2526requestUrl%253Dhttps%25253A%25252F%25252Fm.jr.airstarfinance.net%25252Fmp%25252Factivity"
        "%25252FvideoActivity%25253Ffrom%25253Dmipay_indexicon_TVcard%252526_noDarkMode%25253Dtrue%252526_transparentNaviBar"
        "%25253Dtrue%252526cUserId%25253Dusyxgr5xjumiQLUoAKTOgvi858Q%252526_statusBarHeight%25253D137&sid=jrairstar"
        "&_group=DEFAULT&_snsNone=true&_loginType=ticket"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/135.0.0.0 Safari/537.36 Edg/135.0.0.0",
        "Cookie": f"passToken={pass_token}; userId={user_id};"
    }
    try:
        session.get(login_url, headers=headers, verify=False, timeout=10)
        cookies = session.cookies.get_dict()
        print("登录后抓到的 cookies:", cookies)
        if "cUserId" in cookies and "serviceToken" in cookies:
            return f"cUserId={cookies.get('cUserId')};jrairstar_serviceToken={cookies.get('serviceToken')}"
    except Exception as e:
        print("获取小米 cookie 失败:", e)
    return None

# 主程序开关
if __name__ == "__main__":
    accounts = [
        {
            'passToken': '替换为你的passToken1',
            'userId': '替换为你的userId1',
            'phone': '13812345678',
            'auto_exchange': True,  # True尝试兑换，False不兑换
        },
        {
            'passToken': '替换为你的passToken2',
            'userId': '替换为你的userId2',
            'auto_exchange': False,
        },
    ]

    EXCHANGE_TYPE = "iqiyi" # 具有多种选择类型：iqiyi/tencent/youku/mango
    MIN_DAYS_TO_EXCHANGE = 7

    for acc in accounts:
        user_id = acc.get('userId', '未知')
        print(f"\n==== 开始执行 {user_id}的账号 ====")
        cookie = get_xiaomi_cookie(acc.get('passToken', ''), acc.get('userId', ''))
        if not cookie:
            print(f"账号 {user_id} 获取 Cookie 失败，无法继续执行，跳过")
            continue

        task = XiaomiTask(cookie, user_id=user_id)
        ok = task.run_py()
        if not ok:
            print(f"账号{user_id} 运行失败，错误: {task.error_info}")
            continue
        print(f"账号 {user_id} 总时常天数: {task.total_days:.2f} 天")
        print(f"今日已完成观看次数: {task.watch_count} 次")
        if task.today_records:
            for i in task.today_records:
                try:
                    days = int(i.get('value', 0)) / 100.0
                except Exception:
                    days = 0.0
                print(f"{i.get('createTime')}+{days:.2f}天")
        else:
            print("今日无领取记录")

        print(f"曾经兑换过会员: {'是' if task.has_exchanged_before else '否'}")
        print(f"近七天是否已兑换: {'是' if task.exchanged_in_7days else '否'}")

        phone = acc.get('phone')
        auto_exchange = acc.get('auto_exchange', False)
        if auto_exchange and phone:
            if task.total_days >= MIN_DAYS_TO_EXCHANGE:
                print(f"条件满足，尝试兑换到手机号 {phone}（兑换类型 {EXCHANGE_TYPE}）")
                exchange_resp = task.exchange_member(phone=phone, exchange_type=EXCHANGE_TYPE)
            else:
                print("兑换失败（可能是天数不足或今日已兑换）")
        else:
            print("跳过兑换（auto_exchange=False 或未配置 phone）")

        print(f"==== 账号 {user_id} 执行结束 ====\n")
