import os
import cv2
import face_recognition
import base64
import numpy as np
import io
from datetime import datetime, timedelta, date
from PIL import Image
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response, abort, g
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from models import db, User, Attendance, LeaveRequest, Payroll, Notification
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from werkzeug.utils import secure_filename
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
from flask_socketio import SocketIO, emit, join_room, leave_room

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'supersecretkey')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10 MB
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'sammachine07@gmail.com'
app.config['MAIL_PASSWORD'] = 'ltgw zmve rdne krto'
app.config['MAIL_DEFAULT_SENDER'] = 'sammachine07@gmail.com'

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

mail = Mail(app)
serializer = URLSafeTimedSerializer(app.config['SECRET_KEY'])

socketio = SocketIO(app, async_mode='threading')

online_users = {}

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def home():
    return redirect(url_for('dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter((User.username == username) | (User.email == username)).first()
        if user and user.check_password(password):
            if not user.is_verified:
                flash('Please verify your email before logging in.', 'warning')
                return redirect(url_for('login'))
            if not user.is_active:
                flash('Your account has been deactivated. Please contact the administrator.', 'danger')
                return redirect(url_for('login'))
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username/email or password.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.name = request.form['name']
        current_user.email = request.form['email']
        current_user.phone = request.form['phone']
        db.session.commit()
        flash('Profile updated.', 'success')
    return render_template('profile.html')

@app.route('/profile/change_password', methods=['POST'])
@login_required
def change_password():
    current = request.form['current_password']
    new = request.form['new_password']
    confirm = request.form['confirm_password']
    if not current_user.check_password(current):
        flash('Current password is incorrect.', 'danger')
    elif new != confirm:
        flash('New passwords do not match.', 'danger')
    else:
        current_user.set_password(new)
        db.session.commit()
        flash('Password changed successfully.', 'success')
    return redirect(url_for('profile'))

@app.route('/profile/upload_picture', methods=['POST'])
@login_required
def upload_profile_picture():
    if 'profile_picture' not in request.files:
        flash('No file part.', 'danger')
        return redirect(url_for('profile'))
    file = request.files['profile_picture']
    if file.filename == '':
        flash('No selected file.', 'danger')
        return redirect(url_for('profile'))
    if file and file.mimetype.startswith('image/'):
        filename = secure_filename(f"{current_user.id}_" + file.filename)
        save_path = os.path.join('static', 'images', 'profiles')
        os.makedirs(save_path, exist_ok=True)
        file.save(os.path.join(save_path, filename))
        current_user.profile_picture = filename
        db.session.commit()
        flash('Profile picture updated!', 'success')
    else:
        flash('Invalid file type. Please upload an image.', 'danger')
    return redirect(url_for('profile'))

# ------------------- ADMIN ROUTES -------------------
@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_users = User.query.count()
    active_users = User.query.filter_by(is_active=True).count()
    pending_leave = LeaveRequest.query.filter_by(status='Pending').count()
    payroll_this_month = db.session.query(db.func.sum(Payroll.net_pay)).filter(
        db.extract('year', Payroll.period_end) == date.today().year,
        db.extract('month', Payroll.period_end) == date.today().month
    ).scalar() or 0
    todays_attendance = Attendance.query.filter(
        db.func.date(Attendance.timestamp) == date.today()
    ).all()
    return render_template('admin_dashboard.html',
        total_users=total_users,
        active_users=active_users,
        pending_leave=pending_leave,
        payroll_this_month=payroll_this_month,
        todays_attendance=todays_attendance
    )

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.order_by(User.name).all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/users/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_user_edit(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        user.name = request.form['name']
        user.email = request.form['email']
        user.phone = request.form.get('phone')
        user.role = request.form['role']
        user.is_active = bool(int(request.form['is_active']))
        db.session.commit()
        flash('User updated successfully.', 'success')
    user_attendance = Attendance.query.filter_by(user_id=user.id).order_by(Attendance.timestamp.desc()).all()
    user_leaves = LeaveRequest.query.filter_by(user_id=user.id).order_by(LeaveRequest.start_date.desc()).all()
    user_payrolls = Payroll.query.filter_by(user_id=user.id).order_by(Payroll.period_end.desc()).all()
    return render_template('admin_user_edit.html', user=user, user_attendance=user_attendance, user_leaves=user_leaves, user_payrolls=user_payrolls)

@app.route('/admin/users/<int:user_id>/deactivate')
@login_required
@admin_required
def admin_user_deactivate(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_active:
        user.is_active = False
        db.session.commit()
        flash(f'User {(user.name or user.username or "")} has been deactivated.', 'warning')
    else:
        flash('User is already inactive.', 'info')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/activate')
@login_required
@admin_required
def admin_user_activate(user_id):
    user = User.query.get_or_404(user_id)
    if not user.is_active:
        user.is_active = True
        db.session.commit()
        flash(f'User {(user.name or user.username or "")} has been activated.', 'success')
    else:
        flash('User is already active.', 'info')
    return redirect(url_for('admin_users'))

@app.route('/admin/users/<int:user_id>/reset_password', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_user_reset_password(user_id):
    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', user=user)
        user.set_password(new_password)
        db.session.commit()
        flash(f'Password for {(user.name or user.username or "")} has been reset.', 'success')
        return redirect(url_for('admin_users'))
    return render_template('reset_password.html', user=user)

@app.route('/admin/leaves', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_leaves():
    leaves = LeaveRequest.query.order_by(LeaveRequest.requested_at.desc()).all()
    if request.method == 'POST':
        leave_id = int(request.form['leave_id'])
        action = request.form['action']
        leave = LeaveRequest.query.get_or_404(leave_id)
        if action == 'approve':
            leave.status = 'Approved'
            leave.admin_note = request.form.get('admin_note', '')
            leave.reviewed_at = datetime.utcnow()
        elif action == 'reject':
            leave.status = 'Rejected'
            leave.admin_note = request.form.get('admin_note', '')
            leave.reviewed_at = datetime.utcnow()
        elif action == 'cancel':
            leave.status = 'Cancelled'
            leave.reviewed_at = datetime.utcnow()
        db.session.commit()
        # --- Notification for leave status change ---
        message = f"Your leave request from {leave.start_date} to {leave.end_date} was {leave.status.lower()}."
        if leave.admin_note:
            message += f" Note: {leave.admin_note}"
        notification = Notification(user_id=leave.user_id, message=message)
        db.session.add(notification)
        db.session.commit()
        flash('Leave request updated.', 'success')
        return redirect(url_for('admin_leaves'))
    return render_template('admin_leaves.html', leaves=leaves)

@app.route('/admin/payroll')
@login_required
@admin_required
def admin_payroll():
    payrolls = Payroll.query.order_by(Payroll.period_end.desc()).all()
    return render_template('admin_payroll.html', payrolls=payrolls)

@app.route('/admin/payroll/generate', methods=['GET', 'POST'])
@login_required
@admin_required
def generate_payroll():
    users = User.query.filter_by(is_active=True).all()
    if request.method == 'POST':
        period_start = datetime.strptime(request.form['period_start'], '%Y-%m-%d').date()
        period_end = datetime.strptime(request.form['period_end'], '%Y-%m-%d').date()
        daily_rate = float(request.form['daily_rate'])
        for user in users:
            # Count unique attendance days for this user in the period
            attendance_days = db.session.query(db.func.date(Attendance.timestamp)).filter(
                Attendance.user_id == user.id,
                Attendance.timestamp >= period_start,
                Attendance.timestamp <= period_end
            ).distinct().count()
            base_salary = attendance_days * daily_rate
            payroll = Payroll(
                user_id=user.id,
                period_start=period_start,
                period_end=period_end,
                base_salary=base_salary,
                bonuses=0.0,
                deductions=0.0,
                net_pay=base_salary,
                generated_at=datetime.utcnow()
            )
            db.session.add(payroll)
        db.session.commit()
        flash('Payroll generated for all users.', 'success')
        return redirect(url_for('admin_payroll'))
    return render_template('generate_payroll.html', users=users)

@app.route('/admin/attendance')
@login_required
@admin_required
def admin_attendance():
    all_users = User.query.order_by(User.name).all()
    user_id = request.args.get('user_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    query = Attendance.query
    if user_id:
        query = query.filter_by(user_id=user_id)
    if start_date:
        query = query.filter(Attendance.timestamp >= start_date)
    if end_date:
        query = query.filter(Attendance.timestamp <= end_date)
    attendance_records = query.order_by(Attendance.timestamp.desc()).all()
    return render_template('admin_attendance.html', attendance_records=attendance_records, all_users=all_users)

@app.route('/admin/payroll/<int:payroll_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_payroll(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)
    if request.method == 'POST':
        payroll.base_salary = float(request.form['base_salary'])
        payroll.bonuses = float(request.form['bonuses'])
        payroll.deductions = float(request.form['deductions'])
        payroll.net_pay = payroll.base_salary + payroll.bonuses - payroll.deductions
        db.session.commit()
        flash('Payroll updated successfully.', 'success')
        return redirect(url_for('admin_payroll'))
    return render_template('edit_payroll.html', payroll=payroll)

@app.route('/admin/payroll/<int:payroll_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_payroll(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)
    db.session.delete(payroll)
    db.session.commit()
    flash('Payroll record deleted.', 'success')
    return redirect(url_for('admin_payroll'))

# ------------------- USER ROUTES -------------------
@app.route('/attendance')
@login_required
def attendance():
    my_attendance = Attendance.query.filter_by(user_id=current_user.id).order_by(Attendance.timestamp.desc()).all()
    return render_template('attendance.html', my_attendance=my_attendance)

@app.route('/payroll')
@login_required
def payroll():
    payrolls = Payroll.query.filter_by(user_id=current_user.id).order_by(Payroll.period_end.desc()).all()
    return render_template('payroll.html', payrolls=payrolls)

@app.route('/leave', methods=['GET', 'POST'])
@login_required
def leave():
    if request.method == 'POST':
        leave_type = request.form['leave_type']
        start_date = datetime.strptime(request.form['start_date'], '%Y-%m-%d').date()
        end_date = datetime.strptime(request.form['end_date'], '%Y-%m-%d').date()
        reason = request.form['reason']
        leave_request = LeaveRequest(user_id=current_user.id, leave_type=leave_type, start_date=start_date, end_date=end_date, reason=reason, status='Pending')
        db.session.add(leave_request)
        db.session.commit()
        flash('Leave request submitted.', 'success')
        return redirect(url_for('leave'))
    my_leaves = LeaveRequest.query.filter_by(user_id=current_user.id).order_by(LeaveRequest.start_date.desc()).all()
    return render_template('leave.html', my_leaves=my_leaves)

@app.before_request
def before_request():
    if current_user.is_authenticated:
        g.unread_notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    else:
        g.unread_notifications = 0

@app.route('/notifications')
@login_required
def notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.timestamp.desc()).all()
    # Mark all as read when visiting the page
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({Notification.is_read: True})
    db.session.commit()
    return render_template('notifications.html', notifications=notifications)

@app.route('/notifications/delete/<int:notification_id>', methods=['POST'])
@login_required
def delete_notification(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        abort(403)
    db.session.delete(notification)
    db.session.commit()
    flash('Notification deleted.', 'success')
    return redirect(url_for('notifications'))

@app.route('/payroll/<int:payroll_id>/payslip')
@login_required
def view_payslip(payroll_id):
    payroll = Payroll.query.get_or_404(payroll_id)
    if payroll.user_id != current_user.id and current_user.role != 'admin':
        abort(403)
    return render_template('payslip.html', payroll=payroll)

# ------------------- FACE RECOGNITION ROUTES -------------------
@app.route('/register_face', methods=['POST'])
@login_required
def register_face():
    try:
        image_data = request.form.get('image').split(',')[1]
        img = Image.open(io.BytesIO(base64.b64decode(image_data)))
        img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        face_locations = face_recognition.face_locations(img)
        if not face_locations:
            return jsonify({"status": "error", "message": "No face detected."})
        encoding = face_recognition.face_encodings(img, face_locations)[0]
        current_user.face_encoding = encoding
        db.session.commit()
        return jsonify({"status": "success", "message": "Face registered successfully."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/recognize_face', methods=['POST'])
def recognize_face():
    try:
        image_data = request.form.get('image').split(',')[1]
        img = Image.open(io.BytesIO(base64.b64decode(image_data)))
        img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        face_locations = face_recognition.face_locations(img)
        if not face_locations:
            return jsonify({"status": "error", "message": "No face detected for attendance."})
        face_encoding = face_recognition.face_encodings(img, face_locations)[0]
        users_with_encoding = User.query.filter(User.face_encoding != None).all()
        known_encodings = [u.face_encoding for u in users_with_encoding]
        known_names = [u.username for u in users_with_encoding]
        if not known_encodings:
            return jsonify({"status": "error", "message": "No known faces to compare."})
        distances = face_recognition.face_distance(known_encodings, face_encoding)
        best_index = np.argmin(distances)
        if distances[best_index] < 0.35:
            matched_name = known_names[best_index]
            matched_user = users_with_encoding[best_index]
            session['registered_name'] = matched_name
            return jsonify({"status": "success", "match": True, "name": matched_user.name, "user_id": matched_user.id})
        else:
            return jsonify({"status": "error", "message": "Face not recognized."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/mark_attendance', methods=['POST'])
@login_required
def mark_attendance():
    try:
        image_data = request.form.get('image').split(',')[1]
        img = Image.open(io.BytesIO(base64.b64decode(image_data)))
        img = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
        face_locations = face_recognition.face_locations(img)
        if not face_locations:
            return jsonify({"status": "error", "message": "No face detected for attendance."})
        face_encoding = face_recognition.face_encodings(img, face_locations)[0]
        users_with_encoding = User.query.filter(User.face_encoding != None).all()
        known_encodings = [u.face_encoding for u in users_with_encoding]
        known_ids = [u.id for u in users_with_encoding]
        if not known_encodings:
            return jsonify({"status": "error", "message": "No known faces to compare."})
        distances = face_recognition.face_distance(known_encodings, face_encoding)
        best_index = np.argmin(distances)
        if distances[best_index] < 0.35:
            matched_user_id = known_ids[best_index]
            attendance = Attendance(user_id=matched_user_id, timestamp=datetime.utcnow(), location=request.remote_addr, status="Present")
            db.session.add(attendance)
            db.session.commit()
            return jsonify({"status": "success", "message": "Attendance marked successfully!"})
        else:
            return jsonify({"status": "error", "message": "Face not recognized."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        name = request.form['name']
        # Check if user exists
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('register'))
        user = User(username=username, email=email, name=name, is_verified=False)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        # Send verification email
        token = serializer.dumps(user.email, salt='email-verify')
        verify_url = url_for('verify_email', token=token, _external=True)
        msg = Message('Verify Your Email', recipients=[user.email])
        msg.body = f"Welcome to Demachine solutions! Please verify your email by clicking the following link: {verify_url}\nIf you did not register, ignore this email."
        mail.send(msg)
        flash('Registration successful! Please check your email to verify your account.', 'info')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/verify_email/<token>')
def verify_email(token):
    try:
        email = serializer.loads(token, salt='email-verify', max_age=86400)
    except Exception:
        flash('The verification link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))
    user = User.query.filter_by(email=email).first_or_404()
    if user.is_verified:
        flash('Your email is already verified. Please log in.', 'info')
    else:
        user.is_verified = True
        db.session.commit()
        flash('Your email has been verified! You can now log in.', 'success')
    return redirect(url_for('login'))

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if request.method == 'POST':
        if 'change_notifications' in request.form:
            current_user.email_notifications = 'email_notifications' in request.form
            current_user.sms_notifications = 'sms_notifications' in request.form
            db.session.commit()
            flash('Notification preferences updated.', 'success')
        elif 'delete_account' in request.form:
            user_id = current_user.id
            logout_user()
            # Delete user and related data
            User.query.filter_by(id=user_id).delete()
            db.session.commit()
            flash('Your account has been deleted.', 'success')
            return redirect(url_for('login'))
    return render_template('settings.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        user = User.query.filter_by(email=email).first()
        if user:
            token = serializer.dumps(user.email, salt='password-reset')
            reset_url = url_for('reset_password', token=token, _external=True)
            msg = Message('Password Reset Request', recipients=[user.email])
            msg.body = f"To reset your password, click the following link: {reset_url}\nIf you did not request this, ignore this email."
            mail.send(msg)
            flash('A password reset link has been sent to your email.', 'info')
        else:
            flash('If that email is registered, a reset link has been sent.', 'info')
        return redirect(url_for('login'))
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, salt='password-reset', max_age=3600)
    except Exception:
        flash('The password reset link is invalid or has expired.', 'danger')
        return redirect(url_for('login'))
    user = User.query.filter_by(email=email).first_or_404()
    if request.method == 'POST':
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']
        if new_password != confirm_password:
            flash('Passwords do not match.', 'danger')
            return render_template('reset_password.html', token=token)
        user.set_password(new_password)
        db.session.commit()
        flash('Your password has been reset. Please log in.', 'success')
        return redirect(url_for('login'))
    return render_template('reset_password.html', token=token)

@app.route('/admin/users/add', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_user_add():
    if request.method == 'POST':
        name = request.form['name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form.get('role', 'user')
        is_active = bool(int(request.form.get('is_active', 1)))
        # Check if user exists
        if User.query.filter_by(username=username).first() or User.query.filter_by(email=email).first():
            flash('Username or email already exists.', 'danger')
            return redirect(url_for('admin_user_add'))
        user = User(username=username, email=email, name=name, role=role, is_active=is_active, is_verified=True)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash('User added successfully.', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin_user_add.html')

# --- Real-time signaling for in-site calls ---
@socketio.on('connect')
def handle_connect():
    user_id = None
    role = None
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        user_id = current_user.id
        role = current_user.role
        online_users[request.sid] = {'user_id': user_id, 'role': role}

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in online_users:
        del online_users[request.sid]

@socketio.on('call_request')
def handle_call_request(data):
    # data: {from_user_id, to_role}
    # Check if any admin is online
    any_admin_online = any(u['role'] == 'admin' for u in online_users.values())
    if not any_admin_online:
        emit('no_admin_online', {}, room=request.sid)
        return
    emit('incoming_call', data, broadcast=True, include_self=False)

@socketio.on('call_response')
def handle_call_response(data):
    print(f"Received call_response: {data}")
    # data: {from_admin_id, from_admin_sid, to_user_id, accepted: true/false, call_id}
    if data.get('accepted'):
        print(f"Call accepted by admin {data['from_admin_id']} for user {data['to_user_id']} (call_id={data.get('call_id')})")
        # Notify all other admins to close their incoming call modal
        for sid, info in online_users.items():
            if info['role'] == 'admin' and info['user_id'] != data['from_admin_id']:
                print(f"Notifying admin {info['user_id']} to close modal")
                emit('call_answered', {'from_admin_id': data['from_admin_id'], 'to_user_id': data['to_user_id'], 'call_id': data.get('call_id')}, room=sid)
        # Notify the user who called
        for sid, info in online_users.items():
            if info['user_id'] == data['to_user_id']:
                print(f"Notifying user {data['to_user_id']} that call was accepted")
                emit('call_response', data, room=sid)
        # Notify the answering admin directly using their sid
        if 'from_admin_sid' in data:
            print(f"Notifying answering admin {data['from_admin_id']} via sid {data['from_admin_sid']}")
            emit('call_response', data, room=data['from_admin_sid'])
    else:
        print(f"Call rejected by admin {data['from_admin_id']} for user {data['to_user_id']}")
        # If rejected, only notify the user
        for sid, info in online_users.items():
            if info['user_id'] == data['to_user_id']:
                emit('call_response', data, room=sid)

@socketio.on('join_room')
def handle_join_room(data):
    # data: {room}
    join_room(data['room'])

@socketio.on('leave_room')
def handle_leave_room(data):
    # data: {room}
    leave_room(data['room'])

@socketio.on('signal')
def handle_signal(data):
    # data: {room, signal_data}
    emit('signal', data['signal_data'], room=data['room'], include_self=False)

@app.route('/notifications/<int:notification_id>')
@login_required
def view_notification(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        abort(403)
    if not notification.is_read:
        notification.is_read = True
        db.session.commit()
    return render_template('notification_detail.html', notification=notification)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
        socketio.run(app, host="0.0.0.0", port=5050)
