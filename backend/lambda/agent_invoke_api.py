import json
import boto3
import os
import time
import random
import string

# Initialize Bedrock Agent Core client
bedrock_client = boto3.client('bedrock-agentcore')

# Get allowed origin from environment variable
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')

def lambda_handler(event, context):
    """
    Lambda handler for Agent Invoke API operations
    Handles POST requests to invoke Bedrock Agent Core
    """
    try:
        http_method = event['httpMethod']
        
        if http_method == 'POST':
            return handle_agent_invoke(event)
        else:
            return create_response(405, {'error': 'Method not allowed'})
            
    except Exception as e:
        print(f"Error in Agent Invoke API: {str(e)}")
        return create_response(500, {'error': 'Internal server error', 'details': str(e)})

def handle_agent_invoke(event):
    """Handle agent invocation requests"""
    try:
        body = json.loads(event.get('body', '{}'))
        action = body.get('action')
        pdf_filename = body.get('pdfFilename')
        
        if not action or not pdf_filename:
            return create_response(400, {'error': 'Action and PDF filename are required'})
        
        # Validate action type
        valid_actions = ['search_patents', 'search_articles', 'generate_report']
        if action not in valid_actions:
            return create_response(400, {
                'error': f'Invalid action. Must be one of: {", ".join(valid_actions)}'
            })
        
        # Get agent runtime ARN from environment
        agent_runtime_arn = os.environ.get('AGENT_RUNTIME_ARN')
        if not agent_runtime_arn:
            return create_response(500, {'error': 'Bedrock Agent Runtime ARN not configured'})
        
        # Remove PDF extension if present - agent expects filename without extension
        clean_filename = pdf_filename.replace('.pdf', '')
        
        # Prepare payload
        payload = {
            'action': action,
            'pdf_filename': clean_filename
        }
        
        # Generate session ID
        session_id = generate_session_id(action)
        
        # Prepare input for Bedrock Agent Core
        input_data = {
            'runtimeSessionId': session_id,
            'agentRuntimeArn': agent_runtime_arn,
            'qualifier': 'DEFAULT',
            'payload': json.dumps(payload)
        }
        
        # Invoke the agent
        response = bedrock_client.invoke_agent_runtime(**input_data)
        
        if not response.get('response'):
            return create_response(500, {'error': 'No response received from Bedrock Agent Core'})
        
        # Agent invocation successful - results will be stored in DynamoDB
        return create_response(200, {
            'sessionId': session_id,
            'action': action,
            'message': f'{get_action_message(action)} triggered successfully',
            'status': 'processing'
        })
        
    except Exception as e:
        print(f"Error invoking agent: {str(e)}")
        return create_response(500, {'error': 'Failed to invoke agent', 'details': str(e)})

def generate_session_id(action):
    """Generate a unique session ID based on action"""
    timestamp = int(time.time() * 1000)
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=9))
    
    action_prefixes = {
        'search_patents': 'patent-search',
        'search_articles': 'scholarly-search',
        'generate_report': 'report-gen'
    }
    
    prefix = action_prefixes.get(action, 'agent')
    return f'{prefix}-{timestamp}-{random_suffix}'

def get_action_message(action):
    """Get user-friendly message for action"""
    action_messages = {
        'search_patents': 'Patent search',
        'search_articles': 'Scholarly search',
        'generate_report': 'Report generation'
    }
    
    return action_messages.get(action, 'Agent operation')

def create_response(status_code, body):
    """Create API Gateway response"""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(body)
    }
