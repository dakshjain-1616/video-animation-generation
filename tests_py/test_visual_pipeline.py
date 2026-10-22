"""Reference propagation and complete vision verdicts, without external APIs."""
from unittest.mock import patch

import pytest

from vga.codegen import _code_brief
from vga.llm import LlmConfig, resolve_llm_config
from vga.models import Scene, Storyboard
from vga.plan import make_plan
from vga.review import review_scenes

CONFIG = LlmConfig('openai', 'test', 'key', 'https://example.test')
REPORT = {'status': 'ok', 'sources': [{'url': 'https://example.com/motion', 'title': 'Motion example', 'content': 'A recording waveform expands.'}]}


def board(plan):
    return Storyboard(id='test', title='test', category='explainer', target=20, fps=30,
                      width=1080, height=1920, entry='test.tsx',
                      scenes=[Scene(s.id, s.title, s.kind, s.surface, 4, 120) for s in plan.scenes])


def referenced_plan():
    def answer(config, messages, validate, **kwargs):
        assert 'UNTRUSTED WEB REFERENCE DATA' in messages[1]['content']
        assert 'https://example.com/motion' in messages[1]['content']
        return validate({'title': 'Voice', 'angle': 'Sound becomes data', 'audience': 'Phone users',
                         'scenes': [{'title': f'STEP {i}', 'visual': f'A microphone changes {i}',
                                     'weight': 4, 'surface': 'paper'} for i in range(5)]})
    with patch('vga.plan.chat_json', side_effect=answer):
        plan = make_plan('How voice notes work', 20, [], CONFIG, research=REPORT)
    assert plan.to_dict()['research'] == REPORT
    brief = _code_brief(board(plan), plan, [])
    assert 'https://example.com/motion' in brief
    assert 'UNTRUSTED WEB REFERENCE DATA' in brief
    return plan


def test_references_reach_planner_and_codegen():
    referenced_plan()


@pytest.mark.parametrize('rows', [[], [{'id': 'scene01', 'verdict': 'ok'}] * 5,
                                    [{'id': 'scene01', 'verdict': 'maybe'}],
                                    [{'id': 'scene01', 'verdict': 'fix', 'problem': ''}]])
def test_incomplete_or_invalid_review_cannot_pass(rows):
    plan = referenced_plan()
    with patch('vga.review.thumbnail', return_value='data:image/jpeg;base64,x'), \
         patch('vga.review.chat_json', side_effect=lambda c, m, validate, **kw: validate({'scenes': rows})):
        with pytest.raises(ValueError):
            review_scenes(board(plan), plan, ['still'] * 5, CONFIG)


def test_openrouter_defaults_to_visual_capable_quality_model():
    config = resolve_llm_config({'OPENROUTER_API_KEY': 'test'})
    assert config.model == 'anthropic/claude-sonnet-5.5'


def test_vision_review_receives_midpoint_and_late_frames():
    plan = referenced_plan()
    def verdict(config, messages, validate, **kwargs):
        content = messages[1]['content']
        assert sum(row['type'] == 'image_url' for row in content) == 10
        assert any('near 85%' in row.get('text', '') for row in content)
        assert any('(body, layout canvas)' in row.get('text', '') for row in content)
        return validate({'scenes': [{'id': scene.id, 'verdict': 'ok', 'problem': ''} for scene in plan.scenes]})
    with patch('vga.review.thumbnail', return_value='data:image/jpeg;base64,x'), \
         patch('vga.review.chat_json', side_effect=verdict):
        assert review_scenes(board(plan), plan, ['still'] * 10, CONFIG) == []


def test_removed_asset_cannot_leave_a_media_layout():
    from vga.plan import repair_plan
    plan = referenced_plan()
    plan.scenes[0].asset = 'proof'
    plan.scenes[0].layout = 'media'
    plan.scenes[1].asset = 'proof'
    plan.scenes[1].layout = 'media'
    plan.scenes[2].layout = 'media'
    repair_plan(plan, frozenset({'proof'}))
    assert plan.scenes[0].asset == 'proof'
    assert plan.scenes[1].asset is None and plan.scenes[1].layout == 'canvas'
    assert plan.scenes[2].layout == 'canvas'


MOTION = {'start': 'One intact waveform', 'action': 'Slice it into three packets',
          'end': 'Three separate packets are visibly queued'}


def motion_plan(motion):
    def answer(config, messages, validate, **kwargs):
        assert '"motion"' in messages[1]['content']
        assert '75%' in messages[1]['content']
        scenes = [{'title': f'STEP {i}', 'visual': 'Sound packets are queued',
                   'weight': 4, 'surface': 'paper', 'motion': motion} for i in range(5)]
        return validate({'title': 'Voice', 'angle': 'Sound becomes data',
                         'audience': 'Phone users', 'scenes': scenes})
    with patch('vga.plan.chat_json', side_effect=answer):
        return make_plan('How voice notes work', 20, [], CONFIG)


def test_motion_beats_persist_and_reach_codegen_and_review():
    plan = motion_plan(MOTION)
    assert plan.to_dict()['scenes'][0]['motion'] == MOTION
    brief = _code_brief(board(plan), plan, [])
    assert all(value in brief for value in MOTION.values())
    assert 'complete by 75% and hold' in brief
    def verdict(config, messages, validate, **kwargs):
        text = '\n'.join(row.get('text', '') for row in messages[1]['content'])
        assert all(value in text for value in MOTION.values())
        assert 'must be visible in the late frame' in text
        return validate({'scenes': [{'id': scene.id, 'verdict': 'ok'} for scene in plan.scenes]})
    with patch('vga.review.thumbnail', return_value='data:image/jpeg;base64,x'), \
         patch('vga.review.chat_json', side_effect=verdict):
        assert review_scenes(board(plan), plan, ['still'] * 10, CONFIG) == []


@pytest.mark.parametrize('motion', [None, {}, {'start': 'One'},
                                   {**MOTION, 'extra': 'No'}, {**MOTION, 'action': '  '},
                                   {**MOTION, 'end': 'x' * 241}, {**MOTION, 'start': 12}])
def test_invalid_motion_beats_rejected(motion):
    with pytest.raises(ValueError, match='motion needs exactly'):
        motion_plan(motion)


def test_legacy_scene_without_motion_still_loads():
    from vga.plan import PlannedScene
    scene = referenced_plan().scenes[0].to_dict()
    scene.pop('motion')
    assert PlannedScene(**scene).motion == {}


def test_codegen_saves_rejection_reason_before_retry(monkeypatch, tmp_path):
    import json
    from vga import codegen
    plan = referenced_plan()
    monkeypatch.setattr(codegen, 'REPO_ROOT', tmp_path)
    monkeypatch.setattr(codegen, 'chat_text', lambda config, messages, validate, *args, **kwargs: validate('incomplete source'))
    with pytest.raises(ValueError, match='Contract checks failed'):
        codegen.generate_scenes(board(plan), plan, CONFIG, attempts=1)
    attempts = json.loads((tmp_path / 'data/projects/test/code-attempts.json').read_text())
    assert attempts[0]['pass'] is False
    assert 'missing required export' in attempts[0]['errors']


def test_completed_action_can_hold_after_visible_progress():
    from vga.codegen import _strongest_motion
    assert _strongest_motion(2.0, 0.1) == 2.0
    assert _strongest_motion(0.1, 0.2) == 0.2
    assert _strongest_motion(None, None) is None


def test_vision_review_receives_early_middle_late_states():
    from unittest.mock import patch
    plan = referenced_plan()
    def verdict(config, messages, validate, **kwargs):
        content = messages[1]['content']
        assert sum(row['type'] == 'image_url' for row in content) == 15
        assert any('Early state' in row.get('text', '') for row in content)
        return validate({'scenes': [{'id': scene.id, 'verdict': 'ok', 'problem': ''} for scene in plan.scenes]})
    with patch('vga.review.thumbnail', return_value='data:image/jpeg;base64,x'), patch('vga.review.chat_json', side_effect=verdict):
        assert review_scenes(board(plan), plan, ['still'] * 15, CONFIG) == []
