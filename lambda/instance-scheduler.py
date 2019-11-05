import boto3
import sys, os, logging, datetime, time

logger = logging.getLogger()
logger.setLevel(logging.INFO)

debug = False

create_schedule_tag_force = os.getenv('SCHEDULE_TAG_FORCE', 'False')
create_schedule_tag_force = create_schedule_tag_force.capitalize()
logger.info("-> create_schedule_tag_force is %s." % create_schedule_tag_force)

ec2_schedule = os.getenv('EC2_SCHEDULE', 'True')
ec2_schedule = ec2_schedule.capitalize()
logger.info("-> ec2_schedule is %s." % ec2_schedule)

rds_schedule = os.getenv('RDS_SCHEDULE', 'True')
rds_schedule = rds_schedule.capitalize()
logger.info("-> rds_schedule is %s." % rds_schedule)

schedule_tag = os.getenv('TAG', 'schedule')
logger.info("-> Schedule tag name is '%s'. Use create_schedule_tag_force option to force create default tag when needed." % schedule_tag)

aws_region = os.getenv('AWS_REGION', 'eu-west-1')

def ec2_init():
    global ec2
    logger.info("-> Connecting EC2 to region %s." % aws_region)
    ec2 = boto3.resource('ec2', region_name=aws_region)
    logger.info("-> Connected EC2 to region %s." % aws_region)

def rds_init():
    global rds
    logger.info("-> Connecting RDS to region %s." % aws_region)
    rds = boto3.client('rds', region_name=aws_region)
    logger.info("-> Connected RDS to region %s." % aws_region)

#
# Add default 'Schedule' tag to instance.
# (Only if instance.id not excluded and create_schedule_tag_force variable is True.
#
def create_schedule_tag(instance):
    exclude_list = os.environ.get('EXCLUDE').split(',')

    autoscaling = False
    for tag in instance.tags:
        if 'aws:autoscaling:groupName' in tag['Key']:
            autoscaling = True
            break

    instance_name = 'name not set'
    for tag in instance.tags:
        if 'Name' in tag['Key']:
            instance_name = tag['Value']
            break

    if (create_schedule_tag_force == 'True') and (instance.id not in exclude_list) and (not autoscaling):
        try:
            tag_value = os.getenv('DEFAULT', 'any_start=5')
            logger.info("About to create %s (%s) tag on EC2 instance %s with value: %s" % (schedule_tag, instance.id, instance_name, tag_value))
            tags = [{
                "Key" : schedule_tag,
                "Value" : tag_value
            }]
            instance.create_tags(Tags=tags)
        except Exception as e:
            logger.error("Error adding Tag to EC2 instance: %s" % e)
    elif autoscaling and debug:
        logger.info("Ignoring EC2 instance %s, part of an auto scaling group." % instance.id)
    elif instance.id in exclude_list:
        logger.info("Ignoring EC2 instance %s (%s), in exclude_list." % (instance.id, instance_name))

#
# Loop EC2 instances and check if a 'schedule' tag has been set. Next, evaluate value and start/stop instance if needed.
#
def ec2_check():
    # Get current day + hour (using gmt by default if time parameter not set to local)
    time_zone = os.getenv('TIME', 'gmt')
    if time_zone == 'local':
        hh = time.strftime("%k", time.localtime()).strip()
        day = time.strftime("%a", time.localtime()).lower()
    else:
        hh = time.strftime("%k", time.gmtime()).strip()
        day = time.strftime("%a", time.gmtime()).lower()

    logger.info("--> Checking for EC2 instances to start or stop for '%s' hour '%s' on '%s'." %(time_zone, hh, day))

    # Get all reservations.
    instances = ec2.instances.filter(Filters=[{'Name': 'instance-state-name', 'Values': ['pending','running','stopping','stopped']}])

    started = []
    stopped = []
    excluded = []

    if not instances:
        logger.error('---> Unable to find any EC2 Instances, please check configuration.')
    else:
        logger.info('---> Checking %s EC2 instances found.' % len(list(instances)))

    for instance in instances:
        if debug:
            logger.info("Evaluating EC2 instance %s." % instance.id)

        if not instance.tags:
            logger.info("----> No tags found on EC2 instance %s, please check." % instance.id)
            excluded.append(instance.id)

        else:
            instance_name = "name not set"
            for tag in instance.tags:
                if 'Name' in tag['Key']:
                    instance_name = tag['Value']
                    break

            try:
                data = ""
                for tag in instance.tags:
                    if schedule_tag in tag['Key']:
                        data = tag['Value']
                        break

                if data == "":
                    if debug:
                        logger.info("No 'Schedule' tag found on EC2 instance %s (%s)." % (instance.id, instance_name))
                    create_schedule_tag(instance)
                    excluded.append(instance.id)
                else:
                    logger.info("----> EC2 instance %s (%s) schedule is '%s'." %(instance.id, instance_name, data))
                    schedule = dict(x.split('=') for x in data.split(' '))

                    if debug:
                        for k, v in schedule.items():
                            logger.info("Key '%s' Value '%s'." %(k, v))

                    start_match = False
                    if day+'_start' in schedule and hh == schedule[day+'_start']:
                        start_match = True
                    elif 'any_start' in schedule and hh == schedule['any_start']:
                        start_match = True
                    elif 'work_start' in schedule and day in 'mon tue wed thu fri'.split(' ') and hh == schedule['work_start']:
                        start_match = True

                    if start_match:
                        logger.info("-----> Start time %s matches .." % hh)
                        if not instance.state["Name"] == 'running':
                            logger.info("-----> EC2 instance %s is not running, starting .." %(instance.id))
                            started.append(instance.id + ' (' + instance_name + ')')
                            ec2.instances.filter(InstanceIds=[instance.id]).start()
                        else:
                            logger.info("-----> EC2 instance %s is already running." %(instance.id))

                    stop_match = False
                    if day+'_stop' in schedule and hh == schedule[day+'_stop']:
                        stop_match = True
                    elif 'any_stop' in schedule and hh == schedule['any_stop']:
                        stop_match = True
                    elif 'work_stop' in schedule and day in 'mon tue wed thu fri'.split(' ') and hh == schedule['work_stop']:
                        stop_match = True

                    if stop_match:
                        logger.info("-----> Stop time %s matches .." % hh)
                        if instance.state["Name"] == 'running':
                            logger.info("-----> EC2 instance %s is running, stopping .." %(instance.id))
                            stopped.append(instance.id + ' (' + instance_name + ')')
                            ec2.instances.filter(InstanceIds=[instance.id]).stop()
                        else:
                            logger.info("-----> EC2 instance %s is already not running." %(instance.id))

            except ValueError as e:
                # invalid tag?
                logger.error("Invalid value for tag 'Schedule' on EC2 instance %s, please check!" %(instance.id))

    logger.info("<--- Started %s EC2 instances:" % len(started))
    for i in started:
        logger.info("<---- %s" % i)

    logger.info("<--- Stopped %s EC2 instances:" % len(stopped))
    for i in stopped:
        logger.info("<---- %s" % i)

    logger.info("<--- Untagged, excluded & autoscaling instances: %s." % len(excluded))

#
# Add default 'Schedule' tag to instance.
# (Only if instance.id not excluded and create_schedule_tag_force variable is True.
#
def rds_create_schedule_tag(instance):
    exclude_list = os.environ.get('EXCLUDE').split(',')

    if (create_schedule_tag_force == 'True') and (instance['DBInstanceIdentifier'] not in exclude_list):
        try:
            tag_value = os.getenv('DEFAULT', 'any_start=5')
            logger.info("About to create %s tag on RDS instance %s with value: %s" % (schedule_tag,instance['DBInstanceIdentifier'],tag_value))
            tags = [{
                "Key" : schedule_tag,
                "Value" : tag_value
            }]
            rds.add_tags_to_resource(ResourceName=instance['DBInstanceArn'],Tags=tags)
        except Exception as e:
            logger.error("Error adding Tag to RDS instance: %s" % e)
    elif instance['DBInstanceIdentifier'] in exclude_list:
        logger.info("Ignoring RDS instance %s, in exclude_list." % instance['DBInstanceIdentifier'])

#
# Loop RDS instances and check if a 'Schedule' tag has been set. Next, evaluate value and start/stop instance if needed.
#
def rds_check():
    # Get current day + hour (using gmt by default if time parameter not set to local)
    time_zone = os.getenv('TIME', 'gmt')
    if time_zone == 'local':
        hh = time.strftime("%k", time.localtime()).strip()
        day = time.strftime("%a", time.localtime()).lower()
    else:
        hh = time.strftime("%k", time.gmtime()).strip()
        day = time.strftime("%a", time.gmtime()).lower()

    logger.info("--> Checking for RDS instances to start or stop for '%s' hour '%s' on '%s'." %(time_zone, hh, day))

    # Get all reservations.
    instances = rds.describe_db_instances()

    started = []
    stopped = []
    excluded = []

    if not instances:
        logger.error('---> Unable to find any RDS instances, please check configuration.')
    else:
        logger.info('---> Checking %s RDS instances found.' % len(instances['DBInstances']))

    for instance in instances['DBInstances']:
        if debug:
            logger.info("Evaluating RDS instance %s." %(instance['DBInstanceIdentifier']))

        response = rds.list_tags_for_resource(ResourceName=instance['DBInstanceArn'])
        taglist = response['TagList']

        try:
            data = ""
            for tag in taglist:
                if schedule_tag in tag['Key']:
                    data = tag['Value']
                    break

            if data == "":
                if debug:
                    logger.info("No 'Schedule' tag found on RDS instance %s." % instance['DBInstanceIdentifier'])
                rds_create_schedule_tag(instance)
                excluded.append(instance['DBInstanceIdentifier'])
            else:
                logger.info("----> RDS instance %s schedule is '%s'." % (instance['DBInstanceIdentifier'], data))
                schedule = dict(x.split('=') for x in data.split(' '))

                start_match = False
                if day+'_start' in schedule and hh == schedule[day+'_start']:
                    start_match = True
                elif 'any_start' in schedule and hh == schedule['any_start']:
                    start_match = True
                elif 'work_start' in schedule and day in 'mon tue wed thu fri'.split(' ') and hh == schedule['work_start']:
                    start_match = True

                if start_match:
                    logger.info("-----> Start time %s matches .." % hh)
                    if not instance['DBInstanceStatus'] == 'available':
                        logger.info("-----> RDS instance %s is not available, starting .." %(instance['DBInstanceIdentifier']))
                        started.append(instance['DBInstanceIdentifier'])
                        rds.start_db_instance(DBInstanceIdentifier=instance['DBInstanceIdentifier'])
                    else:
                        logger.info("-----> RDS instance %s is already available." %(instance['DBInstanceIdentifier']))

                stop_match = False
                if day+'_stop' in schedule and hh == schedule[day+'_stop']:
                    stop_match = True
                elif 'any_stop' in schedule and hh == schedule['any_stop']:
                    stop_match = True
                elif 'work_stop' in schedule and day in 'mon tue wed thu fri'.split(' ') and hh == schedule['work_stop']:
                    stop_match = True

                if stop_match:
                    logger.info("-----> Stop time %s matches .." % hh)
                    if instance['DBInstanceStatus'] == 'available':
                        logger.info("-----> RDS instance %s is available, stopping .." %(instance['DBInstanceIdentifier']))
                        stopped.append(instance['DBInstanceIdentifier'])
                        rds.stop_db_instance(DBInstanceIdentifier=instance['DBInstanceIdentifier'])
                    else:
                        logger.info("-----> RDS instance %s is already not available." %(instance['DBInstanceIdentifier']))

        except ValueError as e:
            # invalid tag?
            logger.error("Invalid value for tag 'Schedule' on RDS instance %s, please check!" %(instance['DBInstanceIdentifier']))

    logger.info("<--- Started %s RDS instances:" % len(started))
    for i in started:
        logger.info("<---- %s" % i)

    logger.info("<--- Stopped %s RDS instances:" % len(stopped))
    for i in stopped:
        logger.info("<---- %s" % i)

    logger.info("<--- Untagged & excluded instances: %s." % len(excluded))

# Main function. Entrypoint for Lambda
def handler(event, context):

    if (ec2_schedule == 'True'):
        ec2_init()
        ec2_check()

    if (rds_schedule == 'True'):
        rds_init()
        rds_check()

# Manual invocation of the script (only used for testing)
if __name__ == "__main__":
    # Test data
    test = {}
    handler(test, None)
