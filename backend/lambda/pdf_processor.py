import json
import boto3
import os
from urllib.parse import unquote_plus
from datetime import datetime
from typing import Dict, Any

# Initialize clients
bda_client = boto3.client('bedrock-data-automation-runtime', region_name=os.environ.get('AWS_REGION'))
sts_client = boto3.client('sts', region_name=os.environ.get('AWS_REGION'))

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Triggered when PDF is uploaded to S3 uploads/ folder.
    Invokes BDA to process the PDF and extract text/images.
    """
    print(f"Received S3 event: {json.dumps(event, indent=2)}")
    
    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        object_key = unquote_plus(record['s3']['object']['key'])
        
        print(f"Processing file: {object_key} from bucket: {bucket_name}")
        
        try:
            # Validate it's a PDF in uploads/ folder
            if not object_key.startswith('uploads/') or not object_key.lower().endswith('.pdf'):
                print(f"Skipping non-PDF file or file not in uploads/ folder: {object_key}")
                continue
            
            # Extract filename for output naming
            filename = object_key.split('/')[-1].replace('.pdf', '') if '/' in object_key else 'unknown'
            timestamp = datetime.utcnow().isoformat().replace(':', '-').replace('.', '-')
            
            # Define output path
            output_prefix = f"temp/docParser/{filename}-{timestamp}/"
            
            # Get account ID for profile ARN
            identity = sts_client.get_caller_identity()
            account_id = identity['Account']
            region = os.environ.get('AWS_REGION')
            
            # Construct standard profile ARN
            profile_arn = f"arn:aws:bedrock:{region}:{account_id}:data-automation-profile/us.data-automation-v1"
            
            # Invoke BDA project
            response = bda_client.invoke_data_automation_async(
                inputConfiguration={
                    's3Uri': f"s3://{bucket_name}/{object_key}"
                },
                outputConfiguration={
                    's3Uri': f"s3://{bucket_name}/{output_prefix}"
                },
                dataAutomationConfiguration={
                    'dataAutomationProjectArn': os.environ['BDA_PROJECT_ARN'],
                    'stage': 'LIVE'
                },
                dataAutomationProfileArn=profile_arn,
                clientToken=f"pdf-processing-{timestamp}-{hash(object_key) % 1000000}"
            )
            
            print(f"BDA invocation response: {json.dumps(response, indent=2, default=str)}")
            print(f"Successfully initiated BDA processing for {object_key}")
            print(f"Output will be stored in: s3://{bucket_name}/{output_prefix}")
            print(f"Invocation ARN: {response.get('invocationArn')}")
            
        except Exception as error:
            print(f"Error processing {object_key}: {str(error)}")
            raise error
    
    return {
        'statusCode': 200,
        'body': json.dumps('PDF processing initiated successfully')
    }
