import * as cdk from 'aws-cdk-lib';
import * as s3 from 'aws-cdk-lib/aws-s3';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as dynamodb from 'aws-cdk-lib/aws-dynamodb';
import * as ecrAssets from 'aws-cdk-lib/aws-ecr-assets';
import * as os from 'os';
import * as path from 'path';
import { Construct } from 'constructs';

export class PatentNoveltyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const accountId = this.account;
    const region = this.region;
    
    // Architecture detection like the working project
    const hostArchitecture = os.arch(); 
    console.log(`Host architecture: ${hostArchitecture}`);
    
    const lambdaArchitecture = hostArchitecture === 'arm64' ? lambda.Architecture.ARM_64 : lambda.Architecture.X86_64;
    console.log(`Lambda architecture: ${lambdaArchitecture}`);

    // S3 Bucket for PDF processing
    const processingBucket = new s3.Bucket(this, 'PdfProcessingBucket', {
      bucketName: `patent-novelty-pdf-processing-${accountId}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: false,
      publicReadAccess: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // DynamoDB table for storing patent keywords
    const keywordsTable = new dynamodb.Table(this, 'PatentKeywordsTable', {
      tableName: `patent-keywords-${accountId}`,
      partitionKey: { name: 'pdf_filename', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'timestamp', type: dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    // DynamoDB table for storing USPTO patent search results
    const patentResultsTable = new dynamodb.Table(this, 'PatentResultsTable', {
      tableName: `patent-search-results-${accountId}`,
      partitionKey: { name: 'pdf_filename', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'patent_number', type: dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    // DynamoDB table for storing scholarly article search results
    const scholarlyArticlesTable = new dynamodb.Table(this, 'ScholarlyArticlesTable', {
      tableName: `scholarly-articles-results-${accountId}`,
      partitionKey: { name: 'pdf_filename', type: dynamodb.AttributeType.STRING },
      sortKey: { name: 'article_doi', type: dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
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

    // Get BDA Project ARN from context (passed by deployment script)
    const bdaProjectArn = this.node.tryGetContext('bdaProjectArn');
    if (!bdaProjectArn) {
      throw new Error('BDA Project ARN must be provided via context. Run deployment script instead of direct CDK deploy.');
    }

    // Lambda function for PDF processing
    const pdfProcessorFunction = new lambda.Function(this, 'PdfProcessorFunction', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'pdf_processor.lambda_handler',
      code: lambda.Code.fromAsset('backend/lambda'),
      role: lambdaRole,
      timeout: cdk.Duration.minutes(15),
      memorySize: 512,
      environment: {
        BUCKET_NAME: processingBucket.bucketName,
        BDA_PROJECT_ARN: bdaProjectArn,
      },
    });

    // Lambda function for triggering agent when BDA completes
    const agentTriggerFunction = new lambda.Function(this, 'AgentTriggerFunction', {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: 'agent_trigger.lambda_handler',
      code: lambda.Code.fromAsset('backend/lambda'),
      timeout: cdk.Duration.minutes(5),
      memorySize: 256,
      environment: {
        // NOTE: This ARN must be updated after manually creating Agent Core Runtime in AWS Console
        // Format: arn:aws:bedrock-agentcore:REGION:ACCOUNT:runtime/RUNTIME-ID
        AGENT_RUNTIME_ARN: 'arn:aws:bedrock-agentcore:us-west-2:216989103356:runtime/PatentNovelty-dTEUy8Ar35',
      },
    });

    // Grant agent trigger function permissions to invoke Agent Core
    agentTriggerFunction.addToRolePolicy(new iam.PolicyStatement({
      effect: iam.Effect.ALLOW,
      actions: ['bedrock-agentcore:InvokeAgentRuntime'],
      resources: ['*'], // Will be restricted to specific agent ARN later
    }));

    // S3 event notification to trigger Lambda for PDF processing
    processingBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(pdfProcessorFunction),
      { prefix: 'uploads/', suffix: '.pdf' }
    );

    // S3 event notification to trigger agent when BDA completes
    processingBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(agentTriggerFunction),
      { prefix: 'temp/docParser/', suffix: 'result.json' }
    );

    // Build Docker image for Patent Agent with dynamic platform selection
    const patentAgentImage = new ecrAssets.DockerImageAsset(this, 'PatentNoveltyAgentImage', {
      directory: path.join(__dirname, '..', 'PatentNoveltyAgent'),
      platform: lambdaArchitecture === lambda.Architecture.ARM_64 
        ? ecrAssets.Platform.LINUX_ARM64 
        : ecrAssets.Platform.LINUX_AMD64,
    });

    // Build Docker image for Patent Orchestrator (NEW - Single runtime for all agents)
    const patentOrchestratorImage = new ecrAssets.DockerImageAsset(this, 'PatentNoveltyOrchestratorImage', {
      directory: path.join(__dirname, '..', 'PatentNoveltyOrchestrator'),
      platform: lambdaArchitecture === lambda.Architecture.ARM_64 
        ? ecrAssets.Platform.LINUX_ARM64 
        : ecrAssets.Platform.LINUX_AMD64,
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
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                'dynamodb:PutItem',
                'dynamodb:GetItem',
                'dynamodb:UpdateItem',
                'dynamodb:Query',
                'dynamodb:Scan',
              ],
              resources: [keywordsTable.tableArn, patentResultsTable.tableArn, scholarlyArticlesTable.tableArn],
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
      description: 'Docker Image URI for Patent Novelty Agent (Individual - Fallback)',
    });

    new cdk.CfnOutput(this, 'PatentOrchestratorDockerImageURI', {
      value: patentOrchestratorImage.imageUri,
      description: 'Docker Image URI for Patent Novelty Orchestrator (Recommended)',
    });

    new cdk.CfnOutput(this, 'PatentAgentRoleArn', {
      value: patentAgentRole.roleArn,
      description: 'IAM Role ARN for Patent Novelty Agents (Both Individual and Orchestrator)',
    });

    new cdk.CfnOutput(this, 'AgentTriggerFunctionName', {
      value: agentTriggerFunction.functionName,
      description: 'Lambda function that triggers agent when BDA completes',
    });

    new cdk.CfnOutput(this, 'KeywordsTableName', {
      value: keywordsTable.tableName,
      description: 'DynamoDB table for storing patent keywords',
    });

    new cdk.CfnOutput(this, 'PatentResultsTableName', {
      value: patentResultsTable.tableName,
      description: 'DynamoDB table for storing USPTO patent search results',
    });

    new cdk.CfnOutput(this, 'ScholarlyArticlesTableName', {
      value: scholarlyArticlesTable.tableName,
      description: 'DynamoDB table for storing scholarly article search results',
    });

    // Instructions for Agent Runtime Environment Variables
    new cdk.CfnOutput(this, 'AgentRuntimeEnvironmentVariables', {
      value: 'Set these environment variables in Agent Core console: GATEWAY_CLIENT_ID, GATEWAY_CLIENT_SECRET, GATEWAY_TOKEN_URL, GATEWAY_URL, CROSSREF_CLIENT_ID, CROSSREF_CLIENT_SECRET, CROSSREF_TOKEN_URL, CROSSREF_GATEWAY_URL',
      description: 'Required environment variables for Agent Runtime Gateway configuration',
    });
  }
}
