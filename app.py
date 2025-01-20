from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import traceback
import base64
from PIL import Image
from io import BytesIO
import random
import string
from datetime import datetime, timedelta
import sqlite3

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

def generate_random_code(length=2):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


@app.route('/test', methods=['GET'])
def test_connection():
    return jsonify({"status": "ok", "message": "Server is running"})


def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def init_db():
    print("Initializing database")

    conn = sqlite3.connect('orders.db')
    c = conn.cursor()

    c.execute('''
        CREATE TABLE IF NOT EXISTS stores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            address TEXT NOT NULL,
            phone_number INTEGER DEFAULT NULL,
            activity TEXT NOT NULL,
            code TEXT NOT NULL,
            plan TEXT DEFAULT 'free' CHECK (plan IN ('free', 'pro')),
            plan_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    
    c.execute('''
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            phone_number VARCHAR(20),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (store_id) REFERENCES stores (id) ON DELETE CASCADE
        )
    ''')
    # Create products table
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            name VARCHAR(100) NOT NULL,
            description TEXT,
            price FLOAT NOT NULL,
            category VARCHAR(50),
            new INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (store_id) REFERENCES stores (id) ON DELETE CASCADE
        )
    ''')
    
    # Create separate images table
    c.execute('''
        CREATE TABLE IF NOT EXISTS product_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER NOT NULL,
            image_data TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
        )
    ''')
    
    # Create orders table
    c.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            store_id INTEGER NOT NULL,
            client_id INTEGER,
            name VARCHAR(100) DEFAULT 'aucun',
            phone_number VARCHAR(20) DEFAULT 'N/A',
            latitude FLOAT,
            longitude FLOAT,
            total FLOAT NOT NULL,
            products TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (store_id) REFERENCES stores (id) ON DELETE CASCADE,
            FOREIGN KEY (client_id) REFERENCES clients (id) ON DELETE SET NULL
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")


@app.route('/stores', methods=['POST'])
def new_store():
    
    try:
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        data = request.get_json()
        print("Parsed store data:", data)

        required_fields = ['name', 'address', 'phone_number', 'activity']
        for field in required_fields:
            if field not in data:
                error_msg = f"Missing required field: {field}"
                print(error_msg)
                return jsonify({"error": error_msg}), 400
            
        name = data['name']
        address = data['address']
        phone_number = data['phone_number']
        activity = data['activity']

        code = generate_random_code()

        c.execute('''
            INSERT INTO stores (name, address, phone_number, activity, code)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, address, phone_number, activity, code))
        
        conn.commit()
        conn.close()
        return jsonify({"message": "Store added successfully", "code": code}), 201
        
    except Exception as e:
        print(f"Error adding store: {str(e)}")
        return jsonify({"error": str(e)}), 500
    

@app.route('/store/<code>', methods=['GET'])
def get_store_by_code(code):
    try:
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()

        c.execute("SELECT * FROM stores WHERE code = ?", (code,))
        store = c.fetchone()

        conn.close()

        if store:
            column_names = ['id', 'name', 'address', 'phone_number', 'activity', 'code', 'plan', 'plan_updated_at', 'created_at']
            store_data = dict(zip(column_names, store))
            return jsonify({"message": "Store found", "store": store_data}), 200
        
        return jsonify({"message": "Store not found"}), 404

    except Exception as e:
        print(f"Error fetching store: {str(e)}")
        return jsonify({"error": "An error occurred while fetching the store", "details": str(e)}), 500

@app.route('/orders', methods=['GET'])
def get_orders():
    try:
        conn = sqlite3.connect('orders.db')
        conn.row_factory = dict_factory
        c = conn.cursor()
        
        c.execute('''
            SELECT * FROM orders 
            ORDER BY created_at DESC
        ''')
        
        orders = c.fetchall()
        conn.close()
        
        # تحويل المنتجات من JSON string إلى كائن
        for order in orders:
            order['products'] = json.loads(order['products'])
        
        return jsonify(orders)
        
    except Exception as e:
        print("Error fetching orders:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/products/<int:storeId>', methods=['POST', 'GET'])
def manage_products(storeId):

    
    if request.method == 'POST':
        try:
            name = request.form.get('name')
            price = request.form.get('price')
            description = request.form.get('description')
            category = request.form.get('category')
            is_new = request.form.get('new', '0')
            image = request.files.get('image')
            
            conn = sqlite3.connect('orders.db')
            c = conn.cursor()
            
            # Insert product with storeId
            c.execute('''
                INSERT INTO products (name, price, description, category, new, store_id)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (name, price, description, category, is_new, storeId))
            
            product_id = c.lastrowid  # Get the ID of the newly inserted product
            
            # If image was provided, process and save it
            if image:
                image_bytes = image.read()
                compressed_image = compress_image(image_bytes)
                image_data = base64.b64encode(compressed_image).decode('utf-8')
                
                c.execute('''
                    INSERT INTO product_images (product_id, image_data)
                    VALUES (?, ?)
                ''', (product_id, image_data))
            
            conn.commit()
            conn.close()
            return jsonify({"message": "Product added successfully"}), 201
            
        except Exception as e:
            print(f"Error adding product: {str(e)}")
            print(traceback.format_exc())
            return jsonify({"error": str(e)}), 500
    
    elif request.method == 'GET':
        try:
            conn = sqlite3.connect('orders.db')
            conn.row_factory = dict_factory
            c = conn.cursor()
            
            # Get products filtered by storeId
            c.execute('''
                SELECT p.*, pi.image_data
                FROM products p
                LEFT JOIN product_images pi ON p.id = pi.product_id
                WHERE p.store_id = ?
                ORDER BY p.created_at DESC
            ''', (storeId,))
            products = c.fetchall()
            conn.close()
            
            # Process images for each product
            for product in products:
                if 'image_data' in product and product['image_data']:
                    product['image'] = product['image_data']
                del product['image_data']  # Remove raw image data from response
                
            return jsonify(products)
        except Exception as e:
            print(f"Error fetching products: {str(e)}")
            print(traceback.format_exc())
            return jsonify({"error": str(e)}), 500

@app.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    try:
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        
        # Delete product (will cascade delete related images)
        c.execute('DELETE FROM products WHERE id=?', (product_id,))
        
        if c.rowcount > 0:
            conn.commit()
            conn.close()
            return jsonify({'message': 'Product deleted successfully'}), 200
        
        conn.close()
        return jsonify({'error': 'Product not found'}), 404
        
    except Exception as e:
        print(f"Error deleting product: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/orders/<storeId>', methods=['POST', 'GET'])
def manage_orders(storeId):
    print(request.get_data())
    
    if request.method == 'POST':
        try:
            print("Raw request data:", request.get_data())
            data = request.get_json()
            print("Parsed order data:", data)

            # التحقق من البيانات المطلوبة
            required_fields = ['name', 'phoneNumber', 'products', 'store_id', 'client_id', 'total']
            for field in required_fields:
                if field not in data:
                    error_msg = f"Missing required field: {field}"
                    print(error_msg)
                    return jsonify({"error": error_msg}), 400

            # التحقق من صحة المنتجات
            if not isinstance(data['products'], list) or not data['products']:
                error_msg = "Products must be a non-empty list"
                print(error_msg)
                return jsonify({"error": error_msg}), 400

            # معالجة الإحداثيات
            latitude = data.get('latitude', 0)
            longitude = data.get('longitude', 0)
            
            # تحويل المنتجات إلى JSON string
            products_json = json.dumps(data['products'])
            
            conn = sqlite3.connect('orders.db')
            c = conn.cursor()
            
            # إدخال الطلب
            c.execute('''
                INSERT INTO orders 
                (name, phone_number, store_id, client_id, latitude, longitude, total, products)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                data['name'],
                data['phoneNumber'],
                data['store_id'],
                data['client_id'],
                latitude,
                longitude,
                data['total'],
                products_json
            ))
            
            order_id = c.lastrowid
            conn.commit()
            conn.close()
            
            response_data = {
                "message": "Order created successfully",
                "order_id": order_id
            }
            print("Response data:", response_data)
            return jsonify(response_data), 201
            
        except json.JSONDecodeError as e:
            error_msg = f"Invalid JSON format: {str(e)}"
            print(error_msg)
            return jsonify({"error": error_msg}), 400
        except sqlite3.Error as e:
            error_msg = f"Database error: {str(e)}"
            print(error_msg)
            return jsonify({"error": error_msg}), 500
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            print(error_msg)
            print(traceback.format_exc())
            return jsonify({"error": error_msg}), 500
    
    elif request.method == 'GET':
        try:
            conn = sqlite3.connect('orders.db')
            conn.row_factory = dict_factory
            c = conn.cursor()
            
            # استعلام لاسترجاع الطلبات حسب storeId
            c.execute('''
                SELECT id, name, phone_number, latitude, longitude, 
                       total, products, created_at, delivered
                FROM orders 
                WHERE store_id = ?
                ORDER BY created_at DESC
            ''', (storeId,))
            
            orders = c.fetchall()
            conn.close()
            
            # تحويل المنتجات من JSON string إلى كائن
            for order in orders:
                order['products'] = json.loads(order['products'])
            
            return jsonify(orders)
            
        except Exception as e:
            print("Error fetching orders:", str(e))
            return jsonify({"error": str(e)}), 500
        
@app.route('/confirm_delivery/<int:order_id>', methods=['POST'])
def confirm_delivery(order_id):
    print(f"Received POST request to /confirm_delivery/{order_id}")
    try:
        print("Attempting to confirm delivery of order")
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE id=?', (order_id,))
        order = c.fetchone()
        if order:
            c.execute('UPDATE orders SET delivered=? WHERE id=?', (True, order_id))
            conn.commit()
            conn.close()
            print("Successfully confirmed delivery of order")
            return jsonify({'message': 'Order confirmed as delivered'}), 200
        conn.close()
        print("Order not found in database")
        return jsonify({'error': 'Order not found'}), 404
    except Exception as e:
        print(f"Error confirming delivery: {str(e)}")
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/store/plan/<code>', methods=['POST'])
def update_plan(code):
    try:
        data = request.get_json()
        new_plan = data.get('plan')
        
        if new_plan not in ['free', 'pro']:
            return jsonify({"error": "Plan must be either 'free' or 'pro'"}), 400
            
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        
        # تحديث خطة المحل
        c.execute('''
            UPDATE stores 
            SET plan = ?, plan_updated_at = CURRENT_TIMESTAMP 
            WHERE code = ?
        ''', (new_plan, code))
        
        # تحديث الخطط المنتهية (أكثر من 30 يوم)
        c.execute('''
            UPDATE stores 
            SET plan = 'free' 
            WHERE plan = 'pro' 
            AND julianday('now') - julianday(plan_updated_at) >= 30
        ''')
        
        conn.commit()
        conn.close()
        
        return jsonify({"message": "Plan updated successfully"}), 200
        
    except Exception as e:
        print("Error:", str(e))
        return jsonify({"error": str(e)}), 500

@app.route('/register_client', methods=['POST'])
def register_client():
    try:
        data = request.get_json()
        name = data.get('name')
        phone_number = data.get('phone_number')
        store_id = data.get('store_id')
        
        if not all([name, phone_number, store_id]):
            return jsonify({'error': 'Missing required fields'}), 400
        
        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        
        # التحقق من عدم وجود رقم الهاتف مسبقاً لنفس المتجر
        c.execute('SELECT id FROM clients WHERE phone_number = ? AND store_id = ?', (phone_number, store_id))
        existing_client = c.fetchone()
        
        if existing_client:
            return jsonify({'client_id': existing_client[0]}), 200
            
        c.execute('''
            INSERT INTO clients (name, phone_number, store_id)
            VALUES (?, ?, ?)
        ''', (name, phone_number, store_id))
        
        client_id = c.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({'client_id': client_id}), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_statistics():
    try:
        # Connect to the database
        conn = sqlite3.connect('orders.db')
        conn.row_factory = dict_factory
        cur = conn.cursor()

        # Example query to get statistics
        cur.execute('SELECT COUNT(*) as total_orders FROM orders')
        total_orders = cur.fetchone()['total_orders']

        cur.execute('SELECT COUNT(*) as total_stores FROM stores')
        total_stores = cur.fetchone()['total_stores']

        # Additional statistics
        cur.execute('SELECT COUNT(*) as total_clients FROM clients')
        total_clients = cur.fetchone()['total_clients']

        cur.execute('SELECT COUNT(*) as total_products FROM products')
        total_products = cur.fetchone()['total_products']

        # Return the updated statistics as JSON
        return jsonify({
            'total_orders': total_orders,
            'total_stores': total_stores,
            'total_clients': total_clients,
            'total_products': total_products
        })
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({'error': 'An error occurred while fetching statistics'}), 500
    finally:
        conn.close()

@app.route('/api/store_stats/<store_id>', methods=['GET'])
def get_store_statistics(store_id):
    try:
        # Get current date and time
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)

        # Basic statistics
        conn = sqlite3.connect('orders.db')
        conn.row_factory = dict_factory
        cur = conn.cursor()

        cur.execute('SELECT COUNT(*) as total_clients FROM clients WHERE store_id = ?', (store_id,))
        total_clients = cur.fetchone()['total_clients']

        cur.execute('SELECT COUNT(*) as total_orders FROM orders WHERE store_id = ?', (store_id,))
        total_orders = cur.fetchone()['total_orders']

        # Today's statistics
        cur.execute('SELECT COUNT(*) as today_orders FROM orders WHERE store_id = ? AND created_at >= ?', (store_id, today_start))
        today_orders = cur.fetchone()['today_orders']
        cur.execute('SELECT SUM(total) as today_revenue FROM orders WHERE store_id = ? AND created_at >= ?', (store_id, today_start))
        today_revenue = cur.fetchone()['today_revenue'] or 0

        # Weekly statistics
        cur.execute('SELECT COUNT(*) as week_orders FROM orders WHERE store_id = ? AND created_at >= ?', (store_id, week_start))
        week_orders = cur.fetchone()['week_orders']
        cur.execute('SELECT SUM(total) as week_revenue FROM orders WHERE store_id = ? AND created_at >= ?', (store_id, week_start))
        week_revenue = cur.fetchone()['week_revenue'] or 0

        # Monthly statistics
        cur.execute('SELECT COUNT(*) as month_orders FROM orders WHERE store_id = ? AND created_at >= ?', (store_id, month_start))
        month_orders = cur.fetchone()['month_orders']
        cur.execute('SELECT SUM(total) as month_revenue FROM orders WHERE store_id = ? AND created_at >= ?', (store_id, month_start))
        month_revenue = cur.fetchone()['month_revenue'] or 0

        # Order status statistics
        cur.execute('SELECT COUNT(*) as pending_orders FROM orders WHERE store_id = ? AND status = "pending"', (store_id,))
        pending_orders = cur.fetchone()['pending_orders']
        cur.execute('SELECT COUNT(*) as delivered_orders FROM orders WHERE store_id = ? AND delivered = TRUE', (store_id,))
        delivered_orders = cur.fetchone()['delivered_orders']

        # Latest orders
        cur.execute('SELECT id, total, created_at FROM orders WHERE store_id = ? ORDER BY created_at DESC LIMIT 5', (store_id,))
        latest_orders = cur.fetchall()

        latest_orders_data = [{
            'id': order['id'],
            'total': float(order['total']),
            'created_at': order['created_at']
        } for order in latest_orders]

        # Top 3 clients this week
        cur.execute('''
            SELECT 
                c.id,
                c.name,
                c.phone_number,
                COUNT(o.id) as orders_count,
                SUM(o.total) as total_spent
            FROM clients c
            JOIN orders o ON c.id = o.client_id
            WHERE o.store_id = ? 
            AND o.created_at >= ?
            GROUP BY c.id
            ORDER BY total_spent DESC
            LIMIT 3
        ''', (store_id, week_start))
        top_clients = [{
            'id': row['id'],
            'name': row['name'],
            'phone': row['phone_number'],
            'orders_count': row['orders_count'],
            'total_spent': float(row['total_spent'])
        } for row in cur.fetchall()]

        conn.close()

        return jsonify({
            'total_clients': total_clients,
            'total_orders': total_orders,
            'today_orders': today_orders,
            'today_revenue': float(today_revenue),
            'week_orders': week_orders,
            'week_revenue': float(week_revenue),
            'month_orders': month_orders,
            'month_revenue': float(month_revenue),
            'pending_orders': pending_orders,
            'delivered_orders': delivered_orders,
            'latest_orders': latest_orders_data,
            'top_clients': top_clients
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,POST,DELETE,OPTIONS')
    return response

def compress_image(image_data, max_size=(800, 800)):
    img = Image.open(BytesIO(image_data))
    img.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffer = BytesIO()
    img.save(buffer, format="JPEG", quality=85)
    return buffer.getvalue()

init_db()

if __name__ == '__main__':
    print("Starting server")
    app.run(host='0.0.0.0', port=5050, debug=True)
