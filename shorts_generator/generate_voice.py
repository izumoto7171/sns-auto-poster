"""
音声生成 - VOICEVOX HTTP API優先、無音WAVフォールバック
"""
import struct
import wave
import requests
from config import VOICEVOX_URL, VOICEVOX_SPEAKER


def _silent_wav(output_path: str, duration_sec: float) -> str:
    """無音WAVを生成"""
    sample_rate = 24000
    n_samples = int(sample_rate * duration_sec)
    with wave.open(output_path, "w") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(sample_rate)
        f.writeframes(struct.pack("<" + "h" * n_samples, *([0] * n_samples)))
    return output_path


def generate_voice(text: str, output_path: str, speaker_id: int = None) -> str:
    """
    VOICEVOXでテキストを音声に変換。
    未起動の場合は無音WAVを生成。
    """
    if speaker_id is None:
        speaker_id = VOICEVOX_SPEAKER

    try:
        # audio_query生成
        res = requests.post(
            f"{VOICEVOX_URL}/audio_query",
            params={"text": text, "speaker": speaker_id},
            timeout=10,
        )
        res.raise_for_status()
        query = res.json()

        # 音声合成
        audio_res = requests.post(
            f"{VOICEVOX_URL}/synthesis",
            params={"speaker": speaker_id},
            json=query,
            timeout=30,
        )
        audio_res.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(audio_res.content)
        return output_path

    except Exception as e:
        print(f"⚠️  VOICEVOX未起動または失敗: {e} → 無音WAV生成")
        # テキスト量から推定秒数（1文字≒0.15秒）
        duration = max(1.5, len(text) * 0.15)
        return _silent_wav(output_path, duration)
