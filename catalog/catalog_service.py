import csv
import threading
from flask import Flask, request, jsonify
import requests

FRONTEND_SERVICE_ADDRESS = "http://127.0.0.1:12345"

catalog_filename = "data/catalog.csv"
lock = threading.RLock()
catalog_data = {}


def load_catalog_data():
    global catalog_data
    with lock:
        catalog_data.clear()
        try:
            with open(catalog_filename, mode='r', newline='') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    catalog_data[row["name"]] = {
                        "name": row["name"],
                        "price": float(row["price"]),
                        "quantity": int(row["quantity"])
                    }
        except FileNotFoundError:
            print(f"{catalog_filename} not found. Starting with an empty catalog.")


def save_catalog_data():
    with lock:
        with open(catalog_filename, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(["name", "price", "quantity"])
            for item in catalog_data.values():
                writer.writerow([item["name"], item["price"], item["quantity"]])


app = Flask(__name__)


@app.route("/stocks/<string:stock_name>", methods=["GET"])
def get_stock(stock_name):
    with lock:
        item = catalog_data.get(stock_name)
        if not item:
            return jsonify(error={"code": 404, "message": "Stock not found"}), 404
        return jsonify(data=item), 200
    

@app.route("/update", methods=["POST"])
def update_stock():
    body = request.get_json() or {}
    stock_name = body.get("name")
    quantity_change = body.get("change")

    if not all([stock_name, quantity_change]):
        return jsonify(error={"code": 400, "message": "Missing required fields"}), 400

    with lock:
        item = catalog_data.get(stock_name)
        if not item:
            return jsonify(error={"code": 404, "message": "Stock not found"}), 404
        
        if item["quantity"] + quantity_change >= 0:
            # send invalidation request to frontend
            try:
                requests.post(f"{FRONTEND_SERVICE_ADDRESS}/invalidate/{stock_name}")
            except requests.RequestException as e:
                return jsonify(error={"code": 500, "message": "Invalidation request failed"}), 500

            item["quantity"] += quantity_change
            save_catalog_data()
            return jsonify(data={"code": 200, "message": "Stock update successful"}), 200
        
        return jsonify(error={"code": 400, "message": "Insufficient stock quantity"}), 400


def main():
    load_catalog_data()
    print("Catalog service up!")
    app.run(host="0.0.0.0", port=12346, threaded=True)


if __name__ == "__main__":
    main()
