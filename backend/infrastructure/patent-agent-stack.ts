import * as cdk from 'aws-cdk-lib';
import { Construct } from 'constructs';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as ecrAssets from 'aws-cdk-lib/aws-ecr-assets';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as os from 'os';
import * as path from 'path';

export class PatentAgentStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    // basic information retrieval before writing resources
    const aws_region = cdk.Stack.of(this).region;
    const accountId = cdk.Stack.of(this).account;
    console.log(`AWS Region: ${aws_region}`);

    const hostArchitecture = os.arch(); 
    console.log(`Host architecture: ${hostArchitecture}`);
    
    const lambdaArchitecture = hostArchitecture === 'arm64' ? lambda.Architecture.ARM_64 : lambda.Architecture.X86_64;
    console.log(`Lambda architecture: ${lambdaArchitecture}`);

    // Get existing S3 bucket from the PDF processing stack
    const bucketName = `patent-novelty-pdf-processing-${accountId}`;

    // Build Docker image and push to ECR as part of CDK deployment
    const patentAgentImage = new ecrAssets.DockerImageAsset(this, 'PatentNoveltyAgentImage', {
      directory: path.join(__dirname, '..', '..', 'PatentNoveltyAgent'),
      platform: ecrAssets.Platform.LINUX_ARM64,   // Always ARM64 for Bedrock Agent Core
    });

    // Create IAM role for the agent (for manual console setup)
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
                `arn:aws:s3:::${bucketName}`,
                `arn:aws:s3:::${bucketName}/*`,
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

    // Outputs for manual console setup
    new cdk.CfnOutput(this, 'PatentAgentDockerImageURI', {
      value: patentAgentImage.imageUri,
      description: 'Docker Image URI for Patent Novelty Agent',
      exportName: 'PatentNoveltyAgentImageURI',
    });

    new cdk.CfnOutput(this, 'PatentAgentRoleArn', {
      value: patentAgentRole.roleArn,
      description: 'IAM Role ARN for Patent Novelty Agent',
      exportName: 'PatentNoveltyAgentRoleArn',
    });

    new cdk.CfnOutput(this, 'S3BucketName', {
      value: bucketName,
      description: 'S3 Bucket name for patent processing',
      exportName: 'PatentProcessingBucketName',
    });
  }
}
