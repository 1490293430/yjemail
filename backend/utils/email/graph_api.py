"""
Microsoft Graph API 邮件处理模块
使用 Graph API 替代 IMAP 方式获取 Outlook 邮件
"""

import requests
import time
from datetime import datetime, timezone
from .logger import logger

class GraphAPIMailHandler:
    """Microsoft Graph API 邮箱处理类"""
    
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
    
    def __init__(self, email_address, access_token):
        """初始化 Graph API 处理器"""
        self.email_address = email_address
        self.access_token = access_token
        self.error = None
    
    def _get_headers(self):
        """获取请求头"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    def get_folders(self):
        """获取邮件文件夹列表"""
        try:
            url = f"{self.GRAPH_API_BASE}/me/mailFolders"
            response = requests.get(url, headers=self._get_headers())
            
            if response.status_code == 200:
                data = response.json()
                folders = []
                for folder in data.get("value", []):
                    folders.append({
                        "id": folder.get("id"),
                        "name": folder.get("displayName"),
                        "total_count": folder.get("totalItemCount", 0),
                        "unread_count": folder.get("unreadItemCount", 0)
                    })
                return folders
            else:
                logger.error(f"获取文件夹列表失败: {response.status_code} - {response.text}")
                return []
        except Exception as e:
            logger.error(f"获取文件夹列表异常: {str(e)}")
            return []
    
    def get_messages(self, folder="inbox", limit=100, since=None):
        """
        获取指定文件夹的邮件
        
        Args:
            folder: 文件夹名称，默认为收件箱
            limit: 获取邮件数量限制
            since: 获取该时间之后的邮件 (datetime 对象)
        
        Returns:
            list: 邮件列表
        """
        try:
            # 构建 URL
            url = f"{self.GRAPH_API_BASE}/me/mailFolders/{folder}/messages"
            
            # 构建查询参数
            params = {
                "$top": limit,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,receivedDateTime,body,hasAttachments,bodyPreview"
            }
            
            # 如果指定了时间，添加过滤条件
            if since:
                if isinstance(since, datetime):
                    since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")
                elif isinstance(since, str):
                    # 处理字符串格式的日期，转换为 ISO 8601 格式
                    try:
                        # 尝试解析 "2026-01-05 18:58:09" 格式
                        dt = datetime.strptime(since, "%Y-%m-%d %H:%M:%S")
                        since_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")
                    except:
                        # 如果已经是正确格式，直接使用
                        since_str = since.replace(" ", "T")
                        if not since_str.endswith("Z"):
                            since_str += "Z"
                else:
                    since_str = str(since)
                params["$filter"] = f"receivedDateTime ge {since_str}"
                logger.info(f"Graph API: 过滤条件 - 获取 {since_str} 之后的邮件")
            
            logger.info(f"Graph API: 请求 URL: {url}")
            logger.debug(f"Graph API: 请求参数: {params}")
            
            response = requests.get(url, headers=self._get_headers(), params=params)
            
            logger.info(f"Graph API: 响应状态码: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                messages = []
                
                raw_messages = data.get("value", [])
                logger.info(f"Graph API: 原始响应包含 {len(raw_messages)} 封邮件")
                
                for msg in raw_messages:
                    # 解析发件人
                    from_info = msg.get("from", {}).get("emailAddress", {})
                    sender = f"{from_info.get('name', '')} <{from_info.get('address', '')}>"
                    
                    # 解析接收时间
                    received_time = msg.get("receivedDateTime")
                    if received_time:
                        try:
                            received_time = datetime.fromisoformat(received_time.replace("Z", "+00:00"))
                        except:
                            pass
                    
                    # 获取邮件内容
                    body = msg.get("body", {})
                    content = body.get("content", "")
                    content_type = body.get("contentType", "text")
                    
                    messages.append({
                        "id": msg.get("id"),
                        "subject": msg.get("subject", "(无主题)"),
                        "sender": sender,
                        "received_time": received_time,
                        "content": content,
                        "content_type": content_type,
                        "has_attachments": msg.get("hasAttachments", False),
                        "body_preview": msg.get("bodyPreview", "")
                    })
                
                logger.info(f"Graph API: 成功解析 {len(messages)} 封邮件")
                return messages
            else:
                error_text = response.text
                logger.error(f"Graph API: 获取邮件失败: {response.status_code} - {error_text}")
                self.error = f"获取邮件失败: {response.status_code} - {error_text}"
                return []
                
        except Exception as e:
            logger.error(f"Graph API: 获取邮件异常: {str(e)}")
            import traceback
            traceback.print_exc()
            self.error = str(e)
            return []
    
    def get_message_detail(self, message_id):
        """获取邮件详情"""
        try:
            url = f"{self.GRAPH_API_BASE}/me/messages/{message_id}"
            params = {
                "$select": "id,subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments"
            }
            
            response = requests.get(url, headers=self._get_headers(), params=params)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"获取邮件详情失败: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"获取邮件详情异常: {str(e)}")
            return None
    
    def get_attachments(self, message_id):
        """获取邮件附件列表"""
        try:
            url = f"{self.GRAPH_API_BASE}/me/messages/{message_id}/attachments"
            response = requests.get(url, headers=self._get_headers())
            
            if response.status_code == 200:
                data = response.json()
                return data.get("value", [])
            else:
                logger.error(f"获取附件列表失败: {response.status_code}")
                return []
        except Exception as e:
            logger.error(f"获取附件列表异常: {str(e)}")
            return []
    
    @staticmethod
    def get_new_access_token(refresh_token, client_id):
        """刷新获取新的 access_token"""
        url = GraphAPIMailHandler.TOKEN_URL
        data = {
            "client_id": client_id,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "scope": "https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/User.Read offline_access"
        }
        
        try:
            response = requests.post(url, data=data)
            result = response.json()
            
            if "error" in result:
                logger.error(f"获取访问令牌失败: {result.get('error_description', result.get('error'))}")
                return None
            
            access_token = result.get("access_token")
            if access_token:
                logger.info("Graph API: 成功获取新的访问令牌")
                return access_token
            else:
                logger.error("获取访问令牌失败: 响应中没有 access_token")
                return None
                
        except Exception as e:
            logger.error(f"刷新令牌过程中发生异常: {str(e)}")
            return None
    
    @staticmethod
    def fetch_emails(email_address, access_token, folder="inbox", callback=None, last_check_time=None):
        """
        通过 Graph API 获取邮件
        
        Args:
            email_address: 邮箱地址
            access_token: OAuth2 访问令牌
            folder: 邮件文件夹，默认为收件箱
            callback: 进度回调函数
            last_check_time: 上次检查时间
        
        Returns:
            list: 邮件记录列表
        """
        if callback is None:
            callback = lambda progress, folder: None
        
        logger.info(f"Graph API: 开始获取邮箱 {email_address} 的邮件")
        
        if last_check_time:
            logger.info(f"Graph API: 获取 {last_check_time} 之后的新邮件")
        
        callback(10, folder)
        
        try:
            handler = GraphAPIMailHandler(email_address, access_token)
            
            callback(20, folder)
            
            # 获取邮件
            messages = handler.get_messages(folder=folder, limit=100, since=last_check_time)
            
            callback(80, folder)
            
            total = len(messages)
            logger.info(f"Graph API: 获取到 {total} 封邮件")
            
            # 转换为统一格式
            mail_records = []
            for msg in messages:
                mail_records.append({
                    "subject": msg.get("subject", ""),
                    "sender": msg.get("sender", ""),
                    "received_time": msg.get("received_time"),
                    "content": msg.get("content", ""),
                    "has_attachments": 1 if msg.get("has_attachments") else 0
                })
            
            callback(90, folder)
            
            return mail_records
            
        except Exception as e:
            logger.error(f"Graph API 获取邮件异常: {str(e)}")
            return []
    
    @staticmethod
    def check_mail(email_info, db, progress_callback=None):
        """
        检查 Outlook 邮箱中的邮件并存储到数据库 (Graph API 方式)
        
        Args:
            email_info: 邮箱信息字典
            db: 数据库实例
            progress_callback: 进度回调函数
        
        Returns:
            dict: 检查结果
        """
        email_id = email_info["id"]
        email_address = email_info["email"]
        refresh_token = email_info.get("refresh_token")
        client_id = email_info.get("client_id")
        last_check_time = email_info.get("last_check_time")
        
        logger.info(f"Graph API: 开始检查邮箱 ID={email_id}, 邮箱={email_address}")
        
        # 检查是否是首次同步（数据库中没有该邮箱的邮件记录）
        is_first_sync = False
        try:
            existing_mail_count = db.get_mail_count_by_email_id(email_id)
            if existing_mail_count == 0:
                is_first_sync = True
                logger.info(f"Graph API: 邮箱 {email_address} 是首次同步，将获取所有邮件（不使用时间过滤）")
        except Exception as e:
            # 如果获取邮件数量失败，尝试使用其他方式判断
            logger.warning(f"Graph API: 获取邮件数量失败: {str(e)}，尝试其他方式判断")
            try:
                # 尝试获取该邮箱的邮件列表
                mail_records = db.get_mail_records(email_id, limit=1)
                if not mail_records or len(mail_records) == 0:
                    is_first_sync = True
                    logger.info(f"Graph API: 邮箱 {email_address} 是首次同步（无邮件记录）")
            except:
                pass
        
        # 如果是首次同步，不使用时间过滤
        if is_first_sync:
            last_check_time = None
        
        if not refresh_token or not client_id:
            error_msg = f"邮箱 {email_address} 缺少 OAuth2 认证信息 (refresh_token 或 client_id)"
            logger.error(error_msg)
            if progress_callback:
                progress_callback(0, error_msg)
            return {"success": False, "message": error_msg}
        
        if progress_callback is None:
            progress_callback = lambda progress, message: None
        
        progress_callback(0, "正在获取访问令牌...")
        
        try:
            # 获取新的访问令牌
            access_token = GraphAPIMailHandler.get_new_access_token(refresh_token, client_id)
            if not access_token:
                error_msg = f"邮箱 {email_address} 获取访问令牌失败"
                logger.error(error_msg)
                progress_callback(0, error_msg)
                return {"success": False, "message": error_msg}
            
            logger.info(f"Graph API: 邮箱 {email_address} 成功获取访问令牌")
            
            # 更新令牌到数据库
            try:
                db.update_email_token(email_id, access_token)
            except Exception as e:
                logger.warning(f"更新令牌到数据库失败: {str(e)}")
            
            progress_callback(10, "开始获取邮件...")
            
            # 要检查的文件夹列表：收件箱和垃圾邮件
            folders_to_check = [
                ("inbox", "INBOX"),
                ("junkemail", "JUNK")  # 垃圾邮件文件夹
            ]
            
            all_mail_records = []
            
            for folder_id, folder_name in folders_to_check:
                # 获取邮件
                def folder_progress_callback(progress, folder):
                    total_progress = 10 + int(progress * 0.4)  # 每个文件夹占40%进度
                    progress_callback(total_progress, f"正在处理 {folder_name} 文件夹")
                
                try:
                    mail_records = GraphAPIMailHandler.fetch_emails(
                        email_address,
                        access_token,
                        folder_id,
                        folder_progress_callback,
                        last_check_time
                    )
                    
                    # 标记文件夹来源
                    for record in mail_records:
                        record["folder"] = folder_name
                    
                    all_mail_records.extend(mail_records)
                    logger.info(f"Graph API: 从 {folder_name} 获取到 {len(mail_records)} 封邮件")
                except Exception as e:
                    logger.warning(f"Graph API: 获取 {folder_name} 文件夹邮件失败: {str(e)}")
            
            count = len(all_mail_records)
            logger.info(f"Graph API: 邮箱 {email_address} 总共获取到 {count} 封邮件")
            progress_callback(90, f"获取到 {count} 封邮件，正在保存...")
            
            if count == 0:
                # 没有新邮件也更新检查时间
                try:
                    db.update_check_time(email_id)
                except Exception as e:
                    logger.warning(f"更新检查时间失败: {str(e)}")
                
                progress_callback(100, "没有新邮件")
                return {"success": True, "message": "没有新邮件", "total": 0, "saved": 0}
            
            # 保存邮件到数据库
            saved_count = 0
            for i, record in enumerate(all_mail_records):
                try:
                    # 处理接收时间
                    received_time = record.get("received_time")
                    if isinstance(received_time, datetime):
                        received_time = received_time.strftime("%Y-%m-%d %H:%M:%S")
                    
                    folder = record.get("folder", "INBOX")
                    logger.debug(f"Graph API: 保存邮件 {i+1}/{count}: {record.get('subject', '(无主题)')[:30]} ({folder})")
                    
                    success, mail_id = db.add_mail_record(
                        email_id=email_id,
                        subject=record.get("subject", "(无主题)"),
                        sender=record.get("sender", "(未知发件人)"),
                        received_time=received_time,
                        content=record.get("content", ""),
                        folder=folder,
                        has_attachments=record.get("has_attachments", 0)
                    )
                    if success:
                        saved_count += 1
                        logger.debug(f"Graph API: 邮件保存成功, mail_id={mail_id}")
                except Exception as e:
                    logger.error(f"Graph API: 保存邮件记录失败: {str(e)}")
                    import traceback
                    traceback.print_exc()
            
            # 更新最后检查时间
            try:
                db.update_check_time(email_id)
                logger.info(f"Graph API: 已更新邮箱 {email_address} 的最后检查时间")
            except Exception as e:
                logger.error(f"Graph API: 更新检查时间失败: {str(e)}")
            
            success_msg = f"完成，共处理 {count} 封邮件，新增 {saved_count} 封"
            progress_callback(100, success_msg)
            
            logger.info(f"Graph API: 邮箱 {email_address} 检查完成，获取 {count} 封，新增 {saved_count} 封")
            
            return {
                "success": True,
                "message": success_msg,
                "total": count,
                "saved": saved_count
            }
            
        except Exception as e:
            error_msg = f"处理邮箱过程中出错: {str(e)}"
            logger.error(f"Graph API: 邮箱 {email_address} {error_msg}")
            import traceback
            traceback.print_exc()
            progress_callback(0, error_msg)
            return {"success": False, "message": error_msg}
