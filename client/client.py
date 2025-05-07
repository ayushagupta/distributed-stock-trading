import requests
import random
import time

lookup_time = 0
lookup_count = 0
trade_time = 0
trade_count = 0

class HTTPClient:
    def __init__(self, server_url, p):
        self.server_url = server_url
        self.p = p # probability of making a trade
        self.session = requests.Session()

    # send random requests of lookup and trade to the server with a probability p
    def execute_session(self, stock_name_list, N):
        try:
            for i in range(N):
                stock_name = random.choice(stock_name_list)
                lookup_response = self.lookup(stock_name)
                
                if lookup_response is None:
                    continue

                if "error" in lookup_response:
                    continue

                # no need to trade if no quantity available
                if "data" in lookup_response and lookup_response["data"]["quantity"] <= 0:
                    continue
                
                # execute trade if random number is less than 'p'
                if random.random() < self.p:
                    order_type = random.choice(["buy", "sell"])
                    quantity = random.randint(1, lookup_response["data"]["quantity"]//2)
                    self.trade(stock_name, order_type, quantity)

                time.sleep(0.5)

        finally:
            self.session.close()

    
    # function to call the lookup API in front-end
    def lookup(self, stock_name):
        global lookup_time
        global lookup_count
        url = f"{self.server_url}/stocks/{stock_name}"
        start_time = time.time()
        response = self.session.get(url)
        end_time = time.time()
        lookup_time += (end_time-start_time)
        lookup_count += 1
        data = response.json()
        print(f"Lookup response: {data}, Time taken: {end_time - start_time}")
        return data
    

    # function to call the order API in front-end
    def trade(self, stock_name, order_type, quantity):
        global trade_time
        global trade_count
        url = f"{self.server_url}/orders"
        order = {
            "name": stock_name,
            "quantity": quantity,
            "type": order_type
        }
        print(f"Trade request: {order}")
        start_time = time.time()
        response = self.session.post(url=url, json=order)
        end_time = time.time()
        trade_time += (end_time - start_time)
        trade_count += 1
        data = response.json()
        print(f"Trade response: {data}, Time taken: {end_time - start_time}")


def main():
    server_url = "http://127.0.0.1:12345"
    stock_name_list = ["GameStart", "RottenFishCo", "BoarCo", "MenhirCo", "IsenbergCo", "CICSorg"]
    client = HTTPClient(server_url=server_url, p=0.5)
    client.execute_session(stock_name_list=stock_name_list, N=10)
    print(f"Lookup time: {lookup_time}, Lookup count: {lookup_count}, Lookup latency = {lookup_time/lookup_count}")
    print(f"Trade time: {trade_time}, Trade count: {trade_count}, Trade latency: {trade_time / trade_count if trade_count != 0 else 0}")


if __name__ == "__main__":
    main()