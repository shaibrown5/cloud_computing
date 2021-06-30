import json
from datetime import datetime
from flask import Flask, request
import requests
import boto3
from uhashring import HashRing

dynamodb = boto3.resource('dynamodb', region_name="us-east-2")
table = dynamodb.Table('aliveNodes')
delay_period = 30 * 1000
last = 0
ip_address = requests.get('https://api.ipify.org').text
print(ip_address)

# elb = boto3.client('elbv2', region_name='us-east-2')
# ec2 = boto3.client('ec2', region_name='us-east-2')
primary_cache = {}
secondary_cache = {}
app = Flask(__name__)
checking_second_node = False


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
        number_of_nodes = len(nodes_hash.get_nodes())
        update_live_nodes()
        if number_of_nodes != len(nodes_hash.get_nodes()):
            initiate_redistribution()

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
    update_live_nodes()
    # if request.remote_addr and request.remote_addr not in nodes_hash.get_nodes():
    #     return json.dumps({'status code': 404})
    try:
        try:
            key = request.args.get('str_key')
            data = request.args.get('data')
            expiration_date = request.args.get('expiration_date')
            first_or_second = request.args.get('cache')
        except ValueError as v:
            # back up mode: updates the secondary_cache
            # will throw an exception if different
            backup = request.args.get('backup')

            data_dict = request.get_json(force=True)
            app.logger.info(data_dict)
            secondary_cache.update(data)
            print(data_dict)
            return {'status code': 200,
                    'msg': "backup worked"}

        dict_to_return = {'status code': 200}

        if first_or_second == 'primary':
            primary_cache[key] = (data, expiration_date)
            dict_to_return['item'] = primary_cache[key]
            print(primary_cache)
        else:
            secondary_cache[key] = (data, expiration_date)
            dict_to_return['item'] = secondary_cache[key]
            print(secondary_cache)

        return json.dumps(dict_to_return)

    except Exception as e:
        return json.dumps({'status code': 404,
                           'item': str(e) + "\nin set_val exception"})


#  get items from nodes
@app.route('/get', methods=['GET', 'POST'])
def get():
    try:
        key = request.args.get('str_key')
        number_of_nodes = len(nodes_hash.get_nodes())
        update_live_nodes()
        if number_of_nodes != len(nodes_hash.get_nodes()):
            initiate_redistribution()
        node_ip = nodes_hash.get_node(key)
        alt_node = get_second_node_ip(key)

        try:
            ans = requests.get(f'http://{node_ip}:8080/get_val?str_key={key}&cache=primary')
        except requests.exceptions.ConnectionError as c:
            try:
                ans = requests.get(f'https://{alt_node}:8080/get_val?str_key={key}&cache=secondary')
            except requests.exceptions.ConnectionError as ce:
                ans = json.dumps({'status_code': 404, 'item': str(ce)})
        if not ans.json().get('item'):
            raise Exception()
        return ans.json().get('item')

    except Exception as e:
        return json.dumps({'status code': 404,
                           'item': 'Item not in Cache',
                           'error': str(e)})


@app.route('/get_val', methods=['GET', 'POST'])
def get_val():
    update_live_nodes()
    # if request.remote_addr and request.remote_addr not in nodes_hash.get_nodes():
    #     return json.dumps({'status code': 404})

    key = request.args.get('str_key')
    first_or_second = request.args.get('cache')

    try:
        if first_or_second == 'primary':
            try:
                item = primary_cache[key]
            except KeyError as k:
                try:
                    item = secondary_cache[key]
                    backup_data()
                except KeyError as ke:
                    return json.dumps({'status code': 404,
                                       'error': str(ke)})
        else:
            item = secondary_cache[key]
            backup_data()

        response = json.dumps({'status code': 200,
                               'item': item[0]})
        return response

    except Exception as e:
        return json.dumps({'status code': 404,
                           'error': str(e)})


def backup_data():
    #     # put all the secondary items in the primary
    #     primary_cache.update(secondary_cache)
    #
    #     alt_node = get_second_node_ip(list(secondary_cache.keys())[0])
    #     try:
    #         if alt_node != '-1':
    #             ans = requests.post(f'http://{alt_node}:8080/set_val?backup=true', data=secondary_cache)
    #
    #         secondary_cache.clear()
    #     except Exception as e:
    #         return json.dumps({'status code': 404,
    #                            'item': str(e)})
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


def initiate_redistribution():
    update_live_nodes()
    for node in nodes_hash:
        try:
            if node != '-1':
                requests.post(f'http://{node}:8080/redistribute_data')
        except Exception as e:
            return json.dumps({'status code': 404,
                               'item': str(e)})
    return json.dumps({'status code': 200})


@app.route('/redistribute_data', methods=['GET', 'POST'])
def redistribute_data():
    # while checking_second_node:
    #     pass
    update_live_nodes()
    # if request.remote_addr and request.remote_addr not in nodes_hash.get_nodes():
    #     return json.dumps({'status code': 404})
    primary_keys_to_keep = []
    secondary_keys_to_keep = []
    try:
        for key in primary_cache:
            node = nodes_hash.get_node(key)
            data = primary_cache[key][0]
            expiration_date = primary_cache[key][1]
            if node == ip_address:
                primary_keys_to_keep.append(key)
                continue
            else:
                try:
                    if node != '-1':
                        ans = requests.post(
                            f'http://{node}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}&cache=primary')
                    # primary_cache.pop(key)
                    # primary_keys_to_keep.append(key)
                except Exception as e:
                    return json.dumps({'status code': 404,
                                       'item': str(e)})
    except:
        return json.dumps({'status code': 404,
                           'error': 'failed redistribution'})

    try:

        for key in primary_cache:
            if key not in primary_keys_to_keep:
                primary_cache.pop(key)
        for key in secondary_cache:
            alt_node = get_second_node_ip(key)
            data = secondary_cache[key][0]
            expiration_date = secondary_cache[key][1]
            if alt_node == ip_address:
                secondary_keys_to_keep.append(key)
                continue
            else:
                try:
                    if alt_node != '-1':
                        ans = requests.post(
                            f'http://{alt_node}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}&cache=secondary')
                    # secondary_cache.pop(key)
                    # secondary_keys_to_keep.append(key)
                except Exception as e:
                    return json.dumps({'status code': 404,
                                       'item': str(e)})
        for key in secondary_cache:
            if key not in secondary_keys_to_keep:
                secondary_cache.pop(key)
    except:
        return json.dumps({'status code': 404,
                           'error': 'failed redistribution'})

    return json.dumps({'status code': 200})


@app.route('/test-data', methods=['GET', 'POST'])
def test_get_data():
    data = request.get_json(force=True)
    app.logger.info(data)
    print(data)
    return data


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
    nodes_number = len(nodes_hash.get_nodes())
    live_nodes_list = get_live_node_list()
    remove_list = []

    update_hash_nodes(live_nodes_list)

    for node_key in nodes_hash.get_nodes():
        if node_key not in live_nodes_list:
            remove_list.append(node_key)

    for node_key in remove_list:
        nodes_hash.remove_node(node_key)

    # if len(nodes_hash.get_nodes()) != nodes_number:
    #     initiate_redistribution()


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
        temp = HashRing(nodes=get_live_node_list())
        original_node = temp.get_node(key)
        temp.remove_node(original_node)
        second_node = temp.get_node(key)

        if second_node is None:
            second_node = '-1'

        temp.add_node(original_node)
    except Exception as e:
        # checking_second_node = False
        return json.dumps({'item': str(e)})
    # checking_second_node = False
    return second_node




if __name__ == '__main__':
    ip_address = requests.get('https://api.ipify.org').text
    update_live_nodes()
    initiate_redistribution()
    print('My public IP address is: {}'.format(ip_address))
    app.run(host='0.0.0.0', port=8080)

    # sudo lsof -i :8080
    # sudo kill -9 7711
