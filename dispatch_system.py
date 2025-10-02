import requests
import os
import logging
import sqlite3
from flask import Flask, request, jsonify, Response
from datetime import datetime
import csv
from io import StringIO
from dotenv import load_dotenv

# Load .env file
load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize database
def init_db():
    conn = sqlite3.connect("orders.db")
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT UNIQUE,
            customer_name TEXT,
            pickup_address TEXT,
            delivery_address TEXT,
            amount REAL,
            status TEXT,
            platform TEXT,
            team_id TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revenue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            total_amount REAL,
            owner_share REAL,
            team_share REAL,
            system_share REAL,
            date DATE,
            FOREIGN KEY (order_id) REFERENCES orders (order_id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS payouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id TEXT,
            recipient_type TEXT,      -- owner / team / system
            recipient_account TEXT,   -- Bank account
            amount REAL,
            status TEXT DEFAULT 'pending', -- pending / processed
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

init_db()

def send_telegram_notification(message: str):
    """Send Telegram notification"""
    try:
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')

        if not bot_token or not chat_id:
            logger.error("Telegram credentials not configured")
            return False

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {str(e)}")
        return False

def calculate_revenue_split(amount, owner_ratio=0.70, team_ratio=0.20, system_ratio=0.10):
    """Calculate revenue split"""
    return {
        "owner": amount * owner_ratio,
        "team": amount * team_ratio,
        "system": amount * system_ratio,
        "total": amount
    }

def save_order(order_data):
    """Save order data"""
    try:
        conn = sqlite3.connect("orders.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR REPLACE INTO orders
            (order_id, customer_name, pickup_address, delivery_address,
             amount, status, platform, team_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            order_data.get('order_id'),
            order_data.get('customer_name'),
            order_data.get('pickup_address'),
            order_data.get('delivery_address'),
            order_data.get('amount'),
            order_data.get('status'),
            order_data.get('platform'),
            order_data.get('team_id')
        ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        return False

def save_revenue(order_id, revenue_split):
    """Save revenue split"""
    try:
        conn = sqlite3.connect("orders.db")
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO revenue
            (order_id, total_amount, owner_share, team_share, system_share, date)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            order_id,
            revenue_split['total'],
            revenue_split['owner'],
            revenue_split['team'],
            revenue_split['system'],
            datetime.now().date()
        ))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Revenue save error: {str(e)}")
        return False

def save_payouts(order_id, revenue_split):
    """Write split amounts to payouts, reading accounts from environment variables"""
    try:
        conn = sqlite3.connect("orders.db")
        cursor = conn.cursor()

        # Read accounts from .env
        owner_account = os.getenv("BANK_CTBC_ACCOUNT")
        team_account = os.getenv("BANK_POST_ACCOUNT")
        system_account = "SYSTEM_ACCOUNT_PLACEHOLDER" # Placeholder

        payouts_data = [
            (order_id, "owner", owner_account, revenue_split["owner"]),
            (order_id, "team", team_account, revenue_split["team"]),
            (order_id, "system", system_account, revenue_split["system"]),
        ]

        cursor.executemany("""
            INSERT INTO payouts (order_id, recipient_type, recipient_account, amount)
            VALUES (?, ?, ?, ?)
        """, payouts_data)

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Payout save error: {str(e)}")
        return False

@app.route('/webhook', methods=['POST'])
def webhook_handler():
    """Handle Webhook requests"""
    try:
        data = request.get_json()

        required_fields = ['order_id', 'customer_name', 'amount', 'team_id']
        if not all(field in data for field in required_fields):
            return jsonify({"error": "Missing required fields"}), 400

        order_data = {
            'order_id': data['order_id'],
            'customer_name': data['customer_name'],
            'pickup_address': data.get('pickup_address', ''),
            'delivery_address': data.get('delivery_address', ''),
            'amount': float(data['amount']),
            'status': data.get('status', 'received'),
            'platform': data.get('platform', 'unknown'),
            'team_id': data['team_id']
        }

        if save_order(order_data):
            revenue_split = calculate_revenue_split(order_data['amount'])
            save_revenue(order_data['order_id'], revenue_split)
            save_payouts(order_data['order_id'], revenue_split)

            message = f"""
📦 New Order #{order_data['order_id']}
👤 Customer: {order_data['customer_name']}
💰 Amount: ${order_data['amount']:.2f}
🏢 Team: {order_data['team_id']}
📍 Platform: {order_data['platform']}

💵 Revenue Split:
• Commander: ${revenue_split['owner']:.2f} (70%)
• Team: ${revenue_split['team']:.2f} (20%)
• System: ${revenue_split['system']:.2f} (10%)
            """

            send_telegram_notification(message)

            return jsonify({
                "status": "success",
                "order_id": order_data['order_id'],
                "revenue_split": revenue_split
            })
        else:
            return jsonify({"error": "Failed to save order"}), 500

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/list_payouts', methods=['GET'])
def list_payouts():
    """List all pending payout records"""
    try:
        conn = sqlite3.connect("orders.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, order_id, recipient_type, recipient_account, amount, status, created_at
            FROM payouts WHERE status = 'pending'
        """)
        rows = cursor.fetchall()
        conn.close()

        payouts_list = [
            {
                "id": row[0],
                "order_id": row[1],
                "recipient_type": row[2],
                "recipient_account": row[3],
                "amount": row[4],
                "status": row[5],
                "created_at": row[6]
            }
            for row in rows
        ]

        return jsonify(payouts_list)
    except Exception as e:
        logger.error(f"List payouts error: {str(e)}")
        return jsonify({"error": "Failed to fetch payouts"}), 500

@app.route('/generate_payout_file', methods=['GET'])
def generate_payout_file():
    """Generate a batch file for pending payouts (CSV)"""
    try:
        conn = sqlite3.connect("orders.db")
        cursor = conn.cursor()
        cursor.execute("""
            SELECT order_id, recipient_type, recipient_account, amount
            FROM payouts WHERE status = 'pending'
        """)
        rows = cursor.fetchall()
        conn.close()

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["OrderID", "RecipientType", "RecipientAccount", "Amount"])
        for row in rows:
            writer.writerow(row)
        output.seek(0)

        return Response(
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=payouts.csv"}
        )
    except Exception as e:
        logger.error(f"Payout file error: {str(e)}")
        return jsonify({"error": "Failed to generate payout file"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)