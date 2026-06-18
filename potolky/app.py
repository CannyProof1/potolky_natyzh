from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from datetime import datetime
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ceiling_site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

# Создаем папку для загрузок
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Модели базы данных
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), default='customer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    products = db.relationship('Product', backref='seller', lazy=True)
    requests = db.relationship('Request', backref='user', lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    material = db.Column(db.String(50), nullable=False)
    texture = db.Column(db.String(50))
    color = db.Column(db.String(30))
    size = db.Column(db.String(30))
    image_url = db.Column(db.String(200))
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_approved = db.Column(db.Boolean, default=False)
    requests = db.relationship('Request', backref='product', lazy=True)

class Request(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    admin_comment = db.Column(db.Text)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Декораторы для проверки ролей
def role_required(role):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated or current_user.role != role:
                flash('У вас нет доступа к этой странице', 'error')
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def admin_required(f):
    return role_required('admin')(f)

def seller_required(f):
    return role_required('seller')(f)

# Роуты
@app.route('/')
def index():
    products = Product.query.filter_by(is_approved=True).all()
    return render_template('index.html', products=products)

@app.route('/products')
def products():
    # Получаем параметры фильтрации
    category = request.args.get('category')
    material = request.args.get('material')
    
    query = Product.query.filter_by(is_approved=True)
    if category:
        query = query.filter_by(category=category)
    if material:
        query = query.filter_by(material=material)
    
    products = query.all()
    categories = db.session.query(Product.category).distinct().all()
    materials = db.session.query(Product.material).distinct().all()
    return render_template('products.html', products=products, categories=categories, materials=materials)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        password_confirm = request.form.get('password_confirm')
        role = request.form.get('role', 'customer')
        
        # Проверка совпадения паролей
        if password != password_confirm:
            flash('Пароли не совпадают!', 'error')
            return redirect(url_for('register'))
        
        # Проверка существования пользователя
        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже занято', 'error')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Email уже используется', 'error')
            return redirect(url_for('register'))
        
        # Создание пользователя
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        user = User(username=username, email=email, password_hash=hashed_password, role=role)
        db.session.add(user)
        db.session.commit()
        
        flash('Регистрация успешна! Войдите в систему.', 'success')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            flash(f'Добро пожаловать, {user.username}!', 'success')
            
            if user.role == 'admin':
                return redirect(url_for('admin_panel'))
            elif user.role == 'seller':
                return redirect(url_for('seller_dashboard'))
            else:
                return redirect(url_for('index'))
        else:
            flash('Неверное имя пользователя или пароль', 'error')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('index'))

# Панель продавца
@app.route('/seller/dashboard')
@login_required
@role_required('seller')
def seller_dashboard():
    products = Product.query.filter_by(seller_id=current_user.id).all()
    return render_template('dashboard.html', products=products)

@app.route('/seller/add_product', methods=['GET', 'POST'])
@login_required
@role_required('seller')
def add_product():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        price = float(request.form['price'])
        category = request.form['category']
        material = request.form['material']
        texture = request.form.get('texture')
        color = request.form.get('color')
        size = request.form.get('size')
        
        # Обработка загрузки изображения
        image_file = request.files.get('image')
        image_url = None
        
        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_url = os.path.join('uploads', filename)
        
        product = Product(
            title=title,
            description=description,
            price=price,
            category=category,
            material=material,
            texture=texture,
            color=color,
            size=size,
            image_url=image_url,
            seller_id=current_user.id,
            is_approved=False
        )
        
        db.session.add(product)
        db.session.commit()
        
        flash('Товар добавлен и ожидает одобрения администратора', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('add_product.html')

@app.route('/seller/edit_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
@role_required('seller')
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    if product.seller_id != current_user.id:
        flash('У вас нет прав на редактирование этого товара', 'error')
        return redirect(url_for('seller_dashboard'))
    
    if request.method == 'POST':
        product.title = request.form['title']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.category = request.form['category']
        product.material = request.form['material']
        product.texture = request.form.get('texture')
        product.color = request.form.get('color')
        product.size = request.form.get('size')
        
        image_file = request.files.get('image')
        if image_file and image_file.filename:
            filename = secure_filename(image_file.filename)
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_')
            filename = timestamp + filename
            image_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            product.image_url = os.path.join('uploads', filename)
        
        # После редактирования товар снова отправляется на модерацию
        product.is_approved = False
        db.session.commit()
        flash('Товар обновлен и отправлен на повторную модерацию', 'success')
        return redirect(url_for('seller_dashboard'))
    
    return render_template('edit_product.html', product=product)

@app.route('/seller/delete_product/<int:product_id>')
@login_required
@role_required('seller')
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    if product.seller_id != current_user.id:
        flash('У вас нет прав на удаление этого товара', 'error')
        return redirect(url_for('seller_dashboard'))
    
    if product.image_url:
        try:
            os.remove(os.path.join(app.config['UPLOAD_FOLDER'], os.path.basename(product.image_url)))
        except:
            pass
    
    db.session.delete(product)
    db.session.commit()
    flash('Товар удален', 'success')
    return redirect(url_for('seller_dashboard'))

@app.route('/request_product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def request_product(product_id):
    product = Product.query.get_or_404(product_id)
    
    if request.method == 'POST':
        message = request.form['message']
        req = Request(user_id=current_user.id, product_id=product_id, message=message)
        db.session.add(req)
        db.session.commit()
        flash('Запрос отправлен', 'success')
        return redirect(url_for('product_detail', product_id=product_id))
    
    return render_template('request_product.html', product=product)

# Админ панель
@app.route('/admin')
@login_required
@admin_required
def admin_panel():
    # Статистика для админ-панели
    products_count = Product.query.count()
    users_count = User.query.count()
    requests_count = Request.query.count()
    
    pending_products = Product.query.filter_by(is_approved=False).count()
    approved_products = Product.query.filter_by(is_approved=True).count()
    
    admin_count = User.query.filter_by(role='admin').count()
    seller_count = User.query.filter_by(role='seller').count()
    customer_count = User.query.filter_by(role='customer').count()
    
    pending_requests = Request.query.filter_by(status='pending').count()
    approved_requests = Request.query.filter_by(status='approved').count()
    rejected_requests = Request.query.filter_by(status='rejected').count()
    
    latest_product = Product.query.order_by(Product.created_at.desc()).first()
    latest_user = User.query.order_by(User.created_at.desc()).first()
    latest_request = Request.query.order_by(Request.created_at.desc()).first()
    
    return render_template('admin_panel.html',
                         products_count=products_count,
                         users_count=users_count,
                         requests_count=requests_count,
                         pending_products=pending_products,
                         approved_products=approved_products,
                         admin_count=admin_count,
                         seller_count=seller_count,
                         customer_count=customer_count,
                         pending_requests=pending_requests,
                         approved_requests=approved_requests,
                         rejected_requests=rejected_requests,
                         latest_product=latest_product,
                         latest_user=latest_user,
                         latest_request=latest_request)

@app.route('/admin/products')
@login_required
@admin_required
def admin_products():
    products = Product.query.all()
    return render_template('admin_products.html', products=products)

@app.route('/admin/approve_product/<int:product_id>')
@login_required
@admin_required
def approve_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_approved = True
    db.session.commit()
    flash('Товар одобрен', 'success')
    return redirect(url_for('admin_products'))

@app.route('/admin/reject_product/<int:product_id>')
@login_required
@admin_required
def reject_product(product_id):
    product = Product.query.get_or_404(product_id)
    product.is_approved = False
    db.session.commit()
    flash('Товар отклонен', 'warning')
    return redirect(url_for('admin_products'))

@app.route('/admin/requests')
@login_required
@admin_required
def admin_requests():
    requests = Request.query.all()
    return render_template('admin_requests.html', requests=requests)

@app.route('/admin/request/<int:request_id>/<action>')
@login_required
@admin_required
def handle_request(request_id, action):
    req = Request.query.get_or_404(request_id)
    
    if action == 'approve':
        req.status = 'approved'
        flash('Запрос одобрен', 'success')
    elif action == 'reject':
        req.status = 'rejected'
        flash('Запрос отклонен', 'warning')
    else:
        flash('Неизвестное действие', 'error')
        return redirect(url_for('admin_requests'))
    
    db.session.commit()
    return redirect(url_for('admin_requests'))

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin_users.html', users=users)

@app.route('/admin/change_user_role/<int:user_id>', methods=['POST'])
@login_required
@admin_required
def change_user_role(user_id):
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Нельзя изменить свою роль', 'error')
        return redirect(url_for('admin_users'))
    
    new_role = request.form['role']
    user.role = new_role
    db.session.commit()
    flash(f'Роль пользователя {user.username} изменена на {new_role}', 'success')
    return redirect(url_for('admin_users'))

# Создание базы данных и админа по умолчанию
with app.app_context():
    db.create_all()
    
    # Создание админа по умолчанию
    if not User.query.filter_by(username='admin').first():
        admin = User(
            username='admin',
            email='admin@ceiling.com',
            password_hash=generate_password_hash('admin123', method='pbkdf2:sha256'),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()
        print('✅ Администратор создан: admin / admin123')
        print('✅ Продавец: seller / seller123 (создайте через регистрацию)')
        print('✅ Покупатель: customer / customer123 (создайте через регистрацию)')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)