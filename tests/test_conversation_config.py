"""验证 conversation_config.yaml 配置正确性（Phase 2）。"""

import os
import yaml
import unittest


class TestConversationConfig(unittest.TestCase):
    """conversation_config.yaml 配置测试。"""

    @classmethod
    def setUpClass(cls):
        config_path = os.path.join(
            os.path.dirname(__file__), "..", "config", "conversation_config.yaml"
        )
        with open(config_path, "r", encoding="utf-8") as f:
            cls.config = yaml.safe_load(f)

    def test_basic_fields(self):
        self.assertEqual(self.config["podcast_name"], "科技早知道")
        self.assertEqual(self.config["output_language"], "Chinese")
        self.assertEqual(self.config["creativity"], 0.8)

    def test_roles_are_updated(self):
        """角色配置已更新为芊悦/萌萌。"""
        self.assertIn("芊悦", self.config["roles_person1"])
        self.assertIn("萌萌", self.config["roles_person2"])

    def test_no_cosyvoice(self):
        """不应包含 CosyVoice 或男声配置。"""
        config_str = yaml.dump(self.config)
        self.assertNotIn("cosyvoice", config_str.lower())
        self.assertNotIn("龙安洋", config_str)
        self.assertNotIn("longanyang", config_str)
        self.assertNotIn("安洋", config_str)

    def test_tts_uses_qwen(self):
        tts = self.config["text_to_speech"]
        self.assertEqual(tts["default_tts_model"], "qwen3-tts-instruct-flash")

    def test_voices_config(self):
        voices = self.config["text_to_speech"]["voices"]
        self.assertEqual(voices["芊悦"]["voice"], "Cherry")
        self.assertEqual(voices["萌萌"]["voice"], "Bunny")

    def test_conversation_style(self):
        styles = self.config["conversation_style"]
        self.assertIn("engaging", styles)
        self.assertIn("humorous", styles)


if __name__ == "__main__":
    unittest.main()
