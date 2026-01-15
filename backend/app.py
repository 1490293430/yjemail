import os
import sys
import logging
import threading
import argparse
import datetime
import jwt
import random
from functools import wraps
from flask import Flask, send_from_directory, jsonify, request, Response, make_response
from flask_cors import CORS
from database.db import Database
from utils.email import EmailBatchProcessor
from ws_server.handler import WebSocketHandler
import asyncio
import concurrent.futures

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("FireMail.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('FireMail')

# 确保数据目录存在
data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
os.makedirs(data_dir, exist_ok=True)

# 初始化Flask应用
app = Flask(__name__)
CORS(app, supports_credentials=True, resources={r"/api/*": {"origins": "*"}})  # 允许跨域请求和凭据

# 增加捕获所有OPTIONS请求的处理方法，支持预检请求
@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    """处理所有OPTIONS请求"""
    response = make_response()
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,PUT,DELETE,OPTIONS')
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    return response

# JWT密钥
JWT_SECRET = os.environ.get('JWT_SECRET_KEY', 'huohuo_email_secret_key')

# 打印所有环境变量，帮助调试
print("\n========= 环境变量 =========")
for key, value in os.environ.items():
    if key in ['JWT_SECRET_KEY', 'HOST', 'FLASK_PORT', 'WS_PORT', 'API_URL', 'WS_URL']:
        print(f"{key}: {value}")
print("===========================\n")

# 初始化数据库
db = Database()

# 确保注册功能默认开启，只通过数据库控制
allow_register = db.is_registration_allowed()
logger.info(f"系统启动: 注册功能状态 = {allow_register}")

# 初始化邮件处理器
email_processor = EmailBatchProcessor(db)

# 初始化WebSocket处理器
ws_handler = WebSocketHandler()
ws_handler.set_dependencies(db, email_processor)

# 用户认证装饰器
def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # 从请求头或Cookie获取token
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(" ")[1]
        elif request.cookies.get('token'):
            token = request.cookies.get('token')

        if not token:
            return jsonify({'error': '未认证，请先登录'}), 401

        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            current_user = db.get_user_by_id(data['user_id'])
            if not current_user:
                return jsonify({'error': '无效的用户令牌'}), 401
        except jwt.ExpiredSignatureError:
            return jsonify({'error': '令牌已过期，请重新登录'}), 401
        except Exception as e:
            logger.error(f"令牌验证失败: {str(e)}")
            return jsonify({'error': '无效的令牌'}), 401

        # 将当前用户信息添加到kwargs
        kwargs['current_user'] = current_user
        return f(*args, **kwargs)

    return decorated

# 管理员权限装饰器
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        current_user = kwargs.get('current_user')
        if not current_user or not current_user['is_admin']:
            return jsonify({'error': '需要管理员权限'}), 403
        return f(*args, **kwargs)

    return decorated

# 认证相关API
@app.route('/api/auth/login', methods=['POST'])
def login():
    """用户登录"""
    try:
        data = request.json
        if not data:
            logger.error("登录请求没有JSON数据")
            return jsonify({'error': '无效的请求数据格式'}), 400

        username = data.get('username')
        password = data.get('password')

        logger.info(f"收到登录请求: 用户名={username}")

        if not username or not password:
            logger.warning("登录失败: 用户名或密码为空")
            return jsonify({'error': '用户名和密码不能为空'}), 400

        user = db.authenticate_user(username, password)
        if not user:
            logger.warning(f"登录失败: 用户名或密码错误, 用户名={username}")
            return jsonify({'error': '用户名或密码错误'}), 401

        # 确保user对象包含所有必要属性
        if 'id' not in user or 'username' not in user or 'is_admin' not in user:
            logger.error(f"用户对象缺少必要字段: {user}")
            return jsonify({'error': '内部服务器错误'}), 500

        # 生成JWT令牌
        token = jwt.encode({
            'user_id': user['id'],
            'username': user['username'],
            'is_admin': user['is_admin'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=365)  # 1年有效期
        }, JWT_SECRET, algorithm="HS256")

        # 创建响应
        response_data = {
            'token': token,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'is_admin': user['is_admin']
            }
        }

        logger.info(f"登录成功: 用户名={username}, 用户ID={user['id']}")

        # 创建JSON响应并设置CORS头
        response = make_response(jsonify(response_data))
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST')

        # 设置Cookie
        response.set_cookie(
            'token',
            token,
            httponly=True,
            max_age=7*24*60*60,  # 7天
            secure=False,  # 开发环境设为False，生产环境设为True
            samesite='Lax'
        )

        logger.info(f"用户 {username} 登录成功")
        return response
    except Exception as e:
        logger.error(f"登录过程中发生错误: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """用户登出"""
    response = make_response(jsonify({'message': '已成功登出'}))
    response.delete_cookie('token')
    return response

@app.route('/api/auth/register', methods=['POST'])
def register():
    """用户注册"""
    # 检查系统是否允许注册
    allow_register = db.is_registration_allowed()
    logger.info(f"收到注册请求，当前注册功能状态: {allow_register}")

    if not allow_register:
        logger.warning("注册功能已禁用，拒绝注册请求")
        return jsonify({'error': '注册功能已禁用'}), 403

    data = request.json
    username = data.get('username')
    password = data.get('password')

    logger.info(f"注册用户名: {username}")

    if not username or not password:
        logger.warning("注册失败: 用户名或密码为空")
        return jsonify({'error': '用户名和密码不能为空'}), 400

    # 用户名格式验证
    if len(username) < 3 or len(username) > 20:
        logger.warning("注册失败: 用户名长度不符合要求")
        return jsonify({'error': '用户名长度必须在3-20个字符之间'}), 400

    # 密码强度验证
    if len(password) < 6:
        logger.warning("注册失败: 密码长度不符合要求")
        return jsonify({'error': '密码长度必须至少为6个字符'}), 400

    try:
        # 创建用户
        success, is_admin = db.create_user(username, password)
        if not success:
            logger.warning(f"注册失败: 用户名 {username} 已存在")
            return jsonify({'error': '用户名已存在'}), 409

        logger.info(f"注册成功: 用户名 {username}, 是否管理员: {is_admin}")
        return jsonify({
            'message': '注册成功',
            'username': username,
            'is_admin': is_admin,
            'note': '您是第一个注册的用户，已被自动设置为管理员' if is_admin else ''
        })
    except Exception as e:
        logger.error(f"注册过程出错: {str(e)}")
        return jsonify({'error': f'注册失败: {str(e)}'}), 500

@app.route('/api/auth/user', methods=['GET'])
@token_required
def get_current_user(current_user):
    """获取当前用户信息"""
    return jsonify({
        'id': current_user['id'],
        'username': current_user['username'],
        'is_admin': current_user['is_admin']
    })

@app.route('/api/auth/change-password', methods=['POST'])
@token_required
def change_password(current_user):
    """更改当前用户密码"""
    data = request.json
    old_password = data.get('old_password')
    new_password = data.get('new_password')

    if not old_password or not new_password:
        return jsonify({'error': '旧密码和新密码不能为空'}), 400

    # 验证旧密码
    user = db.authenticate_user(current_user['username'], old_password)
    if not user:
        return jsonify({'error': '旧密码不正确'}), 401

    # 密码强度验证
    if len(new_password) < 6:
        return jsonify({'error': '新密码长度必须至少为6个字符'}), 400

    # 更新密码
    success = db.update_user_password(current_user['id'], new_password)
    if not success:
        return jsonify({'error': '密码更新失败'}), 500

    return jsonify({'message': '密码已成功更新'})

# 用户管理API
@app.route('/api/users', methods=['GET'])
@token_required
@admin_required
def get_all_users(current_user):
    """获取所有用户 (仅管理员)"""
    users = db.get_all_users()
    return jsonify([dict(user) for user in users])

@app.route('/api/users', methods=['POST'])
@token_required
@admin_required
def create_user(current_user):
    """创建新用户 (仅管理员)"""
    data = request.json
    username = data.get('username')
    password = data.get('password')
    is_admin = data.get('is_admin', False)

    if not username or not password:
        return jsonify({'error': '用户名和密码不能为空'}), 400

    # 用户名格式验证
    if len(username) < 3 or len(username) > 20:
        return jsonify({'error': '用户名长度必须在3-20个字符之间'}), 400

    # 密码强度验证
    if len(password) < 6:
        return jsonify({'error': '密码长度必须至少为6个字符'}), 400

    # 创建用户
    success, _ = db.create_user(username, password, is_admin)
    if not success:
        return jsonify({'error': '用户名已存在'}), 409

    return jsonify({
        'message': '用户创建成功',
        'username': username,
        'is_admin': is_admin
    })

@app.route('/api/users/<int:user_id>', methods=['DELETE'])
@token_required
@admin_required
def delete_user(current_user, user_id):
    """删除用户 (仅管理员)"""
    # 检查是否是当前用户
    if user_id == current_user['id']:
        return jsonify({'error': '不能删除自己的账户'}), 400

    # 删除用户
    success = db.delete_user(user_id)
    if not success:
        return jsonify({'error': '删除用户失败'}), 500

    return jsonify({'message': f'用户ID {user_id} 已删除'})

@app.route('/api/users/<int:user_id>/reset-password', methods=['POST'])
@token_required
@admin_required
def reset_user_password(current_user, user_id):
    """重置用户密码 (仅管理员)"""
    data = request.json
    new_password = data.get('new_password')

    if not new_password:
        return jsonify({'error': '新密码不能为空'}), 400

    # 密码强度验证
    if len(new_password) < 6:
        return jsonify({'error': '新密码长度必须至少为6个字符'}), 400

    # 更新密码
    success = db.update_user_password(user_id, new_password)
    if not success:
        return jsonify({'error': '密码重置失败'}), 500

    return jsonify({'message': f'用户ID {user_id} 的密码已重置'})

# 修改现有API以加入用户认证和授权
@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({'status': 'ok', 'message': 'Outlook邮箱助手服务正在运行'})

@app.route('/api/config', methods=['GET'])
def get_config():
    """获取系统配置"""
    try:
        # 确保从数据库获取最新的注册状态
        allow_register = db.is_registration_allowed()
        logger.info(f"获取系统配置: 注册功能状态 = {allow_register}")

        config = {
            'allow_register': allow_register,
            'server_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # 设置CORS头，确保前端可以正常访问
        response = jsonify(config)
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET')

        logger.info(f"返回系统配置: {config}")
        return response
    except Exception as e:
        logger.error(f"获取系统配置出错: {str(e)}")
        # 返回默认配置，确保注册功能默认开启
        default_config = {
            'allow_register': True,
            'server_time': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'error': f"配置获取错误: {str(e)}"
        }
        response = jsonify(default_config)
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

@app.route('/api/emails', methods=['GET'])
@token_required
def get_all_emails(current_user):
    """获取当前用户的所有邮箱（支持分页和搜索）"""
    # 获取分页和搜索参数
    page = request.args.get('page', 1, type=int)
    page_size = request.args.get('page_size', 200, type=int)
    search = request.args.get('search', '').strip()
    
    # 普通用户只能获取自己的邮箱，管理员可以获取所有邮箱
    if current_user['is_admin']:
        emails = db.get_all_emails()
    else:
        emails = db.get_all_emails(current_user['id'])

    # 获取所有订阅，统计每个邮箱的订阅数
    subscriptions = db.get_all_subscriptions()
    email_sub_count = {}
    for sub in subscriptions:
        email_id = sub.get('email_id')
        if email_id:
            email_sub_count[email_id] = email_sub_count.get(email_id, 0) + 1

    # 为每个邮箱添加平台标签和订阅数
    all_emails = []
    for email in emails:
        email_dict = dict(email)
        email_dict['platforms'] = db.get_email_platforms(email_dict['id'])
        email_dict['subscription_count'] = email_sub_count.get(email_dict['id'], 0)
        all_emails.append(email_dict)
    
    # 异常邮箱排在前面（有错误或订阅不足2个）
    all_emails.sort(key=lambda x: (
        -(1 if x.get('last_error') else 0) - (1 if x.get('subscription_count', 0) < 2 else 0)
    ))
    
    # 搜索过滤（前缀匹配）
    if search:
        search_lower = search.lower()
        all_emails = [e for e in all_emails if e['email'].lower().startswith(search_lower)]
    
    # 计算总数
    total = len(all_emails)
    
    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    paged_emails = all_emails[start:end]
    
    return jsonify({
        'emails': paged_emails,
        'total': total,
        'page': page,
        'page_size': page_size,
        'total_pages': (total + page_size - 1) // page_size
    })

@app.route('/api/emails/export', methods=['GET'])
@token_required
def export_emails(current_user):
    """导出邮箱列表为文本文件"""
    from flask import Response
    from datetime import datetime
    
    # 获取用户的邮箱
    if current_user['is_admin']:
        emails = db.get_all_emails()
    else:
        emails = db.get_all_emails(current_user['id'])
    
    # 按导入格式生成内容：邮箱地址----密码----客户端ID----刷新令牌
    lines = []
    for email in emails:
        mail_type = email.get('mail_type', 'outlook')
        if mail_type == 'outlook':
            line = f"{email['email']}----{email.get('password', '')}----{email.get('client_id', '')}----{email.get('refresh_token', '')}"
        else:
            # 非 Outlook 邮箱只导出邮箱和密码
            line = f"{email['email']}----{email.get('password', '')}----{mail_type}"
        lines.append(line)
    
    content = '\n'.join(lines)
    
    # 生成文件名：邮箱备份_年月日_时分秒.txt
    from urllib.parse import quote
    filename = f"邮箱备份_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    encoded_filename = quote(filename)
    
    return Response(
        content,
        mimetype='text/plain',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{encoded_filename}"}
    )

@app.route('/api/emails', methods=['POST'])
@token_required
def add_email(current_user):
    """添加新邮箱"""
    data = request.json
    email = data.get('email')
    password = data.get('password')
    mail_type = data.get('mail_type', 'outlook')

    if not email or not password:
        return jsonify({'error': '邮箱地址和密码是必需的'}), 400

    # 根据不同邮箱类型验证参数并添加
    if mail_type == 'outlook':
        client_id = data.get('client_id')
        refresh_token = data.get('refresh_token')

        if not client_id or not refresh_token:
            return jsonify({'error': 'Outlook邮箱需要提供Client ID和Refresh Token'}), 400

        success = db.add_email(
            current_user['id'],
            email,
            password,
            client_id,
            refresh_token,
            mail_type
        )
    elif mail_type in ['imap', 'gmail', 'qq']:
        # Gmail和QQ邮箱使用IMAP协议，服务器和端口是固定的
        if mail_type == 'gmail':
            server = 'imap.gmail.com'
            port = 993
        elif mail_type == 'qq':
            server = 'imap.qq.com'
            port = 993
        else:
            server = data.get('server', 'imap.gmail.com')
            port = data.get('port', 993)

        success = db.add_email(
            current_user['id'],
            email,
            password,
            mail_type=mail_type,
            server=server,
            port=port,
            use_ssl=True
        )
    else:
        return jsonify({'error': f'不支持的邮箱类型: {mail_type}'}), 400

    if success:
        # 如果是 Outlook 邮箱且 Webhook 已配置，自动创建订阅
        if mail_type == 'outlook' and graph_webhook_manager:
            try:
                email_info = db.get_email_by_id(success)  # success 是新邮箱的 ID
                if email_info:
                    # 在后台线程中创建订阅，不阻塞响应
                    import threading
                    threading.Thread(
                        target=graph_webhook_manager.create_subscription,
                        args=(email_info,),
                        daemon=True
                    ).start()
                    logger.info(f"已为新邮箱 {email} 启动订阅创建任务")
            except Exception as e:
                logger.warning(f"为新邮箱创建订阅失败: {str(e)}")
        
        return jsonify({'message': f'邮箱 {email} 添加成功'})
    else:
        return jsonify({'error': f'邮箱 {email} 已存在或添加失败'}), 409

@app.route('/api/emails/<int:email_id>', methods=['DELETE'])
@token_required
def delete_email(current_user, email_id):
    """删除邮箱"""
    # 获取邮箱信息
    email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
    if not email_info:
        return jsonify({'error': f'邮箱ID {email_id} 不存在或您没有权限'}), 404

    # 停止正在处理的邮箱
    if email_processor.is_email_being_processed(email_id):
        email_processor.stop_processing(email_id)

    # 管理员可以删除任何邮箱，普通用户只能删除自己的邮箱
    db.delete_email(email_id, None if current_user['is_admin'] else current_user['id'])
    return jsonify({'message': f'邮箱 ID {email_id} 已删除'})

@app.route('/api/emails/batch_delete', methods=['POST'])
@token_required
def batch_delete_emails(current_user):
    """批量删除邮箱"""
    data = request.json
    email_ids = data.get('email_ids', [])

    if not email_ids:
        return jsonify({'error': '未提供邮箱ID'}), 400

    # 停止正在处理的邮箱
    for email_id in email_ids:
        if email_processor.is_email_being_processed(email_id):
            email_processor.stop_processing(email_id)

    # 管理员可以删除任何邮箱，普通用户只能删除自己的邮箱
    db.delete_emails(email_ids, None if current_user['is_admin'] else current_user['id'])
    return jsonify({'message': f'已删除 {len(email_ids)} 个邮箱'})

@app.route('/api/emails/<int:email_id>/check', methods=['POST'])
@token_required
def check_email(current_user, email_id):
    """检查指定邮箱的新邮件"""
    try:
        # 获取邮箱信息
        email_info = db.get_email_by_id(email_id)
        if not email_info:
            return jsonify({'error': '邮箱不存在'}), 404

        # 检查邮箱是否属于当前用户
        if email_info['user_id'] != current_user['id']:
            return jsonify({'error': '无权操作此邮箱'}), 403

        # 检查邮箱是否正在处理中
        if email_processor.is_email_being_processed(email_id):
            logger.info(f"邮箱 ID {email_id} 正在处理中，拒绝重复请求")
            return jsonify({
                'success': False,
                'message': '邮箱正在处理中，请稍后再试',
                'status': 'processing'
            }), 409

        # 从数据库获取全局 Graph API 设置
        use_graph_api = db.is_graph_api_enabled()
        
        # 如果启用了 Graph API 且是 Outlook 邮箱，设置标志
        if use_graph_api and email_info.get('mail_type') == 'outlook':
            email_info = dict(email_info)  # 转换为可修改的字典
            email_info['use_graph_api'] = 1
            logger.info(f"邮箱 ID {email_id} 使用 Graph API 模式")

        # 创建进度回调
        def progress_callback(progress, message):
            logger.info(f"邮箱 ID {email_id} 处理进度: {progress}%, 消息: {message}")
            # 通过WebSocket发送进度更新
            try:
                # 使用日志记录进度，不尝试调用异步方法
                logger.info(f"向用户 {current_user['id']} 发送邮箱检查进度: {progress}%, {message}")
                # 这里应使用同步方式发送消息，但WSHandler.broadcast_to_user是异步方法
            except Exception as e:
                logger.error(f"发送进度更新失败: {str(e)}")

        # 提交任务到线程池
        future = email_processor.manual_thread_pool.submit(
            email_processor._check_email_task,
            email_info,
            progress_callback
        )

        # 等待任务完成
        result = future.result(timeout=300)  # 设置超时时间为5分钟

        # 记录任务完成
        logger.info(f"任务完成: {result}")

        return jsonify(result)

    except concurrent.futures.TimeoutError:
        logger.error(f"检查邮箱超时: {email_id}")
        return jsonify({
            'success': False,
            'message': '检查邮箱超时，请稍后再试'
        }), 408

    except Exception as e:
        logger.error(f"检查邮箱失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'检查邮箱失败: {str(e)}'
        }), 500

@app.route('/api/emails/batch_check', methods=['POST'])
@token_required
def batch_check_emails(current_user):
    """批量检查邮箱邮件"""
    data = request.json
    email_ids = data.get('email_ids', []) if data else []
    
    # 从数据库获取全局 Graph API 设置
    use_graph_api = db.is_graph_api_enabled()

    if not email_ids:
        # 如果没有提供 ID，则获取当前用户拥有的所有邮箱
        if current_user['is_admin']:
            emails = db.get_all_emails()
        else:
            emails = db.get_all_emails(current_user['id'])

        email_ids = [email['id'] for email in emails]
    else:
        # 如果提供了ID，验证用户权限
        if not current_user['is_admin']:
            # 获取该用户拥有的邮箱
            owned_emails = db.get_all_emails(current_user['id'])
            owned_ids = [email['id'] for email in owned_emails]
            # 过滤出用户有权限的邮箱ID
            email_ids = [id for id in email_ids if id in owned_ids]

    if not email_ids:
        logger.warning(f"批量检查邮件：未找到邮箱 (用户ID: {current_user['id']})")
        return jsonify({'error': '没有找到邮箱或您没有权限'}), 404

    # 过滤掉已经在处理的邮箱ID
    processing_ids = []
    valid_ids = []
    for email_id in email_ids:
        if email_processor.is_email_being_processed(email_id):
            processing_ids.append(email_id)
        else:
            valid_ids.append(email_id)

    if processing_ids:
        logger.info(f"批量检查：跳过正在处理的邮箱IDs: {processing_ids}")

    if not valid_ids:
        logger.warning("批量检查邮件：所有选择的邮箱都在处理中")
        return jsonify({
            'message': '所有选择的邮箱都在处理中',
            'processing_ids': processing_ids
        }), 409

    # 记录有效的邮箱ID
    valid_emails = [db.get_email_by_id(email_id)['email'] for email_id in valid_ids if db.get_email_by_id(email_id)]
    logger.info(f"批量检查开始处理 {len(valid_ids)} 个邮箱: {valid_emails} (用户ID: {current_user['id']}, Graph API: {use_graph_api})")

    # 自定义进度回调
    def progress_callback(email_id, progress, message):
        logger.info(f"邮箱 ID {email_id} 处理进度: {progress}%, 消息: {message}")

    # 启动邮件检查线程，传递 use_graph_api 参数
    email_processor.check_emails(valid_ids, progress_callback, use_graph_api=use_graph_api)

    return jsonify({
        'message': f'开始检查 {len(valid_ids)} 个邮箱',
        'skipped': len(processing_ids),
        'total': len(email_ids)
    })

@app.route('/api/emails/batch_check_unchecked', methods=['POST'])
@token_required
def batch_check_unchecked_emails(current_user):
    """批量检查未收信的邮箱（last_check_time 为空的邮箱）"""
    # 从数据库获取全局 Graph API 设置
    use_graph_api = db.is_graph_api_enabled()

    # 获取用户的邮箱
    if current_user['is_admin']:
        emails = db.get_all_emails()
    else:
        emails = db.get_all_emails(current_user['id'])

    # 筛选未检查过的邮箱（last_check_time 为空）
    unchecked_ids = [email['id'] for email in emails if not email.get('last_check_time')]

    if not unchecked_ids:
        return jsonify({'message': '没有未收信的邮箱', 'count': 0})

    # 过滤掉已经在处理的邮箱ID
    valid_ids = [eid for eid in unchecked_ids if not email_processor.is_email_being_processed(eid)]

    if not valid_ids:
        return jsonify({'message': '所有未收信的邮箱都在处理中', 'count': 0})

    logger.info(f"批量检查未收信邮箱: {len(valid_ids)} 个 (用户ID: {current_user['id']})")

    # 自定义进度回调
    def progress_callback(email_id, progress, message):
        logger.info(f"邮箱 ID {email_id} 处理进度: {progress}%, 消息: {message}")

    # 启动邮件检查线程
    email_processor.check_emails(valid_ids, progress_callback, use_graph_api=use_graph_api)

    return jsonify({
        'message': f'开始检查 {len(valid_ids)} 个未收信的邮箱',
        'count': len(valid_ids),
        'total_unchecked': len(unchecked_ids)
    })

@app.route('/api/emails/<int:email_id>/mail_records', methods=['GET'])
@token_required
def get_mail_records(current_user, email_id):
    """获取指定邮箱的邮件记录"""
    # 获取邮箱信息
    email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
    if not email_info:
        return jsonify({'error': f'邮箱 ID {email_id} 不存在或您没有权限'}), 404

    mail_records = db.get_mail_records(email_id)
    return jsonify([dict(record) for record in mail_records])

@app.route('/api/emails/get_code', methods=['POST'])
@token_required
def get_verification_code(current_user):
    """
    提取指定邮箱的验证码（等待收信模式）
    
    请求体:
    {
        "email": "example@outlook.com",  # 邮箱地址
        "keyword": "验证码",              # 可选，搜索关键词，默认搜索常见验证码关键词
        "timeout": 60                     # 可选，超时时间（秒），默认60秒
    }
    
    返回:
    {
        "success": true,
        "email": "example@outlook.com",
        "code": "123456",
        "subject": "您的验证码",
        "sender": "noreply@example.com",
        "received_time": "2026-01-09 12:00:00"
    }
    """
    import re
    import time
    from datetime import datetime, timedelta
    
    data = request.get_json() or {}
    email_address = data.get('email')
    keyword = data.get('keyword', '')
    timeout = data.get('timeout', 120)  # 默认120秒超时
    
    if not email_address:
        return jsonify({'success': False, 'error': '请提供邮箱地址'}), 400
    
    # 查找邮箱
    if current_user['is_admin']:
        emails = db.get_all_emails()
    else:
        emails = db.get_all_emails(current_user['id'])
    
    email_info = None
    for e in emails:
        if e['email'].lower() == email_address.lower():
            email_info = e
            break
    
    if not email_info:
        return jsonify({'success': False, 'error': f'邮箱 {email_address} 不存在或您没有权限'}), 404
    
    # 验证码匹配模式
    code_patterns = [
        r'验证码[：:\s]*(\d{4,8})',
        r'code[：:\s]+is[：:\s]+(\d{4,8})',  # code is 123456
        r'code[：:\s]*(\d{4,8})',
        r'verification[：:\s]+code[：:\s]+is[：:\s]+(\d{4,8})',  # verification code is 123456
        r'verification[：:\s]*(\d{4,8})',
        r'(\d{4,8})\s*(?:是您的|为您的|is your)',
        r'\b(\d{4,8})\b',  # 4-8位纯数字（放最后，优先级最低）
    ]
    
    # 常见验证码关键词
    code_keywords = ['验证码', 'verification', 'code', 'verify', '确认码', 'OTP', 'pin']
    
    def extract_code_from_mail(mail):
        """从邮件中提取验证码"""
        subject = mail.get('subject', '')
        content = mail.get('content', '')
        sender = mail.get('sender', '')
        received_time = mail.get('received_time', '')
        
        # 如果指定了关键词，检查是否匹配
        if keyword:
            if keyword.lower() not in subject.lower() and keyword.lower() not in content.lower():
                return None
        else:
            # 检查是否包含验证码相关关键词
            has_keyword = False
            for kw in code_keywords:
                if kw.lower() in subject.lower() or kw.lower() in content.lower():
                    has_keyword = True
                    break
            if not has_keyword:
                return None
        
        # 尝试提取验证码
        text_to_search = f"{subject} {content}"
        
        for pattern in code_patterns:
            matches = re.findall(pattern, text_to_search, re.IGNORECASE)
            if matches:
                code = matches[0] if isinstance(matches[0], str) else matches[0][0]
                # 验证码通常是4-8位数字
                if code.isdigit() and 4 <= len(code) <= 8:
                    return {
                        'success': True,
                        'email': email_address,
                        'code': code,
                        'subject': subject,
                        'sender': sender,
                        'received_time': received_time
                    }
        return None
    
    # 记录开始时间，用于筛选新邮件
    start_time = datetime.now()
    end_time = start_time + timedelta(seconds=timeout)
    
    # 先检查现有邮件（最近30秒内的），按时间倒序排列，返回最新的
    mail_records = db.get_mail_records(email_info['id'])
    recent_limit = start_time - timedelta(seconds=30)
    
    logger.info(f"检查邮箱 {email_address} 的邮件，共 {len(mail_records)} 封，时间范围: {recent_limit}")
    
    # 按时间倒序排列，最新的在前面
    def get_mail_time(mail):
        received_time = mail.get('received_time', '')
        if not received_time:
            return datetime.min
        try:
            if 'T' in str(received_time):
                return datetime.fromisoformat(received_time.replace('Z', '+00:00').replace('+00:00', ''))
            else:
                return datetime.strptime(str(received_time), "%Y-%m-%d %H:%M:%S")
        except:
            return datetime.min
    
    mail_records_sorted = sorted(mail_records, key=get_mail_time, reverse=True)
    
    for mail in mail_records_sorted:
        received_time = mail.get('received_time', '')
        subject = mail.get('subject', '')
        logger.info(f"检查邮件: {subject}, 时间: {received_time}")
        
        if received_time:
            try:
                # 处理多种时间格式
                if 'T' in str(received_time):
                    mail_time = datetime.fromisoformat(received_time.replace('Z', '+00:00').replace('+00:00', ''))
                else:
                    mail_time = datetime.strptime(str(received_time), "%Y-%m-%d %H:%M:%S")
                
                logger.info(f"邮件时间: {mail_time}, 限制时间: {recent_limit}")
                
                if mail_time >= recent_limit:
                    result = extract_code_from_mail(mail)
                    if result:
                        logger.info(f"找到验证码: {result['code']}")
                        return jsonify(result)
            except Exception as e:
                logger.error(f"解析时间失败: {received_time}, 错误: {e}")
    
    # 等待新邮件（Graph API订阅模式会自动推送）
    logger.info(f"等待邮箱 {email_address} 的验证码，超时时间 {timeout} 秒")
    
    check_interval = 2  # 每2秒检查一次数据库
    last_mail_count = len(mail_records)
    
    while datetime.now() < end_time:
        # 等待一段时间
        time.sleep(check_interval)
        
        # 重新获取邮件记录
        mail_records = db.get_mail_records(email_info['id'])
        
        # 检查是否有新邮件
        if len(mail_records) > last_mail_count:
            # 检查新邮件
            for mail in mail_records:
                received_time = mail.get('received_time', '')
                if received_time:
                    try:
                        mail_time = datetime.fromisoformat(received_time.replace('Z', '+00:00').replace('+00:00', ''))
                        # 只检查开始等待后收到的邮件
                        if mail_time >= start_time - timedelta(seconds=10):
                            result = extract_code_from_mail(mail)
                            if result:
                                logger.info(f"成功提取验证码: {result['code']}")
                                return jsonify(result)
                    except:
                        pass
            last_mail_count = len(mail_records)
    
    logger.info(f"等待验证码超时: {email_address}")
    return jsonify({
        'success': False,
        'error': f'等待{timeout}秒后仍未收到验证码邮件',
        'email': email_address
    }), 404

@app.route('/api/mail_records/latest', methods=['GET'])
@token_required
def get_latest_mail_records(current_user):
    """获取当前用户所有邮箱的最新邮件（10分钟内，否则最新20条）"""
    try:
        records = db.get_latest_mail_records(current_user['id'], limit=20, minutes=10)
        return jsonify(records)
    except Exception as e:
        logger.error(f"获取最新邮件失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/mail_records/<int:mail_id>/attachments', methods=['GET'])
@token_required
def get_mail_attachments(current_user, mail_id):
    """获取指定邮件的附件列表"""
    try:
        # 先获取邮件信息，验证权限
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        # 验证用户是否有权限访问该邮件
        email_id = mail_record['email_id']
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权访问此邮件'}), 403

        # 获取附件列表
        attachments = db.get_attachments(mail_id)
        return jsonify([dict(attachment) for attachment in attachments])
    except Exception as e:
        logger.error(f"获取附件列表失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/attachments/<int:attachment_id>/download', methods=['GET'])
@token_required
def download_attachment(current_user, attachment_id):
    """下载附件"""
    try:
        # 获取附件信息
        attachment = db.get_attachment(attachment_id)
        if not attachment:
            return jsonify({'error': '附件不存在'}), 404

        # 验证用户是否有权限下载该附件
        mail_id = attachment['mail_id']
        mail_record = db.get_mail_record_by_id(mail_id)
        if not mail_record:
            return jsonify({'error': '邮件不存在'}), 404

        email_id = mail_record['email_id']
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '无权下载此附件'}), 403

        # 准备下载响应
        filename = attachment['filename']
        content_type = attachment['content_type']
        content = attachment['content']

        response = make_response(content)
        response.headers['Content-Type'] = content_type
        response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response
    except Exception as e:
        logger.error(f"下载附件失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/<int:email_id>/upload_email_file', methods=['POST'])
@token_required
def upload_email_file(current_user, email_id):
    """上传邮件文件并解析"""
    try:
        # 验证用户是否有权限操作该邮箱
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': f'邮箱 ID {email_id} 不存在或您没有权限'}), 404

        # 检查是否有文件上传
        if 'file' not in request.files:
            return jsonify({'error': '没有上传文件'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': '没有选择文件'}), 400

        # 检查文件扩展名
        allowed_extensions = ['.eml', '.txt', '.msg', '.mbox', '.emlx']
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({'error': f'不支持的文件格式，仅支持 {", ".join(allowed_extensions)}'}), 400

        # 保存文件到临时目录
        temp_dir = os.path.join(os.getcwd(), 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        temp_file_path = os.path.join(temp_dir, f"{int(time.time())}_{file.filename}")
        file.save(temp_file_path)

        try:
            # 导入邮件处理模块
            from utils.email import EmailFileParser

            # 解析邮件文件
            mail_record = EmailFileParser.parse_email_file(temp_file_path)

            if not mail_record:
                return jsonify({'error': '解析邮件文件失败'}), 400

            # 保存邮件记录到数据库
            success, mail_id = db.add_mail_record(
                email_id=email_id,
                subject=mail_record.get('subject', '(无主题)'),
                sender=mail_record.get('sender', '(未知发件人)'),
                content=mail_record.get('content', '(无内容)'),
                received_time=mail_record.get('received_time', datetime.now()),
                folder='IMPORTED',
                has_attachments=1 if mail_record.get('has_attachments', False) else 0
            )

            if success and mail_id and mail_record.get('has_attachments', False):
                # 保存附件
                attachments = mail_record.get('full_attachments', [])
                for attachment in attachments:
                    db.add_attachment(
                        mail_id=mail_id,
                        filename=attachment.get('filename', '未命名'),
                        content_type=attachment.get('content_type', 'application/octet-stream'),
                        size=attachment.get('size', 0),
                        content=attachment.get('content', b'')
                    )

            # 删除临时文件
            os.remove(temp_file_path)

            return jsonify({
                'success': True,
                'message': '邮件文件解析成功',
                'mail_id': mail_id
            })

        finally:
            # 确保临时文件被删除
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)

    except Exception as e:
        logger.error(f"上传邮件文件失败: {str(e)}")
        traceback.print_exc()
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/import', methods=['POST'])
@token_required
def import_emails(current_user):
    """批量导入邮箱"""
    data = request.json.get('data')
    mail_type = request.json.get('mail_type', 'outlook')

    if not data:
        return jsonify({'error': '导入数据不能为空'}), 400

    # 解析导入的数据
    lines = data.strip().split('\n')
    total = len(lines)
    success_count = 0
    failed_details = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue

        try:
            parts = line.split('----')
            if len(parts) != 4:
                failed_details.append({
                    'line': i + 1,
                    'content': line,
                    'reason': '格式错误，需要4个字段'
                })
                continue

            email, password, client_id, refresh_token = parts
            if not all([email, password, client_id, refresh_token]):
                failed_details.append({
                    'line': i + 1,
                    'content': line,
                    'reason': '有空白字段'
                })
                continue

            success = db.add_email(current_user['id'], email, password, client_id, refresh_token, mail_type)
            if success:
                success_count += 1
            else:
                failed_details.append({
                    'line': i + 1,
                    'content': line,
                    'reason': '邮箱地址已存在'
                })
        except Exception as e:
            logger.error(f"导入邮箱出错: {str(e)}")
            failed_details.append({
                'line': i + 1,
                'content': line,
                'reason': f'导入异常: {str(e)}'
            })

    # 返回导入结果
    return jsonify({
        'total': total,
        'success': success_count,
        'failed': len(failed_details),
        'failed_details': failed_details
    })

# 系统配置管理
@app.route('/api/admin/config/registration', methods=['POST'])
@token_required
@admin_required
def toggle_registration(current_user):
    """管理员开启/关闭注册功能"""
    data = request.json
    allow = data.get('allow', False)

    if db.toggle_registration(allow):
        action = "开启" if allow else "关闭"
        logger.info(f"管理员 {current_user['username']} 已{action}注册功能")
        return jsonify({'message': f'已成功{action}注册功能', 'allow_register': allow})
    else:
        return jsonify({'error': '更新注册配置失败'}), 500

# 前端静态文件服务
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """提供前端静态文件"""
    # 确定前端构建目录的路径
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend', 'dist')

    # 如果路径为空或者是根路径，则返回 index.html
    if not path or path == '/':
        return send_from_directory(frontend_dir, 'index.html')

    # 检查请求的文件是否存在
    file_path = os.path.join(frontend_dir, path)
    if os.path.isfile(file_path):
        return send_from_directory(frontend_dir, path)
    else:
        # 如果文件不存在，返回 index.html 让前端路由处理
        return send_from_directory(frontend_dir, 'index.html')

@app.route('/api/emails/<int:email_id>/password', methods=['GET'])
@token_required
def get_email_password(current_user, email_id):
    """获取指定邮箱的密码"""
    try:
        email = db.get_email_by_id(email_id)
        if not email:
            return jsonify({'error': '邮箱不存在'}), 404

        # 验证是否为当前用户的邮箱或管理员
        if email['user_id'] != current_user['id'] and not current_user['is_admin']:
            return jsonify({'error': '无权访问此邮箱'}), 403

        return jsonify({'password': email['password']})
    except Exception as e:
        logger.error(f"获取邮箱密码失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/search', methods=['POST'])
@token_required
def search_emails(current_user):
    """搜索邮件内容"""
    try:
        data = request.json
        if not data:
            return jsonify({'error': '无效的请求数据格式'}), 400

        query = data.get('query', '').strip()
        search_in = data.get('search_in', [])  # 可以包含 'subject', 'sender', 'recipient', 'content'

        if not query:
            return jsonify({'error': '搜索关键词不能为空'}), 400

        if not search_in:
            search_in = ['subject', 'sender', 'recipient', 'content']  # 默认搜索所有字段

        logger.info(f"用户 {current_user['username']} 执行搜索: {query}, 搜索范围: {search_in}")

        # 获取用户的所有邮箱
        user_emails = db.get_emails_by_user_id(current_user['id'])
        user_email_ids = [email['id'] for email in user_emails]

        # 根据搜索条件查询邮件
        results = db.search_mail_records(
            user_email_ids,
            query,
            search_in_subject='subject' in search_in,
            search_in_sender='sender' in search_in,
            search_in_recipient='recipient' in search_in,
            search_in_content='content' in search_in
        )

        # 增加邮箱信息到结果中
        emails_map = {email['id']: email for email in user_emails}
        for record in results:
            email_id = record.get('email_id')
            if email_id in emails_map:
                record['email_address'] = emails_map[email_id]['email']

        return jsonify({'results': results})
    except Exception as e:
        logger.error(f"搜索邮件失败: {str(e)}")
        return jsonify({'error': f'服务器错误: {str(e)}'}), 500

@app.route('/api/emails/<int:email_id>', methods=['PUT'])
@token_required
def update_email(current_user, email_id):
    """更新邮箱信息"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '无效的请求数据'}), 400

        # 获取当前邮箱信息，用于保留不允许修改的字段
        current_email = db.get_email_by_id(email_id, current_user['id'])
        if not current_email:
            return jsonify({'error': '邮箱不存在或您没有权限修改'}), 404

        # 验证邮箱信息
        required_fields = ['email', 'password']
        for field in required_fields:
            if field not in data and field != 'password':  # 密码可以不修改
                return jsonify({'error': f'缺少必要字段: {field}'}), 400

        # 准备更新数据，保持邮箱类型不变
        update_data = {
            'email': data.get('email'),
            'mail_type': current_email['mail_type']  # 使用已有数据，不允许修改
        }

        # 仅当提供了非空密码时才更新密码
        if data.get('password') and data.get('password') != '******':
            update_data['password'] = data.get('password')

        # 根据不同邮箱类型更新特定字段
        if current_email['mail_type'] == 'outlook':
            if data.get('client_id'):
                update_data['client_id'] = data.get('client_id')
            if data.get('refresh_token'):
                update_data['refresh_token'] = data.get('refresh_token')
            # 支持更新 use_graph_api 字段
            if 'use_graph_api' in data:
                update_data['use_graph_api'] = 1 if data.get('use_graph_api') else 0
        elif current_email['mail_type'] in ['imap', 'gmail', 'qq']:
            if data.get('server'):
                update_data['server'] = data.get('server')
            if data.get('port') is not None:
                update_data['port'] = data.get('port')
            if data.get('use_ssl') is not None:
                update_data['use_ssl'] = data.get('use_ssl')

        # 更新邮箱信息
        success = db.update_email(
            email_id,
            user_id=current_user['id'],
            **update_data
        )

        if not success:
            return jsonify({'error': '更新邮箱信息失败'}), 500

        logger.info(f"用户 {current_user['username']} 更新了邮箱 ID: {email_id}")

        return jsonify({
            'message': '邮箱信息更新成功',
            'data': {
                'email_id': email_id,
                'email': update_data['email'],
                'mail_type': update_data['mail_type']
            }
        }), 200

    except Exception as e:
        logger.error(f"更新邮箱信息失败: {str(e)}")
        return jsonify({'error': '更新邮箱信息失败'}), 500

# ==================== 邮箱平台标签 API ====================

@app.route('/api/emails/<int:email_id>/platforms', methods=['GET'])
@token_required
def get_email_platforms(current_user, email_id):
    """获取邮箱的平台标签"""
    # 验证邮箱所有权
    email = db.get_email_by_id(email_id, current_user['id'])
    if not email:
        return jsonify({'error': '邮箱不存在或无权访问'}), 404
    
    platforms = db.get_email_platforms(email_id)
    return jsonify(platforms)

@app.route('/api/emails/<int:email_id>/platforms', methods=['POST'])
@token_required
def add_email_platform(current_user, email_id):
    """为邮箱添加平台标签"""
    # 验证邮箱所有权
    email = db.get_email_by_id(email_id, current_user['id'])
    if not email:
        return jsonify({'error': '邮箱不存在或无权访问'}), 404
    
    data = request.get_json()
    platform_name = data.get('platform_name', '').strip()
    
    if not platform_name:
        return jsonify({'error': '平台名称不能为空'}), 400
    
    if len(platform_name) > 50:
        return jsonify({'error': '平台名称不能超过50个字符'}), 400
    
    success = db.add_email_platform(email_id, platform_name)
    if success:
        return jsonify({'message': '添加成功', 'platform': platform_name})
    return jsonify({'error': '添加失败'}), 500

@app.route('/api/emails/<int:email_id>/platforms/<platform_name>', methods=['DELETE'])
@token_required
def remove_email_platform(current_user, email_id, platform_name):
    """移除邮箱的平台标签"""
    # 验证邮箱所有权
    email = db.get_email_by_id(email_id, current_user['id'])
    if not email:
        return jsonify({'error': '邮箱不存在或无权访问'}), 404
    
    success = db.remove_email_platform(email_id, platform_name)
    if success:
        return jsonify({'message': '移除成功'})
    return jsonify({'error': '移除失败'}), 500

@app.route('/api/platforms', methods=['GET'])
@token_required
def get_all_platforms(current_user):
    """获取所有已使用的平台列表"""
    platforms = db.get_all_platforms(current_user['id'])
    return jsonify(platforms)

@app.route('/api/platforms/<platform_name>/unregistered', methods=['GET'])
@token_required
def get_unregistered_emails(current_user, platform_name):
    """
    获取未注册某个平台的一个邮箱
    
    返回:
    {
        "platform": "MoreLogin",
        "email": "a@outlook.com",
        "remaining": 99
    }
    """
    # 获取用户所有邮箱
    if current_user['is_admin']:
        all_emails = db.get_all_emails()
    else:
        all_emails = db.get_all_emails(current_user['id'])
    
    # 筛选未注册该平台的邮箱
    platform_lower = platform_name.lower()
    unregistered_emails = []
    
    for email in all_emails:
        # 跳过异常邮箱
        if email.get('last_error'):
            continue
        platforms = db.get_email_platforms(email['id'])
        # 检查是否已注册该平台（不区分大小写）
        has_platform = any(p.lower() == platform_lower for p in platforms)
        if not has_platform:
            unregistered_emails.append(email)
    
    # 如果没有未注册的邮箱，返回空结果
    if not unregistered_emails:
        return jsonify({
            'platform': platform_name,
            'email': None,
            'remaining': 0,
            'message': '没有未注册的邮箱了'
        })
    
    # 随机选择一个未注册的邮箱
    selected_email = random.choice(unregistered_emails)
    remaining = len(unregistered_emails) - 1
    
    return jsonify({
        'platform': platform_name,
        'email': selected_email['email'],
        'remaining': remaining
    })

@app.route('/api/platforms/<platform_name>/unregistered/all', methods=['GET'])
@token_required
def get_all_unregistered_emails(current_user, platform_name):
    """
    获取未注册某个平台的所有邮箱
    
    返回:
    {
        "platform": "比特浏览器",
        "count": 50,
        "emails": ["a@outlook.com", "b@outlook.com", ...]
    }
    """
    # 获取用户所有邮箱
    if current_user['is_admin']:
        all_emails = db.get_all_emails()
    else:
        all_emails = db.get_all_emails(current_user['id'])
    
    # 筛选未注册该平台的邮箱
    unregistered = []
    platform_lower = platform_name.lower()
    
    for email in all_emails:
        # 跳过异常邮箱
        if email.get('last_error'):
            continue
        platforms = db.get_email_platforms(email['id'])
        # 检查是否未注册该平台（不区分大小写）
        has_platform = any(p.lower() == platform_lower for p in platforms)
        if not has_platform:
            unregistered.append(email['email'])
    
    return jsonify({
        'platform': platform_name,
        'count': len(unregistered),
        'emails': unregistered
    })

@app.route('/api/platforms/<platform_name>/registered', methods=['GET'])
@token_required
def get_registered_emails(current_user, platform_name):
    """
    获取已注册某个平台的所有邮箱
    
    返回:
    {
        "platform": "MoreLogin",
        "count": 17,
        "emails": ["a@outlook.com", "b@outlook.com", ...]
    }
    """
    # 获取用户所有邮箱
    if current_user['is_admin']:
        all_emails = db.get_all_emails()
    else:
        all_emails = db.get_all_emails(current_user['id'])
    
    # 筛选已注册该平台的邮箱
    registered = []
    platform_lower = platform_name.lower()
    
    for email in all_emails:
        platforms = db.get_email_platforms(email['id'])
        # 检查是否已注册该平台（不区分大小写）
        has_platform = any(p.lower() == platform_lower for p in platforms)
        if has_platform:
            registered.append(email['email'])
    
    return jsonify({
        'platform': platform_name,
        'count': len(registered),
        'emails': registered
    })

@app.route('/api/emails/batch_add_platform', methods=['POST'])
@token_required
def batch_add_platform(current_user):
    """批量为邮箱添加平台标签"""
    data = request.get_json()
    email_ids = data.get('email_ids', [])
    platform_name = data.get('platform_name', '').strip()
    
    if not email_ids:
        return jsonify({'error': '请选择邮箱'}), 400
    
    if not platform_name:
        return jsonify({'error': '平台名称不能为空'}), 400
    
    # 验证邮箱所有权
    valid_ids = []
    for email_id in email_ids:
        email = db.get_email_by_id(email_id, current_user['id'])
        if email:
            valid_ids.append(email_id)
    
    if not valid_ids:
        return jsonify({'error': '没有有效的邮箱'}), 400
    
    count = db.batch_add_email_platforms(valid_ids, platform_name)
    return jsonify({'message': f'已为 {count} 个邮箱添加标签', 'count': count})

# ==================== 平台识别规则 API ====================

@app.route('/api/platform_rules', methods=['GET'])
@token_required
def get_platform_rules(current_user):
    """获取平台识别规则列表"""
    rules = db.get_platform_rules(current_user['id'])
    return jsonify(rules)

@app.route('/api/platform_rules', methods=['POST'])
@token_required
def add_platform_rule(current_user):
    """添加平台识别规则"""
    data = request.get_json()
    platform_name = data.get('platform_name', '').strip()
    sender_pattern = data.get('sender_pattern', '').strip() or None
    subject_pattern = data.get('subject_pattern', '').strip() or None
    content_pattern = data.get('content_pattern', '').strip() or None
    
    if not platform_name:
        return jsonify({'error': '平台名称不能为空'}), 400
    
    if not sender_pattern and not subject_pattern and not content_pattern:
        return jsonify({'error': '至少需要设置一个匹配规则'}), 400
    
    rule_id = db.add_platform_rule(
        current_user['id'], platform_name, 
        sender_pattern, subject_pattern, content_pattern
    )
    
    if rule_id:
        return jsonify({'message': '添加成功', 'id': rule_id})
    return jsonify({'error': '添加失败'}), 500

@app.route('/api/platform_rules/<int:rule_id>', methods=['PUT'])
@token_required
def update_platform_rule(current_user, rule_id):
    """更新平台识别规则"""
    data = request.get_json()
    
    update_data = {}
    if 'platform_name' in data:
        update_data['platform_name'] = data['platform_name'].strip()
    if 'sender_pattern' in data:
        update_data['sender_pattern'] = data['sender_pattern'].strip() or None
    if 'subject_pattern' in data:
        update_data['subject_pattern'] = data['subject_pattern'].strip() or None
    if 'content_pattern' in data:
        update_data['content_pattern'] = data['content_pattern'].strip() or None
    if 'is_enabled' in data:
        update_data['is_enabled'] = 1 if data['is_enabled'] else 0
    
    success = db.update_platform_rule(rule_id, current_user['id'], **update_data)
    if success:
        return jsonify({'message': '更新成功'})
    return jsonify({'error': '更新失败'}), 500

@app.route('/api/platform_rules/<int:rule_id>', methods=['DELETE'])
@token_required
def delete_platform_rule(current_user, rule_id):
    """删除平台识别规则"""
    success = db.delete_platform_rule(rule_id, current_user['id'])
    if success:
        return jsonify({'message': '删除成功'})
    return jsonify({'error': '删除失败'}), 500

# ==================== 平台名称纠正 API ====================

@app.route('/api/platform_corrections', methods=['GET'])
@token_required
def get_platform_corrections(current_user):
    """获取平台纠正映射列表"""
    corrections = db.get_all_platform_corrections(current_user['id'])
    return jsonify(corrections)

@app.route('/api/platform_corrections/<int:correction_id>', methods=['DELETE'])
@token_required
def delete_platform_correction(current_user, correction_id):
    """删除平台纠正映射"""
    success = db.delete_platform_correction(correction_id, current_user['id'])
    if success:
        return jsonify({'message': '删除成功'})
    return jsonify({'error': '删除失败'}), 500

@app.route('/api/emails/<int:email_id>/correct_platform', methods=['POST'])
@token_required
def correct_email_platform(current_user, email_id):
    """
    纠正邮箱的平台标签
    - old_name: 旧的平台名称（可选，用于移除）
    - new_name: 新的平台名称
    - sender: 发件人地址（可选，用于保存纠正映射）
    """
    # 验证邮箱所有权
    email = db.get_email_by_id(email_id, current_user['id'])
    if not email:
        return jsonify({'error': '邮箱不存在或无权限'}), 404
    
    data = request.get_json()
    old_name = data.get('old_name', '').strip() or None
    new_name = data.get('new_name', '').strip()
    sender = data.get('sender', '').strip() or None
    
    if not new_name:
        return jsonify({'error': '新平台名称不能为空'}), 400
    
    success = db.correct_platform_name(email_id, old_name, new_name, sender)
    if success:
        return jsonify({'message': '纠正成功'})
    return jsonify({'error': '纠正失败'}), 500

@app.route('/api/platforms/rename', methods=['POST'])
@token_required
def rename_platform(current_user):
    """
    重命名平台：批量更新所有使用该平台名的邮箱
    - old_name: 旧的平台名称
    - new_name: 新的平台名称
    """
    data = request.get_json()
    old_name = data.get('old_name', '').strip()
    new_name = data.get('new_name', '').strip()
    
    if not old_name or not new_name:
        return jsonify({'error': '平台名称不能为空'}), 400
    
    if old_name == new_name:
        return jsonify({'error': '新旧名称相同'}), 400
    
    count = db.rename_platform(current_user['id'], old_name, new_name)
    return jsonify({'message': f'已更新 {count} 个邮箱', 'count': count})

@app.route('/api/platforms/scan_emails', methods=['POST'])
@token_required
def scan_emails_for_platforms(current_user):
    """
    扫描已有邮件，识别平台并标记
    """
    try:
        # 获取用户的所有邮箱
        emails = db.get_all_emails_by_user(current_user['id'])
        if not emails:
            return jsonify({'message': '没有邮箱', 'scanned': 0, 'tagged': 0})
        
        scanned_count = 0
        tagged_count = 0
        
        for email in emails:
            # 获取该邮箱的所有邮件
            mail_records = db.get_mail_records(email['id'], current_user['id'])
            
            for mail in mail_records:
                scanned_count += 1
                sender = mail.get('sender', '')
                subject = mail.get('subject', '')
                content = mail.get('content', '')
                if isinstance(content, dict):
                    content = content.get('text', '') or content.get('html', '')
                
                # 调用自动标记逻辑
                # 先检查纠正映射
                sender_domain = db._extract_sender_domain(sender)
                if sender_domain:
                    corrected_name = db.get_platform_correction(current_user['id'], sender_domain)
                    if corrected_name:
                        if db.add_email_platform(email['id'], corrected_name):
                            tagged_count += 1
                        continue
                
                # 尝试用户自定义规则
                matched_platforms = db.match_platform_rules(current_user['id'], sender, subject, content)
                
                # 如果没有匹配，尝试通用识别
                if not matched_platforms:
                    platform = db._detect_registration_email(sender, subject, content)
                    if platform:
                        matched_platforms = [platform]
                
                # 添加平台标签
                for platform in matched_platforms:
                    if db.add_email_platform(email['id'], platform):
                        tagged_count += 1
        
        return jsonify({
            'message': f'扫描完成，共扫描 {scanned_count} 封邮件，标记 {tagged_count} 个平台',
            'scanned': scanned_count,
            'tagged': tagged_count
        })
    except Exception as e:
        logger.error(f"扫描邮件失败: {str(e)}")
        return jsonify({'error': f'扫描失败: {str(e)}'}), 500

@app.route('/api/email/start_real_time_check', methods=['POST'])
@token_required
def start_real_time_check():
    """启动实时邮件检查"""
    try:
        check_interval = request.json.get('check_interval', 60)
        if check_interval < 30:  # 最小检查间隔为30秒
            check_interval = 30

        success = email_processor.start_real_time_check(check_interval)
        if success:
            return jsonify({
                'success': True,
                'message': f'实时邮件检查已启动，检查间隔: {check_interval}秒'
            })
        else:
            return jsonify({
                'success': False,
                'message': '实时邮件检查已在运行中'
            })
    except Exception as e:
        logger.error(f"启动实时邮件检查失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'启动实时邮件检查失败: {str(e)}'
        })

@app.route('/api/email/stop_real_time_check', methods=['POST'])
@token_required
def stop_real_time_check():
    """停止实时邮件检查"""
    try:
        success = email_processor.stop_real_time_check()
        if success:
            return jsonify({
                'success': True,
                'message': '实时邮件检查已停止'
            })
        else:
            return jsonify({
                'success': False,
                'message': '实时邮件检查未在运行'
            })
    except Exception as e:
        logger.error(f"停止实时邮件检查失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'停止实时邮件检查失败: {str(e)}'
        })

@app.route('/api/email/add_to_real_time_queue', methods=['POST'])
@token_required
def add_to_real_time_queue():
    """将邮箱添加到实时检查队列"""
    try:
        email_id = request.json.get('email_id')
        if not email_id:
            return jsonify({
                'success': False,
                'message': '缺少邮箱ID'
            })

        email_processor.add_to_real_time_queue(email_id)
        return jsonify({
            'success': True,
            'message': f'邮箱ID: {email_id} 已添加到实时检查队列'
        })
    except Exception as e:
        logger.error(f"添加邮箱到实时检查队列失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'添加邮箱到实时检查队列失败: {str(e)}'
        })

@app.route('/api/emails/<int:email_id>/realtime', methods=['POST'])
@token_required
def toggle_email_realtime_check(current_user, email_id):
    """开启/关闭指定邮箱的实时检查"""
    try:
        data = request.json
        enable = data.get('enable', False)

        # 获取当前邮箱信息
        email_info = db.get_email_by_id(email_id, current_user['id'])
        if not email_info:
            return jsonify({'error': '邮箱不存在或您没有权限'}), 404

        # 更新实时检查状态
        success = db.set_email_realtime_check(email_id, enable)
        if not success:
            return jsonify({'error': '更新实时检查状态失败'}), 500

        action = "开启" if enable else "关闭"
        logger.info(f"用户 {current_user['username']} {action}了邮箱 {email_info['email']} 的实时检查")

        return jsonify({
            'success': True,
            'message': f'已{action}邮箱的实时检查',
            'data': {
                'email_id': email_id,
                'email': email_info['email'],
                'enable_realtime_check': enable
            }
        })
    except Exception as e:
        logger.error(f"切换邮箱实时检查状态失败: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'切换邮箱实时检查状态失败: {str(e)}'
        }), 500

# ==================== Graph API Webhook 相关端点 ====================

# 全局 Webhook 管理器实例
graph_webhook_manager = None
graph_webhook_handler = None

def init_graph_webhook():
    """初始化 Graph API Webhook 管理器"""
    global graph_webhook_manager, graph_webhook_handler
    
    # 从环境变量获取 webhook URL
    webhook_url = os.environ.get('GRAPH_WEBHOOK_URL')
    if not webhook_url:
        logger.warning("未配置 GRAPH_WEBHOOK_URL 环境变量，Graph API Webhook 功能未启用")
        return False
    
    try:
        from utils.email.graph_webhook import GraphWebhookManager, GraphWebhookHandler
        
        graph_webhook_manager = GraphWebhookManager(db, webhook_url)
        graph_webhook_handler = GraphWebhookHandler(db, graph_webhook_manager)
        
        # 启动订阅续订循环
        graph_webhook_manager.start_renew_loop(check_interval=3600)
        
        # 自动为所有 Outlook 邮箱创建订阅（后台执行）
        graph_webhook_manager.create_subscriptions_async()
        
        logger.info(f"Graph API Webhook 已初始化，webhook URL: {webhook_url}")
        logger.info("已启动后台任务为所有 Outlook 邮箱创建订阅")
        return True
    except Exception as e:
        logger.error(f"初始化 Graph API Webhook 失败: {str(e)}")
        return False

@app.route('/api/graph/webhook', methods=['POST'])
def graph_webhook_endpoint():
    """
    Graph API Webhook 接收端点
    
    微软会向此端点发送：
    1. 订阅验证请求（带 validationToken 参数）
    2. 邮件变更通知（POST JSON 数据）
    """
    # 处理订阅验证请求
    validation_token = request.args.get('validationToken')
    if validation_token:
        logger.info("收到 Graph API 订阅验证请求")
        # 必须返回纯文本格式的 validationToken
        response = make_response(validation_token)
        response.headers['Content-Type'] = 'text/plain'
        return response
    
    # 处理邮件变更通知
    if graph_webhook_handler:
        try:
            notification_data = request.json
            logger.info(f"收到 Graph API 通知: {notification_data}")
            
            # 异步处理通知，立即返回 202 Accepted
            threading.Thread(
                target=graph_webhook_handler.handle_notification,
                args=(notification_data,),
                daemon=True
            ).start()
            
            return '', 202
        except Exception as e:
            logger.error(f"处理 Graph API 通知失败: {str(e)}")
            return '', 202  # 即使失败也返回 202，避免微软重试
    else:
        logger.warning("Graph API Webhook 未初始化")
        return '', 202

@app.route('/api/graph/subscriptions', methods=['GET'])
@token_required
@admin_required
def get_graph_subscriptions(current_user):
    """获取所有 Graph API 订阅（仅管理员）"""
    try:
        subscriptions = db.get_all_subscriptions()
        return jsonify(subscriptions)
    except Exception as e:
        logger.error(f"获取订阅列表失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/graph/subscriptions/create_all', methods=['POST'])
@token_required
@admin_required
def create_all_graph_subscriptions(current_user):
    """为所有 Outlook 邮箱创建订阅（仅管理员）"""
    if not graph_webhook_manager:
        return jsonify({'error': 'Graph API Webhook 未配置，请设置 GRAPH_WEBHOOK_URL 环境变量'}), 400
    
    try:
        data = request.json or {}
        async_mode = data.get('async', True)  # 默认异步执行
        
        if async_mode:
            # 异步执行，立即返回
            graph_webhook_manager.create_subscriptions_async()
            
            # 获取当前统计
            outlook_count = len(db.get_all_outlook_emails())
            existing_count = len(db.get_all_subscriptions())
            
            return jsonify({
                'success': True,
                'message': f'已开始后台创建订阅任务，共 {outlook_count} 个 Outlook 邮箱，已有 {existing_count} 个订阅',
                'note': '由于 API 限流，批量创建需要较长时间（约每分钟 50 个）'
            })
        else:
            # 同步执行（不推荐用于大量邮箱）
            result = graph_webhook_manager.create_subscriptions_for_all_outlook_emails()
            if result:
                return jsonify({
                    'success': True,
                    'message': f"创建订阅完成：成功 {result['created']}，失败 {result['failed']}，跳过 {result['skipped']}",
                    'data': result
                })
            else:
                return jsonify({'error': '创建订阅失败'}), 500
    except Exception as e:
        logger.error(f"批量创建订阅失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/graph/subscriptions/<int:email_id>', methods=['POST'])
@token_required
def create_graph_subscription(current_user, email_id):
    """为指定邮箱创建 Graph API 订阅"""
    if not graph_webhook_manager:
        return jsonify({'error': 'Graph API Webhook 未配置'}), 400
    
    try:
        # 验证邮箱权限
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '邮箱不存在或您没有权限'}), 404
        
        if email_info.get('mail_type') != 'outlook':
            return jsonify({'error': '只有 Outlook 邮箱支持 Graph API 订阅'}), 400
        
        result = graph_webhook_manager.create_subscription(email_info)
        if result:
            return jsonify({
                'success': True,
                'message': '订阅创建成功',
                'data': {
                    'subscription_id': result['subscription_id'],
                    'expiration_time': str(result['expiration_time'])
                }
            })
        else:
            return jsonify({'error': '创建订阅失败'}), 500
    except Exception as e:
        logger.error(f"创建订阅失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/graph/subscriptions/<int:email_id>', methods=['DELETE'])
@token_required
def delete_graph_subscription(current_user, email_id):
    """删除指定邮箱的 Graph API 订阅"""
    if not graph_webhook_manager:
        return jsonify({'error': 'Graph API Webhook 未配置'}), 400
    
    try:
        # 验证邮箱权限
        email_info = db.get_email_by_id(email_id, None if current_user['is_admin'] else current_user['id'])
        if not email_info:
            return jsonify({'error': '邮箱不存在或您没有权限'}), 404
        
        # 获取订阅信息
        subscription = db.get_subscription_by_email_id(email_id)
        if not subscription:
            return jsonify({'error': '该邮箱没有订阅'}), 404
        
        # 删除订阅
        success = graph_webhook_manager.delete_subscription(
            subscription['subscription_id'],
            email_info.get('refresh_token'),
            email_info.get('client_id')
        )
        
        if success:
            return jsonify({'success': True, 'message': '订阅已删除'})
        else:
            # 即使微软端删除失败，也删除本地记录
            db.delete_subscription_by_email_id(email_id)
            return jsonify({'success': True, 'message': '订阅记录已删除（微软端可能已过期）'})
    except Exception as e:
        logger.error(f"删除订阅失败: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/graph/config', methods=['GET'])
@token_required
@admin_required
def get_graph_config(current_user):
    """获取 Graph API 配置状态（仅管理员）"""
    webhook_url = os.environ.get('GRAPH_WEBHOOK_URL', '')
    return jsonify({
        'webhook_enabled': graph_webhook_manager is not None,
        'webhook_url': webhook_url,
        'subscription_count': len(db.get_all_subscriptions()) if graph_webhook_manager else 0,
        'use_graph_api': db.is_graph_api_enabled()
    })

@app.route('/api/graph/config', methods=['POST'])
@token_required
@admin_required
def set_graph_config(current_user):
    """设置 Graph API 配置（仅管理员）"""
    data = request.json or {}
    
    if 'use_graph_api' in data:
        enabled = data.get('use_graph_api', True)
        success = db.set_graph_api_enabled(enabled)
        if success:
            logger.info(f"管理员 {current_user['username']} {'启用' if enabled else '禁用'}了 Graph API")
            return jsonify({
                'success': True,
                'message': f"已{'启用' if enabled else '禁用'} Graph API",
                'use_graph_api': enabled
            })
        else:
            return jsonify({'error': '设置失败'}), 500
    
    return jsonify({'error': '无效的请求参数'}), 400

@app.route('/api/config/graph_api', methods=['GET'])
@token_required
def get_graph_api_status(current_user):
    """获取 Graph API 开关状态（所有用户可访问）"""
    from datetime import datetime
    
    # 获取 Outlook 邮箱数量
    outlook_emails = db.get_all_outlook_emails()
    outlook_count = len(outlook_emails) if outlook_emails else 0
    
    # 获取订阅数量和过期数量
    subscriptions = db.get_all_subscriptions()
    subscription_count = len(subscriptions) if subscriptions else 0
    
    # 每个邮箱有2个订阅（Inbox + JunkEmail）
    expected_subscription_count = outlook_count * 2
    
    # 统计过期订阅
    expired_count = 0
    now = datetime.now()
    if subscriptions:
        for sub in subscriptions:
            exp_time = sub.get('expiration_time')
            if exp_time:
                try:
                    if isinstance(exp_time, str):
                        exp_dt = datetime.strptime(exp_time, "%Y-%m-%d %H:%M:%S")
                    else:
                        exp_dt = exp_time
                    if exp_dt < now:
                        expired_count += 1
                except:
                    pass
    
    return jsonify({
        'use_graph_api': db.is_graph_api_enabled(),
        'outlook_email_count': outlook_count,
        'subscription_count': subscription_count,
        'expected_subscription_count': expected_subscription_count,
        'expired_count': expired_count
    })

@app.route('/api/subscriptions/missing', methods=['GET'])
@token_required
@admin_required
def get_missing_subscriptions(current_user):
    """查找缺少订阅的邮箱"""
    # 获取所有 Outlook 邮箱
    outlook_emails = db.get_all_outlook_emails()
    
    # 获取所有订阅
    subscriptions = db.get_all_subscriptions()
    
    # 统计每个邮箱的订阅数
    email_sub_count = {}
    for sub in subscriptions:
        email_id = sub.get('email_id')
        if email_id:
            email_sub_count[email_id] = email_sub_count.get(email_id, 0) + 1
    
    # 找出订阅不完整的邮箱（应该有2个订阅：Inbox + JunkEmail）
    missing = []
    for email in outlook_emails:
        email_id = email['id']
        sub_count = email_sub_count.get(email_id, 0)
        if sub_count < 2:
            missing.append({
                'id': email_id,
                'email': email['email'],
                'subscription_count': sub_count,
                'missing': 2 - sub_count
            })
    
    return jsonify({
        'total_emails': len(outlook_emails),
        'missing_count': len(missing),
        'emails': missing
    })

def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='Outlook邮箱助手')
    parser.add_argument('--host', default='0.0.0.0', help='主机地址')
    parser.add_argument('--port', type=int, default=5000, help='HTTP端口')
    parser.add_argument('--ws-port', type=int, default=8765, help='WebSocket端口')
    parser.add_argument('--debug', action='store_true', help='启用调试模式')
    return parser.parse_args()

def start_websocket_server():
    """启动WebSocket服务器"""
    try:
        logger.info("启动WebSocket服务器")
        ws_handler.run()
    except Exception as e:
        logger.error(f"WebSocket服务器异常: {e}")
        sys.exit(1)

if __name__ == '__main__':
    try:
        args = parse_args()

        # 设置WebSocket端口
        ws_handler.port = args.ws_port

        # 启动WebSocket服务器
        ws_thread = threading.Thread(target=start_websocket_server)
        ws_thread.daemon = True
        ws_thread.start()

        # 初始化 Graph API Webhook（如果配置了）
        init_graph_webhook()
        
        # 将 webhook_manager 传递给 WebSocket handler
        if graph_webhook_manager:
            ws_handler.set_webhook_manager(graph_webhook_manager)
        
        # 将 ws_handler 传递给 webhook_handler 用于广播新邮件
        if graph_webhook_handler:
            graph_webhook_handler.set_ws_handler(ws_handler)

        # 注释掉 IMAP 轮询，改用 Graph API Webhook 或手动检查
        # email_processor.start_real_time_check(check_interval=60)
        # logger.info("实时邮件检查已启动")
        logger.info("IMAP 轮询已禁用，请使用 Graph API Webhook 或手动检查")

        # 启动Flask应用
        logger.info(f"Outlook邮箱助手启动于 http://{args.host}:{args.port}")
        app.run(host=args.host, port=args.port, debug=args.debug)
    except KeyboardInterrupt:
        logger.info("程序被用户中断，正在关闭...")
    except Exception as e:
        logger.error(f"程序启动异常: {e}")
    finally:
        # 清理资源
        if graph_webhook_manager:
            graph_webhook_manager.stop_renew_loop()
        if db:
            db.close()
        logger.info("程序已关闭")