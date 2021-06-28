# figure out my ip
echo "getting my ip"
MY_IP=$(curl ipinfo.io/ip)
echo "My IP: $MY_IP"


# get subnets for the ELB and vpc id
echo "getting all subnets and vpc id's"
SEC_GROUP=$(aws ec2 describe-security-groups --group-names shaiEladSecGroup | jq -r .SecurityGroups[0].GroupId)
KEY_NAME="shai-elad-key"

NOW=$(date +"%T")
STACK_NAME="shai-elad-add-node-stack-$NOW"


echo "createing stack shai-elad-add-node stack now"
STACK_RES=$(aws cloudformation create-stack --stack-name $STACK_NAME --template-body file://raiseOneNodeCloudFormation.yml --capabilities CAPABILITY_IAM \
	--parameters ParameterKey=InstanceType,ParameterValue=t2.micro \
    ParameterKey=KeyName,ParameterValue=$KEY_NAME \
	ParameterKey=SecGroupId,ParameterValue=$SEC_GROUP)

echo "waiting for stack to be created - this may take a while"
STACK_ID=$(echo $STACK_RES | jq -r '.StackId')
aws cloudformation wait stack-create-complete --stack-name $STACK_ID

REGION=us-east-2

STACK=$(aws cloudformation --region $REGION describe-stacks --stack-name $STACK_NAME | jq -r .Stacks[0])

# stack outputs
echo "printing stack outputs"
OUTPUTS=$(echo $STACK | jq -r .Outputs)
echo $OUTPUTS
InstanceIP=$(aws cloudformation --region $REGION describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='InstanceIP'].OutputValue" --output text)
InstanceId=$(aws cloudformation --region $REGION describe-stacks --stack-name $STACK_NAME --query "Stacks[0].Outputs[?OutputKey=='InstanceId'].OutputValue" --output text)
TGARN=$(aws cloudformation --region $REGION describe-stacks --stack-name shai-elad-stack --query "Stacks[0].Outputs[?OutputKey=='TargetGroup'].OutputValue" --output text)

# register instance to target group
echo " registering instance to target group"
aws elbv2 register-targets --target-group-arn $TGARN --targets Id=$InstanceId,Port=8080

echo " "
echo "waiting abit for instance  to register healthy"
aws ec2 wait instance-status-ok --instance-ids $InstanceId

aws elbv2 describe-target-health  --target-group-arn $TGARN