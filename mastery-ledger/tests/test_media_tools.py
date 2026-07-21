from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

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
    def run_script(self, name: str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ROOT / "scripts" / name), *args],
            check=check,
            capture_output=True,
            text=True,
        )

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

    def test_metadata_probe_needs_no_rights_declaration_but_acquisition_does(self) -> None:
        tool = load_module("download_media_rights", "scripts/download_media.py")
        self.assertEqual("not_applicable_metadata_probe", tool.resolve_rights_basis("probe", None))
        self.assertEqual(
            "user_attested_authorized_use",
            tool.resolve_rights_basis("human_subtitles", "user_attested_authorized_use"),
        )
        with self.assertRaisesRegex(ValueError, "learner-confirmed authorization"):
            tool.resolve_rights_basis("automatic_subtitles", None)

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

    def test_local_media_transcript_is_registered_and_visible_to_extractor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            self.run_script("init_study.py", "Media Course", "--mode", "local-media", "--studies-dir", str(parent))
            course = parent / "media-course"
            self.run_script(
                "record_scope_approval.py",
                str(course),
                "--summary",
                "Learn from one supplied video",
                "--source-limit",
                "1",
                "--research-workers",
                "0",
                "--chapter-count",
                "1",
            )
            staged = ROOT / "tests" / "fixtures" / "sample.vtt"
            promoted = self.run_script(
                "promote_media_artifact.py",
                str(course),
                "--source-id",
                "SRC-001",
                "--input",
                str(staged),
                "--filename",
                "source.en.vtt",
                "--kind",
                "raw_caption",
            )
            self.assertEqual("records/source/media/SRC-001/source.en.vtt", json.loads(promoted.stdout)["path"])
            bundle = course / "records" / "source" / "media" / "SRC-001"
            self.run_script(
                "normalize_subtitles.py",
                str(bundle / "source.en.vtt"),
                "--output-dir",
                str(bundle),
                "--source-id",
                "SRC-001",
                "--item-id",
                "VIDEO-001",
                "--origin",
                "auto_caption",
                "--language",
                "en",
            )
            knowledge = course / "records" / "source" / "SRC-001.md"
            knowledge.write_text(
                "# Supplied video\n\nA locator-oriented note backed by the durable transcript bundle.\n",
                encoding="utf-8",
            )
            self.run_script(
                "register_source.py",
                str(course),
                "--source-id",
                "SRC-001",
                "--title",
                "Supplied video",
                "--location",
                "https://example.invalid/video",
                "--knowledge-path",
                "records/source/SRC-001.md",
                "--provider",
                "Fixture provider",
                "--source-type",
                "video",
                "--rights-basis",
                "user_attested_authorized_use",
                "--processing-mode",
                "local_only",
                "--artifact",
                "raw_caption=records/source/media/SRC-001/source.en.vtt",
                "--artifact",
                "transcript_markdown=records/source/media/SRC-001/transcript.md",
                "--artifact",
                "transcript_json=records/source/media/SRC-001/transcript.json",
            )
            reconciled = self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            self.assertEqual("CORPUS_MAPPED", json.loads(reconciled.stdout)["current_state"])
            self.run_script("create_provided_evidence_plan.py", str(course), "--authorized")
            self.run_script("compile_worker_context.py", str(course), "TASK-EXTRACT-SRC-001", "--json")
            plan = yaml.safe_load(
                (course / ".work" / "orchestration" / "run-plan.yaml").read_text(encoding="utf-8")
            )
            task = next(item for item in plan["task_graph"] if item["task_id"] == "TASK-EXTRACT-SRC-001")
            context = json.loads((course / task["context_path"]).read_text(encoding="utf-8"))
            allowed = {item["path"] for item in context["allowed_inputs"]}
            self.assertIn("records/source/media/SRC-001/transcript.md", allowed)
            self.assertIn("records/source/media/SRC-001/transcript.json", allowed)
            manifest = yaml.safe_load((course / "records" / "source-manifest.yaml").read_text(encoding="utf-8"))
            record = manifest["sources"][0]
            self.assertEqual("local_only", record["processing_mode"])
            self.assertIn("transcription", record["permitted_uses"])
            self.assertTrue(all(item.get("content_hash", "").startswith("sha256:") for item in record["artifacts"]))

    def test_local_media_plan_rejects_source_without_registered_transcript(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parent = Path(directory)
            self.run_script("init_study.py", "Missing Transcript", "--mode", "local-media", "--studies-dir", str(parent))
            course = parent / "missing-transcript"
            self.run_script(
                "record_scope_approval.py",
                str(course),
                "--summary",
                "Learn from one supplied video",
                "--source-limit",
                "1",
                "--research-workers",
                "0",
                "--chapter-count",
                "1",
            )
            knowledge = course / "records" / "source" / "SRC-001.md"
            knowledge.write_text("# Video metadata\n\nA metadata-only note without a durable transcript.\n", encoding="utf-8")
            self.run_script(
                "register_source.py",
                str(course),
                "--source-id",
                "SRC-001",
                "--title",
                "Video",
                "--location",
                "https://example.invalid/video",
                "--knowledge-path",
                "records/source/SRC-001.md",
                "--source-type",
                "video",
            )
            self.run_script("reconcile_workflow.py", str(course), "--json", check=False)
            rejected = self.run_script("create_provided_evidence_plan.py", str(course), "--authorized", check=False)
            self.assertNotEqual(0, rejected.returncode)
            self.assertIn("durable transcript.md or transcript.json", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
