from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MediaToolTests(unittest.TestCase):
    def test_media_options_use_python_api_and_keep_caption_origins_separate(self) -> None:
        tool = load_module("download_media", "scripts/download_media.py")
        human = tool.build_options(
            output_dir=Path("out"),
            source_id="SRC-1",
            mode="human_subtitles",
            languages=["en.*"],
            playlist=False,
        )
        automatic = tool.build_options(
            output_dir=Path("out"),
            source_id="SRC-1",
            mode="automatic_subtitles",
            languages=["en.*"],
            playlist=False,
        )
        self.assertTrue(human["ignoreconfig"])
        self.assertTrue(human["noplaylist"])
        self.assertTrue(human["writesubtitles"])
        self.assertFalse(human["writeautomaticsub"])
        self.assertFalse(automatic["writesubtitles"])
        self.assertTrue(automatic["writeautomaticsub"])
        self.assertIn("SRC-1", human["outtmpl"]["default"])

        located = tool.build_options(
            output_dir=Path("out"),
            source_id="SRC-1",
            mode="video",
            languages=["en.*"],
            playlist=False,
            ffmpeg_location=Path("tools/ffmpeg"),
        )
        self.assertTrue(Path(located["ffmpeg_location"]).is_absolute())

    def test_media_runtime_probe_is_read_only_and_reports_dependency_ownership(self) -> None:
        tool = load_module("check_media_runtime", "scripts/check_media_runtime.py")
        payload = tool.inspect_runtime()
        self.assertEqual("media-runtime-v1", payload["schema_version"])
        self.assertIn(payload["status"], {"ready", "degraded"})
        self.assertIn("yt_dlp", payload["packages"])
        self.assertIn("ffmpeg", payload["native_tools"])
        self.assertIn("never an individual course run", payload["ownership"]["updates"])
        self.assertIsInstance(payload["capabilities"]["caption_acquisition"], bool)

    def test_media_source_id_rejects_unsafe_paths(self) -> None:
        tool = load_module("download_media_validation", "scripts/download_media.py")
        with self.assertRaises(ValueError):
            tool.validate_source_id("../outside")

    def test_srt_parser_preserves_cue_ids_and_timestamps(self) -> None:
        tool = load_module("normalize_subtitles", "scripts/normalize_subtitles.py")
        content = (ROOT / "tests" / "fixtures" / "sample.srt").read_text(encoding="utf-8")
        cues = tool.parse_srt(content)
        self.assertEqual("1", cues[0]["cue_id"])
        self.assertEqual(1000, cues[0]["start_ms"])
        self.assertEqual(3500, cues[1]["end_ms"])
        self.assertIn("reinforcement learning", cues[0]["text"].lower())

    def test_vtt_normalizer_removes_incremental_caption_overlap(self) -> None:
        tool = load_module("normalize_subtitles", "scripts/normalize_subtitles.py")
        content = (ROOT / "tests" / "fixtures" / "sample.vtt").read_text(encoding="utf-8")
        cues = tool.parse_vtt(content)
        segments = tool.build_segments(cues, max_segment_ms=30000, max_gap_ms=1500)
        combined = " ".join(segment["text"] for segment in segments).lower()
        self.assertEqual(1, combined.count("the agent explores"))
        self.assertIn("and the environment responds", combined)
        self.assertTrue(all(segment["cue_ids"] for segment in segments))

    def test_write_outputs_preserves_locator_mapping(self) -> None:
        tool = load_module("normalize_subtitles", "scripts/normalize_subtitles.py")
        content = (ROOT / "tests" / "fixtures" / "sample.srt").read_text(encoding="utf-8")
        cues = tool.parse_srt(content)
        segments = tool.build_segments(cues)
        with tempfile.TemporaryDirectory() as temp_dir:
            json_path, md_path = tool.write_outputs(
                cues=cues,
                segments=segments,
                output_dir=Path(temp_dir),
                source_id="SRC-1",
                item_id="LESSON-1",
                origin="human_caption",
                source_path="sample.srt",
            )
            payload = json.loads(json_path.read_text(encoding="utf-8"))
            self.assertEqual("SRC-1", payload["source_id"])
            self.assertEqual(["1", "2"], payload["segments"][0]["cue_ids"])
            self.assertIn("00:00:01.000", md_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
