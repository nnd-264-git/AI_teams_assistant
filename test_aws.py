"""Quick sanity check for AWS access: S3, Bedrock, Transcribe."""
from src import config
from src.aws_pipeline import _session

session = _session()

print(f"Region: {config.AWS_REGION}")
print(f"Bucket: {config.S3_BUCKET}")
print(f"Model:  {config.BEDROCK_MODEL_ID}")
print()

print("--- S3: list buckets ---")
try:
    s3 = session.client("s3")
    buckets = [b["Name"] for b in s3.list_buckets().get("Buckets", [])]
    print("OK. Buckets visible:", buckets)
except Exception as e:
    print("FAILED:", e)

print()
print("--- Bedrock: list foundation models ---")
try:
    bedrock = session.client("bedrock")
    models = bedrock.list_foundation_models().get("modelSummaries", [])
    claude_models = [m["modelId"] for m in models if "claude" in m["modelId"].lower()]
    print(f"OK. {len(models)} models visible. Claude models:", claude_models)
except Exception as e:
    print("FAILED:", e)

print()
print("--- Bedrock: invoke configured model ---")
try:
    from src.aws_pipeline import invoke_llm
    reply = invoke_llm(
        "You are a test assistant.",
        [{"role": "user", "content": [{"text": "Reply with exactly: PONG"}]}],
    )
    print("OK. Model replied:", reply.strip())
except Exception as e:
    print("FAILED:", e)

print()
print("--- Transcribe: list jobs (permission check) ---")
try:
    transcribe = session.client("transcribe")
    transcribe.list_transcription_jobs(MaxResults=1)
    print("OK. Transcribe accessible.")
except Exception as e:
    print("FAILED:", e)
