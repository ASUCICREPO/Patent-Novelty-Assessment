import json
import boto3
import os
from typing import Dict, Any

# Initialize clients
agent_core_client = boto3.client('bedrock-agentcore', region_name=os.environ.get('AWS_REGION'))

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Triggered when BDA completes and creates result.json in S3.
    Automatically invokes the Patent Keyword Generator Agent.
    """
    print(f"Received S3 event: {json.dumps(event, indent=2)}")
    
    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key'].replace('+', ' ')
        
        print(f"Processing BDA result: {object_key}")
        
        try:
            # Validate it's a BDA result.json file
            if 'temp/docParser/' not in object_key or not object_key.endswith('result.json'):
                print(f"Skipping non-BDA result file: {object_key}")
                continue
            
            # Extract session info from path
            # Path: temp/docParser/filename-timestamp/job-id/0/standard_output/0/result.json
            path_parts = object_key.split('/')
            filename_timestamp = path_parts[2]  # ROI2022-test-2025-08-31T00-33-09-644Z
            session_id = f"agent-session-{filename_timestamp}"
            
            # Prepare agent payload
            agent_payload = {
                "prompt": "Analyze the patent novelty for the invention described in the BDA results. Extract key technical features, identify potential prior art conflicts, and provide a comprehensive novelty assessment.",
                "session_id": session_id,
                "bda_file_path": object_key
            }
            
            print(f"Invoking agent with session: {session_id}")
            
            # Invoke Agent Core
            response = agent_core_client.invoke_agent_runtime(
                agentRuntimeArn=os.environ['AGENT_RUNTIME_ARN'],
                runtimeSessionId=session_id,
                payload=json.dumps(agent_payload).encode('utf-8')
            )
            
            print(f"Agent invocation successful: {response.get('ResponseMetadata', {}).get('RequestId')}")
            
        except Exception as error:
            print(f"Error processing {object_key}: {str(error)}")
            raise error
    
    return {
        'statusCode': 200,
        'body': json.dumps('Agent trigger completed successfully')
    }
