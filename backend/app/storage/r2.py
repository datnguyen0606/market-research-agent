import os
import boto3


def get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=f"https://{os.getenv('R2_ACCOUNT_ID')}.r2.cloudflarestorage.com",
        aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
        aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
        region_name="auto",
    )


def upload_pdf(ticker: str, filename: str, pdf_bytes: bytes) -> str:
    r2 = get_r2_client()
    key = f"pdfs/{ticker}/{filename}"
    r2.put_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=key, Body=pdf_bytes)
    return key


def download_pdf(r2_key: str) -> bytes:
    r2 = get_r2_client()
    obj = r2.get_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=r2_key)
    return obj["Body"].read()
