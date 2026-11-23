import tempfile
import unittest
from pathlib import Path
from app import parse_pasted_draft, PHOTO_MARKER_NATURAL, safe_naver_typing_text


class DraftParsingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.photos = [Path(self.temp.name) / "1.jpg", Path(self.temp.name) / "2.jpg"]
        for photo in self.photos:
            photo.write_bytes(b"fake-image-for-parser-test")

    def tearDown(self):
        self.temp.cleanup()

    def test_natural_photo_marker_and_bold_question(self):
        raw = ("의정부 양촌리 후기\n\n"
               "**Q. 양촌리는 어떤 곳일까요?**\n"
               "📸 사진 1 — 매장 외관\n\n"
               "A.\n"
               "가게 외관이 눈에 띄었어요\n"
               "다음 줄도 짧게 적어요")
        data = parse_pasted_draft(raw, self.photos)
        kinds = [block["type"] for block in data["blocks"]]
        self.assertEqual(kinds, ["question", "image", "answer_label", "text"])
        self.assertEqual(data["blocks"][0]["value"], "Q. 양촌리는 어떤 곳일까요?")
        self.assertEqual(data["blocks"][1]["path"], str(self.photos[0]))
        self.assertEqual(data["blocks"][2]["value"], "A.")
        self.assertEqual(data["blocks"][3]["value"], "가게 외관이 눈에 띄었어요\n다음 줄도 짧게 적어요")

    def test_bracketed_marker(self):
        data = parse_pasted_draft("제목\n[사진 2]", self.photos)
        self.assertEqual(data["blocks"][0]["type"], "image")
        self.assertEqual(data["blocks"][0]["path"], str(self.photos[1]))

    def test_photo_not_converted_to_text(self):
        with self.assertRaises(ValueError):
            parse_pasted_draft("제목\n사진 99 — 없는 사진", self.photos)

    def test_no_duplicate_photos(self):
        with self.assertRaises(ValueError):
            parse_pasted_draft("제목\n📸 사진 1 — 첫 장\n[사진 1]", self.photos)

    def test_sanitize_unrenderable_emoji_without_damaging_korean(self):
        original = "안녕하세요 시아애비입니다 \ufffd😊"
        self.assertEqual(safe_naver_typing_text(original).strip(), "안녕하세요 시아애비입니다")
        self.assertEqual(safe_naver_typing_text("사진📸 1 — 매장 외관"), "사진 1 — 매장 외관")

    def test_answer_label_always_separate(self):
        data = parse_pasted_draft("제목\nQ. 외관은?\n📸 사진 1 — 외관\nA.\n답변입니다",self.photos)
        self.assertEqual([b["type"] for b in data["blocks"]],
                         ["question","image","answer_label","text"])


if __name__ == "__main__":
    unittest.main()
