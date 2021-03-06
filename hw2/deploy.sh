KEY_NAME="shai-elad-key"
KEY_PEM="$KEY_NAME.pem"

echo "create key pair $KEY_PEM to connect to instances and save locally"
aws ec2 create-key-pair --key-name $KEY_NAME | jq -r ".KeyMaterial" > $KEY_PEM

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
STACK_RES=$(aws cloudformation create-stack --stack-name shai-elad-stack --template-body file://ec2CloudFormation.yml --capabilities CAPABILITY_NAMED_IAM \
	--parameters ParameterKey=InstanceType,ParameterValue=t2.micro \
	ParameterKey=KeyName,ParameterValue=$KEY_NAME \
	ParameterKey=SSHLocation,ParameterValue=$MY_IP/32 \
	ParameterKey=SubNetId1,ParameterValue=$SUB_ID_1 \
	ParameterKey=SubNetId2,ParameterValue=$SUB_ID_2 \
	ParameterKey=SubNetId3,ParameterValue=$SUB_ID_3 \
	ParameterKey=VPCId,ParameterValue=$VPC_ID \
	ParameterKey=VPCcidr,ParameterValue=$VPC_CIDR_BLOCK)

echo "waiting for stack to be created - this may take a while"
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
ID3=$(aws cloudformation --region $REGION describe-stacks --stack-name shai-elad-stack --query "Stacks[0].Outputs[?OutputKey=='InstanceId3'].OutputValue" --output text)
TGARN=$(aws cloudformation --region $REGION describe-stacks --stack-name shai-elad-stack --query "Stacks[0].Outputs[?OutputKey=='TargetGroup'].OutputValue" --output text)

echo " "
echo "waiting abit for instance  to register healthy"
aws ec2 wait instance-status-ok --instance-ids $ID3
# target health check command
aws elbv2 describe-target-health  --target-group-arn $TGARN

DNS_ADD=$(aws elbv2 describe-load-balancers --names ShaiEladELB | jq -r .LoadBalancers[0].DNSName)
echo $DNS_ADD
echo "aws elbv2 describe-target-health  --target-group-arn $TGARN"
