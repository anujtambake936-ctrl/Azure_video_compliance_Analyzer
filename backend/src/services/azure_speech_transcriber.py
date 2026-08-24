"""Fast speech-to-text transcription using Azure AI Speech."""
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

import requests

logger = logging.getLogger("azure-speech-transcriber")


def _find_ffmpeg() -> str | None:
    executable = shutil.which("ffmpeg")
    if executable:
        return executable

    winget_root = Path(os.getenv("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget_root.exists():
        matches = winget_root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe")
        match = next(matches, None)
        return str(match) if match else None
    return None


class AzureSpeechTranscriber:
    """Extract audio locally and transcribe it with Azure AI Speech."""

    def __init__(self):
        self.endpoint = os.getenv("AZURE_SPEECH_ENDPOINT", "").rstrip("/")
        self.key = os.getenv("AZURE_SPEECH_KEY")
        self.region = os.getenv("AZURE_SPEECH_REGION")
        self.language = os.getenv("AZURE_SPEECH_LANGUAGE", "en-US")

        missing = [
            name for name, value in {
                "AZURE_SPEECH_ENDPOINT": self.endpoint,
                "AZURE_SPEECH_KEY": self.key,
                "AZURE_SPEECH_REGION": self.region,
            }.items() if not value
        ]
        if missing:
            raise RuntimeError(
                f"Missing Azure Speech configuration: {', '.join(missing)}"
            )

    def extract_audio(self, video_path: str, output_path: str | None = None) -> str:
        """Convert a video file to mono 16 kHz PCM WAV for Speech."""
        if output_path is None:
            output_path = str(Path(video_path).with_suffix(".wav"))
        ffmpeg = _find_ffmpeg()
        if ffmpeg is None:
            raise RuntimeError(
                "ffmpeg is required for Azure Speech transcription. "
                "Install ffmpeg and add it to PATH, then restart the terminal."
            )

        try:
            subprocess.run(
                [
                    ffmpeg, "-i", video_path, "-vn", "-ac", "1", "-ar", "16000",
                    "-acodec", "pcm_s16le", "-y", output_path,
                ],
                check=True,
                capture_output=True,
            )
            return output_path
        except subprocess.CalledProcessError as error:
            details = error.stderr.decode(errors="replace").strip()
            raise RuntimeError(f"ffmpeg audio extraction failed: {details}") from error

    def transcribe_audio(self, audio_path: str) -> str:
        """Transcribe a short audio file through Azure Speech."""
        url = (
            f"{self.endpoint}/speech/recognition/conversation/cognitiveservices/v1"
            f"?language={self.language}"
        )
        headers = {
            "Ocp-Apim-Subscription-Key": self.key,
            "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
            "Accept": "application/json",
        }
        with open(audio_path, "rb") as audio_file:
            response = requests.post(
                url, headers=headers, data=audio_file, timeout=(10, 120)
            )
        response.raise_for_status()
        payload = response.json()
        if payload.get("RecognitionStatus") != "Success":
            raise RuntimeError(
                "Azure Speech recognition failed: "
                f"{payload.get('RecognitionStatus', 'Unknown')}"
            )
        return payload.get("DisplayText", "")

    def process_video(self, video_path: str) -> Dict[str, Any]:
        """Extract audio, transcribe it, and remove the temporary audio file."""
        audio_path = self.extract_audio(video_path)
        try:
            return {
                "transcript": self.transcribe_audio(audio_path),
                "ocr_text": [],
                "video_metadata": {
                    "platform": "youtube",
                    "transcription_method": "azure-speech",
                    "language": self.language,
                },
            }
        finally:
            if os.path.exists(audio_path):
                os.remove(audio_path)