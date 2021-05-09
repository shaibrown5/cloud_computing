from time import sleep
from zipfile import ZipFile
import boto3
import json


class DeployLambda:

    def __init__(self):
        session = boto3.Session(profile_name='default')
        creds = session.get_credentials()

        self.aws_access_key = creds.access_key
        self.aws_secret_access_key = creds.secret_key
        self.region = 'us-east-2'
        self.lambda_client = boto3.client('lambda', region_name=self.region)
        self.account_id = 0
        self.lambda_name = 'EladShaiHW'
        self.zip_file_name = 'lambda_function.zip'

        with ZipFile(self.zip_file_name, 'w') as zipObj:
            zipObj.write('lambda_function.py')

    def create_table(self):
        """
        This method creates the wanted DB
        :return: table
        """
        dynamodb = boto3.resource('dynamodb', region_name=self.region, )

        table = dynamodb.create_table(
            TableName='CarPark',
            KeySchema=[
                {
                    'AttributeName': 'ticketId',
                    'KeyType': 'HASH'  # Partition key
                }
            ],
            AttributeDefinitions=[
                {
                    'AttributeName': 'ticketId',
                    'AttributeType': 'S'
                }
            ],
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )

        print("table created")

        return table.table_name

    def create_IAM_Policy(self, table_name):
        client_sts = boto3.client("sts", aws_access_key_id=self.aws_access_key,
                                  aws_secret_access_key=self.aws_secret_access_key)
        self.account_id = client_sts.get_caller_identity()["Account"]
        # Create IAM client
        iam = boto3.client('iam')

        # Create a policy
        my_managed_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "ReadWriteTable",
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:BatchGetItem",
                        "dynamodb:GetItem",
                        "dynamodb:Query",
                        "dynamodb:Scan",
                        "dynamodb:BatchWriteItem",
                        "dynamodb:PutItem",
                        "dynamodb:UpdateItem"
                    ],
                    "Resource": f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/{table_name}"
                },
                {
                    "Sid": "GetStreamRecords",
                    "Effect": "Allow",
                    "Action": "dynamodb:GetRecords",
                    "Resource": f"arn:aws:dynamodb:{self.region}:{self.account_id}:table/SampleTable/stream/* "
                },
                {
                    "Sid": "WriteLogStreamsAndGroups",
                    "Effect": "Allow",
                    "Action": [
                        "logs:CreateLogStream",
                        "logs:PutLogEvents"
                    ],
                    "Resource": "*"
                },
                {
                    "Sid": "CreateLogGroup",
                    "Effect": "Allow",
                    "Action": "logs:CreateLogGroup",
                    "Resource": "*"
                },
                {
                    "Sid": "DynamoDBPolicy",
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:*"
                    ],
                    "Resource": "*"
                }
            ]
        }

        response = iam.create_policy(
            PolicyName='EladShaiLambdaHW1Policy',
            PolicyDocument=json.dumps(my_managed_policy)
        )

        print("policy created")

        return response['Policy']['Arn']

    def create_role(self, arn):
        # Create IAM client
        iam_client = boto3.client('iam')
        aPd = json.dumps({'Version': '2012-10-17',
                          'Statement': [{'Effect': 'Allow',
                                         'Principal': {'Service': 'lambda.amazonaws.com'},
                                         'Action': 'sts:AssumeRole'}]})
        role_name = 'EladShai_role'

        role = iam_client.create_role(RoleName=role_name,
                                      AssumeRolePolicyDocument=aPd)

        # attach myLambdaPolicy
        iam_client.attach_role_policy(
            PolicyArn=arn,
            RoleName=role_name
        )

        # Attach dynamodb access policy
        iam_client.attach_role_policy(
            PolicyArn='arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess',
            RoleName=role_name
        )
        role_arn = f'arn:aws:iam::{self.account_id}:role/{role_name}'

        print('sleeping 10 seconds to allow role creation')
        sleep(10)

        print("role created")

        return role_arn

    def create_lambda(self, role_arn):
        with open(self.zip_file_name, 'rb') as z:
            file = z.read()

        response = self.lambda_client.create_function(
            FunctionName=self.lambda_name,
            Runtime='python3.7',
            Role=role_arn,
            Handler='lambda_function.lambda_handler',
            Code={
                'ZipFile': file
            },
            Description='eladShaiHw1',
            Publish=True,
            PackageType='Zip'
        )

        print("lambda created")

        return response['FunctionArn']

    def create_rest_api(self, lambda_arn, api_name, operation, statement_id):
        api_client = boto3.client('apigateway', region_name=self.region)

        result = api_client.create_rest_api(name=api_name,
                                            endpointConfiguration={
                                                'types': ['REGIONAL']
                                            })
        api_id = result['id']

        res = api_client.get_resources(restApiId=api_id)
        root_id = next(item['id'] for item in res['items'] if item['path'] == '/')

        response_enter = api_client.create_resource(restApiId=api_id, parentId=root_id, pathPart=operation)
        base_id_enter = response_enter['id']

        api_client.put_method(restApiId=api_id, resourceId=base_id_enter, httpMethod='ANY',
                              authorizationType='NONE')

        lambda_uri = \
            f'arn:aws:apigateway:{api_client.meta.region_name}:lambda:path/2015-03-31/functions/{lambda_arn}/invocations'

        api_client.put_integration(
            restApiId=api_id, resourceId=base_id_enter, httpMethod='ANY', type='AWS_PROXY',
            integrationHttpMethod='POST', uri=lambda_uri)

        api_client.create_deployment(restApiId=api_id, stageName=operation)

        source_arn = f'arn:aws:execute-api:{api_client.meta.region_name}:{self.account_id}:{api_id}/*/*/{operation}'

        self.lambda_client.add_permission(
            FunctionName=self.lambda_name, StatementId=statement_id,
            Action='lambda:InvokeFunction', Principal='apigateway.amazonaws.com',
            SourceArn=source_arn)

        return api_id

    def main(self):
        table_name = self.create_table()
        policy_arn = self.create_IAM_Policy(table_name)
        role_arn = self.create_role(policy_arn)
        lambda_arn = self.create_lambda(role_arn)
	print('creating entry api')
        entry_id = self.create_rest_api(lambda_arn=lambda_arn, api_name='entryTest', operation='entry',
                                        statement_id='entry-invoke1')
        print('entry url:')
        print(f'https://{entry_id}.execute-api.{self.region}.amazonaws.com/entry/entry')
	print('creating exit api')
        exit_id = self.create_rest_api(lambda_arn=lambda_arn, api_name='exitTest', operation='exit',
                                       statement_id='exit-invoke1')
        print('\nexit url:')
        print(f'https://{exit_id}.execute-api.{self.region}.amazonaws.com/exit/exit')


if __name__ == '__main__':
    m = DeployLambda()
    m.main()
