from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this to a random secret key
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Database connection
def get_db():
    conn = sqlite3.connect('database.db')
    conn.row_factory = sqlite3.Row
    return conn

# Initialize database
def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT DEFAULT 'customer'
    )''')
    
    # Products table
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        price REAL NOT NULL,
        quantity INTEGER NOT NULL,
        image TEXT,
        category TEXT NOT NULL
    )''')
    
    # Cart table
    c.execute('''CREATE TABLE IF NOT EXISTS cart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (product_id) REFERENCES products (id)
    )''')
    
    # Orders table
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        total REAL NOT NULL,
        status TEXT DEFAULT 'Pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    # Order items table
    c.execute('''CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        price REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES orders (id),
        FOREIGN KEY (product_id) REFERENCES products (id)
    )''')
    
    # Payments table
    c.execute('''CREATE TABLE IF NOT EXISTS payments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        screenshot_path TEXT,
        status TEXT DEFAULT 'Pending',
        FOREIGN KEY (order_id) REFERENCES orders (id)
    )''')
    
    # Insert default admin user
    c.execute("INSERT OR IGNORE INTO users (email, password, role) VALUES (?, ?, ?)", ('admin@kirana.com', generate_password_hash('admin123'), 'admin'))
    
    # Insert sample products
    c.execute("INSERT OR IGNORE INTO products (name, price, quantity, category) VALUES (?, ?, ?, ?)", ('Apple', 50.0, 100, 'Fruits'))
    c.execute("INSERT OR IGNORE INTO products (name, price, quantity, category) VALUES (?, ?, ?, ?)", ('Banana', 30.0, 150, 'Fruits'))
    c.execute("INSERT OR IGNORE INTO products (name, price, quantity, category) VALUES (?, ?, ?, ?)", ('Tomato', 40.0, 80, 'Vegetables'))
    c.execute("INSERT OR IGNORE INTO products (name, price, quantity, category) VALUES (?, ?, ?, ?)", ('Milk', 60.0, 50, 'Dairy'))
    
    conn.commit()
    conn.close()

# Routes
@app.route('/')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    conn.close()
    return render_template('home.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        hashed_password = generate_password_hash(password)
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (email, password) VALUES (?, ?)", (email, hashed_password))
            conn.commit()
            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already exists.')
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE email = ?", (email,))
        user = c.fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['role'] = user['role']
            return redirect(url_for('home'))
        flash('Invalid email or password.')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT cart.id, products.name, products.price, cart.quantity, (products.price * cart.quantity) as total
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id = ?
    """, (session['user_id'],))
    cart_items = c.fetchall()
    total = sum(item['total'] for item in cart_items)
    conn.close()
    return render_template('cart.html', cart_items=cart_items, total=total)

@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    quantity = int(request.form['quantity'])
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM cart WHERE user_id = ? AND product_id = ?", (session['user_id'], product_id))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE cart SET quantity = quantity + ? WHERE id = ?", (quantity, existing['id']))
    else:
        c.execute("INSERT INTO cart (user_id, product_id, quantity) VALUES (?, ?, ?)", (session['user_id'], product_id, quantity))
    conn.commit()
    conn.close()
    flash('Item added to cart.')
    return redirect(url_for('home'))

@app.route('/remove_from_cart/<int:cart_id>')
def remove_from_cart(cart_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM cart WHERE id = ? AND user_id = ?", (cart_id, session['user_id']))
    conn.commit()
    conn.close()
    flash('Item removed from cart.')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT cart.id, products.name, products.price, cart.quantity, (products.price * cart.quantity) as total
        FROM cart
        JOIN products ON cart.product_id = products.id
        WHERE cart.user_id = ?
    """, (session['user_id'],))
    cart_items = c.fetchall()
    total = sum(item['total'] for item in cart_items)
    if request.method == 'POST':
        # Create order
        c.execute("INSERT INTO orders (user_id, total) VALUES (?, ?)", (session['user_id'], total))
        order_id = c.lastrowid
        # Add order items
        for item in cart_items:
            c.execute("INSERT INTO order_items (order_id, product_id, quantity, price) VALUES (?, ?, ?, ?)",
                      (order_id, item['id'], item['quantity'], item['price']))
        # Clear cart
        c.execute("DELETE FROM cart WHERE user_id = ?", (session['user_id'],))
        conn.commit()
        conn.close()
        return redirect(url_for('payment', order_id=order_id))
    conn.close()
    return render_template('checkout.html', cart_items=cart_items, total=total)

@app.route('/payment/<int:order_id>', methods=['GET', 'POST'])
def payment(order_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, session['user_id']))
    order = c.fetchone()
    if not order:
        conn.close()
        return redirect(url_for('home'))
    if request.method == 'POST':
        file = request.files['screenshot']
        if file:
            filename = secure_filename(file.filename)
            unique_filename = str(uuid.uuid4()) + '_' + filename
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_filename))
            c.execute("INSERT INTO payments (order_id, screenshot_path) VALUES (?, ?)", (order_id, unique_filename))
            conn.commit()
            flash('Payment proof uploaded. Waiting for verification.')
        conn.close()
        return redirect(url_for('orders'))
    conn.close()
    return render_template('payment.html', order=order)

@app.route('/orders')
def orders():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("""
        SELECT orders.id, orders.total, orders.status, orders.created_at
        FROM orders
        WHERE orders.user_id = ?
        ORDER BY orders.created_at DESC
    """, (session['user_id'],))
    user_orders = c.fetchall()
    conn.close()
    return render_template('orders.html', orders=user_orders)

@app.route('/admin')
def admin():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM orders ORDER BY created_at DESC")
    all_orders = c.fetchall()
    c.execute("SELECT * FROM products")
    products = c.fetchall()
    conn.close()
    return render_template('admin.html', orders=all_orders, products=products)

@app.route('/admin/add_product', methods=['GET', 'POST'])
def add_product():
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        category = request.form['category']
        image = request.form.get('image', '')
        conn = get_db()
        c = conn.cursor()
        c.execute("INSERT INTO products (name, price, quantity, image, category) VALUES (?, ?, ?, ?, ?)",
                  (name, price, quantity, image, category))
        conn.commit()
        conn.close()
        flash('Product added.')
        return redirect(url_for('admin'))
    return render_template('add_product.html')

@app.route('/admin/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        category = request.form['category']
        image = request.form.get('image', '')
        c.execute("UPDATE products SET name=?, price=?, quantity=?, image=?, category=? WHERE id=?",
                  (name, price, quantity, image, category, product_id))
        conn.commit()
        flash('Product updated.')
        conn.close()
        return redirect(url_for('admin'))
    c.execute("SELECT * FROM products WHERE id=?", (product_id,))
    product = c.fetchone()
    conn.close()
    return render_template('edit_product.html', product=product)

@app.route('/admin/delete_product/<int:product_id>')
def delete_product(product_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    conn.close()
    flash('Product deleted.')
    return redirect(url_for('admin'))

@app.route('/admin/view_payment/<int:order_id>')
def view_payment(order_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM payments WHERE order_id=?", (order_id,))
    payment = c.fetchone()
    conn.close()
    return render_template('view_payment.html', payment=payment, order_id=order_id)

@app.route('/admin/verify_payment/<int:order_id>', methods=['POST'])
def verify_payment(order_id):
    if 'user_id' not in session or session.get('role') != 'admin':
        return redirect(url_for('login'))
    action = request.form['action']
    status = 'Confirmed' if action == 'accept' else 'Rejected'
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    c.execute("UPDATE payments SET status=? WHERE order_id=?", (status, order_id))
    conn.commit()
    conn.close()
    flash(f'Payment {status.lower()}.')
    return redirect(url_for('admin'))

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    init_db()
    app.run(debug=True)