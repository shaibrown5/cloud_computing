import redis
import json
import xxhash
from datetime import datetime
from flask import Flask, request
import requests
import boto3
import time
from uhashring import HashRing

dynamodb = boto3.resource('dynamodb', region_name="us-east-2")
table = dynamodb.Table('aliveNodes')
# cache = redis.Redis(host='localhost', port=6379, db=0)
delay_period = 30 * 1000
last = 0
ip_address = ""


# elb = boto3.client('elbv2', region_name='us-east-2')
# ec2 = boto3.client('ec2', region_name='us-east-2')


def get_live_node_list():
    """
    list of Ip's for the node list.
    :return:
    """
    try:
        app.logger.info('get_live_node_list')
        now = get_millis(datetime.now())
        response = table.scan()
        app.logger.info(f'get_live_node_list-  response: {response}')
        nodes = []
        for item in response['Items']:
            if int(item['lastAlive']) >= now - delay_period:
                nodes.append(item['ip'])
        return nodes
    except Exception as e:
        # app.logger.info(f'error in get_live_node_list {e}')
        return "failed in the get_live_node_list"


cache = {}
app = Flask(__name__)
# this will hold the nodes , and hash them consistentaly
nodes_hash = HashRing(nodes=get_live_node_list())


@app.route('/health-check', methods=['GET', 'POST'])
def health_check():
    timestamp = get_millis(datetime.now())
    item = {'ip': ip_address,
            'lastAlive': timestamp
            }
    table.put_item(Item=item)
    return f'it is I {ip_address} - at time {timestamp} im still alive'


def get_millis(dt):
    return int(round(dt.timestamp() * 1000))


@app.route('/put', methods=['GET', 'POST'])
def put():
    #    nodes = get_live_node_list()
    key = request.args.get('str_key')
    data = request.args.get('data')
    expiration_date = request.args.get('expiration_date')

    # key_v_node_id = xxhash.xxh64_intdigest(key) % 1024
    #
    # node = nodes[(key_v_node_id % len(nodes))]
    # alt_node = nodes[((key_v_node_id + 1) % len(nodes))]

    update_live_nodes()
    node_ip = nodes_hash.get_node(key)
    second_node_ip = get_second_node_ip(key)

    try:
        ans = requests.post(
            f'http://{node_ip}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}')
        ans = requests.post(
            f'http://{second_node_ip}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}')
    except requests.exceptions.ConnectionError:
        ans = json.dumps({'status_code': 404})

    return ans.json()


@app.route('/put-test', methods=['GET', 'POST'])
def put_test():
    key = request.args.get('str_key')
    data = request.args.get('data')
    exp_date = request.args.get('exp_date')

    cache[key] = (data, exp_date)
    print(cache)

    return json.dumps({'status code': 200,
                       'item': cache[key]})


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
    key = request.args.get('str_key')

    # key_v_node_id = xxhash.xxh64_intdigest(key) % 1024
    #     #
    #     # node = nodes[key_v_node_id % len(nodes)]
    #     # alt_node = nodes[((key_v_node_id + 1) % len(nodes))]
    update_live_nodes()
    node_ip = nodes_hash.get_node(key)

    try:
        ans = requests.get(f'http://{node_ip}:8080/get_val?str_key={key}')
    except requests.exceptions.ConnectionError:
        ans = json.dumps({'status_code': 404})
    # except:
    #     try:
    #         ans = requests.get(f'https://{alt_node}:8080/get_val?str_key={key}')
    #     except requests.exceptions.ConnectionError:
    #         return ans

    return ans.json().get('item')


@app.route('/get_val', methods=['GET', 'POST'])
def get_val():
    key = request.args.get('str_key')
    # item = cache.get(key)
    item = cache[key]
    response = json.dumps({'status code': 200,
                           'item': item[0]})
    return response


@app.route('/get-test', methods=['GET', 'POST'])
def get_test():
    ans_dict = dict()

    ans_dict[key] = request.args.get('str_key')
    ans_dict[curr_dict_of_nodes] = nodes_hash.nodes
    ans_dict[node_ip] = nodes_hash.get_node(key)
    ans_dict[second_ip] = get_second_node_ip(key)
    update_live_nodes()
    ans_dict[new_dict_of_nodes] = nodes_hash.nodes

    return json.dumps({'status code': 200,
                       'item': ans_dict})


def update_live_nodes():
    nodes_list = get_live_node_list()

    for node_key in nodes_hash.nodes:
        if node_key not in nodes_list:
            nodes_list.remove_node(node_key)


def get_second_node_ip(key):
    original_node = nodes_hash.get_node(key)
    nodes_hash.remove_node(original_node)
    second_node = nodes_hash.get_node(key)
    nodes_hash.add_node(original_node)

    return second_node


if __name__ == '__main__':
    ip_address = requests.get('https://api.ipify.org').text
    print('My public IP address is: {}'.format(ip_address))
    app.run(host='0.0.0.0', port=8080)
