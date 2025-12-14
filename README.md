# Bedrock SD3.5 Serverless Image Generator (AWS SAM)

Serverless API that generates an image using **Amazon Bedrock (Stability SD3.5)**, stores it in **S3**, and returns a **time-limited presigned URL**.

## Architecture
API Gateway → Lambda → Bedrock Runtime → S3 → Presigned URL

## What it does
- Accepts a JSON prompt via HTTP `POST`
- Calls Bedrock `InvokeModel` (Stability SD3.5) to generate a PNG
- Uploads the PNG to a private S3 bucket
- Returns:
  - `bucket`, `key`
  - `url` (presigned S3 URL, expires ~1 hour)
  - `seed`, `modelId`

## Repo structure
template.yaml
src/app.py
README.md


## Deploy (AWS SAM)
Prereqs:
- AWS CLI configured (`aws configure`)
- AWS SAM CLI installed

Commands:
```bash
sam validate
sam build
sam deploy --guided

After deployment, SAM prints stack outputs including:

ApiUrl (POST endpoint)

BucketName (S3 bucket for generated images)

Test
PowerShell (recommended)

Replace the URL with your ApiUrl from the deploy output.

$uri = "https://<YOUR_API_ID>.execute-api.us-west-2.amazonaws.com/prod/generate"
$body = @{ prompt = "a clean corporate poster, minimal style" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $uri -ContentType "application/json" -Body $body