import csv
import threading
import requests
from flask import Flask, request, jsonify
import argparse
import os
from dotenv import load_dotenv
import time

# extract replica number from CLI argument
parser = argparse.ArgumentParser()
parser.add_argument(
    "--replica", "-i",
    type=int,
    required=True
)
args = parser.parse_args()
REPLICA = args.replica

# set configuration for replica from environment
load_dotenv(dotenv_path=os.path.join("config", f"order_config_{REPLICA}.env"))
NODE_ID = int(os.getenv("NODE_ID"))
PORT = int(os.getenv("PORT"))

CATALOG_SERVICE_ADDRESS = "http://127.0.0.1:12346"
ORDER_SERVICE_IP = "http://127.0.0.1"
ORDER_SERVICE_PORTS = {12347, 12348, 12349}
orders_filename = f"data/order_history_{NODE_ID}.csv"
lock = threading.Lock()
transaction_id = 0


def add_to_order_transaction_history(transaction_id, stock_name, order_type, quantity):
    with lock:
        with open(orders_filename, mode="a", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([transaction_id, stock_name, order_type, quantity])


def get_order_from_transaction_history(transaction_id):
    with lock:
        with open(orders_filename, mode="r", newline="") as file:
            reader = csv.reader(file)
            for row in reader:
                id, name, order_type, quantity = row
                if int(id) == transaction_id:
                    return {"number": int(id), "name": name, "type": order_type, "quantity": int(quantity)}
    return None


def get_orders_from_transaction_history_since(transaction_id):
    order_logs = []
    with lock:
        with open(orders_filename, mode="r", newline="") as file:
            reader = csv.reader(file)
            for row in reader:
                try:
                    id, name, order_type, quantity = row
                    if int(id) > transaction_id:
                        order_logs.append({"number": int(id), "name": name, "type": order_type, "quantity": int(quantity)})
                except:
                    pass
    return order_logs


def get_last_transaction_id_from_transaction_history():
    last_id = 0
    with lock:
        with open(orders_filename, mode="r", newline="") as file:
            reader = csv.reader(file)
            for row in reader:
                try:
                    id = int(row[0])
                    last_id = id
                except:
                    pass
    return last_id


def sync_with_replicas():
    global transaction_id

    last_transaction_id = get_last_transaction_id_from_transaction_history()
    sync_status = None

    for port in ORDER_SERVICE_PORTS:
        if port == PORT:
            continue

        try:
            response = requests.get(f"{ORDER_SERVICE_IP}:{port}/orders/logs/{last_transaction_id}")
            response.raise_for_status()
            sync_status = True
            data = response.json() or {}
            for order in data.get("data", []):
                add_to_order_transaction_history(int(order["number"]), order["name"], order["type"], int(order["quantity"]))
                last_transaction_id = int(order["number"])

            with lock:
                transaction_id = last_transaction_id              

        except requests.RequestException as e:
            print(f"Could not sync with {ORDER_SERVICE_IP}:{port}, {e}")
            if sync_status is None:
                sync_status = False
            continue

    return sync_status


def sync_in_background():
    retry_time = 3
    while True:
        sync_status = sync_with_replicas()
        if sync_status:
            print("Sync successful")
            break
        else:
            print(f"Sync failed, retrying in {retry_time} seconds")
            time.sleep(retry_time)


app = Flask(__name__)


@app.route("/health", methods=["GET"])
def health():
    return jsonify(node_id=NODE_ID), 200


@app.route("/orders", methods=["POST"])
def execute_order():
    global transaction_id

    body = request.get_json() or {}
    stock_name = body.get("name")
    quantity = int(body.get("quantity"))
    order_type = body.get("type")

    signed_quantity = quantity

    if not all([stock_name, quantity, order_type]):
        return jsonify(error={"code": 400, "message": "Missing required fields"}), 400
    
    if order_type == "buy":
        signed_quantity = -signed_quantity
    elif order_type == "sell":
        pass
    else:
        return jsonify(error={"code": 400, "message": "Invalid trade operation"}), 400
    
    try:
        response = requests.post(
            f"{CATALOG_SERVICE_ADDRESS}/update",
            json={"name": stock_name, "change": signed_quantity}
        )
    except requests.RequestException as e:
        return jsonify(error={"code": 500, "message": f"Catalog service error: {e}"}), 500
    
    data = response.json() or {}
    if response.status_code == 200:
        current_id = 0
        with lock:
            transaction_id += 1
            current_id = transaction_id
        add_to_order_transaction_history(current_id, stock_name, order_type, quantity)

        # propagate the change to other replicas
        for port in ORDER_SERVICE_PORTS:
            if port == PORT:
                continue

            payload = {"transaction_number": current_id, "name": stock_name, "type": order_type, "quantity": quantity}

            try:
                requests.post(f"{ORDER_SERVICE_IP}:{port}/replicate", json=payload)
            except requests.RequestException as e:
                print(f"Failed to replicate order {current_id} in {ORDER_SERVICE_IP}:{port}")
                continue

        return jsonify(data={"transaction_number": current_id}), 200
    
    else:
        return jsonify(error={"code": data["error"]["code"], "message": data["error"]["message"]})
    

@app.route("/replicate", methods=["POST"])
def propagate_to_replica():
    global transaction_id

    body = request.get_json() or {}
    id = body.get("transaction_number")
    stock_name = body.get("name")
    order_type = body.get("type")
    quantity = body.get("quantity")

    with lock:
        transaction_id = id

    if not all([id, stock_name, order_type, quantity]):
        return jsonify(error={"code": 400, "message": "Invalid replication payload"}), 400
    
    add_to_order_transaction_history(id, stock_name, order_type, quantity)

    return jsonify(data={"success": True}), 200


@app.route("/orders/<int:order_number>", methods=["GET"])
def get_order(order_number):
    response = get_order_from_transaction_history(order_number)
    if response is None:
        return jsonify(error={"code": 400, "message": "Order number invalid"}), 400
    return jsonify(response), 200


@app.route("/orders/logs/<int:last_sync_order_number>")
def get_logs(last_sync_order_number):
    order_logs = get_orders_from_transaction_history_since(last_sync_order_number)
    return jsonify(data=order_logs), 200


def main():
    t = threading.Thread(target=sync_in_background, daemon=True)
    t.start()
    app.run(host="0.0.0.0", port=PORT, threaded=True)

if __name__ == "__main__":
    main()