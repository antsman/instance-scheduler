# Cloudwatch event rule
resource "aws_cloudwatch_event_rule" "instance-scheduler" {
  name = "instance-scheduler-hourly"
  description = "Stop and start EC2 and RDS instances according to Schedule"
  schedule_expression = "${var.schedule_expression}"
  depends_on = ["aws_lambda_function.instance-scheduler"]
}

# Cloudwatch event target
resource "aws_cloudwatch_event_target" "instance-scheduler" {
    target_id = "instance-scheduler"
    rule = "${aws_cloudwatch_event_rule.instance-scheduler.name}"
    arn = "${aws_lambda_function.instance-scheduler.arn}"
}

# AWS Lambda need a zip file
data "archive_file" "instance-scheduler" {
  type = "zip"
  source_file = "${path.module}/lambda/instance-scheduler.py"
  output_path = "${path.module}/lambda/instance-scheduler.zip"
}

# AWS Lambda function
resource "aws_lambda_function" "instance-scheduler" {
  filename = "${data.archive_file.instance-scheduler.output_path}"
  function_name = "${var.environment}-instance-scheduler"
  description = "Stop and start EC2 and RDS instances according to schedule"
  role = "${aws_iam_role.scheduler-lambda.arn}"
  handler = "instance-scheduler.handler"
  runtime = "python2.7"
  timeout = 300
  source_code_hash = "${data.archive_file.instance-scheduler.output_base64sha256}"
  vpc_config = {
    security_group_ids = "${var.security_group_ids}"
    subnet_ids = "${var.subnet_ids}"
  }
  environment {
    variables = {
      TAG = "${var.tag}"
      SCHEDULE_TAG_FORCE = "${var.schedule_tag_force}"
      EXCLUDE = "${var.exclude}"
      DEFAULT = "${var.default}"
      TIME = "${var.time}"
      RDS_SCHEDULE = "${var.rds_schedule}"
      EC2_SCHEDULE = "${var.ec2_schedule}"
    }
  }
  tags = "${merge(var.base_tags, map(
    "Name", "${var.environment}-instance-scheduler"
  ))}"
}

resource "aws_lambda_permission" "allow-from-cloudwatch" {
  statement_id = "AllowExecutionFromCloudWatch"
  action = "lambda:InvokeFunction"
  function_name = "${aws_lambda_function.instance-scheduler.function_name}"
  principal = "events.amazonaws.com"
  source_arn = "${aws_cloudwatch_event_rule.instance-scheduler.arn}"
}

resource "aws_cloudwatch_log_group" "instance-scheduler" {
  name = "/aws/lambda/${aws_lambda_function.instance-scheduler.function_name}"
  retention_in_days = 30
  tags = "${merge(var.base_tags, map(
    "Name", "${aws_lambda_function.instance-scheduler.function_name}"
  ))}"
}
