import redis
import json
import xxhash
from datetime import datetime
from flask import Flask, request
import requests
import boto3
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('aliveNodes')
# cache = redis.Redis(host='localhost', port=6379, db=0)
delay_period = 30 * 1000
last = 0
ip_address = ""


elb = boto3.client('elbv2', region_name='us-east-2')
ec2 = boto3.client('ec2', region_name='us-east-2')
cache = {}
app = Flask(__name__)


@app.route('/health-check', methods=['GET', 'POST'])
def health_check():
    timestamp = get_millis(datetime.now())
    item = {'ip': ip_address,
            'lastAlive': timestamp
            }
    table.put_item(Item=item)
    return f'it is I {ip_address} - at time {timestamp} im still alive'


def get_millis(dt):
    return (int(round(dt.timestamp() * 1000)))


def get_live_node_list():
    try:
        app.logger.info('get_live_node_list')
        now = get_millis(datetime.now())
        response = table.scan()
        app.logger.info(f'get_live_node_list-  response: {response}')
        nodes = []
        for x in response['Items']:
            if (int)(x['lastAlive']) >= now - delay_period:
                nodes.append(x['ip'])
        return nodes
    except Exception as e:
        # app.logger.info(f'error in get_live_node_list {e}')
        return "failed in the get_live_node_list"


# @app.route('/nodes', methods=['GET', 'POST'])
# def get_live_node_list_test():
#     try:
#         target_group = elb.describe_target_groups()
#     except:
#         return "target_group"
#     try:
#         target_group_arn = target_group["TargetGroups"][0]["TargetGroupArn"]
#     except:
#         return "target_group_arn"
#     try:
#         health = elb.describe_target_health(TargetGroupArn=target_group_arn)
#     except:
#         return "health"
#     healthy = []
#     try:
#         for target in health["TargetHealthDescriptions"]:
#             if target["TargetHealth"]["State"] != "unhealthy":
#                 healthy.append(target["Target"]["Id"])
#
#         healthy_ips = []
#         for node_id in healthy:
#             healthy_ips.append(
#                 ec2.describe_instances(InstanceIds=[node_id])["Reservations"][0]["Instances"][0]["PublicIpAddress"])
#     except:
#         return "falied 4"
#     return json.dumps({'nodes': healthy_ips})
#
#
# def get_live_node_list():
#     target_group = elb.describe_target_groups(Names=["ShaiEladTargetGroup"])
#     target_group_arn = target_group["TargetGroups"][0]["TargetGroupArn"]
#     health = elb.describe_target_health(TargetGroupArn=target_group_arn)
#     healthy = []
#     for target in health["TargetHealthDescriptions"]:
#         if target["TargetHealth"]["State"] != "unhealthy":
#             healthy.append(target["Target"]["Id"])
#
#     healthy_ips = []
#     for node_id in healthy:
#         healthy_ips.append(
#             ec2.describe_instances(InstanceIds=[node_id])["Reservations"][0]["Instances"][0]["PublicIpAddress"])
#
#     return healthy_ips


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
        ans = requests.post(
            f'http://{alt_node}:8080/set_val?str_key={key}&data={data}&expiration_date={expiration_date}')
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


# @app.route('/health-check', methods=['GET', 'POST'])
# def health_check():
#     return "ah ah ah ah staying alive"


# def signal_alive():
#     threading.Timer(10.0, signal_alive).start()
#     ip = socket.gethostbyname(socket.gethostname())
#     timestamp = str(datetime.now())
#     print(timestamp)
#     # item = {'ip': ip,
#     #         'last_timestamp': timestamp
#     #         }
#     # table.put_item(Item=item)
#
#
# signal_alive()


if __name__ == '__main__':
    ip_address = requests.get('https://api.ipify.org').text
    print('My public IP address is: {}'.format(ip_address))
    app.run(host='0.0.0.0', port=8080)
