# instance-scheduler
Stop and start EC2 and RDS instances according to schedule via Lambda and CloudWatch.

Based on [terraform-aws-lambda-scheduler](https://github.com/neillturner/terraform-aws-lambda-scheduler) by Neill Turner. Main changes: 1) same string tags on RDS and EC2, 2) support 'any' day, 3) check for no tags on EC2 (throws error).

# Overview
The scheduler looks at the schedule tag to see if it needs to stop or start and instance.<br>
It works by setting a tag (default name Schedule) to a string giving the stop and start time hour for each day.

A schedule tag for an EC2 and a RDS instance is a string of keyword parameters separated by a space. Following is also valid using 'any' day:
```
any_stop=20 mon_start=7 tue_start=7 wed_start=7 thu_start=7 fri_start=7
```

It ignores instances that are part of autoscaling groups assuming scheduling actions can be used to stop and start these instances.<br>
The scheduler can be configured to add a default schedule tag to EC2 and RDS instances it finds without a schedule tag.

## Requirements
This module requires Terraform version `0.11.x` or newer.

## Dependencies
This module depends on a correctly configured [AWS Provider](https://www.terraform.io/docs/providers/aws/index.html) in your Terraform codebase.

## Usage
```
module "instance_scheduler" {
  source = "../../modules/instance_scheduler"

  # schedule_expression = "rate(5 minutes)" # When debugging
  # schedule_expression = "cron(5 * * * ? *)" # Default, every hour:05
  tag = "Schedule"
  default = "any_start=7"
  time = "local"
  ec2_schedule = "true"
  rds_schedule = "true"

  environment = "${var.environment}"
  base_tags = "${module.tagging.base_tags}"
}
```
## Variables

### schedule_expression
The aws cloudwatch event rule schedule expression that specifies when the scheduler runs.<br>
Default = `cron(5 * * * ? *)` i.e. 5 minuts past the hour. For debugging use `rate(5 minutes)`. See [ScheduledEvents](https://docs.aws.amazon.com/AmazonCloudWatch/latest/events/ScheduledEvents.html).

### tag
The tag name used on the EC2 and RDS instance to contain the schedule string for the instance, default is 'Schedule'.

### schedule_tag_force
Whether to force the EC2 and RDS instance to have the default schedule tag if no schedule tag exists for the instance.

Default is false. If set to true it with create a default schedule tag for each instance it finds.

### exclude
String containing comma separated list of ECS2 and RDS instance ids to exclude from scheduling.

### default
The default schedule tag containing schedule information to add to EC2 or RDS instance when schedule_tag_force set to true. Default for default is: `any_start=5`.

### time
Timezone to use for scheduler. Can be 'local' or 'gmt', default is gmt. Local time is for the AWS region.

### ec2_schedule
Whether to do scheduling for EC2 instances, default = "true".

### rds_schedule
Whether to do scheduling for RDS instances, default = "true".

### security_group_ids
List of the vpc security groups to run lambda scheduler in, defaults to []. Usually this does not need to be specified.

### subnet_ids
List of subnet_ids that the scheduler runs in, defaults to []. Usually this does not need to be specified.
