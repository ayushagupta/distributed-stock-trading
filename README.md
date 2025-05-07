# Distributed Stock Trading Platform

## Overview

This project is a distributed stock trading platform built with Flask, featuring a replicated order service with CSV-based persistence and leader-based request handling. It supports fault-tolerant startup with background synchronization, log replication across replicas, and crash recovery using incremental sync. A front-end proxy routes trade requests to the current leader and includes a thread-safe LRU cache with server-push invalidation to optimize stock lookups. The system ensures high availability, consistency, and low-latency performance in a multi-replica setup.

## Components

### 1. Frontend Service

The frontend service allows the client to lookup stocks, perform orders and query existing orders.

#### Implementation

The service is started with an LRU cache of the size specified via command line arguemnts. Then, it selects the leader node among all replicas of the order service. The leader selection is done by calling the `health` API of each order service replica in decreasing order of node ID until a live node is found. The node ID and port information about the replicas are stored in an environment file. If the leader node fails and a request has to be made with the order service, then the leader selection process is repeated to find a new leader.


#### API Details

1. `GET /stocks/<stock_name>`

    This API is used to query stock details from the catalog service. It first checks the in-memory cache to see if the response for the stock is present in it. If the stock is found in the cache, the cached response is returned. Otherwise, it makes a GET request to the catalog service and returns the response. The following is an example response in case the stock is found in the catalog.
    ```json
    {
        "data": {
            "name": "GameStart",
            "price": 15.99,
            "quantity": 100
        }
    }
    ```
    If the stock is not found in the catalog, an error response is returned.
    ```json
    {
        "error": {
            "code": 404,
            "message": "Stock not found"
        }
    }
    ```

2. `POST /orders`

    This API is used to place trade orders, including both, buy and sell. It makes a POST request to the order service and returns the reponse. The following is an example request that can be used to place a sell order.
    ```json
    {
        "name": "GameStart",
        "quantity": 1,
        "type": "sell"
    }
    ```
    In case the transaction is a success, the follwing response will be returned.
    ```json
    {
        "data": {
            "transaction_number": 10
        }
    }
    ```
    In case of any error including insufficient stocks and internal service failure, an appropriate error response is returned like the following.
    ```json
    {
        "error": {
            "code": 500,
            "message": "Insufficient stock quantity"
        }
    }
    ```

3. `GET /orders/<order_number>`

    This API is used to get the details of an order based on the order number. It makes a GET request to the order service and returns the response. The following is an example request if the order number exists in the database.
    ```json
    {
        "data": {
            "number": 1,
            "name": "Google",
            "type": "sell",
            "quantity": 10
        }
    }
    ```
    If the order number is not found in the database, the following response will be returned.
    ```json
    {
        "error": {
            "code": 400,
            "message": "Order number invalid"
        }
    }
    ```

4. `POST /invalidate/<stock_name>`

    This API is used to evict a stale record with the given stock name from the in-memory cache. A sample response looks like the following.
    ```json
    {
        "data": {
            "success": true
        }
    }
    ```


### 2. Catalog Service

The catalog service provides the functionality to lookup the details of a stock and to make updates to a stock's quantity. This service is used by both the front-end and order service.

#### Implementation

The GET call is used for lookup requests which interacts with the `data/catalog.csv` file to get the details of each stock. A `catalog_data` variable is used to maintain the list of stocks from the data file. The variable is loaded with data from the file when the service is started. Writing to `catalog_data` and reading from it is protected by a lock.

The POST call is used to update the quantity of a stock in the data file. Before performing the update, a check is performed to ensure that the final quantity of the stock should be a non-negative number. This is used to flag invalid buy orders. If the update is valid, then the `catalog_data` variable is updated and its contents are written to the data file. Both of these operations are protected by a lock. The lock used in this case is `RLock` instead of `Lock` due to the way the file is updated. A normal lock variable will cause a deadlock scenario.

If a stock volume is successfully updated, the `invalidate` API of the frontend service is called to evict the stock's response from the cache, if present.


#### API Details

1. `GET /stocks/<stock_name>`
    
    This API is used to get the details of a stock based on the stock name. In case the stock is found in the database, the following success response is returned.
    ```json
    {
        "data": {
            "name": "GameStart",
            "price": 15.99,
            "quantity": 100
        }
    }
    ```
    In case the stock is not found in the database, an error reponse with appropriate message is returned.
    ```json
    {
        "error": {
            "code": 404,
            "message": "Stock not found"
        }
    }
    ```


2. `POST /update`

    This API is used to increase or decrease the quantity of a stock in the database. A sample request contains the name of the stock and the change in quantity. A negative value of change is allowed, representing a buy order.
    ```json
    {
        "name": "GameStart",
        "change": 10
    }
    ```
    If the change is negative and there are not enough stocks according to the database, then an error response is returned.
    ```json
    {
        "error": {
            "code": 500,
            "message": "Insufficient stock quantity"
        }
    }
    ```
    In case the stock is not present in the database, an appropriate error response is provided.
    ```json
    {
        "error": {
            "code": 404,
            "message": "Stock not found"
        }
    }
    ```
    If all fields are not present in the request body, the following error response is returned.
    ```json
    {
        "error": {
            "code": 400,
            "message": "Missing required fields"
        }
    }
    ```

### 3. Order Service

The order service is assigned with the functionality to handle all trade orders that are requested by the front-end.

#### Implementation

The order service is replicated thrice and the information regarding node IDs and port numbers are stored in environment files. It exposes a health check API which is used for leader selection process. When the service is started, it initiates sync process in background which tries to sync data with other replicas and this process continues until the sync is completed. The sync process first finds the last order in its own database and then gets logs from other replicas carried out after this last order. The database is then updated with any new orders. 

The trade is carried out by forwarding the request to catalog service to check if the order is possible or not. If the order is successful, the leader propagates the information to other replicas to maintain consistent database. 


#### API Details

1. `GET /health `

    This API returns the node ID of the running replica. Below is a sample response.
    ```json
    {
        "node_id": 1
    }
    ```

2. `POST /orders`

    This API is used to perform a trade order and requires the details of the order. A sample request is shown below.
    ```json
    {
        "name": "GameStart",
        "quantity": 1,
        "type": "sell"
    }
    ```
    If the trade is successful, then the following success response is provided to return the transaction number.
    ```json
    {
        "data": {
            "transaction_number": 10
        }
    }
    ```
    In case the trade could not be performed, an error response is returned with an appropriate error message like the following.
    ```json
    {
        "error": {
            "code": 500,
            "message": "Insufficient stock quantity"
        }
    }
    ```
    If any of the fields in the requet body is missing, the following response is provided.
    ```json
    {
        "error": {
            "code": 400,
            "message": "Missing required fields"
        }
    }
    ```

3. `POST /replicate`

    This API is used to propagate order information to other replicas of order service. The recipient updates its transaction history with the order details present in the request body. A sample request looks like the following.
    ```json
    {
        "transaction_number": 1,
        "name": "Google",
        "type": "sell",
        "quantity": 10
    }
    ```
    If the request is successful, the following response is returned.
    ```json
    {
        "data": {
            "success": true
        }
    }
    ```



4. `GET /orders/<order_number>`

    This API is used to get the details of an order based on the order number. In case the order number is found in the database, the following success response is returned.
    ```json
    {
        "data": {
            "number": 1,
            "name": "Google",
            "type": "sell",
            "quantity": 10
        }
    }
    ```
    If the order number is not found in the database, the following response will be returned.
    ```json
    {
        "error": {
            "code": 400,
            "message": "Order number invalid"
        }
    }
    ```


5. `GET /orders/logs/<order_number>`

    This API is used to get the transaction logs from another replica of order service in sequence after the given order number. A sample response looks like the following.
    ```json
    {
        "data": [
            {
                "name": "CICSorg",
                "number": 12,
                "quantity": 1818,
                "type": "buy"
            }
        ]
    }
    ```