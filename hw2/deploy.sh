KEY_NAME="shai-elad-key-`date +'%N'`"
KEY_PEM="$KEY_NAME.pem"

echo "create key pair $KEY_PEM to connect to instances and save locally"
aws ec2 create-key-pair --key-name $KEY_NAME \
    | jq -r ".KeyMaterial" > $KEY_PEM

# secure the key pair
chmod 400 $KEY_PEM

# figure out my ip
echo "getting my ip"
MY_IP=$(curl ipinfo.io/ip)
echo "My IP: $MY_IP"


# get subnets for the ELB and vpc id
echo "getting all subnets and vpc id's"
SUB_ID_1=$(aws ec2 describe-subnets --filters Name=default-for-az,Values=true | jq -r .Subnets[0] | jq -r .SubnetId)
SUB_ID_2=$(aws ec2 describe-subnets --filters Name=default-for-az,Values=true | jq -r .Subnets[1] | jq -r .SubnetId)
SUB_ID_3=$(aws ec2 describe-subnets --filters Name=default-for-az,Values=true | jq -r .Subnets[2] | jq -r .SubnetId)
VPC_ID=$(aws ec2 describe-subnets --filters Name=default-for-az,Values=true | jq -r .Subnets[0] | jq -r .VpcId)
VPC_CIDR_BLOCK=$(aws ec2 describe-vpcs --filters Name=vpc-id,Values=$VPC_ID | jq -r .Vpcs[0].CidrBlock)
echo $SUB_ID_1
echo $SUB_ID_2
echo $SUB_ID_3
echo $VPC_ID
echo $VPC_CIDR_BLOCK

echo "createing stack shai-elad stack now"
STACK_RES=$(aws cloudformation create-stack --stack-name shai-elad-stack --template-body file://ec2CloudFormation.yml \
	--parameters ParameterKey=InstanceType,ParameterValue=t2.micro \
	ParameterKey=KeyName,ParameterValue=$KEY_NAME \
	ParameterKey=SSHLocation,ParameterValue=$MY_IP/32 \
	ParameterKey=SubNetId1,ParameterValue=$SUB_ID_1 \
	ParameterKey=SubNetId2,ParameterValue=$SUB_ID_2 \
	ParameterKey=SubNetId3,ParameterValue=$SUB_ID_3 \
	ParameterKey=VPCId,ParameterValue=$VPC_ID \
	ParameterKey=VPCcidr,ParameterValue=$VPC_CIDR_BLOCK)

echo "waiting for stack shai-elad-stack to be created"
STACK_ID=$(echo $STACK_RES | jq -r '.StackId')
aws cloudformation wait stack-create-complete --stack-name $STACK_ID

REGION=us-east-2

# get the wanted stack 
STACK=$(aws cloudformation --region $REGION describe-stacks --stack-name shai-elad-stack | jq -r .Stacks[0])

# stack outputs
echo "printing stack outputs"
OUTPUTS=$(echo $STACK | jq -r .Outputs)
echo $OUTPUTS
# or i acn query the outputs 
Instance1IP=$(aws cloudformation --region $REGION describe-stacks --stack-name shai-elad-stack --query "Stacks[0].Outputs[?OutputKey=='Instance1IP'].OutputValue" --output text)
Instance2IP=$(aws cloudformation --region $REGION describe-stacks --stack-name shai-elad-stack --query "Stacks[0].Outputs[?OutputKey=='Instance2IP'].OutputValue" --output text)
Instance3IP=$(aws cloudformation --region $REGION describe-stacks --stack-name shai-elad-stack --query "Stacks[0].Outputs[?OutputKey=='Instance3IP'].OutputValue" --output text)
TGARN=$(aws cloudformation --region $REGION describe-stacks --stack-name shai-elad-stack --query "Stacks[0].Outputs[?OutputKey=='TargetGroup'].OutputValue" --output text)

# put ther server file on the instances.
# the other option for this was to create an s3 bucket, and then have the ec2 read and save the app.py from there during the
# cloudformation start up under UserData.
# this is better in our case
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" app.py ubuntu@$Instance1IP:/home/ubuntu/
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" app.py ubuntu@$Instance2IP:/home/ubuntu/
scp -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=60" app.py ubuntu@$Instance3IP:/home/ubuntu/



# target health check command
aws elbv2 describe-target-health  --target-group-arn $TGARN

ssh -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=10" ubuntu@$Instance1IP <<EOF
    # run app
    nohup flask run --host 0.0.0.0  &>/dev/null &
    exit
EOF

ssh -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=10" ubuntu@$Instance2IP <<EOF
    # run app
    nohup flask run --host 0.0.0.0  &>/dev/null &
    exit
EOF

ssh -i $KEY_PEM -o "StrictHostKeyChecking=no" -o "ConnectionAttempts=10" ubuntu@$Instance3IP <<EOF
    # run app
    nohup flask run --host 0.0.0.0  &>/dev/null &
    exit
EOF


