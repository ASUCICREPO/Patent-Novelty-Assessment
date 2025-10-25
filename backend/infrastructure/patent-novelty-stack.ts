import * as cdk from "aws-cdk-lib";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as s3n from "aws-cdk-lib/aws-s3-notifications";
import * as iam from "aws-cdk-lib/aws-iam";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as ecrAssets from "aws-cdk-lib/aws-ecr-assets";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as os from "os";
import * as path from "path";
import { Construct } from "constructs";

export class PatentNoveltyStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, props);

    const accountId = this.account;
    const region = this.region;

    // Architecture detection like the working project
    const hostArchitecture = os.arch();
    console.log(`Host architecture: ${hostArchitecture}`);

    const lambdaArchitecture =
      hostArchitecture === "arm64"
        ? lambda.Architecture.ARM_64
        : lambda.Architecture.X86_64;
    console.log(`Lambda architecture: ${lambdaArchitecture}`);

    // S3 Bucket for PDF processing
    const processingBucket = new s3.Bucket(this, "PdfProcessingBucket", {
      bucketName: `patent-novelty-pdf-processing-${accountId}`,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      versioned: false,
      publicReadAccess: false,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      cors: [
        {
          allowedHeaders: ["*"],
          allowedMethods: [
            s3.HttpMethods.GET,
            s3.HttpMethods.PUT,
            s3.HttpMethods.POST,
          ],
          allowedOrigins: ["*"],
          exposedHeaders: [],
          maxAge: 3000,
        },
      ],
    });

    // DynamoDB table for storing patent analysis (keywords, title, descriptions)
    const keywordsTable = new dynamodb.Table(this, "PatentKeywordsTable", {
      tableName: `patent-keywords-${accountId}`,
      partitionKey: {
        name: "pdf_filename",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: "timestamp", type: dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    // DynamoDB table for storing USPTO patent search results
    const patentResultsTable = new dynamodb.Table(this, "PatentResultsTable", {
      tableName: `patent-search-results-${accountId}`,
      partitionKey: {
        name: "pdf_filename",
        type: dynamodb.AttributeType.STRING,
      },
      sortKey: { name: "patent_number", type: dynamodb.AttributeType.STRING },
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
    });

    // DynamoDB table for storing scholarly article search results
    const scholarlyArticlesTable = new dynamodb.Table(
      this,
      "ScholarlyArticlesTable",
      {
        tableName: `scholarly-articles-results-${accountId}`,
        partitionKey: {
          name: "pdf_filename",
          type: dynamodb.AttributeType.STRING,
        },
        sortKey: { name: "article_doi", type: dynamodb.AttributeType.STRING },
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      }
    );

    // DynamoDB table for storing early commercial assessment results
    const commercialAssessmentTable = new dynamodb.Table(
      this,
      "CommercialAssessmentTable",
      {
        tableName: `early-commercial-assessment-${accountId}`,
        partitionKey: {
          name: "pdf_filename",
          type: dynamodb.AttributeType.STRING,
        },
        sortKey: { name: "timestamp", type: dynamodb.AttributeType.STRING },
        removalPolicy: cdk.RemovalPolicy.DESTROY,
        billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      }
    );

    // Lambda execution role with BDA permissions
    const lambdaRole = new iam.Role(this, "PdfProcessorLambdaRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
      inlinePolicies: {
        BdaAndS3Access: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "bedrock:InvokeDataAutomationAsync",
                "bedrock:GetDataAutomationStatus",
              ],
              resources: ["*"],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
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
    const bdaProjectArn = this.node.tryGetContext("bdaProjectArn");
    if (!bdaProjectArn) {
      throw new Error(
        "BDA Project ARN must be provided via context. Run deployment script instead of direct CDK deploy."
      );
    }

    // Get Agent Runtime ARN from context (passed by deployment script)
    const agentRuntimeArn = this.node.tryGetContext("agentRuntimeArn");
    if (!agentRuntimeArn) {
      throw new Error(
        "Agent Runtime ARN must be provided via context. Run deployment script instead of direct CDK deploy."
      );
    }

    // Lambda function for PDF processing
    const pdfProcessorFunction = new lambda.Function(
      this,
      "PdfProcessorFunction",
      {
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: "pdf_processor.lambda_handler",
        code: lambda.Code.fromAsset("lambda"),
        role: lambdaRole,
        timeout: cdk.Duration.minutes(15),
        memorySize: 512,
        environment: {
          BUCKET_NAME: processingBucket.bucketName,
          BDA_PROJECT_ARN: bdaProjectArn,
        },
      }
    );

    // Lambda function for triggering agent when BDA completes
    const agentTriggerFunction = new lambda.Function(
      this,
      "AgentTriggerFunction",
      {
        runtime: lambda.Runtime.PYTHON_3_12,
        handler: "agent_trigger.lambda_handler",
        code: lambda.Code.fromAsset("lambda"),
        timeout: cdk.Duration.minutes(5),
        memorySize: 256,
        environment: {
          AGENT_RUNTIME_ARN: agentRuntimeArn,
        },
      }
    );

    // Grant agent trigger function permissions to invoke Agent Core
    agentTriggerFunction.addToRolePolicy(
      new iam.PolicyStatement({
        effect: iam.Effect.ALLOW,
        actions: ["bedrock-agentcore:InvokeAgentRuntime"],
        resources: ["*"], // Will be restricted to specific agent ARN later
      })
    );

    // Create API Gateway Lambda functions
    const apiRole = new iam.Role(this, "ApiLambdaRole", {
      assumedBy: new iam.ServicePrincipal("lambda.amazonaws.com"),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName(
          "service-role/AWSLambdaBasicExecutionRole"
        ),
      ],
      inlinePolicies: {
        ApiAccessPolicy: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "s3:GetObject",
                "s3:PutObject",
                "s3:DeleteObject",
                "s3:ListBucket",
                "s3:HeadObject",
              ],
              resources: [
                processingBucket.bucketArn,
                `${processingBucket.bucketArn}/*`,
              ],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: [
                "dynamodb:PutItem",
                "dynamodb:GetItem",
                "dynamodb:UpdateItem",
                "dynamodb:Query",
                "dynamodb:Scan",
              ],
              resources: [
                keywordsTable.tableArn,
                patentResultsTable.tableArn,
                scholarlyArticlesTable.tableArn,
                commercialAssessmentTable.tableArn,
              ],
            }),
            new iam.PolicyStatement({
              effect: iam.Effect.ALLOW,
              actions: ["bedrock-agentcore:InvokeAgentRuntime"],
              resources: ["*"],
            }),
          ],
        }),
      },
    });

    // S3 API Lambda function
    const s3ApiFunction = new lambda.Function(this, "S3ApiFunction", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "s3_api.lambda_handler",
      code: lambda.Code.fromAsset("lambda"),
      role: apiRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 256,
      environment: {
        BUCKET_NAME: processingBucket.bucketName,
      },
    });

    // DynamoDB API Lambda function
    const dynamodbApiFunction = new lambda.Function(this, "DynamoDBApiFunction", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "dynamodb_api.lambda_handler",
      code: lambda.Code.fromAsset("lambda"),
      role: apiRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 256,
      environment: {
        KEYWORDS_TABLE: keywordsTable.tableName,
        PATENT_RESULTS_TABLE: patentResultsTable.tableName,
        SCHOLARLY_ARTICLES_TABLE: scholarlyArticlesTable.tableName,
        COMMERCIAL_ASSESSMENT_TABLE: commercialAssessmentTable.tableName,
      },
    });

    // Agent Invoke API Lambda function
    const agentInvokeApiFunction = new lambda.Function(this, "AgentInvokeApiFunction", {
      runtime: lambda.Runtime.PYTHON_3_12,
      handler: "agent_invoke_api.lambda_handler",
      code: lambda.Code.fromAsset("lambda"),
      role: apiRole,
      timeout: cdk.Duration.minutes(5),
      memorySize: 256,
      environment: {
        AGENT_RUNTIME_ARN: agentRuntimeArn,
      },
    });

    // Create API Gateway
    const api = new apigateway.RestApi(this, "PatentNoveltyApi", {
      restApiName: "Patent Novelty Assessment API",
      description: "API for Patent Novelty Assessment application",
      defaultCorsPreflightOptions: {
        allowOrigins: apigateway.Cors.ALL_ORIGINS,
        allowMethods: apigateway.Cors.ALL_METHODS,
        allowHeaders: [
          "Content-Type",
          "X-Amz-Date",
          "Authorization",
          "X-Api-Key",
          "X-Amz-Security-Token",
        ],
      },
    });

    // S3 API endpoints
    const s3Resource = api.root.addResource("s3");
    s3Resource.addMethod("POST", new apigateway.LambdaIntegration(s3ApiFunction));
    s3Resource.addMethod("GET", new apigateway.LambdaIntegration(s3ApiFunction));

    // DynamoDB API endpoints
    const dynamodbResource = api.root.addResource("dynamodb");
    dynamodbResource.addMethod("GET", new apigateway.LambdaIntegration(dynamodbApiFunction));
    dynamodbResource.addMethod("PUT", new apigateway.LambdaIntegration(dynamodbApiFunction));

    // Agent Invoke API endpoints
    const agentInvokeResource = api.root.addResource("agent-invoke");
    agentInvokeResource.addMethod("POST", new apigateway.LambdaIntegration(agentInvokeApiFunction));

    // S3 event notification to trigger Lambda for PDF processing
    processingBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(pdfProcessorFunction),
      { prefix: "uploads/", suffix: ".pdf" }
    );

    // S3 event notification to trigger agent when BDA completes
    processingBucket.addEventNotification(
      s3.EventType.OBJECT_CREATED,
      new s3n.LambdaDestination(agentTriggerFunction),
      { prefix: "temp/docParser/", suffix: "result.json" }
    );

    // Build Docker image for Patent Orchestrator (Single runtime for all agents)
    const patentOrchestratorImage = new ecrAssets.DockerImageAsset(
      this,
      "PatentNoveltyOrchestratorImage",
      {
        directory: path.join(__dirname, "..", "PatentNoveltyOrchestrator"),
        platform:
          lambdaArchitecture === lambda.Architecture.ARM_64
            ? ecrAssets.Platform.LINUX_ARM64
            : ecrAssets.Platform.LINUX_AMD64,
      }
    );

    // Create IAM role for the orchestrator agent
    const patentOrchestratorRole = new iam.Role(
      this,
      "PatentNoveltyOrchestratorRole",
      {
        assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
        description:
          "IAM role for Patent Novelty Orchestrator with S3 and Bedrock permissions",
        managedPolicies: [
          iam.ManagedPolicy.fromAwsManagedPolicyName(
            "BedrockAgentCoreFullAccess"
          ),
          iam.ManagedPolicy.fromAwsManagedPolicyName("AmazonBedrockFullAccess"),
          iam.ManagedPolicy.fromAwsManagedPolicyName("CloudWatchFullAccessV2"),
        ],
        inlinePolicies: {
          S3AccessPolicy: new iam.PolicyDocument({
            statements: [
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  "s3:GetObject",
                  "s3:PutObject",
                  "s3:DeleteObject",
                  "s3:ListBucket",
                ],
                resources: [
                  processingBucket.bucketArn,
                  `${processingBucket.bucketArn}/*`,
                ],
              }),
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  "ecr:GetAuthorizationToken",
                  "ecr:BatchCheckLayerAvailability",
                  "ecr:GetDownloadUrlForLayer",
                  "ecr:BatchGetImage",
                ],
                resources: ["*"],
              }),
              new iam.PolicyStatement({
                effect: iam.Effect.ALLOW,
                actions: [
                  "dynamodb:PutItem",
                  "dynamodb:GetItem",
                  "dynamodb:UpdateItem",
                  "dynamodb:Query",
                  "dynamodb:Scan",
                ],
                resources: [
                  keywordsTable.tableArn,
                  patentResultsTable.tableArn,
                  scholarlyArticlesTable.tableArn,
                  commercialAssessmentTable.tableArn,
                ],
              }),
            ],
          }),
        },
      }
    );

    // Outputs
    new cdk.CfnOutput(this, "BucketName", {
      value: processingBucket.bucketName,
      description: "S3 bucket for PDF processing",
    });

    new cdk.CfnOutput(this, "LambdaFunctionName", {
      value: pdfProcessorFunction.functionName,
      description: "Lambda function for PDF processing",
    });

    new cdk.CfnOutput(this, "PatentOrchestratorDockerImageURI", {
      value: patentOrchestratorImage.imageUri,
      description: "Docker Image URI for Patent Novelty Orchestrator",
    });

    new cdk.CfnOutput(this, "PatentOrchestratorRoleArn", {
      value: patentOrchestratorRole.roleArn,
      description: "IAM Role ARN for Patent Novelty Orchestrator",
    });

    new cdk.CfnOutput(this, "AgentTriggerFunctionName", {
      value: agentTriggerFunction.functionName,
      description: "Lambda function that triggers agent when BDA completes",
    });

    new cdk.CfnOutput(this, "KeywordsTableName", {
      value: keywordsTable.tableName,
      description: "DynamoDB table for storing patent keywords",
    });

    new cdk.CfnOutput(this, "PatentResultsTableName", {
      value: patentResultsTable.tableName,
      description: "DynamoDB table for storing USPTO patent search results",
    });

    new cdk.CfnOutput(this, "ScholarlyArticlesTableName", {
      value: scholarlyArticlesTable.tableName,
      description:
        "DynamoDB table for storing scholarly article search results",
    });

    new cdk.CfnOutput(this, "CommercialAssessmentTableName", {
      value: commercialAssessmentTable.tableName,
      description:
        "DynamoDB table for storing early commercial assessment results",
    });

    // Instructions for Agent Runtime Environment Variables
    new cdk.CfnOutput(this, "AgentRuntimeEnvironmentVariables", {
      value:
        "Set these environment variables in Agent Core console: PATENTVIEW_CLIENT_ID, PATENTVIEW_CLIENT_SECRET, PATENTVIEW_TOKEN_URL, PATENTVIEW_GATEWAY_URL, SEMANTIC_SCHOLAR_CLIENT_ID, SEMANTIC_SCHOLAR_CLIENT_SECRET, SEMANTIC_SCHOLAR_TOKEN_URL, SEMANTIC_SCHOLAR_GATEWAY_URL",
      description:
        "Required environment variables for Agent Runtime Gateway configuration (PatentView OAuth and Semantic Scholar)",
    });

    new cdk.CfnOutput(this, "ApiGatewayUrl", {
      value: api.url,
      description: "API Gateway URL for the Patent Novelty Assessment API",
    });

    new cdk.CfnOutput(this, "S3ApiFunctionName", {
      value: s3ApiFunction.functionName,
      description: "Lambda function for S3 API operations",
    });

    new cdk.CfnOutput(this, "DynamoDBApiFunctionName", {
      value: dynamodbApiFunction.functionName,
      description: "Lambda function for DynamoDB API operations",
    });

    new cdk.CfnOutput(this, "AgentInvokeApiFunctionName", {
      value: agentInvokeApiFunction.functionName,
      description: "Lambda function for Agent Invoke API operations",
    });
  }
}
