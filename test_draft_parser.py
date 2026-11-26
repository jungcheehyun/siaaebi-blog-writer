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

    def test_short_filename_numbers_sort_and_resolve_in_order(self):
        import app
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ("10.jpg","2.jpg","1.jpg","3.png"):
                (root/name).write_bytes(b"test")
            photos=app.sorted_photos(root)
            self.assertEqual([p.name for p in photos],
                             ["1.jpg","2.jpg","3.png","10.jpg"])
            parsed=app.parse_pasted_draft(
                "후킹 제목\n[부제목] 김선장횟집 방어회\n"
                "Q. 매장 모습은?\n[사진 1]\nA.\n좋아요\n"
                "Q. 음식은?\n[사진 2]\nA.\n맛있어요",photos)
            images=[b["path"] for b in parsed["blocks"] if b["type"]=="image"]
            self.assertEqual([Path(p).name for p in images],["1.jpg","2.jpg"])

    def test_filename_focus_shortcut_does_not_fire_if_another_window_is_active(self):
        import app,sys
        from unittest.mock import patch,MagicMock
        from types import SimpleNamespace
        fake_gui=SimpleNamespace(GetForegroundWindow=lambda:777)
        fake_auto=SimpleNamespace(hotkey=MagicMock())
        with patch.dict(sys.modules,{"win32gui":fake_gui,"pyautogui":fake_auto}):
            focused=app._recover_filename_control_with_shortcut(
                123,lambda value:None)
        self.assertIsNone(focused)
        fake_auto.hotkey.assert_not_called()

    def test_filename_focus_shortcut_checks_focus_after_keypress(self):
        import app,sys
        from unittest.mock import patch,MagicMock
        from types import SimpleNamespace
        fake_gui=SimpleNamespace(GetForegroundWindow=lambda:123)
        fake_auto=SimpleNamespace(hotkey=MagicMock())
        with patch.dict(sys.modules,{"win32gui":fake_gui,"pyautogui":fake_auto}):
            with patch.object(app,"_focused_windows_filename_control",
                              return_value=456) as focus:
                with patch.object(app.time,"sleep"):
                    value=app._recover_filename_control_with_shortcut(
                        123,lambda value:None)
        self.assertEqual(value,456)
        fake_auto.hotkey.assert_called_once_with("alt","n")
        focus.assert_called_once_with(123)

    def test_file_picker_recovery_is_path_verified_and_never_blind_enter(self):
        import app,inspect
        source=inspect.getsource(app.upload_via_naver_button)
        self.assertIn("_recover_filename_control_with_shortcut(dialog,notify)",source)
        self.assertIn("_write_windows_file_name(focus_edit,str(path))",source)
        self.assertIn("_paste_windows_file_name(focus_edit,str(path))",source)
        self.assertIn("if not opened:",source)
        self.assertNotIn("pyautogui.press('enter')",source)
        self.assertNotIn("hotkey('ctrl', 'l')",source)

    def test_windows_filename_is_written_and_verified_with_correct_win32_lengths(self):
        import ctypes
        import app
        filename=r'C:\\Users\\user\\OneDrive\\사진\\한글 사진 01.jpg'
        writes=[]
        state={'value':''}
        def sender(hwnd,msg,wparam,ptr,flags,timeout,result):
            if msg==0x000C:
                self.assertEqual(wparam,0)
                state['value']=ctypes.wstring_at(ptr)
                writes.append(('set',wparam))
                ctypes.cast(result,ctypes.POINTER(ctypes.c_size_t))[0]=1
            elif msg==0x000D:
                # Regression: old code sent wParam=0 and could only read empty text.
                self.assertGreater(wparam,len(state['value']))
                self.assertGreater(wparam,0)
                value=ctypes.create_unicode_buffer(state['value'])
                ctypes.memmove(ptr,value,ctypes.sizeof(value))
                writes.append(('get',wparam))
                ctypes.cast(result,ctypes.POINTER(ctypes.c_size_t))[0]=len(state['value'])
            else:
                self.fail('unexpected native message')
            return 1
        self.assertTrue(app._write_windows_file_name(12345,filename,sender=sender))
        self.assertEqual(state['value'],filename)
        self.assertEqual([kind for kind,_ in writes],['set','get'])

    def test_windows_filename_verification_rejects_empty_or_wrong_text(self):
        import ctypes
        import app
        expected=r'C:\\Pictures\\correct.jpg'
        for response in ('',r'C:\\Pictures\\wrong.jpg'):
            with self.subTest(response=response):
                def sender(hwnd,msg,wparam,ptr,flags,timeout,result):
                    if msg==0x000D:
                        self.assertGreater(wparam,0)
                        data=ctypes.create_unicode_buffer(response)
                        ctypes.memmove(ptr,data,ctypes.sizeof(data))
                        ctypes.cast(result,ctypes.POINTER(ctypes.c_size_t))[0]=len(response)
                    else:
                        ctypes.cast(result,ctypes.POINTER(ctypes.c_size_t))[0]=1
                    return 1
                self.assertFalse(app._verify_windows_file_name(12345,expected,sender=sender))

    def test_photo_upload_does_not_use_unverified_enter_or_address_bar(self):
        import inspect,app
        body=inspect.getsource(app.upload_via_naver_button)
        self.assertNotIn("hotkey('ctrl', 'l')",body)
        self.assertNotIn("hotkey('alt', 'n')",body)
        self.assertNotIn("pyautogui.press('enter')",body)
        self.assertIn("_write_windows_file_name(edit,str(path))",body)
        self.assertIn("_paste_windows_file_name(edit,str(path))",body)

    def test_final_frame_exit_creates_separate_normal_paragraph(self):
        import app, sys
        from unittest.mock import patch
        from types import SimpleNamespace
        actions=[]
        fake=SimpleNamespace(
            press=lambda key,**kwargs: actions.append(('press',key,kwargs)))
        with patch.dict(sys.modules,{'pyautogui':fake}):
            with patch.object(app.time,'sleep'):
                app.exit_final_quote(lambda msg: actions.append(('notify',msg,{})))
        presses=[(name,kwargs) for typ,name,kwargs in actions if typ=='press']
        self.assertEqual([name for name,_ in presses],['end','down','enter'])
        self.assertEqual(presses[1][1]['presses'],2)
        self.assertEqual(presses[1][1]['interval'],.3)
        self.assertNotEqual([name for name,_ in presses],['end','enter'])

    def test_photo_delay_is_saved_per_pc_and_old_config_defaults_to_12(self):
        import json, app
        from unittest.mock import patch
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            config=Path(folder)/'editor_positions.json'
            config.write_text(json.dumps({'quote_exit_offset':500,
                                          'body_anchor_verified':True}),encoding='utf-8')
            with patch.object(app,'CONFIG_PATH',config):
                self.assertEqual(app.load_editor_positions()['photo_settle_seconds'],12)
            controls=SimpleNamespace(
                quote_exit_offset=SimpleNamespace(get=lambda:500),
                photo_settle_seconds=SimpleNamespace(get=lambda:22),
                body_anchor_verified=True,
                **{name:(700,450) for name in app.POSITION_FIELDS})
            with patch.object(app,'CONFIG_DIR',Path(folder)),patch.object(app,'CONFIG_PATH',config):
                app.save_editor_positions(controls)
                loaded=app.load_editor_positions()
            self.assertEqual(loaded['photo_settle_seconds'],22)
            self.assertEqual(loaded['body_point'],(700,450))
            self.assertTrue(loaded['body_anchor_verified'])

    def test_slow_pc_photo_delay_is_configurable_and_bounded(self):
        import app,inspect
        source=inspect.getsource(app.upload_via_naver_button)
        self.assertIn('photo_settle_seconds=12',inspect.signature(app.upload_via_naver_button).__str__())
        self.assertIn('delay=min(36,base+size_padding+',source)
        self.assertIn('_wait_for_native_file_dialog(timeout=16.0)',source)
        self.assertIn('range(100)',source)
        self.assertIn('네이버 사진 처리 대기',source)

    def test_chatgpt_prompt_matches_parser_and_prefills_current_fields(self):
        import app
        prompt=app.build_chatgpt_draft_prompt(
            shop="복실네 평양찹쌀순대", menu="평양정식, 만둣국",
            keywords="의정부 순대국 맛집", photo_count=13)
        self.assertIn("상호명: 복실네 평양찹쌀순대", prompt)
        self.assertIn("대표메뉴: 평양정식, 만둣국", prompt)
        self.assertIn("검색 키워드: 의정부 순대국 맛집", prompt)
        self.assertIn("사진 수: 13장 — 사진 1부터 사진 13까지", prompt)
        self.assertIn("[부제목]", prompt)
        self.assertIn("Q. 사진 내용과 관련된 자연스러운 질문?", prompt)
        self.assertIn("[사진 1]\nA.\n", prompt)
        self.assertIn("[마무리]\n", prompt)
        self.assertIn("말투", prompt)
        self.assertIn("완성 원고만 출력", prompt)
        self.assertNotIn("OPENAI_API_KEY",prompt)
        sample = ("후킹 제목\n[부제목] 의정부 순대국 맛집 복실네\n"
                  "안녕하세요\nQ. 어떤가요?\n[사진 1]\nA.\n맛있어요\n"
                  "[마무리]\n또 먹고 싶어요\n#의정부맛집")
        parsed = app.parse_pasted_draft(sample, self.photos)
        self.assertEqual([b["type"] for b in parsed["blocks"]],
                         ["hero_quote","text","question","image","answer_label",
                          "text","final_quote","text","text"])
        self.assertEqual(parsed["blocks"][-3]["value"], "마무리한마디")

    def test_copy_chatgpt_prompt_button_writes_clipboard_without_browser(self):
        import app
        from unittest.mock import MagicMock, patch
        from types import SimpleNamespace
        root=MagicMock()
        root.clipboard_append.side_effect=lambda value: None
        fake=SimpleNamespace(
            folder=SimpleNamespace(get=lambda: "photos"),
            shop=SimpleNamespace(get=lambda: "복실네"),
            menu=SimpleNamespace(get=lambda: "순대국"),
            keywords=SimpleNamespace(get=lambda *args: "지역맛집\n"),
            root=root,
            setstatus=MagicMock())
        with patch.object(app, "sorted_photos", return_value=self.photos), \
             patch.object(app.messagebox, "showinfo") as info, \
             patch.object(app.messagebox, "showerror") as error, \
             patch.object(app.webbrowser, "open") as browse:
            app.App.copy_chatgpt_prompt(fake)
        root.clipboard_clear.assert_called_once()
        root.clipboard_append.assert_called_once()
        root.update_idletasks.assert_called_once()
        self.assertIn("사진 수: 2장", root.clipboard_append.call_args.args[0])
        info.assert_called_once()
        error.assert_not_called()
        browse.assert_not_called()

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
                          "final_quote","text","text"])
        self.assertEqual(data["blocks"][-3]["value"], "마무리한마디")
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
        self.assertEqual([b["type"] for b in data["blocks"]][-3:],
                         ["final_quote","text","text"])
        self.assertEqual(data["blocks"][-3]["value"], "마무리한마디")
        self.assertEqual(data["blocks"][-2]["value"],
                         "가족외식 장소로 좋았어요\n오늘도 맛있는 하루 보내세요\n시아애비였습니다")

    def test_generated_final_quote_has_no_question_or_answer(self):
        from app import compose
        data=compose("의정부 양촌리","돼지갈비","",self.photos[:1],
                     sections=[{"q":"외관은?","a":"큰 건물이에요"}])
        kinds=[b["type"] for b in data["blocks"]]
        self.assertEqual(kinds[-3:],["final_quote","text","text"])
        self.assertEqual(data["blocks"][-3]["value"], "마무리한마디")
        self.assertIn("시아애비",data["blocks"][-2]["value"])

    def test_final_frame_preview_does_not_wrap_closing_prose(self):
        from app import save_preview
        from unittest.mock import patch
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with patch('app.OUTPUT', Path(folder)):
                data = parse_pasted_draft(
                    "후킹 제목\n[부제목] 복실네 순대국 맛집\n"
                    "[마무리]\n정말 맛있었어요\n또 갈게요\n"
                    "#맛집 #시아애비", self.photos)
                preview = save_preview(data).read_text(encoding='utf-8')
        self.assertIn('class="final-frame">마무리한마디</blockquote>', preview)
        self.assertIn('<p>정말 맛있었어요</p>', preview)
        self.assertNotIn('class="final-frame">정말 맛있었어요', preview)

    def test_image_upload_never_navigates_to_image_path_in_address_bar(self):
        import inspect, app
        body = inspect.getsource(app.upload_via_naver_button)
        self.assertNotIn("hotkey('ctrl', 'l')", body)
        self.assertIn("사진 선택 후 네이버 브라우저가 활성화되지 않았습니다", body)

    def test_resume_checkpoint_matches_exact_draft(self):
        import app
        from unittest.mock import patch
        draft = app.parse_pasted_draft(
            "후킹 제목\n[부제목] 맛집 메뉴\nQ. 외관은?\n[사진 1]\nA.\n좋아요",
            self.photos)
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(app, "RESUME_PATH", Path(folder) / "resume.json"):
                app.write_resume_checkpoint(draft, 2, True, "running")
                self.assertEqual(app.read_resume_checkpoint(draft)["next_block"], 2)
                self.assertEqual(app.read_resume_checkpoint(draft)["phase"], "running")
                changed = dict(draft, title="다른 블로그 제목")
                self.assertIsNone(app.read_resume_checkpoint(changed))
                app.write_resume_checkpoint(draft, 3, True, "ready")
                self.assertEqual(app.read_resume_checkpoint(draft)["next_block"], 3)
                app.clear_resume_checkpoint(draft)
                self.assertIsNone(app.read_resume_checkpoint(draft))

    def test_resumed_automator_skips_title_and_completed_blocks(self):
        import app
        from unittest.mock import patch
        from types import SimpleNamespace
        import sys
        draft = {"title": "다시 쓰면 안 되는 제목", "blocks": [
            {"type": "text", "value": "이미 입력된 내용"},
            {"type": "text", "value": "이어쓸 내용"}]}
        calls = []
        fake = SimpleNamespace(PAUSE=0,press=lambda *a,**k: None)
        with patch.dict(sys.modules, {"pyautogui": fake}):
            with patch.object(app, "type_unicode_text") as typed:
                with patch.object(app, "check_control"), patch.object(app.time, "sleep"):
                    app.automate_naver(
                        draft, lambda message: None, lambda: True,
                        (200,100), (800,500), (500,100), (600,200),
                        (600,250), (600,300), 500, None, None,
                        start_block=1, title_done=True,
                        progress=lambda stage,index: calls.append((stage,index)))
        self.assertEqual(typed.call_count, 1)
        self.assertEqual(typed.call_args.args[0], "이어쓸 내용")
        self.assertEqual(calls, [("block_start", 1), ("block_done", 1)])

    def test_resume_after_image_keeps_image_previous_block_semantics(self):
        import app
        from unittest.mock import patch
        from types import SimpleNamespace
        import sys
        draft = {"title": "제목", "blocks": [
            {"type": "question", "value": "Q. 어떤가요?"},
            {"type": "image", "path": str(self.photos[0])},
            {"type": "answer_label", "value": "A."},
            {"type": "text", "value": "답변 내용"}]}
        calls = []
        fake = SimpleNamespace(PAUSE=0, press=lambda *a,**k: calls.append(a))
        with patch.dict(sys.modules, {"pyautogui": fake}):
            with patch.object(app, "type_unicode_text") as typed:
                with patch.object(app, "check_control"), patch.object(app.time, "sleep"):
                    app.automate_naver(
                        draft, lambda message: None, lambda: True,
                        (200,100), (800,500), (500,100), (600,200),
                        (600,250), (600,300), 500, None, None,
                        start_block=2, title_done=True)
        self.assertEqual(typed.call_count, 2)
        self.assertEqual(typed.call_args_list[0].args[0], "A.")
        self.assertEqual(typed.call_args_list[1].args[0], "답변 내용")
        self.assertEqual(calls, [('enter',)])

    def test_normal_question_keeps_question_quote_style(self):
        data=parse_pasted_draft("제목\nQ. 메뉴는 어떤가요?\nA.\n좋아요",self.photos)
        self.assertEqual(data["blocks"][0]["type"],"question")
        self.assertEqual(data["blocks"][1]["value"],"A.")


if __name__ == "__main__":
    unittest.main()
