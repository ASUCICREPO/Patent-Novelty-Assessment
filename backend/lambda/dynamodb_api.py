import json
import boto3
import os
from decimal import Decimal
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb')

# Get allowed origin from environment variable
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')

def lambda_handler(event, context):
    """
    Lambda handler for DynamoDB API operations
    Handles GET (query) and PUT (update) operations
    """
    try:
        http_method = event['httpMethod']
        
        if http_method == 'GET':
            return handle_get_operations(event)
        elif http_method == 'PUT':
            return handle_put_operations(event)
        else:
            return create_response(405, {'error': 'Method not allowed'})
            
    except Exception as e:
        print(f"Error in DynamoDB API: {str(e)}")
        return create_response(500, {'error': 'Internal server error', 'details': str(e)})

def handle_get_operations(event):
    """Handle GET operations for querying DynamoDB"""
    try:
        query_params = event.get('queryStringParameters') or {}
        table_type = query_params.get('tableType')
        pdf_filename = query_params.get('pdfFilename')
        file_name = query_params.get('fileName')
        
        # Determine which table and operation based on tableType
        table_name, filename = get_table_and_filename(table_type, pdf_filename, file_name)
        if isinstance(table_name, dict):  # Error response
            return table_name
        
        clean_filename = filename.replace('.pdf', '')
        
        # Query DynamoDB
        table = dynamodb.Table(table_name)
        
        query_params = {
            'KeyConditionExpression': Key('pdf_filename').eq(clean_filename),
            'ScanIndexForward': False  # Get most recent first
        }
        
        # Only add Limit for analysis results
        if table_type == 'analysis':
            query_params['Limit'] = 1
            
        response = table.query(**query_params)
        
        if table_type == 'analysis':
            # For analysis results, return single item or null
            if not response.get('Items'):
                return create_response(200, {'result': None})
            return create_response(200, {'result': response['Items'][0]})
        else:
            # For patent/scholarly results, return array with count
            return create_response(200, {
                'results': response.get('Items', []),
                'count': response.get('Count', 0)
            })
            
    except Exception as e:
        print(f"Error in GET operations: {str(e)}")
        return create_response(500, {'error': 'Failed to fetch results', 'details': str(e)})

def handle_put_operations(event):
    """Handle PUT operations for updating DynamoDB"""
    try:
        body = json.loads(event.get('body', '{}'))
        operation = body.get('operation')
        table_type = body.get('tableType')
        pdf_filename = body.get('pdfFilename')
        file_name = body.get('fileName')
        
        if not operation or not table_type:
            return create_response(400, {'error': 'Operation and tableType are required'})
        
        # Determine which table based on tableType
        table_name, filename = get_table_and_filename(table_type, pdf_filename, file_name)
        if isinstance(table_name, dict):  # Error response
            return table_name
        
        clean_filename = filename.replace('.pdf', '')
        
        # Handle different operations
        if operation == 'update_keywords':
            return update_keywords(table_name, clean_filename, body.get('keywords', []))
        elif operation == 'update_add_to_report':
            return update_add_to_report(table_name, table_type, clean_filename, body)
        else:
            return create_response(400, {'error': 'Invalid operation. Must be: update_keywords or update_add_to_report'})
            
    except Exception as e:
        print(f"Error in PUT operations: {str(e)}")
        return create_response(500, {'error': 'Failed to update DynamoDB', 'details': str(e)})

def get_table_and_filename(table_type, pdf_filename, file_name):
    """Get table name and filename based on table type"""
    if table_type == 'analysis':
        if not file_name:
            return create_response(400, {'error': 'File name is required for analysis results'})
        return os.environ['KEYWORDS_TABLE'], file_name
    elif table_type == 'patent-results':
        if not pdf_filename:
            return create_response(400, {'error': 'PDF filename is required for patent results'})
        return os.environ['PATENT_RESULTS_TABLE'], pdf_filename
    elif table_type == 'scholarly-results':
        if not pdf_filename:
            return create_response(400, {'error': 'PDF filename is required for scholarly results'})
        return os.environ['SCHOLARLY_ARTICLES_TABLE'], pdf_filename
    else:
        return create_response(400, {'error': 'Invalid tableType. Must be: analysis, patent-results, or scholarly-results'})

def update_keywords(table_name, clean_filename, keywords):
    """Update keywords for a document"""
    try:
        if not keywords or not isinstance(keywords, list):
            return create_response(400, {'error': 'Keywords array is required for update_keywords operation'})
        
        table = dynamodb.Table(table_name)
        
        # First, find the item to get its full key structure
        response = table.query(
            KeyConditionExpression=Key('pdf_filename').eq(clean_filename),
            Limit=1
        )
        
        if not response.get('Items'):
            return create_response(404, {'error': 'Item not found in DynamoDB'})
        
        item = response['Items'][0]
        
        # Build the key dynamically based on what we find
        key = {'pdf_filename': item['pdf_filename']}
        
        # Add any additional key fields that might exist
        for key_field in ['timestamp', 'id', 'sk']:
            if key_field in item:
                key[key_field] = item[key_field]
        
        # Update the keywords field
        table.update_item(
            Key=key,
            UpdateExpression='SET keywords = :keywords',
            ExpressionAttributeValues={
                ':keywords': ', '.join(keywords)
            },
            ReturnValues='UPDATED_NEW'
        )
        
        return create_response(200, {'message': 'Keywords updated successfully'})
        
    except Exception as e:
        print(f"Error updating keywords: {str(e)}")
        return create_response(500, {'error': 'Failed to update keywords', 'details': str(e)})

def update_add_to_report(table_name, table_type, clean_filename, body):
    """Update add_to_report flag for patents or scholarly articles"""
    try:
        add_to_report = body.get('addToReport')
        if not isinstance(add_to_report, bool):
            return create_response(400, {'error': 'addToReport boolean is required for update_add_to_report operation'})
        
        table = dynamodb.Table(table_name)
        
        if table_type == 'patent-results':
            patent_number = body.get('patentNumber')
            if not patent_number:
                return create_response(400, {'error': 'patentNumber is required for patent add_to_report update'})
            
            table.update_item(
                Key={
                    'pdf_filename': clean_filename,
                    'patent_number': patent_number
                },
                UpdateExpression='SET add_to_report = :addToReport',
                ExpressionAttributeValues={
                    ':addToReport': 'Yes' if add_to_report else 'No'
                },
                ReturnValues='UPDATED_NEW'
            )
            
            return create_response(200, {
                'message': f'Updated add_to_report for patent {patent_number} to {"Yes" if add_to_report else "No"}'
            })
            
        elif table_type == 'scholarly-results':
            article_doi = body.get('articleDoi')
            if not article_doi:
                return create_response(400, {'error': 'articleDoi is required for scholarly add_to_report update'})
            
            table.update_item(
                Key={
                    'pdf_filename': clean_filename,
                    'article_doi': article_doi
                },
                UpdateExpression='SET add_to_report = :addToReport',
                ExpressionAttributeValues={
                    ':addToReport': 'Yes' if add_to_report else 'No'
                },
                ReturnValues='UPDATED_NEW'
            )
            
            return create_response(200, {
                'message': f'Updated add_to_report for article {article_doi} to {"Yes" if add_to_report else "No"}'
            })
        else:
            return create_response(400, {'error': 'Invalid table type for add_to_report update'})
            
    except Exception as e:
        print(f"Error updating add_to_report: {str(e)}")
        return create_response(500, {'error': 'Failed to update add_to_report', 'details': str(e)})

def convert_decimals(obj):
    """Convert Decimal objects to float for JSON serialization"""
    if isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, dict):
        return {key: convert_decimals(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_decimals(item) for item in obj]
    else:
        return obj

def create_response(status_code, body):
    """Create API Gateway response"""
    # Convert Decimal objects to float for JSON serialization
    converted_body = convert_decimals(body)
    
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': ALLOWED_ORIGIN,
            'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
            'Access-Control-Allow-Methods': 'GET,POST,PUT,DELETE,OPTIONS'
        },
        'body': json.dumps(converted_body)
    }
