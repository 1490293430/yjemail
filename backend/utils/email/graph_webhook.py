"""
Microsoft Graph API Webhook 订阅管理模块
实现邮件变更通知的订阅、续订和处理
"""

import requests
import threading
import time
from datetime import datetime, timedelta, timezone
from .logger import logger
from .graph_api import GraphAPIMailHandler

class GraphWebhookManager:
    """Graph API Webhook 订阅管理器"""
    
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    # 订阅最长有效期为 4230 分钟（约 3 天）
    MAX_EXPIRATION_MINUTES = 4230
    # 提前续订时间（小时）
    RENEW_BEFORE_HOURS = 12
    
    def __init__(self, db, webhook_url):
        """
        初始化 Webhook 管理器
        
        Args:
            db: 数据库实例
            webhook_url: 接收通知的公网 HTTPS URL
        """
        self.db = db
        self.webhook_url = webhook_url
        self.running = False
        self.renew_thread = None
        
    def start_renew_loop(self, check_interval=3600):
        """启动订阅续订循环"""
        if self.running:
            logger.warning("订阅续订循环已在运行")
            return False
            
        self.running = True
        self.renew_thread = threading.Thread(
            target=self._renew_loop,
            args=(check_interval,),
            daemon=True
        )
        self.renew_thread.start()
        logger.info(f"订阅续订循环已启动，检查间隔: {check_interval}秒")
        return True
    
    def stop_renew_loop(self):
        """停止订阅续订循环"""
        self.running = False
        if self.renew_thread:
            self.renew_thread.join(timeout=5)
        logger.info("订阅续订循环已停止")
    
    def _renew_loop(self, check_interval):
        """订阅续订循环"""
        while self.running:
            try:
                self._check_and_renew_subscriptions()
            except Exception as e:
                logger.error(f"续订检查出错: {str(e)}")
            
            # 等待下一次检查
            for _ in range(check_interval):
                if not self.running:
                    break
                time.sleep(1)
    
    def _check_and_renew_subscriptions(self):
        """检查并续订即将过期的订阅"""
        try:
            # 获取所有即将过期的订阅（12小时内过期）
            expiring_subs = self.db.get_expiring_subscriptions(hours=self.RENEW_BEFORE_HOURS)
            
            for sub in expiring_subs:
                try:
                    email_info = self.db.get_email_by_id(sub['email_id'])
                    if not email_info:
                        # 邮箱已删除，删除订阅记录
                        self.db.delete_subscription(sub['id'])
                        continue
                    
                    # 续订
                    success = self.renew_subscription(
                        sub['subscription_id'],
                        email_info.get('refresh_token'),
                        email_info.get('client_id')
                    )
                    
                    if success:
                        logger.info(f"订阅 {sub['subscription_id']} 续订成功")
                    else:
                        logger.warning(f"订阅 {sub['subscription_id']} 续订失败，尝试重新创建")
                        # 续订失败，尝试重新创建
                        self.db.delete_subscription(sub['id'])
                        self.create_subscription(email_info)
                        
                except Exception as e:
                    logger.error(f"处理订阅 {sub.get('subscription_id')} 时出错: {str(e)}")
                    
        except Exception as e:
            logger.error(f"检查订阅时出错: {str(e)}")
    
    def create_subscription(self, email_info):
        """
        为邮箱创建 webhook 订阅
        
        Args:
            email_info: 邮箱信息字典
            
        Returns:
            dict: 订阅信息，失败返回 None
        """
        email_id = email_info['id']
        refresh_token = email_info.get('refresh_token')
        client_id = email_info.get('client_id')
        
        if not refresh_token or not client_id:
            logger.error(f"邮箱 {email_info['email']} 缺少 OAuth2 认证信息")
            return None
        
        # 检查是否已有订阅
        existing = self.db.get_subscription_by_email_id(email_id)
        if existing:
            logger.info(f"邮箱 {email_info['email']} 已有订阅，跳过创建")
            return existing
        
        try:
            # 获取访问令牌
            access_token = GraphAPIMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                logger.error(f"邮箱 {email_info['email']} 获取访问令牌失败")
                return None
            
            # 计算过期时间（使用最大有效期）
            expiration_time = datetime.now(timezone.utc) + timedelta(minutes=self.MAX_EXPIRATION_MINUTES)
            expiration_str = expiration_time.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
            
            # 创建订阅
            url = f"{self.GRAPH_API_BASE}/subscriptions"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "changeType": "created",
                "notificationUrl": self.webhook_url,
                "resource": "me/mailFolders('Inbox')/messages",
                "expirationDateTime": expiration_str,
                "clientState": f"email_{email_id}"  # 用于验证通知来源
            }
            
            response = requests.post(url, headers=headers, json=payload)
            
            if response.status_code == 201:
                data = response.json()
                subscription_id = data.get('id')
                
                # 保存到数据库
                self.db.add_subscription(
                    email_id=email_id,
                    subscription_id=subscription_id,
                    resource=payload['resource'],
                    expiration_time=expiration_time.strftime("%Y-%m-%d %H:%M:%S")
                )
                
                logger.info(f"邮箱 {email_info['email']} 创建订阅成功: {subscription_id}")
                return {
                    'subscription_id': subscription_id,
                    'expiration_time': expiration_time
                }
            elif response.status_code == 429:
                # 限流，需要等待
                retry_after = response.headers.get('Retry-After', '60')
                logger.warning(f"创建订阅被限流，需要等待 {retry_after} 秒")
                return None
            else:
                error_msg = response.text
                logger.error(f"创建订阅失败: {response.status_code} - {error_msg}")
                return None
                
        except Exception as e:
            logger.error(f"创建订阅异常: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def renew_subscription(self, subscription_id, refresh_token, client_id):
        """
        续订订阅
        
        Args:
            subscription_id: 订阅 ID
            refresh_token: 刷新令牌
            client_id: 客户端 ID
            
        Returns:
            bool: 是否成功
        """
        try:
            access_token = GraphAPIMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                return False
            
            # 计算新的过期时间
            expiration_time = datetime.now(timezone.utc) + timedelta(minutes=self.MAX_EXPIRATION_MINUTES)
            expiration_str = expiration_time.strftime("%Y-%m-%dT%H:%M:%S.0000000Z")
            
            url = f"{self.GRAPH_API_BASE}/subscriptions/{subscription_id}"
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "expirationDateTime": expiration_str
            }
            
            response = requests.patch(url, headers=headers, json=payload)
            
            if response.status_code == 200:
                # 更新数据库中的过期时间
                self.db.update_subscription_expiration(
                    subscription_id,
                    expiration_time.strftime("%Y-%m-%d %H:%M:%S")
                )
                return True
            else:
                logger.error(f"续订失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"续订异常: {str(e)}")
            return False
    
    def delete_subscription(self, subscription_id, refresh_token, client_id):
        """
        删除订阅
        
        Args:
            subscription_id: 订阅 ID
            refresh_token: 刷新令牌
            client_id: 客户端 ID
            
        Returns:
            bool: 是否成功
        """
        try:
            access_token = GraphAPIMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                return False
            
            url = f"{self.GRAPH_API_BASE}/subscriptions/{subscription_id}"
            headers = {
                "Authorization": f"Bearer {access_token}"
            }
            
            response = requests.delete(url, headers=headers)
            
            if response.status_code in [200, 204]:
                # 从数据库删除
                self.db.delete_subscription_by_id(subscription_id)
                logger.info(f"订阅 {subscription_id} 已删除")
                return True
            else:
                logger.error(f"删除订阅失败: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"删除订阅异常: {str(e)}")
            return False
    
    def create_subscriptions_for_all_outlook_emails(self, batch_size=50, delay_between_batches=60):
        """
        为所有 Outlook 邮箱创建订阅
        
        Args:
            batch_size: 每批处理的邮箱数量（默认50）
            delay_between_batches: 批次之间的等待时间（秒，默认60）
        """
        try:
            # 获取所有 Outlook 邮箱
            emails = self.db.get_all_outlook_emails()
            total = len(emails)
            
            logger.info(f"开始批量创建订阅，共 {total} 个邮箱")
            
            created = 0
            failed = 0
            skipped = 0
            throttled = 0
            
            for i, email_info in enumerate(emails):
                # 检查是否已有订阅
                existing = self.db.get_subscription_by_email_id(email_info['id'])
                if existing:
                    skipped += 1
                    continue
                
                result = self.create_subscription(email_info)
                if result:
                    created += 1
                elif result is None:
                    # 可能是限流，记录并稍后重试
                    failed += 1
                else:
                    failed += 1
                
                # 每个请求之间等待 2 秒，避免触发限流
                time.sleep(2)
                
                # 每处理一批，等待更长时间
                if (i + 1) % batch_size == 0 and i + 1 < total:
                    logger.info(f"已处理 {i + 1}/{total}，等待 {delay_between_batches} 秒后继续...")
                    time.sleep(delay_between_batches)
            
            logger.info(f"批量创建订阅完成: 创建 {created}, 失败 {failed}, 跳过 {skipped}")
            return {
                'created': created, 
                'failed': failed, 
                'skipped': skipped,
                'total': total
            }
            
        except Exception as e:
            logger.error(f"批量创建订阅异常: {str(e)}")
            return None
    
    def create_subscriptions_async(self, callback=None):
        """
        异步批量创建订阅（在后台线程中执行）
        
        Args:
            callback: 完成后的回调函数
        """
        def task():
            result = self.create_subscriptions_for_all_outlook_emails()
            if callback:
                callback(result)
        
        thread = threading.Thread(target=task, daemon=True)
        thread.start()
        return True


class GraphWebhookHandler:
    """Graph API Webhook 通知处理器"""
    
    def __init__(self, db, webhook_manager):
        """
        初始化通知处理器
        
        Args:
            db: 数据库实例
            webhook_manager: Webhook 管理器实例
        """
        self.db = db
        self.webhook_manager = webhook_manager
        self.ws_handler = None  # WebSocket handler，用于广播新邮件
        self._processing_emails = set()  # 正在处理的邮箱ID，用于防抖
        self._processing_lock = threading.Lock()
    
    def set_ws_handler(self, ws_handler):
        """设置 WebSocket handler"""
        self.ws_handler = ws_handler
    
    def handle_validation(self, validation_token):
        """
        处理订阅验证请求
        
        微软在创建订阅时会发送验证请求，需要原样返回 validationToken
        
        Args:
            validation_token: 验证令牌
            
        Returns:
            str: 验证令牌
        """
        logger.info(f"收到订阅验证请求")
        return validation_token
    
    def handle_notification(self, notification_data):
        """
        处理邮件变更通知
        
        Args:
            notification_data: 通知数据
            
        Returns:
            bool: 是否处理成功
        """
        try:
            notifications = notification_data.get('value', [])
            
            for notification in notifications:
                try:
                    self._process_single_notification(notification)
                except Exception as e:
                    logger.error(f"处理单个通知失败: {str(e)}")
            
            return True
            
        except Exception as e:
            logger.error(f"处理通知异常: {str(e)}")
            return False
    
    def _process_single_notification(self, notification):
        """处理单个通知"""
        change_type = notification.get('changeType')
        client_state = notification.get('clientState', '')
        resource = notification.get('resource', '')
        
        logger.info(f"收到通知: changeType={change_type}, clientState={client_state}")
        
        # 从 clientState 解析邮箱 ID
        if not client_state.startswith('email_'):
            logger.warning(f"无效的 clientState: {client_state}")
            return
        
        try:
            email_id = int(client_state.replace('email_', ''))
        except ValueError:
            logger.warning(f"无法解析邮箱 ID: {client_state}")
            return
        
        # 获取邮箱信息
        email_info = self.db.get_email_by_id(email_id)
        if not email_info:
            logger.warning(f"邮箱不存在: {email_id}")
            return
        
        # 只处理新邮件通知
        if change_type == 'created':
            # 防抖：如果该邮箱正在处理中，跳过
            with self._processing_lock:
                if email_id in self._processing_emails:
                    logger.debug(f"邮箱 {email_id} 正在处理中，跳过重复通知")
                    return
                self._processing_emails.add(email_id)
            
            try:
                self._fetch_new_mail(email_info)
            finally:
                with self._processing_lock:
                    self._processing_emails.discard(email_id)
    
    def _fetch_new_mail(self, email_info):
        """获取新邮件"""
        try:
            email_id = email_info['id']
            user_id = email_info.get('user_id')
            refresh_token = email_info.get('refresh_token')
            client_id = email_info.get('client_id')
            
            if not refresh_token or not client_id:
                logger.error(f"邮箱 {email_info['email']} 缺少认证信息")
                return
            
            # 获取访问令牌
            access_token = GraphAPIMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                logger.error(f"邮箱 {email_info['email']} 获取访问令牌失败")
                return
            
            # 获取最近的邮件（只获取最新的几封）
            handler = GraphAPIMailHandler(email_info['email'], access_token)
            messages = handler.get_messages(folder="inbox", limit=5)
            
            if not messages:
                logger.info(f"邮箱 {email_info['email']} 没有新邮件")
                return
            
            # 保存邮件
            saved_count = 0
            new_mails = []  # 保存新邮件信息用于广播
            
            for msg in messages:
                try:
                    received_time = msg.get('received_time')
                    if isinstance(received_time, datetime):
                        received_time = received_time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    success, mail_id = self.db.add_mail_record(
                        email_id=email_id,
                        subject=msg.get('subject', '(无主题)'),
                        sender=msg.get('sender', '(未知发件人)'),
                        received_time=received_time,
                        content=msg.get('content', ''),
                        folder='INBOX',
                        has_attachments=1 if msg.get('has_attachments') else 0
                    )
                    if success and mail_id:
                        saved_count += 1
                        # 只有真正新增的邮件才加入广播列表
                        new_mails.append({
                            'id': mail_id,
                            'email_id': email_id,
                            'recipient_email': email_info['email'],
                            'subject': msg.get('subject', '(无主题)'),
                            'sender': msg.get('sender', '(未知发件人)'),
                            'received_time': received_time,
                            'content': msg.get('content', ''),
                            'has_attachments': 1 if msg.get('has_attachments') else 0
                        })
                except Exception as e:
                    logger.error(f"保存邮件失败: {str(e)}")
            
            # 更新检查时间
            self.db.update_check_time(email_id)
            
            logger.info(f"邮箱 {email_info['email']} 通过 Webhook 获取到 {len(messages)} 封邮件，新增 {saved_count} 封")
            
            # 只有真正有新邮件时才广播
            if saved_count > 0 and self.ws_handler and new_mails:
                self._broadcast_new_mails(user_id, new_mails)
            
        except Exception as e:
            logger.error(f"获取新邮件异常: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def _broadcast_new_mails(self, user_id, new_mails):
        """广播新邮件到 WebSocket"""
        try:
            import asyncio
            
            # 构建广播消息
            message = {
                'type': 'new_mails',
                'data': new_mails,
                'count': len(new_mails)
            }
            
            # 广播给指定用户
            if user_id and hasattr(self.ws_handler, 'broadcast_to_user'):
                asyncio.run(self.ws_handler.broadcast_to_user(user_id, message))
                logger.info(f"已向用户 {user_id} 广播 {len(new_mails)} 封新邮件")
            
        except Exception as e:
            logger.error(f"广播新邮件失败: {str(e)}")
