import json
import boto3
import os
import time
from typing import Dict, Any

# Initialize clients
agent_core_client = boto3.client('bedrock-agentcore', region_name=os.environ.get('AWS_REGION'))

def extract_pdf_filename(filename_timestamp: str) -> str:
    """
    Extract clean PDF filename from the timestamp-appended folder name.
    Example: 'ROI2022-013-test01-2025-10-04T18-39-47-263373' -> 'ROI2022-013-test01'
    """
    # Split by date pattern (YYYY-MM-DD or YYYY-MM-DDT)
    parts = filename_timestamp.split('-2025-')
    if len(parts) > 1:
        return parts[0]
    
    # Fallback: return as-is
    return filename_timestamp

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Triggered when BDA completes and creates result.json in S3.
    Automatically invokes both Keyword Generator and Commercial Assessment agents sequentially.
    """
    print(f"Received S3 event: {json.dumps(event, indent=2)}")
    
    results = {
        'keywords_triggered': False,
        'eca_triggered': False,
        'errors': []
    }
    
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
            filename_timestamp = path_parts[2]  # ROI2022-013-test01-2025-10-04T18-39-47-263373
            pdf_filename = extract_pdf_filename(filename_timestamp)
            
            print(f"Extracted PDF filename: {pdf_filename}")
            
            # ========================================================================
            # INVOCATION 1: Keyword Generator Agent
            # ========================================================================
            try:
                keywords_session_id = f"agent-session-{filename_timestamp}-keywords"
                
                keywords_payload = {
                    "action": "generate_keywords",
                    "pdf_filename": pdf_filename,
                    "bda_file_path": object_key,
                    "prompt": f"Conduct a professional patent search keyword analysis for the invention disclosure document at {object_key}"
                }
                
                print(f"[1/2] Invoking Keyword Generator Agent with session: {keywords_session_id}")
                
                keywords_response = agent_core_client.invoke_agent_runtime(
                    agentRuntimeArn=os.environ['AGENT_RUNTIME_ARN'],
                    runtimeSessionId=keywords_session_id,
                    payload=json.dumps(keywords_payload).encode('utf-8')
                )
                
                print(f"✅ Keyword Generator invoked successfully: {keywords_response.get('ResponseMetadata', {}).get('RequestId')}")
                results['keywords_triggered'] = True
                
            except Exception as keywords_error:
                error_msg = f"Error invoking Keyword Generator: {str(keywords_error)}"
                print(f"❌ {error_msg}")
                results['errors'].append(error_msg)
                # Continue to ECA even if keywords fail
            
            # Small delay to avoid overwhelming the runtime
            time.sleep(2)
            
            # ========================================================================
            # INVOCATION 2: Early Commercial Assessment Agent
            # ========================================================================
            try:
                eca_session_id = f"agent-session-{filename_timestamp}-eca"
                
                eca_payload = {
                    "action": "commercial_assessment",
                    "pdf_filename": pdf_filename,
                    "bda_file_path": object_key
                }
                
                print(f"[2/2] Invoking Commercial Assessment Agent with session: {eca_session_id}")
                
                eca_response = agent_core_client.invoke_agent_runtime(
                    agentRuntimeArn=os.environ['AGENT_RUNTIME_ARN'],
                    runtimeSessionId=eca_session_id,
                    payload=json.dumps(eca_payload).encode('utf-8')
                )
                
                print(f"✅ Commercial Assessment invoked successfully: {eca_response.get('ResponseMetadata', {}).get('RequestId')}")
                results['eca_triggered'] = True
                
            except Exception as eca_error:
                error_msg = f"Error invoking Commercial Assessment: {str(eca_error)}"
                print(f"❌ {error_msg}")
                results['errors'].append(error_msg)
            
            # Summary
            print(f"\n{'='*60}")
            print(f"Auto-trigger Summary for {pdf_filename}:")
            print(f"  Keywords Agent: {'✅ Triggered' if results['keywords_triggered'] else '❌ Failed'}")
            print(f"  ECA Agent: {'✅ Triggered' if results['eca_triggered'] else '❌ Failed'}")
            if results['errors']:
                print(f"  Errors: {len(results['errors'])}")
                for error in results['errors']:
                    print(f"    - {error}")
            print(f"{'='*60}\n")
            
        except Exception as error:
            error_msg = f"Error processing {object_key}: {str(error)}"
            print(f"❌ {error_msg}")
            results['errors'].append(error_msg)
            # Don't raise - allow Lambda to complete and report partial success
    
    # Return success if at least one agent was triggered
    success = results['keywords_triggered'] or results['eca_triggered']
    
    return {
        'statusCode': 200 if success else 500,
        'body': json.dumps({
            'message': 'Agent auto-trigger completed',
            'results': results
        })
    }
