import json
import boto3
import os
import time
from botocore.exceptions import ClientError
import base64
import re

# Initialize AWS clients
s3_client = boto3.client('s3')
# Path-style addressing is more reliable for CORS with temporary credentials
s3_presigner = boto3.client(
    's3',
    region_name=os.environ.get('AWS_REGION', 'us-west-2'),
    config=boto3.session.Config(
        signature_version='s3v4',
        s3={'addressing_style': 'path'}
    )
)

# Get allowed origin from environment variable
ALLOWED_ORIGIN = os.environ.get('ALLOWED_ORIGIN', '*')

def lambda_handler(event, context):
    """
    Lambda handler for S3 API operations
    Handles file upload (POST) and signed URL generation/status checks (GET)
    """
    try:
        http_method = event['httpMethod']
        
        if http_method == 'POST':
            return handle_file_upload(event)
        elif http_method == 'GET':
            return handle_get_operations(event)
        else:
            return create_response(405, {'error': 'Method not allowed'})
            
    except Exception as e:
        print(f"Error in S3 API: {str(e)}")
        return create_response(500, {'error': 'Internal server error', 'details': str(e)})

def handle_file_upload(event):
    """Handle file upload to S3"""
    try:
        print(f"Received event: {json.dumps(event, default=str)}")
        
        # Get the request body
        body = event.get('body', '')
        is_base64 = event.get('isBase64Encoded', False)
        print(f"Body length: {len(body)}, isBase64Encoded: {is_base64}")
        
        # Handle binary data properly
        if is_base64:
            file_data = base64.b64decode(body)
        else:
            # For direct binary upload, the body should be bytes
            if isinstance(body, str):
                # If it's a string, it might be corrupted - try to handle it
                try:
                    # Try to decode as latin-1 to preserve binary data
                    file_data = body.encode('latin-1')
                except:
                    file_data = body.encode('utf-8')
            else:
                file_data = body
        
        # Get filename from query parameters or headers
        query_params = event.get('queryStringParameters') or {}
        filename = query_params.get('filename')
        
        if not filename:
            # Try to get from headers
            headers = event.get('headers', {})
            for key, value in headers.items():
                if key.lower() == 'x-filename':
                    filename = value
                    break
        
        if not filename:
            return create_response(400, {'error': 'Filename must be provided in query parameter or X-Filename header'})
        
        print(f"Filename: {filename}")
        
        # Validate file type
        if not filename.lower().endswith('.pdf'):
            return create_response(400, {'error': 'Only PDF files are supported'})
        
        # Validate PDF file header for BDA compatibility
        if len(file_data) < 4:
            return create_response(400, {'error': 'File too small to be a valid PDF'})
        
        # Check minimum file size (very small files might not be valid PDFs)
        if len(file_data) < 1024:  # 1KB minimum
            return create_response(400, {'error': 'PDF file appears to be too small to be valid'})
        
        # Sanitize filename
        sanitized_filename = sanitize_filename(filename)
        print(f"Sanitized filename: {sanitized_filename}")
        
        # Upload to S3
        bucket_name = os.environ['BUCKET_NAME']
        s3_key = f"uploads/{sanitized_filename}"
        print(f"Uploading to S3: {bucket_name}/{s3_key}")
        
        # Upload to S3 with proper metadata for BDA compatibility
        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=file_data,
            ContentType='application/pdf',
            Metadata={
                'original-filename': filename,
                'upload-timestamp': str(int(time.time())),
                'file-size': str(len(file_data))
            }
        )
        
        print("S3 upload successful")
        print(f"File details - Size: {len(file_data)} bytes, Type: application/pdf, Key: {s3_key}")
        
        return create_response(200, {
            'message': 'File uploaded successfully',
            'fileName': sanitized_filename,
            'size': len(file_data),
            'type': 'application/pdf',
            'uploadedAt': 'success',
            's3Key': s3_key,
            'bucket': bucket_name
        })
        
    except Exception as e:
        print(f"Error uploading file: {str(e)}")
        import traceback
        traceback.print_exc()
        return create_response(500, {'error': 'Failed to upload file', 'details': str(e)})

def handle_get_operations(event):
    """Handle GET operations for signed URLs and status checks"""
    try:
        query_params = event.get('queryStringParameters') or {}
        operation = query_params.get('operation')
        filename = query_params.get('filename')
        
        if not operation or not filename:
            return create_response(400, {'error': 'Operation and filename are required'})
        
        bucket_name = os.environ['BUCKET_NAME']
        clean_filename = filename.replace('.pdf', '')
        
        if operation == 'get_signed_urls':
            return get_signed_urls(bucket_name, clean_filename)
        elif operation == 'check_reports':
            return check_reports(bucket_name, clean_filename)
        elif operation == 'get_presigned_url':
            return get_presigned_upload_url(bucket_name, filename)
        else:
            return create_response(400, {'error': 'Invalid operation. Must be: get_signed_urls, check_reports, or get_presigned_url'})
            
    except Exception as e:
        print(f"Error in GET operations: {str(e)}")
        return create_response(500, {'error': 'S3 operation failed', 'details': str(e)})

def get_signed_urls(bucket_name, clean_filename):
    """Generate signed URLs for both reports"""
    try:
        ptls_key = f"reports/{clean_filename}_report.pdf"
        eca_key = f"reports/{clean_filename}_eca_report.pdf"
        
        # Generate signed URLs (valid for 1 hour)
        ptls_url = s3_presigner.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': ptls_key},
            ExpiresIn=3600
        )
        
        eca_url = s3_presigner.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket_name, 'Key': eca_key},
            ExpiresIn=3600
        )
        
        return create_response(200, {
            'ptlsUrl': ptls_url,
            'ecaUrl': eca_url,
            'filename': clean_filename
        })
        
    except Exception as e:
        print(f"Error generating signed URLs: {str(e)}")
        return create_response(500, {'error': 'Failed to generate signed URLs', 'details': str(e)})

def check_reports(bucket_name, clean_filename):
    """Check if reports exist in S3"""
    try:
        ptls_key = f"reports/{clean_filename}_report.pdf"
        eca_key = f"reports/{clean_filename}_eca_report.pdf"
        
        # Check if both reports exist
        ptls_exists = check_object_exists(bucket_name, ptls_key)
        eca_exists = check_object_exists(bucket_name, eca_key)
        
        return create_response(200, {
            'ptlsReady': ptls_exists,
            'ecaReady': eca_exists,
            'filename': clean_filename
        })
        
    except Exception as e:
        print(f"Error checking reports: {str(e)}")
        return create_response(500, {'error': 'Failed to check reports', 'details': str(e)})

def check_object_exists(bucket_name, key):
    """Check if an object exists in S3"""
    try:
        s3_client.head_object(Bucket=bucket_name, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise

def sanitize_filename(filename):
    """Sanitize filename for S3 storage"""
    # Split name and extension
    name, ext = os.path.splitext(filename)
    
    # Sanitize the name part
    sanitized = re.sub(r'[^\w\-_.]', '_', name)  # Replace special chars with underscore
    sanitized = re.sub(r'_+', '_', sanitized)    # Remove consecutive underscores
    sanitized = sanitized.strip('_')              # Remove leading/trailing underscores
    
    # If sanitization resulted in empty string, use default
    if not sanitized:
        sanitized = 'document'
    
    return sanitized + ext.lower()

def get_presigned_upload_url(bucket_name, filename):
    """Generate a presigned URL for direct S3 upload"""
    try:
        # Sanitize filename
        sanitized_filename = sanitize_filename(filename)
        s3_key = f"uploads/{sanitized_filename}"
        
        # Generate presigned URL for PUT operation
        presigned_url = s3_presigner.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': s3_key,
                'ContentType': 'application/pdf'
            },
            ExpiresIn=3600  # 1 hour
        )
        
        return create_response(200, {
            'uploadUrl': presigned_url,
            'fileName': sanitized_filename,
            's3Key': s3_key,
            'bucket': bucket_name
        })
        
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        return create_response(500, {'error': 'Failed to generate presigned URL', 'details': str(e)})

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
