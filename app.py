from flask import Flask, request, render_template, redirect, url_for, session, flash, jsonify
import pymysql
from pymysql.cursors import DictCursor
import os
import logging
from functools import wraps
import random
import string

# 配置日志
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # 使用随机生成的密钥

# 数据库配置
DB_CONFIG = {
    'host': '120.79.10.51',
    'port': 3306,
    'user': 'app_user',
    'password': 'app_password',
    'database': 'app_db',
    'charset': 'utf8mb4'
}


# 登录验证装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            logger.debug(f"未授权访问尝试: {request.url}")
            # 记录原始访问路径，登录后跳转回来
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)

    return decorated_function

# 生成随机邀请码的函数
def generate_invite_code(length=8):
    """生成随机邀请码"""
    characters = string.ascii_uppercase + string.digits
    return ''.join(random.choice(characters) for _ in range(length))

# 在应用启动时生成邀请码
INVITE_CODE = generate_invite_code()
print(f"当前邀请码: {INVITE_CODE}")  # 在终端显示邀请码

def get_db_connection():
    """获取数据库连接"""
    return pymysql.connect(**DB_CONFIG)


@app.route('/')
@login_required
def root():
    """根路径，必须登录才能访问"""
    return redirect(url_for('index'))


@app.route('/index')
@login_required
def index():
    """首页，必须登录才能访问"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(DictCursor) as cursor:
            cursor.execute("SELECT Id, username FROM userinfo")
            users = cursor.fetchall()
            return render_template('index.html',
                                   users=users,
                                   username=session.get('username'))
    except Exception as e:
        logger.error(f"获取用户列表失败: {str(e)}", exc_info=True)
        return render_template('index.html',
                               error='获取用户列表失败',
                               users=[],
                               username=session.get('username'))
    finally:
        if conn:
            conn.close()


@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面，已登录用户直接跳转首页"""
    # 如果已登录，直接跳转到首页
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'GET':
        # 获取跳转目标（之前尝试访问的URL）
        next_page = request.args.get('next', url_for('index'))
        return render_template('login.html', next=next_page)

    # 处理登录表单提交
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    next_page = request.form.get('next', url_for('index'))  # 从隐藏字段获取

    if not username or not password:
        return render_template('login.html',
                               error='请输入用户名和密码',
                               next=next_page)

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor(DictCursor) as cursor:
            cursor.execute(
                "SELECT * FROM userinfo WHERE username = %s AND password = %s",
                (username, password)
            )
            user = cursor.fetchone()

            if user:
                session['user_id'] = user['id']
                session['username'] = user['username']
                logger.debug(f"用户 {username} 登录成功，跳转到: {next_page}")
                return redirect(next_page)
            else:
                return render_template('login.html',
                                       error='用户名或密码错误',
                                       next=next_page)
    except Exception as e:
        logger.error(f"登录错误: {str(e)}", exc_info=True)
        return render_template('login.html',
                               error='系统错误，请稍后重试',
                               next=next_page)
    finally:
        if conn:
            conn.close()


@app.route('/logout')
def logout():
    """退出登录"""
    session.clear()
    return redirect(url_for('login'))


@app.route('/add_user', methods=['GET', 'POST'])
@login_required
def add_user():
    """添加用户"""
    if request.method == 'GET':
        return render_template('add_user.html', username=session.get('username'))

    # 处理表单提交
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()

    if not username or not password:
        return render_template('add_user.html',
                               error='用户名和密码不能为空',
                               username=session.get('username'))

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 检查用户名是否已存在
            cursor.execute("SELECT id FROM userinfo WHERE username = %s", (username,))
            if cursor.fetchone():
                return render_template('add_user.html',
                                       error='用户名已存在',
                                       username=session.get('username'))

            # 插入新用户
            cursor.execute(
                "INSERT INTO userinfo (username, password) VALUES (%s, %s)",
                (username, password)
            )
            conn.commit()
            logger.debug(f"用户 {username} 添加成功")
            flash('用户添加成功', 'success')
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"添加用户失败: {str(e)}", exc_info=True)
        return render_template('add_user.html',
                               error='添加用户失败，请稍后重试',
                               username=session.get('username'))
    finally:
        if conn:
            conn.close()


@app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    """编辑用户"""
    conn = None
    try:
        conn = get_db_connection()

        if request.method == 'GET':
            with conn.cursor(DictCursor) as cursor:
                cursor.execute("SELECT * FROM userinfo WHERE id = %s", (user_id,))
                user = cursor.fetchone()
                if not user:
                    flash('用户不存在', 'danger')
                    return redirect(url_for('index'))

                return render_template('edit_user.html',
                                       user=user,
                                       username=session.get('username'))

        # 处理表单提交
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()

        if not username:
            return render_template('edit_user.html',
                                   error='用户名不能为空',
                                   user={'id': user_id, 'username': username},
                                   username=session.get('username'))

        with conn.cursor() as cursor:
            # 检查用户名是否已被其他用户使用
            cursor.execute(
                "SELECT id FROM userinfo WHERE username = %s AND id != %s",
                (username, user_id)
            )
            if cursor.fetchone():
                return render_template('edit_user.html',
                                       error='用户名已被其他用户使用',
                                       user={'id': user_id, 'username': username},
                                       username=session.get('username'))

            # 更新用户信息
            if password:
                cursor.execute(
                    "UPDATE userinfo SET username = %s, password = %s WHERE id = %s",
                    (username, password, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE userinfo SET username = %s WHERE id = %s",
                    (username, user_id)
                )
            conn.commit()
            logger.debug(f"用户 {user_id} 更新成功")
            flash('用户信息更新成功', 'success')
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"更新用户失败: {str(e)}", exc_info=True)
        return render_template('edit_user.html',
                               error='更新用户失败，请稍后重试',
                               user={'id': user_id, 'username': username},
                               username=session.get('username'))
    finally:
        if conn:
            conn.close()


@app.route('/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    """删除用户"""
    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM userinfo WHERE id = %s", (user_id,))
            conn.commit()
            logger.debug(f"用户 {user_id} 删除成功")
            flash('用户删除成功', 'success')
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"删除用户失败: {str(e)}", exc_info=True)
        flash('用户删除失败，请稍后重试', 'danger')
        return redirect(url_for('index'))
    finally:
        if conn:
            conn.close()


@app.route('/register', methods=['GET', 'POST'])
def register():
    """注册页面"""
    # 如果已登录，直接跳转到首页
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'GET':
        return render_template('register.html')

    # 处理注册表单提交
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '').strip()
    confirm_password = request.form.get('confirm_password', '').strip()
    invite_code = request.form.get('invite_code', '').strip()  # 获取邀请码

    # 验证输入
    if not username or not password or not confirm_password or not invite_code:
        return render_template('register.html',
                             error='请填写所有字段',
                             username=username)

    if password != confirm_password:
        return render_template('register.html',
                             error='两次输入的密码不一致',
                             username=username)

    if len(password) < 6:
        return render_template('register.html',
                             error='密码长度至少为6位',
                             username=username)

    # 验证邀请码
    if invite_code != INVITE_CODE:
        return render_template('register.html',
                             error='邀请码不正确',
                             username=username)

    conn = None
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 检查用户名是否已存在
            cursor.execute("SELECT id FROM userinfo WHERE username = %s", (username,))
            if cursor.fetchone():
                return render_template('register.html',
                                     error='用户名已存在',
                                     username=username)

            # 插入新用户
            cursor.execute(
                "INSERT INTO userinfo (username, password) VALUES (%s, %s)",
                (username, password)
            )
            conn.commit()

            # 注册成功后自动登录
            session['user_id'] = cursor.lastrowid
            session['username'] = username

            logger.debug(f"用户 {username} 注册并登录成功")
            flash('注册成功！欢迎使用系统', 'success')
            return redirect(url_for('index'))
    except Exception as e:
        logger.error(f"注册失败: {str(e)}", exc_info=True)
        return render_template('register.html',
                             error='注册失败，请稍后重试',
                             username=username)
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    app.run(debug=True)