import { S3Event, S3Handler } from 'aws-lambda';
import { BedrockDataAutomationRuntimeClient, InvokeDataAutomationAsyncCommand } from '@aws-sdk/client-bedrock-data-automation-runtime';
import { STSClient, GetCallerIdentityCommand } from '@aws-sdk/client-sts';

const bdaClient = new BedrockDataAutomationRuntimeClient({ region: process.env.AWS_REGION });
const stsClient = new STSClient({ region: process.env.AWS_REGION });

export const handler: S3Handler = async (event: S3Event) => {
  console.log('Received S3 event:', JSON.stringify(event, null, 2));

  for (const record of event.Records) {
    const bucketName = record.s3.bucket.name;
    const objectKey = decodeURIComponent(record.s3.object.key.replace(/\+/g, ' '));

    console.log(`Processing file: ${objectKey} from bucket: ${bucketName}`);

    try {
      // Validate it's a PDF in uploads/ folder
      if (!objectKey.startsWith('uploads/') || !objectKey.toLowerCase().endsWith('.pdf')) {
        console.log(`Skipping non-PDF file or file not in uploads/ folder: ${objectKey}`);
        continue;
      }

      // Extract filename for output naming
      const fileName = objectKey.split('/').pop()?.replace('.pdf', '') || 'unknown';
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      
      // Define output path
      const outputPrefix = `temp/docParser/${fileName}-${timestamp}/`;

      // Get account ID for profile ARN
      const identity = await stsClient.send(new GetCallerIdentityCommand({}));
      const accountId = identity.Account;
      const region = process.env.AWS_REGION;
      
      // Construct standard profile ARN
      const profileArn = `arn:aws:bedrock:${region}:${accountId}:data-automation-profile/us.data-automation-v1`;

      // Invoke BDA project
      const bdaCommand = new InvokeDataAutomationAsyncCommand({
        inputConfiguration: {
          s3Uri: `s3://${bucketName}/${objectKey}`,
        },
        outputConfiguration: {
          s3Uri: `s3://${bucketName}/${outputPrefix}`,
        },
        dataAutomationConfiguration: {
          dataAutomationProjectArn: process.env.BDA_PROJECT_ARN,
          stage: 'LIVE',
        },
        dataAutomationProfileArn: profileArn,
        clientToken: `pdf-processing-${timestamp}-${Math.random().toString(36).substring(7)}`,
      });

      const response = await bdaClient.send(bdaCommand);
      console.log('BDA invocation response:', JSON.stringify(response, null, 2));

      console.log(`Successfully initiated BDA processing for ${objectKey}`);
      console.log(`Output will be stored in: s3://${bucketName}/${outputPrefix}`);
      console.log(`Invocation ARN: ${response.invocationArn}`);

    } catch (error) {
      console.error(`Error processing ${objectKey}:`, error);
      throw error;
    }
  }
};
