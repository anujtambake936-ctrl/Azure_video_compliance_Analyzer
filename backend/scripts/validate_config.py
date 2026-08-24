"""Validate required environment configuration without printing secret values."""
import os
import sys

from dotenv import load_dotenv


BASE_REQUIRED = (
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "AZURE_SEARCH_ENDPOINT",
    "AZURE_SEARCH_API_KEY",
    "AZURE_SEARCH_INDEX_NAME",
)
FAST_REQUIRED = (
    "AZURE_SPEECH_ENDPOINT",
    "AZURE_SPEECH_KEY",
    "AZURE_SPEECH_REGION",
)
FULL_REQUIRED = (
    "AZURE_VI_NAME",
    "AZURE_VI_LOCATION",
    "AZURE_VI_ACCOUNT_ID",
    "AZURE_SUBSCRIPTION_ID",
    "AZURE_RESOURCE_GROUP",
)


def required_variables() -> tuple[str, ...]:
    mode = os.getenv("USE_FAST_TRANSCRIPTION", "false").lower()
    mode_required = FAST_REQUIRED if mode == "true" else FULL_REQUIRED
    return BASE_REQUIRED + mode_required


def main() -> int:
    load_dotenv(override=True)
    missing = [name for name in required_variables() if not os.getenv(name)]
    if missing:
        print("Configuration is incomplete. Missing variable names:")
        print("\n".join(f"- {name}" for name in missing))
        return 1

    mode = "fast" if os.getenv("USE_FAST_TRANSCRIPTION", "false").lower() == "true" else "full"
    print(f"Configuration is valid for {mode} mode.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
