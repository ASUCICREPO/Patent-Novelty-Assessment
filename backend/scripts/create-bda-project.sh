#!/bin/bash

# Create BDA project for PDF parsing
echo "Creating BDA project..."

BDA_RESPONSE=$(aws bedrock-data-automation create-data-automation-project \
  --project-name pdf-parsing \
  --standard-output-configuration '{
    "document": {
      "extraction": {
        "granularity": {
          "types": ["DOCUMENT", "PAGE", "ELEMENT"]
        },
        "boundingBox": {"state": "DISABLED"}
      },
      "generativeField": {"state": "DISABLED"},
      "outputFormat": {
        "textFormat": {"types": ["PLAIN_TEXT"]},
        "additionalFileFormat": {"state": "ENABLED"}
      }
    }
  }' \
  --output json)

if [ $? -eq 0 ]; then
    PROJECT_ARN=$(echo $BDA_RESPONSE | jq -r '.projectArn')
    echo "BDA project created successfully!"
    echo "Project ARN: $PROJECT_ARN"
    
    # Save ARN to file for later use
    echo $PROJECT_ARN > backend/scripts/bda-project-arn.txt
    echo "ARN saved to backend/scripts/bda-project-arn.txt"
else
    echo "Failed to create BDA project"
    exit 1
fi
