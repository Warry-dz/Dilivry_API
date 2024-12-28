from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import traceback
import base64
from PIL import Image
from io import BytesIO

app = Flask(__name__)
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

@app.route('/test', methods=['GET'])
def test_connection():
    return jsonify({"status": "ok", "message": "Server is running"})

@app.route('/data', methods=['POST'])
def add_data():

    try:   
        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON data received"}), 400
            
        print("Parsed JSON data:", data)
        

        conn = sqlite3.connect('orders.db')
        c = conn.cursor()
        
        c.execute('''
            INSERT INTO orders (name, phone_number, latitude, longitude, total, products)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            data.get('name', 'aucun'),
            data.get('phoneNumber', 'N/A'),
            data.get('latitude'),
            data.get('longitude'),
            data['total'],
            json.dumps(data['products'])
        ))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "status": "success",
            "message": "Order added successfully",
            "data": data
        }), 201
        
    except Exception as e:
        print("Error processing request:", str(e))
        print("Traceback:", traceback.format_exc())
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def init_db():
    print("Initializing database")
    conn = sqlite3.connect('orders.db')
    c = conn.cursor()
    
    # Create products table
    c.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            price REAL NOT NULL,
            new INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
            name VARCHAR(100) DEFAULT 'aucun',
            phone_number VARCHAR(20) DEFAULT 'N/A',
            latitude FLOAT,
            longitude FLOAT,
            total FLOAT NOT NULL,
            products TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            delivered BOOLEAN DEFAULT FALSE
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully")

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

@app.route('/products', methods=['POST', 'GET'])
def manage_products():
    print(f"Received {request.method} request to /products")
    print("Request headers:", dict(request.headers))
    
    if request.method == 'POST':
        try:
            print("Raw request data:", request.get_data())
            name = request.form.get('name')
            price = request.form.get('price')
            is_new = request.form.get('new', '0')
            image = request.files.get('image')
            
            conn = sqlite3.connect('orders.db')
            c = conn.cursor()
            
            # Insert product first
            c.execute('''
                INSERT INTO products (name, price, new)
                VALUES (?, ?, ?)
            ''', (name, price, is_new))
            
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
            
            # Get all products with their images
            c.execute('''
                SELECT p.*, pi.image_data
                FROM products p
                LEFT JOIN product_images pi ON p.id = pi.product_id
                ORDER BY p.created_at DESC
            ''')
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

@app.route('/orders', methods=['POST', 'GET'])
def manage_orders():
    print(f"Received {request.method} request to /orders")
    print("Request headers:", dict(request.headers))
    
    if request.method == 'POST':
        try:
            print("Raw request data:", request.get_data())
            data = request.get_json(force=True)  # force=True to handle any content-type
            print("Parsed order data:", data)

            # التحقق من البيانات المطلوبة
            required_fields = ['name', 'phoneNumber', 'products', 'total']
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
                (name, phone_number, latitude, longitude, total, products)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                data['name'],
                data['phoneNumber'],
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
            
            c.execute('''
                SELECT id, name, phone_number, latitude, longitude, 
                       total, products, created_at, delivered
                FROM orders 
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
