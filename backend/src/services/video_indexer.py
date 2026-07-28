"""Connector: Python and Azure Video Indexer Service integration using yt-dlp

and Azure ARM Authentication.
"""
import traceback
import logging
import os
import time
import requests
import yt_dlp
from azure.identity import AzureCliCredential



logger = logging.getLogger("video-indexer")


class VideoIndexerService:

    def __init__(self):
        self.account_id = os.getenv("AZURE_VI_ACCOUNT_ID")
        self.location = os.getenv("AZURE_VI_LOCATION")
        self.subscription_id = os.getenv("AZURE_SUBSCRIPTION_ID")
        self.resource_group = os.getenv("AZURE_RESOURCE_GROUP")
        self.vi_name = os.getenv("AZURE_VI_NAME", "video-analyzer-project")
        self.credential = AzureCliCredential(process_timeout=60)

    def get_access_token(self):
        try:
            token = self.credential.get_token(
            "https://management.azure.com/.default"
             )
            return token.token
        except Exception:
           traceback.print_exc()
           raise

    def get_account_token(self, arm_access_token: str) -> str:
        """Exchanges the ARM token for a Video Indexer Account Access token."""
        url = (
            f"https://management.azure.com/subscriptions/{self.subscription_id}"
            f"/resourceGroups/{self.resource_group}"
            f"/providers/Microsoft.VideoIndexer/accounts/{self.vi_name}"
            f"/generateAccessToken?api-version=2024-01-01"
        )
        headers = {"Authorization": f"Bearer {arm_access_token}"}
        payload = {"permissionType": "Contributor", "scope": "Account"}

        response = requests.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise Exception(f"Failed to get VI Account token: {response.text}")
        return response.json().get("accessToken")

    def download_youtube_video(
        self, url: str, output_path: str = "temp_video.mp4"
    ) -> str:
        """Downloads a YouTube video to a local file using yt-dlp."""
        logger.info(f"Downloading YouTube video: {url}")

        ydl_opts = {
            "format": "best[ext=mp4]/best",
            "outtmpl": output_path,
            "quiet": False,
            "no_warnings": False,

            'extractor_args':{'youtube':{'player_client':['android','web']}},
            'http_headers':{
            'User-Agent':'Mozilla/5.0(windows NT 10.0;win64;x64) AppleWebKit/537.36'
            }
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            logger.info("Download complete")
            return output_path
        except Exception as e:
            raise Exception(f"YouTube Video Download Failed: {str(e)}")

    def upload_video(self, video_path: str, video_name: str) -> str:
        """Uploads a local video file to Azure Video Indexer and returns the Azure Video ID."""
        arm_token = self.get_access_token()
        vi_token = self.get_account_token(arm_token)

        api_url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos"

        params = {
            "accessToken": vi_token,
            "name": video_name,
            "privacy": "Private",
            "indexingPreset": "Default",
        }

        logger.info(f"Uploading file '{video_path}' to Azure Video Indexer...")

        with open(video_path, "rb") as video_file:
            files = {"file": video_file}
            logger.info(f"Upload URL: {api_url}")
            response = requests.post(api_url, params=params, files=files)

        if response.status_code != 200:
            raise Exception(f"Azure Upload Failed: {response.text}")

        azure_video_id = response.json().get("id")
        return azure_video_id

    def wait_for_processing(self, video_id: str) -> dict:
        """Polls Azure Video Indexer status until processing finishes."""
        logger.info(f"Waiting for video {video_id} to process...")

        arm_token = self.get_access_token()
        vi_token = self.get_account_token(arm_token)
        poll_seconds = int(os.getenv("AZURE_VI_POLL_SECONDS", "30"))
        max_wait_seconds = int(os.getenv("AZURE_VI_MAX_WAIT_SECONDS", "300"))
        deadline = time.monotonic() + max_wait_seconds

        while True:
            
            url = f"https://api.videoindexer.ai/{self.location}/Accounts/{self.account_id}/Videos/{video_id}/Index"
            params = {"accessToken": vi_token}

            response = requests.get(url, params=params)
            data = response.json()

            state = data.get("state")
            if state == "Processed":
                logger.info("Processing complete!")
                return data
            elif state == "Failed":
                raise Exception("Video Indexing Failed in Azure")
            elif state == "Quarantined":
                raise Exception(
                    "Video Quarantined (Copyright/Content Policy Violation)"
                )
            elif time.monotonic() >= deadline:
                raise TimeoutError(
                    f"Azure Video Indexer did not finish within {max_wait_seconds} seconds. "
                    f"Last status: {state}. Try a shorter video or check the video in Azure Video Indexer."
                )

            logger.info(f"Status: {state}... waiting {poll_seconds}s")
            time.sleep(30)

    def extract_data(self, vi_json):
        """Parses the raw Azure Video Indexer JSON into our VideoAuditState schema."""
        transcript_lines = []
        for v in vi_json.get("videos", []):
            for insight in v.get("insights", {}).get("transcript", []):
                transcript_lines.append(insight.get("text"))

        ocr_lines = []
        for v in vi_json.get("videos", []):
            for insight in v.get("insights", {}).get("ocr", []):
                ocr_lines.append(insight.get("text"))

        return {
            "transcript": " ".join(transcript_lines),
            "ocr_text": ocr_lines,
            "video_metadata": {
                "duration": vi_json.get("summarizedInsights", {}).get(
                    "duration"
                ),
                "platform": "youtube",
            },
        }
