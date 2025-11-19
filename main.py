import os
import psycopg2
from psycopg2.extras import RealDictCursor, execute_batch
from flask import Flask, render_template, request, jsonify, redirect, url_for
from datetime import datetime

app = Flask(__name__)

# Database URL
DATABASE_URL = "postgresql://business_06dw_user:2dZ8JetZZDC8Vvg2R3RY7g4Gje4bCbAQ@dpg-d4em89mmcj7s73cpc180-a/business_06dw"
FIXED_BASE_AMOUNT = 2704312

# --- Database Helpers ---
def get_db_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print(f"DB Connection Error: {e}")
        return None

def init_db():
    conn = get_db_connection()
    if not conn: return
    cur = conn.cursor()

    # Tables
    cur.execute('''CREATE TABLE IF NOT EXISTS ledger (page_no INTEGER PRIMARY KEY, amount REAL DEFAULT 0)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS categories (id SERIAL PRIMARY KEY, name TEXT UNIQUE)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS sales 
                   (id SERIAL PRIMARY KEY, category_id INTEGER REFERENCES categories(id), 
                    sale_date DATE, description TEXT, rate REAL, quantity REAL, total_amount REAL, 
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS deposits 
                   (id SERIAL PRIMARY KEY, date DATE, amount REAL, note TEXT, 
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Initialize Ledger Pages
    cur.execute('SELECT count(*) FROM ledger')
    if cur.fetchone()[0] == 0:
        data = [(i, 0) for i in range(1, 601)]
        execute_batch(cur, "INSERT INTO ledger (page_no, amount) VALUES (%s, %s)", data)

    conn.commit()
    cur.close()
    conn.close()

# --- Routes ---

@app.route('/')
def dashboard():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute('SELECT SUM(total_amount) as total FROM sales')
    sales = cur.fetchone()['total'] or 0
    cur.execute('SELECT SUM(amount) as total FROM ledger')
    due = cur.fetchone()['total'] or 0
    cur.execute('SELECT SUM(amount) as total FROM deposits')
    deposit = cur.fetchone()['total'] or 0

    cur.execute('''SELECT c.name, SUM(s.quantity) as total_qty, SUM(s.total_amount) as total_money 
                   FROM sales s JOIN categories c ON s.category_id = c.id 
                   GROUP BY c.id, c.name ORDER BY total_money DESC''')
    cat_stats = cur.fetchall()
    cur.close()
    conn.close()

    balance = sales - ((due - FIXED_BASE_AMOUNT) + deposit)

    return render_template('dashboard.html', active_page='dashboard', 
                           sales=sales, due=due, deposit=deposit, balance=balance, cat_stats=cat_stats)

@app.route('/sales')
def sales():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    edit_id = request.args.get('edit_id')
    edit_item = None
    if edit_id:
        cur.execute('SELECT * FROM sales WHERE id = %s', (edit_id,))
        edit_item = cur.fetchone()

    start = request.args.get('start_date')
    end = request.args.get('end_date')
    cat_filter = request.args.get('cat_filter')

    query = 'SELECT s.*, c.name as rice_name FROM sales s JOIN categories c ON s.category_id = c.id WHERE 1=1'
    params = []
    if start: query += ' AND s.sale_date >= %s'; params.append(start)
    if end: query += ' AND s.sale_date <= %s'; params.append(end)
    if cat_filter: query += ' AND s.category_id = %s'; params.append(cat_filter)

    query += ' ORDER BY s.sale_date DESC, s.id DESC'
    cur.execute(query, tuple(params))
    sales_data = cur.fetchall()

    cur.execute('SELECT * FROM categories ORDER BY name ASC')
    categories = cur.fetchall()
    cur.close()
    conn.close()

    return render_template('sales.html', active_page='sales', sales_data=sales_data, 
                           categories=categories, today=datetime.now().strftime('%Y-%m-%d'), edit_item=edit_item)

@app.route('/deposits')
def deposits():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    edit_id = request.args.get('edit_id')
    edit_item = None
    if edit_id:
        cur.execute('SELECT * FROM deposits WHERE id = %s', (edit_id,))
        edit_item = cur.fetchone()

    start = request.args.get('start_date')
    end = request.args.get('end_date')
    query = 'SELECT * FROM deposits WHERE 1=1'
    params = []
    if start: query += ' AND date >= %s'; params.append(start)
    if end: query += ' AND date <= %s'; params.append(end)
    query += ' ORDER BY date DESC, id DESC'
    cur.execute(query, tuple(params))
    deposits_data = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('deposits.html', active_page='deposits', deposits_data=deposits_data, 
                           today=datetime.now().strftime('%Y-%m-%d'), edit_item=edit_item)

@app.route('/ledger')
def ledger():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute('SELECT * FROM ledger ORDER BY page_no ASC')
    pages = cur.fetchall()
    cur.execute('SELECT SUM(amount) as total FROM ledger')
    res = cur.fetchone()
    total = res['total'] if res else 0
    cur.close()
    conn.close()
    return render_template('ledger.html', active_page='ledger', pages=pages, ledger_total=total)

@app.route('/categories')
def categories():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    edit_id = request.args.get('edit_id')
    edit_cat = None
    if edit_id:
        cur.execute('SELECT * FROM categories WHERE id = %s', (edit_id,))
        edit_cat = cur.fetchone()
    cur.execute('SELECT * FROM categories ORDER BY id DESC')
    cats = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('categories.html', active_page='categories', categories=cats, edit_cat=edit_cat)

# --- Action Routes (Form Submit) ---
@app.route('/add_sale', methods=['POST'])
def add_sale():
    f = request.form
    total = float(f.get('rate')) * float(f.get('quantity'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO sales (category_id, sale_date, description, rate, quantity, total_amount) VALUES (%s,%s,%s,%s,%s,%s)',
                 (f.get('category_id'), f.get('sale_date'), f.get('description'), f.get('rate'), f.get('quantity'), total))
    conn.commit(); conn.close()
    return redirect('/sales')

@app.route('/update_sale/<int:id>', methods=['POST'])
def update_sale(id):
    f = request.form
    total = float(f.get('rate')) * float(f.get('quantity'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE sales SET category_id=%s, sale_date=%s, description=%s, rate=%s, quantity=%s, total_amount=%s WHERE id=%s',
                 (f.get('category_id'), f.get('sale_date'), f.get('description'), f.get('rate'), f.get('quantity'), total, id))
    conn.commit(); conn.close()
    return redirect('/sales')

@app.route('/delete_sale/<int:id>')
def delete_sale(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM sales WHERE id = %s', (id,))
    conn.commit(); conn.close()
    return redirect('/sales')

@app.route('/add_deposit', methods=['POST'])
def add_deposit():
    f = request.form
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('INSERT INTO deposits (date, amount, note) VALUES (%s,%s,%s)', (f.get('date'), f.get('amount'), f.get('note')))
    conn.commit(); conn.close()
    return redirect('/deposits')

@app.route('/update_deposit/<int:id>', methods=['POST'])
def update_deposit(id):
    f = request.form
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE deposits SET date=%s, amount=%s, note=%s WHERE id=%s', (f.get('date'), f.get('amount'), f.get('note'), id))
    conn.commit(); conn.close()
    return redirect('/deposits')

@app.route('/delete_deposit/<int:id>')
def delete_deposit(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM deposits WHERE id = %s', (id,))
    conn.commit(); conn.close()
    return redirect('/deposits')

@app.route('/add_category', methods=['POST'])
def add_category():
    name = request.form.get('name')
    if name:
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO categories (name) VALUES (%s)', (name,))
            conn.commit(); conn.close()
        except: pass 
    return redirect('/categories')

@app.route('/update_category/<int:id>', methods=['POST'])
def update_category(id):
    name = request.form.get('name')
    if name:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('UPDATE categories SET name=%s WHERE id=%s', (name, id))
        conn.commit(); conn.close()
    return redirect('/categories')

@app.route('/delete_category/<int:id>')
def delete_category(id):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM categories WHERE id = %s', (id,))
        conn.commit(); conn.close()
    except: pass
    return redirect('/categories')

# --- API ENDPOINTS ---

# 1. Bulk Update Ledger
@app.route('/api/v1/ledger/bulk_update', methods=['POST'])
def bulk_update_ledger():
    try:
        data = request.get_json()
        updates = data.get('updates', [])
        if not updates: return jsonify({'status': 'error', 'message': 'No updates'}), 400
        conn = get_db_connection(); cur = conn.cursor()
        execute_batch(cur, "UPDATE ledger SET amount = %s WHERE page_no = %s", [(item['amount'], item['page_no']) for item in updates])
        conn.commit()
        cur.execute('SELECT SUM(amount) FROM ledger')
        new_total = cur.fetchone()[0] or 0
        cur.close(); conn.close()
        return jsonify({'status': 'success', 'new_total': new_total})
    except Exception as e: return jsonify({'status': 'error', 'message': str(e)}), 500

# 2. Single Ledger Update
@app.route('/api/ledger', methods=['POST'])
def api_ledger():
    d = request.json
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('UPDATE ledger SET amount=%s WHERE page_no=%s', (d['a'], d['p']))
    conn.commit(); cur.close()
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute('SELECT SUM(amount) FROM ledger')
    new_t = cur.fetchone()[0] or 0
    conn.close()
    return jsonify({'t': new_t})

# 3. Bulk Add Sales (Previous One)
@app.route('/api/v1/sales/bulk_add', methods=['POST'])
def bulk_add_sales():
    try:
        data = request.get_json()
        items = data.get('items', [])
        sale_date = data.get('sale_date', datetime.now().strftime('%Y-%m-%d'))
        if not items: return jsonify({'status': 'error', 'message': 'No items provided'}), 400
        sales_records = []
        for item in items:
            cat_id = item.get('category_id')
            rate = float(item.get('rate', 0))
            qty = float(item.get('quantity', 0))
            desc = item.get('description', '')
            total = rate * qty
            if cat_id and rate > 0 and qty > 0:
                sales_records.append((cat_id, sale_date, desc, rate, qty, total))
        if not sales_records: return jsonify({'status': 'error', 'message': 'Invalid data'}), 400
        conn = get_db_connection(); cur = conn.cursor()
        execute_batch(cur, "INSERT INTO sales (category_id, sale_date, description, rate, quantity, total_amount) VALUES (%s, %s, %s, %s, %s, %s)", sales_records)
        conn.commit(); cur.close(); conn.close()
        return jsonify({'status': 'success', 'message': f'{len(sales_records)} added'})
    except Exception as e: return jsonify({'status': 'error', 'message': str(e)}), 500

# 4. NEW: Quick Add Single Sale
@app.route('/api/v1/sales/quick_add', methods=['POST'])
def quick_add_sale():
    """
    একটি আইটেম দ্রুত যুক্ত করার API।
    Input: { "date": "2025-11-05", "category_id": 1, "quantity": 1, "rate": 2000, "description": "..." }
    """
    try:
        data = request.get_json()

        # ডাটা এক্সট্র্যাক্ট করা
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        cat_id = data.get('category_id')
        qty = float(data.get('quantity', 0))
        rate = float(data.get('rate', 0))
        desc = data.get('description', '')

        # ভ্যালিডেশন
        if not cat_id or qty <= 0 or rate <= 0:
            return jsonify({'status': 'error', 'message': 'Invalid data provided'}), 400

        total = rate * qty

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('''
            INSERT INTO sales (category_id, sale_date, description, rate, quantity, total_amount) 
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        ''', (cat_id, date, desc, rate, qty, total))

        new_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            'status': 'success', 
            'message': 'Sale added successfully', 
            'id': new_id,
            'total_amount': total
        })

    except Exception as e:
        print(f"Quick Add Error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8080, debug=True)


