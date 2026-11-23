import tempfile
import unittest
from pathlib import Path
from app import parse_pasted_draft, PHOTO_MARKER_NATURAL, safe_naver_typing_text, compose, make_hook_title, make_subtitle


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

    def test_camera_emoji_photo_marker_is_image(self):
        data = parse_pasted_draft(
            "후킹 제목\n[부제목] 의정부 순대국 복실네\nQ. 외관은?\n"
            "📷 사진 1 — 식당 외관\nA.\n정감이 가는 곳이에요",
            self.photos)
        self.assertEqual(
            [block["type"] for block in data["blocks"]],
            ["hero_quote", "question", "image", "answer_label", "text"])
        self.assertEqual(data["blocks"][2]["path"], str(self.photos[0]))

    def test_blockquote_subtitle_is_preserved_not_fallback(self):
        data = parse_pasted_draft(
            "이 동네 국밥집이 이렇게 맛있다고?\n"
            "> 의정부 순대국 맛집 복실네 평양찹쌀순대\n"
            "Q. 외관은?\n📸 사진 1 — 외관\nA.\n좋았어요",
            self.photos, default_subtitle="잘못된 자동 부제목")
        self.assertEqual(data["blocks"][0]["type"], "hero_quote")
        self.assertEqual(
            data["blocks"][0]["value"],
            "의정부 순대국 맛집 복실네 평양찹쌀순대")

    def test_input_start_never_opens_another_naver_tab(self):
        import ast
        import inspect
        import textwrap
        import app
        tree = ast.parse(textwrap.dedent(inspect.getsource(app.automate_naver)))
        web_opens = [node for node in ast.walk(tree)
                     if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute)
                     and isinstance(node.func.value, ast.Name)
                     and node.func.value.id == 'webbrowser'
                     and node.func.attr == 'open']
        self.assertEqual(web_opens, [], "Input Start/F7 must not open a browser")
        manual_tree = ast.parse(textwrap.dedent(inspect.getsource(app.App.open_naver)))
        manual_opens = [node for node in ast.walk(manual_tree)
                        if isinstance(node, ast.Call)
                        and isinstance(node.func, ast.Attribute)
                        and isinstance(node.func.value, ast.Name)
                        and node.func.value.id == 'webbrowser'
                        and node.func.attr == 'open']
        self.assertEqual(len(manual_opens), 1, "Open Naver button should still open Naver")

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


    def test_explicit_subtitle_is_quote_block_not_body_text(self):
        data = parse_pasted_draft(
            "의정부에 이런 돼지갈비집이 있었다고?\n"
            "[부제목] 양촌리 돼지갈비 김치찌개 맛집 가족외식 추천\n"
            "안녕하세요 시아애비입니다\n"
            "Q. 외관이 어땠나요?\n"
            "📸 사진 1 — 외관\nA.\n큼직한 건물이 인상적이었어요",
            self.photos)
        self.assertEqual(data["title"], "의정부에 이런 돼지갈비집이 있었다고?")
        self.assertEqual([b["type"] for b in data["blocks"]],
                         ["hero_quote","text","question","image","answer_label","text"])
        self.assertEqual(data["blocks"][0]["value"], "양촌리 돼지갈비 김치찌개 맛집 가족외식 추천")
        self.assertEqual(data["blocks"][1]["value"], "안녕하세요 시아애비입니다")

    def test_markdown_subtitle_in_source(self):
        data = parse_pasted_draft(
            "# 의정부에 이런 돼지갈비집이 있었다고?\n"
            "### 양촌리 돼지갈비 김치찌개 맛집 가족외식 추천\n"
            "안녕하세요 시아애비입니다", self.photos)
        self.assertEqual(data["blocks"][0]["type"], "hero_quote")
        self.assertEqual(data["blocks"][1]["type"], "text")

    def test_pasted_draft_missing_subtitle_uses_explicit_ui_fallback(self):
        data = parse_pasted_draft(
            "의정부에 이런 돼지갈비집이 있었다고?\n안녕하세요 시아애비입니다",
            self.photos, default_subtitle="양촌리 돼지갈비 맛집")
        self.assertEqual(data["blocks"][0], {"type":"hero_quote","value":"양촌리 돼지갈비 맛집"})

    def test_generated_draft_keeps_name_in_quote_not_title(self):
        data = compose("의정부 양촌리", "돼지갈비 김치찌개", "",
                       self.photos[:1], [{"q":"외관은?","a":"건물이 커요"}],
                       title="의정부 양촌리 돼지갈비 맛집", keywords="맛집 가족외식 추천")
        self.assertNotIn("양촌리",data["title"])
        self.assertEqual(data["blocks"][0]["type"], "hero_quote")
        self.assertIn("양촌리",data["blocks"][0]["value"])
        self.assertIn("가족외식",data["blocks"][0]["value"])
        self.assertEqual(data["blocks"][2]["type"], "question")

    def test_hook_title_excludes_business_name(self):
        title=make_hook_title("의정부 양촌리","돼지갈비",
                              suggestion="양촌리 돼지갈비가 좋았어요")
        self.assertNotIn("양촌리",title)
        self.assertIn("돼지갈비",title)


    def test_legacy_coordinates_require_body_recapture(self):
        import json
        from unittest.mock import patch
        import app
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/"positions.json"
            config.write_text(json.dumps({"body_point":[800,450],
                                          "photo_button":[300,200],
                                          "quote_exit_offset":500}),encoding="utf-8")
            with patch.object(app,"CONFIG_PATH",config):
                saved=app.load_editor_positions()
            self.assertEqual(saved["body_point"],(800,450))
            self.assertFalse(saved["body_anchor_verified"])

    def test_new_verified_body_position_is_persisted(self):
        import json
        from types import SimpleNamespace
        from unittest.mock import patch
        import app
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/"positions.json"
            values=SimpleNamespace(
                body_anchor_verified=True,
                quote_exit_offset=SimpleNamespace(get=lambda: 500),
                **{name:(700,430) for name in app.POSITION_FIELDS})
            with patch.object(app,"CONFIG_DIR",Path(folder)), patch.object(app,"CONFIG_PATH",config):
                app.save_editor_positions(values)
                saved=app.load_editor_positions()
            self.assertTrue(saved["body_anchor_verified"])
            self.assertEqual(saved["body_point"],(700,430))

    def test_photo_files_sort_in_windows_numeric_order(self):
        import app
        with tempfile.TemporaryDirectory() as folder:
            for i in range(1,13):
                (Path(folder)/f"{i}.jpg").write_bytes(b"x")
            photos=app.sorted_photos(folder)
            self.assertEqual([p.stem for p in photos], [str(i) for i in range(1,13)])
            self.assertEqual(app.parse_pasted_draft("제목\n[사진 2]",photos)["blocks"][0]["path"],
                             str(Path(folder)/"2.jpg"))

    def test_mixed_names_and_gif_sort_naturally(self):
        import app
        with tempfile.TemporaryDirectory() as folder:
            for name in ("photo10.jpg","photo2.jpg","photo1.jpg","photo9.gif","readme.txt"):
                (Path(folder)/name).write_bytes(b"x")
            self.assertEqual([p.name for p in app.sorted_photos(folder)],
                             ["photo1.jpg","photo2.jpg","photo9.gif","photo10.jpg"])


    def test_legacy_total_review_converts_to_prose_frame(self):
        draft=("궁금증 유발 제목\n[부제목] 양촌리 맛집\n"
               "Q. 외관이 어때요?\n[사진 1]\nA.\n크고 멋져요\n"
               "Q. 의정부 양촌리 총평은 어떨까요?\n"
               "A.\n가족외식 장소로 좋아요\n시아애비였습니다\n"
               "#의정부양촌리 #돼지갈비")
        data=parse_pasted_draft(draft,self.photos)
        self.assertEqual([b["type"] for b in data["blocks"]],
                         ["hero_quote","question","image","answer_label","text",
                          "final_quote","text"])
        self.assertNotIn("Q.",data["blocks"][-2]["value"])
        self.assertNotIn("A.",data["blocks"][-2]["value"])
        self.assertIn("가족외식",data["blocks"][-2]["value"])
        self.assertEqual(data["blocks"][-1]["value"],"#의정부양촌리 #돼지갈비")

    def test_explicit_final_frame_marker(self):
        raw=("의정부에 이렇게 큰 고깃집이?\n[부제목] 양촌리 돼지갈비 맛집\n"
             "Q. 외관은?\n[사진 1]\nA.\n넓어요\n"
             "[마무리]\n가족외식 장소로 좋았어요\n"
             "오늘도 맛있는 하루 보내세요\n시아애비였습니다\n"
             "#의정부양촌리")
        data=parse_pasted_draft(raw,self.photos)
        self.assertEqual([b["type"] for b in data["blocks"]][-2:],
                         ["final_quote","text"])
        self.assertEqual(data["blocks"][-2]["value"],
                         "가족외식 장소로 좋았어요\n오늘도 맛있는 하루 보내세요\n시아애비였습니다")

    def test_generated_final_quote_has_no_question_or_answer(self):
        from app import compose
        data=compose("의정부 양촌리","돼지갈비","",self.photos[:1],
                     sections=[{"q":"외관은?","a":"큰 건물이에요"}])
        kinds=[b["type"] for b in data["blocks"]]
        self.assertEqual(kinds[-2:],["final_quote","text"])
        self.assertNotIn("Q.",data["blocks"][-2]["value"])
        self.assertIn("시아애비",data["blocks"][-2]["value"])

    def test_normal_question_keeps_question_quote_style(self):
        data=parse_pasted_draft("제목\nQ. 메뉴는 어떤가요?\nA.\n좋아요",self.photos)
        self.assertEqual(data["blocks"][0]["type"],"question")
        self.assertEqual(data["blocks"][1]["value"],"A.")


if __name__ == "__main__":
    unittest.main()
