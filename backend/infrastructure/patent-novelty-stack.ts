import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as ecrAssets from 'aws-cdk-lib/aws-ecr-assets';
import * as os from 'os';
import * as path from 'path';
import { Construct } from 'constructs';

export class PatentNoveltyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const accountId = this.account;
    const region = this.region;

    // S3 Bucket for PDF processing
    const processingBucket = new s3.Bucket(this, 'PdfProcessingBucket', {
      bucketName: `patent-novelty-pdf-processing-${accountId}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: false,
      publicReadAccess: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // Lambda execution role with BDA permissions
    const lambdaRole = new iam.Role(this, 'PdfProcessorLambdaRole', {
      assumedBy: new iam.ServicePrincipal('lambda.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AWSLambdaBasicExecutionRole'),
      ],
      inlinePolicies: {
        BdaAndS3Access: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'bedrock:InvokeDataAutomationAsync',
                'bedrock:GetDataAutomationStatus',
              ],
              resources: ['*'],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                's3:GetObject',
                's3:PutObject',
                's3:DeleteObject',
                's3:ListBucket',
              ],
              resources: [
                processingBucket.bucketArn,
                `${processingBucket.bucketArn}/*`,
              ],
            }),
          ],
        }),
      },
    });

    // Lambda function for PDF processing
    const pdfProcessorFunction = new lambda.Function(this, 'PdfProcessorFunction', {
      runtime: lambda.Runtime.NODEJS_20_X,
      handler: 'index.handler',
      code: lambda.Code.fromAsset('backend/lambda/pdf-processor'),
      role: lambdaRole,
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      environment: {
        BUCKET_NAME: processingBucket.bucketName,
        BDA_PROJECT_ARN: '', // Will be set after BDA project creation
      },
    });

    // S3 event notification to trigger Lambda
    processingBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(pdfProcessorFunction),
      { prefix: 'uploads/', suffix: '.pdf' }
    );

    // Build Docker image for Patent Agent
    const patentAgentImage = new ecrAssets.DockerImageAsset(this, 'PatentNoveltyAgentImage', {
      directory: path.join(__dirname, '..', 'PatentNoveltyAgent'),
      platform: ecrAssets.Platform.LINUX_ARM64,
    });

    // Create IAM role for the agent
    const patentAgentRole = new iam.Role(this, 'PatentNoveltyAgentRole', {
      assumedBy: new iam.ServicePrincipal('bedrock-agentcore.amazonaws.com'),
      description: 'IAM role for Patent Novelty Agent with S3 and Bedrock permissions',
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('BedrockAgentCoreFullAccess'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('AmazonBedrockFullAccess'),
        iam.ManagedPolicy.fromAwsManagedPolicyName('CloudWatchFullAccessV2'),
      ],
      inlinePolicies: {
        S3AccessPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                's3:GetObject',
                's3:PutObject',
                's3:DeleteObject',
                's3:ListBucket',
              ],
              resources: [
                processingBucket.bucketArn,
                `${processingBucket.bucketArn}/*`,
              ],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'ecr:GetAuthorizationToken',
                'ecr:BatchCheckLayerAvailability',
                'ecr:GetDownloadUrlForLayer',
                'ecr:BatchGetImage',
              ],
              resources: ['*'],
            }),
          ],
        }),
      },
    });

    // Outputs
    new cdk.CfnOutput(this, 'BucketName', {
      value: processingBucket.bucketName,
      description: 'S3 bucket for PDF processing',
    });

    new cdk.CfnOutput(this, 'LambdaFunctionName', {
      value: pdfProcessorFunction.functionName,
      description: 'Lambda function for PDF processing',
    });

    new cdk.CfnOutput(this, 'PatentAgentDockerImageURI', {
      value: patentAgentImage.imageUri,
      description: 'Docker Image URI for Patent Novelty Agent',
    });

    new cdk.CfnOutput(this, 'PatentAgentRoleArn', {
      value: patentAgentRole.roleArn,
      description: 'IAM Role ARN for Patent Novelty Agent',
    });
  }
}
