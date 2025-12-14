import json
import base64
import boto3
import os
import datetime
import uuid

# Env vars set by SAM template
OUTPUT_BUCKET = os.environ["OUTPUT_BUCKET"]
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-west-2")
MODEL_ID = os.getenv("MODEL_ID", "stability.sd3-5-large-v1:0")
KEY_PREFIX = os.getenv("KEY_PREFIX", "sd35/")

client_bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)
s3 = boto3.client("s3")


def _resp(status_code: int, body: dict):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def _parse_event(event):
    """
    Supports:
    1) Direct Lambda invoke: {"prompt":"..."}
    2) API Gateway/Lambda proxy: {"body":"{...json...}"}
    3) API Gateway base64 body: {"isBase64Encoded": true, "body":"..."}
    """
    if not isinstance(event, dict):
        return {}

    # If API Gateway proxy event
    if "body" in event:
        body = event.get("body")

        # Decode base64 if required
        if event.get("isBase64Encoded") and isinstance(body, str):
            try:
                body = base64.b64decode(body).decode("utf-8")
            except Exception:
                return {"__parse_error__": "Invalid base64-encoded body"}

        # Parse JSON string body
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {"__parse_error__": "Invalid JSON in request body"}

        # If body already a dict (rare, but possible)
        if isinstance(body, dict):
            return body

        return {"__parse_error__": "Unsupported body format"}

    # Direct invoke payload
    return event


def lambda_handler(event, context):
    payload = _parse_event(event)

    if payload.get("__parse_error__"):
        return _resp(400, {"error": payload["__parse_error__"]})

    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        return _resp(400, {"error": "Missing 'prompt'"})

    # Basic constraints (helps cost + stability)
    if len(prompt) > 800:
        return _resp(400, {"error": "Prompt too long (max 800 chars)"})

    # Optional knobs you can expose later
    # negative_prompt = (payload.get("negative_prompt") or "").strip()
    # seed = payload.get("seed")  # if model supports it

    try:
        resp = client_bedrock.invoke_model(
            modelId=MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=json.dumps(
                {
                    "prompt": prompt,
                    "output_format": "png",
                    # "negative_prompt": negative_prompt,
                    # "seed": seed,
                }
            ),
        )
    except Exception:
        return _resp(502, {"error": "Bedrock invoke failed"})

    try:
        data = json.loads(resp["body"].read())
    except Exception:
        return _resp(502, {"error": "Invalid Bedrock response"})

    finish_reasons = data.get("finish_reasons", [])
    if finish_reasons and finish_reasons[0] is not None:
        return _resp(400, {"error": "Filtered/failed", "finish_reasons": finish_reasons})

    images = data.get("images") or []
    if not images:
        return _resp(502, {"error": "No image returned from model"})

    try:
        img_bytes = base64.b64decode(images[0])
    except Exception:
        return _resp(502, {"error": "Image decode failed"})

    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    rid = uuid.uuid4().hex[:10]
    key = f"{KEY_PREFIX}poster_{ts}_{rid}.png"

    try:
        s3.put_object(
            Bucket=OUTPUT_BUCKET,
            Key=key,
            Body=img_bytes,
            ContentType="image/png",
        )
    except Exception:
        return _resp(502, {"error": "S3 upload failed"})

    try:
        url = s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": OUTPUT_BUCKET, "Key": key},
            ExpiresIn=3600,
        )
    except Exception:
        return _resp(502, {"error": "Failed to generate presigned URL"})

    return _resp(
        200,
        {
            "bucket": OUTPUT_BUCKET,
            "key": key,
            "url": url,
            "seed": (data.get("seeds") or [None])[0],
            "modelId": MODEL_ID,
        },
    )
