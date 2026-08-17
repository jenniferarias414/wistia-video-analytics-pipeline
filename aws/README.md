# AWS Resource Setup Reference

This folder records the AWS CLI and IAM patterns used to build the Wistia video analytics pipeline.

These files are reference material for understanding and recreating the environment after teardown. Secrets are not stored here.

## Resource Flow

```text
EventBridge
    ↓
Lambda
    ↓
Wistia API
    ↓
S3 raw

S3 raw
    ↓
Glue PySpark
    ↓
S3 curated
```

## IAM Pattern

For an AWS service that needs to access another AWS resource:

```text
1. Create trust policy
2. Create IAM role using trust policy
3. Attach AWS-managed service policy
4. Create project-specific access policy
5. Attach project-specific policy to role
6. Assign role to Lambda / Glue
7. Verify role and permissions
```

### Trust Policy

Answers:

> Who is allowed to assume this role?

Examples:

```text
lambda.amazonaws.com
glue.amazonaws.com
```

### Managed Service Policy

Provides standard AWS service permissions.

Used in this project:

```text
AWSLambdaBasicExecutionRole
AWSGlueServiceRole
```

### Project-Specific Policy

Provides access only to resources required by this project.

Examples:

```text
Lambda:
S3 GetObject + PutObject

Glue:
S3 ListBucket + GetObject + PutObject + DeleteObject
```

Glue needs `DeleteObject` because curated Parquet output is overwritten during each transformation run.

## Resources

### S3

Bucket:

```text
wistia-video-analytics-dea
```

Logical prefixes:

```text
raw/
state/
scripts/
curated/
```

S3 does not need its own IAM role. Lambda and Glue receive permission to access it through their execution roles.

### Lambda

Function:

```text
wistia-video-analytics-ingestion
```

Role:

```text
wistia-video-analytics-lambda-role
```

Trust principal:

```text
lambda.amazonaws.com
```

Managed policy:

```text
AWSLambdaBasicExecutionRole
```

Custom policy:

```text
WistiaVideoAnalyticsS3Access
```

### EventBridge

Rule:

```text
wistia-video-analytics-schedule
```

Target:

```text
wistia-video-analytics-ingestion
```

The test schedule was:

```text
rate(5 minutes)
```

The final schedule is:

```text
rate(1 day)
```

This implementation does not use a separate EventBridge IAM execution role.

Instead:

1. Lambda grants `events.amazonaws.com` permission to invoke the function.
2. The Lambda function is registered as the EventBridge rule target.

### Glue

Role:

```text
AWSGlueServiceRole-wistia-video-analytics
```

Trust principal:

```text
glue.amazonaws.com
```

Managed policy:

```text
AWSGlueServiceRole
```

Custom policy:

```text
WistiaVideoAnalyticsS3Access
```

The Glue job reads raw JSON from S3 and writes curated Parquet back to the same project bucket.

### CloudWatch

Lambda automatically writes logs under:

```text
/aws/lambda/wistia-video-analytics-ingestion
```

The log group was created automatically when Lambda executed.

## Security

The Wistia API token must never be stored in this folder or committed to Git.

The committed files contain only:

- resource names
- IAM policy definitions
- non-secret AWS CLI examples

The actual Wistia credential is supplied separately at runtime.

## Why These Files Are Kept

The AWS resources for this project will eventually be torn down to avoid unnecessary costs.

Keeping the policy JSON and CLI setup reference in the repository provides a record of:

- which AWS resources were created
- how IAM trust relationships work
- which permissions each service required
- how the resources were connected
- the AWS CLI commands used to build the environment

This makes it possible to review or recreate the architecture after the live AWS resources have been deleted.
