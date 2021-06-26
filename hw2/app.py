import json
from datetime import datetime
from flask import Flask, request
import requests
import boto3
from uhashring import HashRing

dynamodb = boto3.resource('dynamodb', region_name="us-east-2")
table = dynamodb.Table('aliveNodes')
delay_period = 15 * 1000
last = 0
ip_address = ""

# elb = boto3.client('elbv2', region_name='us-east-2')
# ec2 = boto3.client('ec2', region_name='us-east-2')
primary_cache = {}
secondary_cache = {}
app = Flask(__name__)


def get_millis(dt):
    return int(round(dt.timestamp() * 1000))


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
        return f"failed in the get_live_node_list {str(e)}"


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


@app.route('/put', methods=['GET', 'POST'])
def put():
    try:
        key = request.args.get('str_key')
        data = request.args.get('data')
        expiration_date = request.args.get('expiration_date')

        update_live_nodes()
        node_ip = nodes_hash.get_node(key)
        second_node_ip = get_second_node_ip(key)

        try:
            ans = requests.post(
                f'http://{node_ip}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}&cache=primary')

            if second_node_ip != '-1':
                ans = requests.post(
                    f'http://{second_node_ip}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}&cache=secondary')
        except requests.exceptions.ConnectionError:
            ans = json.dumps({'status_code': 404})

        return ans.json()

    except Exception as e:
        return json.dumps({'status code': 404,
                           'item': str(e)})


@app.route('/set_val', methods=['GET', 'POST'])
def set_val():
    try:
        key = request.args.get('str_key')
        data = request.args.get('data')
        expiration_date = request.args.get('expiration_date')
        first_or_second = request.args.get('cache')

        if first_or_second == 'primary':
            primary_cache[key] = (data, expiration_date)
            print(primary_cache)
        else:
            secondary_cache[key] = (data, expiration_date)
            print(secondary_cache)

        return json.dumps({'status code': 200,
                           'item': primary_cache[key]})
    except Exception as e:
        return json.dumps({'status code': 404,
                           'item': str(e)})


#  get items from nodes
@app.route('/get', methods=['GET', 'POST'])
def get():
    try:
        key = request.args.get('str_key')
        update_live_nodes()
        node_ip = nodes_hash.get_node(key)
        alt_node = get_second_node_ip(key)

        try:
            ans = requests.get(f'http://{node_ip}:8080/get_val?str_key={key}&cache=primary')
        except requests.exceptions.ConnectionError as c:
            try:
                ans = requests.get(f'https://{alt_node}:8080/get_val?str_key={key}&cache=secondary')
            except requests.exceptions.ConnectionError as ce:
                ans = json.dumps({'status_code': 404, 'item': str(ce)})

        return ans.json().get('item')

    except Exception as e:
        return json.dumps({'status code': 404,
                           'item': 'Item not in Cache'})


@app.route('/get_val', methods=['GET', 'POST'])
def get_val():
    key = request.args.get('str_key')
    first_or_second = request.args.get('cache')

    if first_or_second == 'primary':
        item = primary_cache[key]
    else:
        item = secondary_cache[key]
        backup_data()

    response = json.dumps({'status code': 200,
                           'item': item[0]})
    return response


def backup_data():
    # put all the secondary items in the
    primary_cache.update(secondary_cache)

    for key in secondary_cache:
        alt_node = get_second_node_ip(key)
        data = secondary_cache[key][0]
        expiration_date = secondary_cache[key][1]
        try:
            if alt_node != '-1':
                ans = requests.post(
                    f'http://{alt_node}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}&cache=secondary')

            secondary_cache.pop(key)
        except Exception as e:
            return json.dumps({'status code': 404,
                               'item': str(e)})

@app.route('/get-test', methods=['GET', 'POST'])
def get_test():
    update_live_nodes()
    try:
        ans_dict = {}

        key = request.args.get('str_key')
        ans_dict['key'] = key
        ans_dict['curr_dict_of_nodes'] = nodes_hash.nodes
        ans_dict['node_ip'] = nodes_hash.get_node(key)
        ans_dict['second_ip'] = get_second_node_ip(key)
        update_live_nodes()
        ans_dict['new_dict_of_nodes'] = nodes_hash.nodes

        return json.dumps({'status code': 200,
                           'item': ans_dict})
    except Exception as e:
        return json.dumps({'status code': 404,
                           'item': str(e)})


@app.route('/nodes-list', methods=['GET', 'POST'])
def nodes_list():
    update_live_nodes()
    ans_dict = {}
    try:
        key = request.args.get('str_key')
        ans_dict['key'] = key
        ans_dict['curr_dict_of_nodes'] = nodes_hash.nodes
        ans_dict['node_ip'] = nodes_hash.get_node(key)
    except Exception as e:
        return json.dumps({'item': str(e)})

    return json.dumps({'status code': 200,
                       'item': ans_dict})


@app.route('/second-nodes', methods=['GET', 'POST'])
def second_nodes_list():
    update_live_nodes()
    ans_dict = {}
    try:
        key = request.args.get('str_key')
        ans_dict['key'] = key
        ans_dict['curr_dict_of_nodes'] = nodes_hash.nodes
        ans_dict['second_ip'] = get_second_node_ip(key)
    except Exception as e:
        return json.dumps({'item': str(e)})

    return json.dumps({'status code': 200,
                       'item': ans_dict})


@app.route('/live-nodes', methods=['GET', 'POST'])
def live_node_list():
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
        return json.dumps({'item': nodes})
    except Exception as e:
        # app.logger.info(f'error in get_live_node_list {e}')
        return json.dumps({'item': f"failed in the get_live_node_list {str(e)}"})


@app.route('/all-nodes', methods=['GET', 'POST'])
def all_nodes_list():
    update_live_nodes()
    ans_dict = {}
    try:
        ans_dict['curr_dict_of_nodes'] = nodes_hash.nodes
    except Exception as e:
        return json.dumps({'item': str(e)})

    return json.dumps({'status code': 200,
                       'item': ans_dict})


def update_live_nodes():
    """
    This method updates the list of nodes in the hash list
    by deleteing nodes that are no longer alive, and added new nodes.
    :return:
    """
    live_nodes_list = get_live_node_list()
    remove_list = []

    update_hash_nodes(live_nodes_list)

    for node_key in nodes_hash.get_nodes():
        if node_key not in live_nodes_list:
            remove_list.append(node_key)

    for node_key in remove_list:
        nodes_hash.remove_node(node_key)


def update_hash_nodes(live_nodes_list):
    """
    This method adds new nodes to the hash pool
    :param live_nodes_list: list of currently alive nodes
    :return:
    """
    for node in live_nodes_list:
        if node not in nodes_hash.get_nodes():
            nodes_hash.add_node(node)


def get_second_node_ip(key):
    """
    This method gets the next node ip to send the data to
    :param key: the wanted key to map
    :return:
    """
    try:
        original_node = nodes_hash.get_node(key)
        nodes_hash.remove_node(original_node)
        second_node = nodes_hash.get_node(key)

        if second_node is None:
            second_node = '-1'

        nodes_hash.add_node(original_node)
    except Exception as e:
        return json.dumps({'item': str(e)})

    return second_node


if __name__ == '__main__':
    ip_address = requests.get('https://api.ipify.org').text
    print('My public IP address is: {}'.format(ip_address))
    app.run(host='0.0.0.0', port=8080)

    # sudo lsof - i: 8080
    # sudo kill - 9 7711
