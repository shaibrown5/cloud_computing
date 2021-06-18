import json
import boto3
import uuid
from boto3.dynamodb.conditions import Key
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('CarPark')


def lambda_handler(event, context):
    if 'entry' in event['path']:

        ticketId = str(uuid.uuid4().int)
        plate = str(event.get('queryStringParameters', {}).get('plate', '<unknown>'))
        parkingLot = str(event.get('queryStringParameters', {}).get('parkingLot', '<unknown>'))
        time_of_entry = str(time.time())
        item = {
            'ticketId': ticketId,
            'parkingLot': parkingLot,
            'plate': plate,
            'time_of_entry': time_of_entry
        }
        response = table.put_item(Item=item)
        return {'body': ticketId}

    else:
        ticketId = event.get('queryStringParameters', {}).get('ticketId', '<unknown>')
        response = table.query(KeyConditionExpression=Key('ticketId').eq(ticketId))

        if response['Items'] != []:
            now = time.time()
            time_of_entry = float(response['Items'][0].get('time_of_entry'))
            difference = int(now - time_of_entry)
            cost = (difference // (60 * 15) * 2.5)
            response['Items'][0]['charge'] = (str(cost) + '$')

            difference = int(difference)

            m, s = divmod(difference, 60)
            h, m = divmod(m, 60)
            difference = f'{h:d}:{m:02d}:{s:02d}'

            response['Items'][0]['total_time_parked'] = difference
            # print difference
            # return {'body': difference}

            answer = {'plate': response['Items'][0]['plate'],
                      'total_time_parked': response['Items'][0]['total_time_parked'],
                      'parkingLot': response['Items'][0]['parkingLot'],
                      'charge': response['Items'][0]['charge']
                      }

            table.delete_item(
                Key={
                    'ticketId': ticketId

                })

            return {
                'statusCode': 200,
                'body': json.dumps(answer)
            }
        return {
            'statusCode': 201,
            'body': json.dumps(response)
        }