we have 2 cloudformation scripts:
1 is the main script that creates a dynamo db, elb, and 3 ec2 instances along with their sec groups and target group.
the other is a template for createing a single instance to join the elb targets group. 

there are 2 deploy scripts:
 deploy.sh is the main deploy script
 deploy_one_node.sh is to deploy a single instance. -> this can only be called after the original stack has been created.

our logic:
each EC2 uses uhashring to consistently hash any incoming request to the wanted node.
we then created logic to find out who will be the alt node , and send the data to them as well


Each node has 2 cache's a primary and secondary cache. this is important to split as we use this to diffrenciate between primary nodes, and secondary nodes.

each node writes to a shared dynamo db their IP adresses and timestamp. this is used to know which nodes are alive internally (not health check)

when a new node is added , initiate ditribution for every node. this starts a round robin chain effect that forces all the nodes to go over their caches, and place them in the correct node.

similarly when a node dies, we have a back up function that notifies the alt node that they are now the primary node, and backs up their data so that no information is lost.


Please note this is our first time actually playing with a real server and trying to send messages from instances to instances, we were not sure 100% what is the proper way to send large ammount of data. we would appreciate your feedback on our methods.
