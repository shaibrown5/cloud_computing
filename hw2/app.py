import redis
import json
import xxhash
from datetime import datetime
from flask import Flask, request
import requests
import boto3
import threading
import socket

# dynamodb = boto3.resource('dynamodb')
# table = dynamodb.Table('live_nodes')
# cache = redis.Redis(host='localhost', port=6379, db=0)
cache = {}
app = Flask(__name__)


def signal_alive():
    threading.Timer(10.0, signal_alive).start()
    ip = socket.gethostbyname(socket.gethostname())
    timestamp = str(datetime.now())
    print(timestamp)
    # item = {'ip': ip,
    #         'last_timestamp': timestamp
    #         }
    # table.put_item(Item=item)


signal_alive()


def get_live_node_list():
    # response = table.scan()
    # return (x['ip'] for x in response['items'])
    return ['127.0.0.1']

    # For testing, put IPs of nodes here, Do it in the same order for all nodes



#  Put item in nodes

@app.route('/put', methods=['GET', 'POST'])
def put():
    key = request.args.get('str_key')
    data = request.args.get('data')
    expiration_date = request.args.get('expiration_date')
    nodes = get_live_node_list()

    key_v_node_id = xxhash.xxh64_intdigest(key) % 1024

    node = nodes[(key_v_node_id % len(nodes))]
    alt_node = nodes[((key_v_node_id + 1) % len(nodes))]

    try:
        ans = requests.post(f'http://{node}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}')
        ans = requests.post(f'http://{alt_node}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}')
    except requests.exceptions.ConnectionError:
        ans = json.dumps({'status_code': 404})

    return ans.json()


@app.route('/set_val', methods=['GET', 'POST'])
def set_val():
    key = request.args.get('str_key')
    data = request.args.get('data')
    expiration_date = request.args.get('expiration_date')
    # cache.s[key] = [data, expiration_date]
    # cache.set(name=key, value=data, ex=expiration_date)
    cache[key] = (data, expiration_date)
    print(cache)
    return json.dumps({'status code': 200,
                       'item': cache[key]})


#  get items from nodes
@app.route('/get', methods=['GET', 'POST'])
def get():
    nodes = get_live_node_list()
    key = request.args.get('str_key')

    key_v_node_id = xxhash.xxh64_intdigest(key) % 1024

    node = nodes[key_v_node_id % len(nodes)]
    alt_node = nodes[((key_v_node_id + 1) % len(nodes))]

    try:
        ans = requests.get(f'http://{node}:8080/get_val?str_key={key}')
    except:
        try:
            ans = requests.get(f'https://{alt_node}:8080/get_val?str_key={key}')
        except requests.exceptions.ConnectionError:
            return ans
    return ans.json().get('item')


@app.route('/get_val', methods=['GET', 'POST'])
def get_val():
    key = request.args.get('str_key')
    # item = cache.get(key)
    item = cache[key]
    response = json.dumps({'status code': 200,
                           'item': item[0]})
    return response


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
