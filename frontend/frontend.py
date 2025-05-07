import requests
from flask import Flask, request, jsonify
from lru_cache import LRUCache
import os
from dotenv import load_dotenv
import argparse

# initialize addresses of catalog and order service
CATALOG_SERVICE_ADDRESS = "http://127.0.0.1:12346"
ORDER_SERVICE_IP = "http://127.0.0.1"
ORDER_SERVICE_ADDRESS = ""

# load order service details from environment
load_dotenv(dotenv_path=os.path.join("config", f"frontend_config.env"))
order_service_map = {
    int(os.getenv(f"ORDER_SERVICE_ID_{i}")): int(os.getenv(f"ORDER_SERVICE_PORT_{i}"))
    for i in (1, 2, 3)
}

# extract cache size from command line argument
parser = argparse.ArgumentParser()
parser.add_argument(
    "--cache-size", "-i",
    type=int,
    default=5
)
args = parser.parse_args()
CACHE_SIZE = args.cache_size

# initialize cache
cache = LRUCache(cache_size=CACHE_SIZE)

# order service leader variables
LEADER_ID = None
LEADER_PORT = None

# select the leader process for order service
def select_leader():
    global LEADER_ID, LEADER_PORT, ORDER_SERVICE_ADDRESS

    for node_id in sorted(order_service_map.keys(), reverse=True):
        port = order_service_map[node_id]
        try:
            response = requests.get(f"{ORDER_SERVICE_IP}:{port}/health")
        except requests.RequestException as e:
            print(f"{ORDER_SERVICE_IP}:{port}/health is unreachable")
            continue
            
        if response.status_code == 200:
            LEADER_ID = node_id
            LEADER_PORT = port
            ORDER_SERVICE_ADDRESS = ORDER_SERVICE_IP + ":" + str(LEADER_PORT)
            print(f"Leader for order service NodeId: {LEADER_ID}, Port: {LEADER_PORT}")
            return
    
    print("Leader selection failed for order service")
    

app = Flask(__name__)

@app.route("/stocks/<string:stock_name>", methods=["GET"])
def get_stock(stock_name):
    # check cache for stock query
    cache_respone = cache.get(stock_name)
    if cache_respone is not None:
        data, status_code = cache_respone["data"], cache_respone["status_code"]
        return jsonify(data), status_code
    
    # send request to catalog service if not in cache
    try:
        response = requests.get(f"{CATALOG_SERVICE_ADDRESS}/stocks/{stock_name}")
    except requests.RequestException as e:
        return jsonify(error={"code": 500, "message": f"Catalog service unreachable {e}"}), 500

    data = response.json() or {}

    # store response in cache
    cache.put(stock_name, {"data": data, "status_code": response.status_code})

    return jsonify(data), response.status_code


@app.route("/orders", methods=["POST"])
def execute_order():
    body = request.get_json() or {}
    try:
        response = requests.post(f"{ORDER_SERVICE_ADDRESS}/orders", json=body)
    except requests.RequestException:
        # select leader again
        select_leader()
        try:
            response = requests.post(f"{ORDER_SERVICE_ADDRESS}/orders", json=body)
        except requests.RequestException as e:
            return jsonify(error={"code": 500, "message": "Order service unreachable {e}"}), 500

    data = response.json() or {}
    return jsonify(data), response.status_code


@app.route("/orders/<int:order_number>", methods=["GET"])
def get_order(order_number):
    try:
        response = requests.get(f"{ORDER_SERVICE_ADDRESS}/orders/{order_number}")
    except requests.RequestException:
        # select leader again
        select_leader()
        try:
            response = requests.get(f"{ORDER_SERVICE_ADDRESS}/orders/{order_number}")
        except requests.RequestException as e:
            return jsonify(error={"code": 500, "message": "Order service unreachable {e}"}), 500
        
    data = response.json() or {}
    return jsonify(data), response.status_code


@app.route("/invalidate/<string:stock_name>", methods=["POST"])
def invalidate_cache(stock_name):
    cache.invalidate(stock_name)
    return jsonify(data={"success": True}), 200


def main():
    select_leader()
    app.run(host="0.0.0.0", port=12345, threaded=True)

if __name__ == "__main__":
    main()